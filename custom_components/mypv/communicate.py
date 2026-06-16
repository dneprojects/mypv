"""Provides the myPV DataUpdateCoordinator."""

import asyncio
from datetime import timedelta
import json
import logging
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOSTS, DOMAIN

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)
# Fixed polling interval; per HA rules this is not user-configurable.
SCAN_INTERVAL = timedelta(seconds=10)


class MypvCommunicator(DataUpdateCoordinator[None]):
    """Class to perform all myPV communications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize data updater."""
        self.hosts: list[str] = entry.data[CONF_HOSTS]
        self.devices: list[MpyDevice] = []
        # myPV devices serve only one HTTP connection at a time; serialize all
        # requests (cyclic poll + user commands) so they never collide, which
        # otherwise shows up as "Connect call failed" on :80.
        self._io_lock = asyncio.Lock()
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
            info_data = await self.check_ip(ip_str)
            if info_data:
                device = MpyDevice(self, ip_str, info_data)
                self.devices.append(device)
                await device.initialize()

    async def _async_update_data(self) -> None:
        """Update status of all ELWA devices."""
        try:
            for mpv_dev in self.devices:
                await mpv_dev.update()
        except (TimeoutError, aiohttp.ClientError, json.JSONDecodeError) as err:
            raise UpdateFailed(f"Error communicating with myPV device: {err}") from err

    async def do_get_request(self, url: str) -> str:
        """Perform a GET request, serialized so the device sees one at a time."""
        session = async_get_clientsession(self.hass)
        async with self._io_lock, session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            return await resp.text()

    async def check_ip(self, ip: str) -> dict[str, Any] | None:
        """Return device info for a host, or None if not reachable."""
        try:
            response_text = await self.do_get_request(f"http://{ip}/mypv_dev.jsn")
        except TimeoutError, aiohttp.ClientError, json.JSONDecodeError:
            return None
        data: dict[str, Any] = json.loads(response_text)
        return data

    async def data_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device data info."""
        response_text = await self.do_get_request(f"http://{device.ip}/data.jsn")
        data: dict[str, Any] = json.loads(response_text)
        return data

    async def setup_update(self, device: MpyDevice) -> dict[str, Any]:
        """Update device setup info."""
        response_text = await self.do_get_request(f"http://{device.ip}/setup.jsn")
        setup: dict[str, Any] = json.loads(response_text)
        return setup

    async def state_update(self, device: MpyDevice) -> bool:
        """Update control state."""
        if not device.control_enabled:
            return False
        try:
            response_text = await self.do_get_request(
                f"http://{device.ip}/control.html?"
            )
            self.get_state_dict(response_text, device)
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during control update: %s", err_msg)
            device.control_enabled = False
            return False
        return True

    async def set_number(self, device: MpyDevice, key: str, act_val: int) -> bool:
        """Set a setup value."""
        try:
            response_text = await self.do_get_request(
                f"http://{device.ip}/setup.jsn?{key}={act_val}"
            )
            self.get_state_dict(response_text, device)
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during set value command: %s", err_msg)
            return False
        return True

    async def set_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power."""
        try:
            response_text = await self.do_get_request(
                f"http://{device.ip}/control.html?power={act_pow}"
            )
            self.get_state_dict(response_text, device)
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during set power command: %s", err_msg)
            return False
        return True

    async def set_control_mode(self, device: MpyDevice, act_mode: int) -> bool:
        """Set power control mode, e.g. html."""
        try:
            await self.do_get_request(f"http://{device.ip}/setup.jsn?ctrl={act_mode}")
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during set control mode command: %s", err_msg)
            return False
        return True

    async def set_pid_power(self, device: MpyDevice, act_pow: int) -> bool:
        """Set heater power with local pid control."""
        try:
            response_text = await self.do_get_request(
                f"http://{device.ip}/control.html?pid_power={act_pow}"
            )
            self.get_state_dict(response_text, device)
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during set pid power command: %s", err_msg)
            return False
        return True

    async def switch(self, device: MpyDevice, key: str, state: bool) -> bool:
        """Set a setup switch."""
        try:
            response_text = await self.do_get_request(
                f"http://{device.ip}/setup.jsn?{key}={int(state)}"
            )
            self.get_state_dict(response_text, device)
        except (TimeoutError, aiohttp.ClientError) as err_msg:
            self.logger.warning("Error during switch command: %s", err_msg)
            return False
        return True

    async def activate_boost(self, device: MpyDevice, mode: int = 1) -> bool:
        """Activate or deactivate boost mode."""
        try:
            await self.do_get_request(f"http://{device.ip}/data.jsn?bststrt={mode}")
        except (TimeoutError, aiohttp.ClientError) as err_msg:
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
