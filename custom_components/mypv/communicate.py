"""Provides the myPV DataUpdateCoordinator.

The transport is provided by the my-pv library connection classes (see
``connection.py``). This coordinator keeps the raw device values and the
``control.html`` power steering the entities depend on; the public method
surface is unchanged so the device model and all entity platforms keep working
without modification.
"""

from datetime import timedelta
import json
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from my_pv.exceptions import MyPVAuthenticationError, MyPVConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .connection import MypvHttpConnection, MypvHttpsConnection, create_connection
from .const import CONF_HOSTS, DOMAIN

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)

# Fixed polling interval; per HA rules this is not user-configurable.
SCAN_INTERVAL = timedelta(seconds=10)

# Errors that mean "device temporarily unreachable" (as opposed to an auth
# failure, which must trigger re-authentication instead of a retry).
_COMM_ERRORS = (TimeoutError, aiohttp.ClientError, MyPVConnectionError)


class MypvCommunicator(DataUpdateCoordinator[None]):
    """Class to perform all myPV communications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize data updater."""
        self.hosts: list[str] = entry.data[CONF_HOSTS]
        self.password: str | None = entry.data.get(CONF_PASSWORD)
        self.devices: list[MpyDevice] = []
        # One library-backed connection per device; each handles its own session
        # and authentication and serialises the device's requests internally.
        self.connections: dict[str, MypvHttpConnection | MypvHttpsConnection] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )

    async def initialize(self) -> None:
        """Detect configured devices and set up their entities."""
        # Import here to avoid a circular import at module load time.
        from .mypv_device import MpyDevice  # noqa: PLC0415

        for ip_str in self.hosts:
            connection = create_connection(ip_str, self.password)
            try:
                opened = await connection.open()
            except MyPVAuthenticationError as err:
                await connection.close()
                raise ConfigEntryAuthFailed(
                    f"Authentication required for myPV device at {ip_str}"
                ) from err
            if not opened or not connection.mypv_dev:
                await connection.close()
                continue
            self.connections[ip_str] = connection
            device = MpyDevice(self, ip_str, connection.mypv_dev)
            self.devices.append(device)
            await device.initialize()

    async def async_close(self) -> None:
        """Close all device connections (called on unload)."""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()

    def _connection(
        self, device: MpyDevice
    ) -> MypvHttpConnection | MypvHttpsConnection:
        """Return the connection belonging to the given device."""
        return self.connections[device.ip]

    async def _async_update_data(self) -> None:
        """Update status of all ELWA devices."""
        try:
            for mpv_dev in self.devices:
                await mpv_dev.update()
        except MyPVAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Authentication with myPV device failed"
            ) from err
        except (
            TimeoutError,
            aiohttp.ClientError,
            json.JSONDecodeError,
            MyPVConnectionError,
        ) as err:
            raise UpdateFailed(f"Error communicating with myPV device: {err}") from err

    async def data_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device data info."""
        return await self._connection(device).get_json("/data.jsn")

    async def setup_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device setup info."""
        return await self._connection(device).get_json("/setup.jsn")

    async def state_update(self, device: MpyDevice) -> bool:
        """Update control state."""
        if not device.control_enabled:
            return False
        try:
            response_text = await self._connection(device).get_text("/control.html")
            self.get_state_dict(response_text, device)
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during control update: %s", err_msg)
            device.control_enabled = False
            return False
        return True

    def _start_reauth(self, err: MyPVAuthenticationError) -> None:
        """Trigger re-authentication after an auth failure during a command.

        The cyclic poll routes auth failures through ``ConfigEntryAuthFailed``;
        user commands raise outside that path, so they must start reauth
        themselves (a no-op if a reauth flow is already in progress).
        """
        self.logger.warning("Authentication with myPV device failed: %s", err)
        assert self.config_entry is not None
        self.config_entry.async_start_reauth(self.hass)

    async def set_number(self, device: MpyDevice, key: str, act_val: int) -> bool:
        """Set a setup value."""
        try:
            response_text = await self._connection(device).get_text(
                "/setup.jsn", {key: act_val}
            )
            self.get_state_dict(response_text, device)
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during set value command: %s", err_msg)
            return False
        return True

    async def set_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power."""
        try:
            response_text = await self._connection(device).get_text(
                "/control.html", {"power": act_pow}
            )
            self.get_state_dict(response_text, device)
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during set power command: %s", err_msg)
            return False
        return True

    async def set_control_mode(self, device: MpyDevice, act_mode: int) -> bool:
        """Set power control mode, e.g. html."""
        try:
            await self._connection(device).get_text("/setup.jsn", {"ctrl": act_mode})
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during set control mode command: %s", err_msg)
            return False
        return True

    async def set_pid_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power with local pid control."""
        try:
            response_text = await self._connection(device).get_text(
                "/control.html", {"pid_power": act_pow}
            )
            self.get_state_dict(response_text, device)
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during set pid power command: %s", err_msg)
            return False
        return True

    async def switch(self, device: MpyDevice, key: str, state: bool) -> bool:
        """Set a setup switch."""
        try:
            response_text = await self._connection(device).get_text(
                "/setup.jsn", {key: int(state)}
            )
            self.get_state_dict(response_text, device)
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during switch command: %s", err_msg)
            return False
        return True

    async def activate_boost(self, device: MpyDevice, mode: int = 1) -> bool:
        """Activate or deactivate boost mode."""
        try:
            await self._connection(device).get_text("/data.jsn", {"bststrt": mode})
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning("Error during boost command: %s", err_msg)
            return False
        return True

    def get_state_dict(self, text: str, device: MpyDevice) -> None:
        """Convert lines to state dict."""
        text = text.replace("\r\n", "<br>").replace("\n", "<br>")
        resp_lines = text.split("<br>")
        for line in resp_lines:
            if len(line) > 4 and not line.startswith("<"):
                parts = line.split("=")
                if len(parts) >= 2:
                    device.state_dict[parts[0]] = parts[1].split()[0].replace(",", "")
