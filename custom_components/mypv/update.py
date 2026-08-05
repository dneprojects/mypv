"""Update entities of myPV integration."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMM_HUB, DOMAIN
from .entity import MpvEntity

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)

# Firmware parts that report an installed/latest version pair plus an
# update-state key. Only the control unit can be updated from Home Assistant;
# the other parts stay report-only.
#   name, installed key, latest key, update-state key
FW_PARTS: tuple[tuple[str, str, str, str], ...] = (
    ("Control Unit Firmware", "fwversion", "fwversionlatest", "upd_state"),
    ("Power Unit Firmware", "psversion", "psversionlatest", "ps_upd_state"),
    (
        "Power Unit Firmware Acthor 9",
        "p9sversion",
        "p9sversionlatest",
        "p9s_upd_state",
    ),
    ("Co-controller Firmware", "coversion", "coversionlatest", "co_upd_state"),
)

# Update-state values that mean the device is actively downloading or
# installing firmware. The enum is offset by one on Solthor devices.
_IN_PROGRESS_STATES = (2, 3, 4, 10)
_IN_PROGRESS_STATES_SOLTHOR = (3, 4, 5, 7)

# Update states that carry a download percentage.
_DOWNLOADING_STATES = (2, 3, 4)

# Control unit update states relevant to an installation.
_STATE_IDLE = 0
_STATE_AVAILABLE = 1
_STATE_DOWNLOADED = 10

# Control unit firmware from which the device accepts ``firmware_download`` /
# ``firmware_update``; below it, new firmware has to be installed from the
# device's own web interface. Versions are a letter for the device series plus
# seven digits, and the series number themselves independently:
#   a - AC.THOR, minimum declared by the my-PV library's device configs
#   e - AC ELWA 2, minimum from our own captures: an e0002410 reports no
#       ``upd_percentage`` at all, an e0002500 does
# A series that is not listed (Solthor, "s...") stays report-only.
_INSTALL_MIN_FW: dict[str, int] = {"a": 20000, "e": 2500}

# Keys that mark firmware which knows the update flow: it reports one of them
# even while idle, and their presence is the second half of the check above --
# a version number alone cannot be compared across series. Which one appears
# depends on the family: an AC ELWA 2 counts percent, an AC.THOR counts the
# files still to fetch (reported for a0022401, issue #52).
_PROGRESS_KEY = "upd_percentage"
_FILES_LEFT_KEY = "upd_files_left"

# How long to wait for the download and for the installation, and how often to
# poll the device while waiting. The device serves one connection at a time, so
# this stays well above the request duration.
_STEP_TIMEOUT = 300
_POLL_INTERVAL = 5


def supports_remote_install(data: dict[str, Any]) -> bool:
    """Return whether this control unit firmware knows the update commands."""
    version = data.get("fwversion")
    if not isinstance(version, str) or len(version) != 8:
        return False
    series, digits = version[0], version[1:]
    minimum = _INSTALL_MIN_FW.get(series)
    if minimum is None or not digits.isdigit() or int(digits) < minimum:
        return False
    return _PROGRESS_KEY in data or _FILES_LEFT_KEY in data


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a firmware update entity for each reported firmware part."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]
    entities = [
        MpvFwUpdate(device, name, installed_key, latest_key, state_key)
        for device in comm.devices
        for name, installed_key, latest_key, state_key in FW_PARTS
        if installed_key in device.data and latest_key in device.data
    ]
    if entities:
        async_add_entities(entities)


class MpvFwUpdate(MpvEntity, UpdateEntity):
    """Firmware update entity for a myPV device part."""

    # Every part reports device-driven progress. Without the flag, HA ignores
    # the ``in_progress`` property entirely and uses its own internal state,
    # which only ever moves while HA itself installs something -- so a download
    # started at the device stayed invisible.
    _attr_supported_features = UpdateEntityFeature.PROGRESS

    def __init__(
        self,
        device: MpyDevice,
        name: str,
        installed_key: str,
        latest_key: str,
        state_key: str,
    ) -> None:
        """Initialize the firmware update entity."""
        super().__init__(device, name)
        self._attr_title = name
        self._installed_key = installed_key
        self._latest_key = latest_key
        self._state_key = state_key
        self._installing = False
        # Only the control unit takes the commands, and only on new enough
        # firmware of a series we have a minimum for.
        self._can_install = installed_key == "fwversion" and supports_remote_install(
            device.data
        )
        if self._can_install:
            self._attr_supported_features |= UpdateEntityFeature.INSTALL

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed firmware version."""
        version = self.device.data.get(self._installed_key)
        return str(version) if version not in (None, "null") else None

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        version = self.device.data.get(self._latest_key)
        if version in (None, "null", ""):
            return self.installed_version
        return str(version)

    @property
    def in_progress(self) -> bool:
        """Return whether the device is downloading or installing firmware."""
        if self._installing:
            return True
        states = (
            _IN_PROGRESS_STATES_SOLTHOR
            if self.device.model == "Solthor"
            else _IN_PROGRESS_STATES
        )
        return self._update_state() in states

    @property
    def update_percentage(self) -> int | None:
        """Return the download progress, if the device is downloading."""
        if self._update_state() not in _DOWNLOADING_STATES:
            return None
        percentage = self.device.data.get(_PROGRESS_KEY)
        if not isinstance(percentage, (int, float)):
            return None
        return int(percentage)

    def _update_state(self) -> int | None:
        """Return the update state as an int, or None if it is unusable."""
        try:
            return int(self.device.data[self._state_key])
        except KeyError, TypeError, ValueError:
            return None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Download the new firmware if needed, then install it."""
        if not self._can_install:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="firmware_install_unsupported",
            )

        self._installing = True
        self.async_write_ha_state()
        try:
            if self._update_state() == _STATE_AVAILABLE:
                await self._send("firmware_download")
                await self._wait_for(_STATE_DOWNLOADED, "firmware_download_timeout")

            if self._update_state() != _STATE_DOWNLOADED:
                # Nothing waiting to be installed -- either the update vanished
                # or the device never picked the download up.
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="firmware_not_downloaded",
                )

            await self._send("firmware_update")
            # The device reboots while installing, so failing polls are normal.
            await self._wait_for(_STATE_IDLE, "firmware_install_timeout")
        finally:
            self._installing = False
            self.async_write_ha_state()

    async def _send(self, command: str) -> None:
        """Send a firmware command, raising if the device did not take it."""
        if not await self.comm.firmware_command(self.device, command):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="firmware_command_failed",
                translation_placeholders={"command": command},
            )

    async def _wait_for(self, state: int, timeout_key: str) -> None:
        """Poll the device until it reports ``state``."""
        try:
            async with asyncio.timeout(_STEP_TIMEOUT):
                while self._update_state() != state:
                    await asyncio.sleep(_POLL_INTERVAL)
                    # A failing refresh is swallowed by the coordinator, which
                    # is what we want while the device is rebooting.
                    await self.coordinator.async_refresh()
                    self.async_write_ha_state()
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=timeout_key,
                translation_placeholders={"minutes": str(_STEP_TIMEOUT // 60)},
            ) from err

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
