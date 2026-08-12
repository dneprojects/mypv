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
    describe_error,
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
# The two writable endpoints. Which of them a write goes to decides how it is
# sent and what happens to the answer -- see ``_write``.
_SETUP_PATH = "/setup.jsn"
_CONTROL_PATH = "/control.html"
_DATA_PATH = "/data.jsn"
# Consecutive ``control.html`` failures tolerated at the full poll rate before
# the read backs off to every _CONTROL_RETRY_CYCLES polls (~5 min at 10 s).
_CONTROL_FAILURES_BEFORE_BACKOFF = 3
_CONTROL_RETRY_CYCLES = 30
# Consecutive failing polls ridden out before the entities go unavailable
# (~30 s at the 10 s interval).
_POLL_FAILURES_TOLERATED = 3
# ``setup.jsn`` carries only settings (targets, modes, ``sec_level``), never a
# measurement, but it used to be read on every poll -- a third of the request
# load against a device that serves one connection at a time. Re-read it every
# ~2 min, immediately after a write that changes it, and right after a failed
# poll: ``sec_level`` selects HTTP vs HTTPS for the other endpoints, so a mode
# change at the device makes them fail until this is read again.
_SETUP_REFRESH_CYCLES = 12


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
        self._poll_failures = 0
        self._had_poll_success = False
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

        if (
            connection is None
            and not self.password
            and await self._speaks_https(ip_str)
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
        except MyPVAuthenticationError, MyPVConnectionError:
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
        """Update status of all ELWA devices, riding out a brief dropout.

        The device serves one connection at a time, so a single poll can time
        out while the device is busy with its own cloud upload or the myPV app.
        Reporting that immediately flips every entity to "unavailable", which
        showed up as gaps in users' graphs even though the device was fine
        moments later. Tolerate a few consecutive failures before giving up --
        but only once a first poll has succeeded, so a device that never
        answers still fails setup instead of appearing to work.

        A failure also schedules a ``setup.jsn`` read, since a changed
        ``sec_level`` is both a plausible cause and only visible there.
        """
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
            # A failed read may mean the device changed encryption mode, which
            # only ``setup.jsn`` reveals -- so re-read it on the next poll
            # instead of waiting out the throttle while every other endpoint
            # keeps failing against the wrong protocol.
            for mpv_dev in self.devices:
                self.request_setup_refresh(mpv_dev)
            self._poll_failures += 1
            if (
                self._had_poll_success
                and self._poll_failures <= _POLL_FAILURES_TOLERATED
            ):
                self.logger.debug(
                    "Poll %s of %s failed, keeping the last values: %s",
                    self._poll_failures,
                    _POLL_FAILURES_TOLERATED,
                    describe_error(err),
                )
                return
            raise UpdateFailed(
                f"Error communicating with myPV device: {describe_error(err)}"
            ) from err
        self._poll_failures = 0
        self._had_poll_success = True

    async def data_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device data info."""
        return await self._connection(device).get_json(_DATA_PATH)

    async def setup_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device setup info and refresh the connection's encryption mode.

        ``setup.jsn`` is read over the connection's own protocol (HTTPS on new
        firmware) and its ``sec_level`` then selects HTTP vs HTTPS for the other
        endpoints (``data.jsn`` / ``control.html``) at runtime.
        """
        connection = self._connection(device)
        setup = await connection.get_json(_SETUP_PATH)
        connection.set_sec_level(setup.get("sec_level"))
        device.setup_skip = _SETUP_REFRESH_CYCLES
        return setup

    @staticmethod
    def request_setup_refresh(device: MpyDevice) -> None:
        """Make the next poll re-read ``setup.jsn``.

        Called after a write that changes it, so the throttled read does not
        leave a user's own change unconfirmed for minutes.
        """
        device.setup_skip = 0

    async def state_update(self, device: MpyDevice) -> bool:
        """Update control state, backing off on failure but never giving up.

        A failing ``control.html`` read used to disable control for the entry's
        whole lifetime, which froze the control state on its last value until a
        reload -- with a 10 s poll against a device that serves one connection
        at a time, a single transient timeout was enough. After a few
        consecutive failures the read is therefore retried only every
        ``_CONTROL_RETRY_CYCLES`` polls (so a device that does not serve the
        endpoint is not hammered), and it recovers on its own as soon as the
        device answers again.
        """
        if device.control_skip > 0:
            device.control_skip -= 1
            return False
        try:
            response_text = await self._connection(device).get_text(_CONTROL_PATH)
            self.get_state_dict(response_text, device)
        except _COMM_ERRORS as err_msg:
            device.control_failures += 1
            if device.control_failures <= _CONTROL_FAILURES_BEFORE_BACKOFF:
                self.logger.warning(
                    "Error during control update: %s", describe_error(err_msg)
                )
            else:
                self.logger.debug(
                    "Control update still failing: %s", describe_error(err_msg)
                )
                device.control_skip = _CONTROL_RETRY_CYCLES
            return False
        device.control_failures = 0
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

    async def _write(
        self, device: MpyDevice, label: str, path: str, params: dict[str, Any]
    ) -> bool:
        """Write to the device, reporting a failure as ``False``.

        The endpoint decides the rest, because the two differ in kind rather
        than in detail. ``/setup.jsn`` is configuration: it answers with the
        whole setup as JSON, so the only thing left to do is to re-read it
        sooner than the throttle would, and confirm the user's change on the
        next poll. ``/control.html`` is real-time control: it answers with the
        ``key=value`` status block that ``_check_http_control`` reads, so that
        one is parsed into ``state_dict``.
        """
        is_setup = path == _SETUP_PATH
        connection = self._connection(device)
        try:
            if is_setup:
                await connection.send(path, params)
            else:
                self.get_state_dict(await connection.command(path, params), device)
        except MyPVAuthenticationError as err:
            self._start_reauth(err)
            return False
        except _COMM_ERRORS as err_msg:
            self.logger.warning(
                "Error during %s command: %s", label, describe_error(err_msg)
            )
            return False
        if is_setup:
            self.request_setup_refresh(device)
        return True

    async def set_number(self, device: MpyDevice, key: str, act_val: int) -> bool:
        """Set a setup value."""
        return await self._write(device, "set value", _SETUP_PATH, {key: act_val})

    async def set_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power."""
        return await self._write(device, "set power", _CONTROL_PATH, {"power": act_pow})

    async def set_control_mode(self, device: MpyDevice, act_mode: int) -> bool:
        """Set power control mode, e.g. html."""
        return await self._write(
            device, "set control mode", _SETUP_PATH, {"ctrl": act_mode}
        )

    async def set_pid_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power with local pid control."""
        return await self._write(
            device, "set pid power", _CONTROL_PATH, {"pid_power": act_pow}
        )

    async def switch(self, device: MpyDevice, key: str, state: bool) -> bool:
        """Set a setup switch."""
        return await self._write(device, "switch", _SETUP_PATH, {key: int(state)})

    async def activate_boost(self, device: MpyDevice, mode: int = 1) -> bool:
        """Activate or deactivate boost mode."""
        return await self._write(device, "boost", _SETUP_PATH, {"bststrt": mode})

    async def firmware_command(self, device: MpyDevice, command: str) -> bool:
        """Trigger a firmware download or installation.

        The device takes ``firmware_download`` and ``firmware_update`` as
        ordinary setup writes; both only exist from control unit firmware
        a0020000 onwards (see ``update.py``).
        """
        return await self._write(device, command, _SETUP_PATH, {command: 1})

    def get_state_dict(self, text: str, device: MpyDevice) -> None:
        """Convert lines to state dict."""
        text = text.replace("\r\n", "<br>").replace("\n", "<br>")
        resp_lines = text.split("<br>")
        for line in resp_lines:
            if len(line) > 4 and not line.startswith("<"):
                parts = line.split("=")
                if len(parts) >= 2:
                    device.state_dict[parts[0]] = parts[1].split()[0].replace(",", "")
