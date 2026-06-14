"""Update entities of myPV integration."""

import logging

from homeassistant.components.update import UpdateEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMM_HUB, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Firmware parts that report an installed/latest version pair plus an
# update-state key. The device downloads and installs new firmware on its
# own, so these entities are report-only (no INSTALL feature).
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
)

# Update-state values that mean the device is actively downloading or
# installing firmware. The enum is offset by one on Solthor devices.
_IN_PROGRESS_STATES = (2, 3, 4, 10)
_IN_PROGRESS_STATES_SOLTHOR = (3, 4, 5, 7)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
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


class MpvFwUpdate(CoordinatorEntity, UpdateEntity):
    """Report-only firmware update entity for a myPV device part."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        device,
        name: str,
        installed_key: str,
        latest_key: str,
        state_key: str,
    ) -> None:
        """Initialize the firmware update entity."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self._name = name
        self._installed_key = installed_key
        self._latest_key = latest_key
        self._state_key = state_key

    @property
    def name(self):
        """Return the name of the update entity."""
        return self._name

    @property
    def title(self):
        """Return the firmware part title."""
        return self._name

    @property
    def unique_id(self):
        """Return unique id based on device serial and firmware part."""
        return f"{self.device.serial_number}_{self._name}"

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, self.device.serial_number)},
            "name": self.device.name,
            "manufacturer": "myPV",
            "model": self.device.model,
        }

    @property
    def installed_version(self):
        """Return the currently installed firmware version."""
        version = self.device.data.get(self._installed_key)
        return str(version) if version not in (None, "null") else None

    @property
    def latest_version(self):
        """Return the latest available firmware version."""
        version = self.device.data.get(self._latest_key)
        if version in (None, "null", ""):
            return self.installed_version
        return str(version)

    @property
    def in_progress(self):
        """Return whether the device is downloading or installing firmware."""
        states = (
            _IN_PROGRESS_STATES_SOLTHOR
            if self.device.model == "Solthor"
            else _IN_PROGRESS_STATES
        )
        try:
            return int(self.device.data[self._state_key]) in states
        except (KeyError, TypeError, ValueError):
            return False

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
