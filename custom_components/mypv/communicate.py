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

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .connection import (
    MyPVAuthenticationError,
    MyPVConnectionError,
    MypvHttpConnection,
    MypvHttpsConnection,
    create_connection,
)
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
        # New firmware speaks HTTPS (self-signed) even without a password
        # (encryption modes 1/2); a password additionally implies HTTPS.
        self.use_https: bool = entry.data.get(CONF_SSL, False)
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
            result = await self._setup_host(ip_str, MpyDevice)
            if result is None:
                continue
            _connection, device = result
            self.devices.append(device)

    async def _setup_host(
        self, ip_str: str, device_cls: type[MpyDevice]
    ) -> tuple[MypvHttpConnection | MypvHttpsConnection, MpyDevice] | None:
        """Open a connection and initialise the device, healing a firmware change.

        An entry set up on old firmware (plain HTTP, no password) whose device is
        now on new firmware can no longer be read over the stored transport. If
        the device then speaks HTTPS and no password is stored, a login is
        required -> start reauth so the user can supply it.
        """
        connection, device = await self._open_and_init(
            ip_str, self.password, self.use_https, device_cls
        )

        if connection is None and not self.password and await self._speaks_https(
            ip_str
        ):
            raise ConfigEntryAuthFailed(
                f"myPV device at {ip_str} now requires a password"
            )

        if connection is None or device is None:
            return None
        return connection, device

    async def _open_and_init(
        self,
        ip_str: str,
        password: str | None,
        use_https: bool,
        device_cls: type[MpyDevice],
    ) -> tuple[MypvHttpConnection | MypvHttpsConnection, MpyDevice] | tuple[None, None]:
        """Open a connection and run ``device.initialize()``.

        Returns ``(None, None)`` when the device is unreachable or the transport
        cannot read it (so the caller can heal). A rejected or missing login
        raises ``ConfigEntryAuthFailed`` to route to reauth.
        """
        connection = create_connection(ip_str, password, use_https=use_https)
        try:
            opened = await connection.open()
        except MyPVAuthenticationError as err:
            await connection.close()
            raise ConfigEntryAuthFailed(
                f"Authentication required for myPV device at {ip_str}"
            ) from err
        if not opened or not connection.mypv_dev:
            await connection.close()
            return None, None
        # Register before initialising: the device reads through this connection
        # via ``self.connections[ip]``.
        self.connections[ip_str] = connection
        device = device_cls(self, ip_str, connection.mypv_dev)
        try:
            await device.initialize()
        except MyPVAuthenticationError as err:
            await connection.close()
            self.connections.pop(ip_str, None)
            raise ConfigEntryAuthFailed(
                f"Authentication required for myPV device at {ip_str}"
            ) from err
        except MyPVConnectionError:
            await connection.close()
            self.connections.pop(ip_str, None)
            return None, None
        return connection, device

    async def _speaks_https(self, ip_str: str) -> bool:
        """Return True if the device answers over HTTPS (new firmware)."""
        probe = create_connection(ip_str, None, use_https=True)
        try:
            return await probe.open()
        except (MyPVAuthenticationError, MyPVConnectionError):
            return False
        finally:
            await probe.close()

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
        """Update device setup info and refresh the connection's encryption mode.

        ``setup.jsn`` is read over the connection's own protocol (HTTPS on new
        firmware) and its ``sec_level`` then selects HTTP vs HTTPS for the other
        endpoints (``data.jsn`` / ``control.html``) at runtime.
        """
        connection = self._connection(device)
        setup = await connection.get_json("/setup.jsn")
        connection.set_sec_level(setup.get("sec_level"))
        return setup

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
            response_text = await self._connection(device).send(
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
            response_text = await self._connection(device).command(
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
            await self._connection(device).send("/setup.jsn", {"ctrl": act_mode})
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
            response_text = await self._connection(device).command(
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
            response_text = await self._connection(device).send(
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
            await self._connection(device).send("/setup.jsn", {"bststrt": mode})
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
