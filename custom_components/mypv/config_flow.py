"""Config flow for ELWA myPV integration."""

import json
from json import JSONDecodeError
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import CONF_HOSTS, DEV_IP, DOMAIN
from .discovery import async_discover_mypv_devices

CHECK_TIMEOUT = aiohttp.ClientTimeout(total=5)


@callback
def mypv_entries(hass: HomeAssistant) -> list[str]:
    """Return the hosts for the domain."""
    try:
        hosts: list[str] = hass.config_entries.async_entries(DOMAIN)[0].data[CONF_HOSTS]
    except IndexError, KeyError:
        # Return empty list on failure
        return []
    return hosts


class MpvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ELWA myPV config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: dict[str, str] = {}
        self._discovered_devices: dict[str, str] = {}
        self._discovery_ip: str | None = None
        self._discovery_name: str | None = None

    def _all_hosts_in_configuration_exist(self, ip_list: list[str]) -> bool:
        """Return True if all hosts found already exist in configuration."""
        return all(ip in mypv_entries(self.hass) for ip in ip_list)

    async def _check_host(self, dev_ip: str) -> tuple[bool, list[str], str]:
        """Check if the myPV device at the given ip answers and fetch its name."""
        host_list: list[str] = []
        device_name = "myPV"

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"http://{dev_ip}/mypv_dev.jsn", timeout=CHECK_TIMEOUT
            ) as resp:
                data = json.loads(await resp.text())
            host_list.append(dev_ip)
            if isinstance(data, dict) and "device" in data:
                device_name = str(data["device"])
        except TimeoutError, aiohttp.ClientError, JSONDecodeError, TypeError:
            pass

        return len(host_list) > 0, host_list, device_name

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery via dhcp."""
        dev_ip = discovery_info.ip

        can_connect, _ips_found, fetched_name = await self._check_host(dev_ip)
        if not can_connect:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(f"mypv_{dev_ip}")
        self._abort_if_unique_id_configured()

        self._discovery_ip = dev_ip
        self._discovery_name = fetched_name
        self.context["title_placeholders"] = {"name": f"{fetched_name} ({dev_ip})"}

        return await self.async_step_confirm()

    async def async_step_discovery(
        self, discovery_info: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery triggered by background scanner."""
        dev_ip = discovery_info["ip"]
        dev_host = discovery_info.get("host", "myPV")

        can_connect, _ips_found, fetched_name = await self._check_host(dev_ip)
        if not can_connect:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(f"mypv_{dev_ip}")
        self._abort_if_unique_id_configured()

        display_name = dev_host if dev_host != "myPV" else fetched_name

        self._discovery_ip = dev_ip
        self._discovery_name = display_name
        self.context["title_placeholders"] = {"name": f"{display_name} ({dev_ip})"}

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm setup of a discovered device (no input needed)."""

        if user_input is not None:
            assert self._discovery_ip is not None

            can_connect, ips_found, _ = await self._check_host(self._discovery_ip)
            if not can_connect:
                return self.async_abort(reason="cannot_connect")

            final_title = (
                f"{self._discovery_name} ({self._discovery_ip})"
                if self._discovery_name != "myPV"
                else f"myPV ({self._discovery_ip})"
            )
            return self.async_create_entry(
                title=final_title,
                data={DEV_IP: self._discovery_ip, CONF_HOSTS: ips_found},
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._discovery_name or "",
                "ip": self._discovery_ip or "",
            },
            errors=self._errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the manual addition step (with IP dropdown)."""

        if not self._discovered_devices and user_input is None:
            # Perform network scan if no devices are known yet
            devices = await async_discover_mypv_devices()
            for device in devices:
                if device["ip"] not in self._discovered_devices:
                    self._discovered_devices[device["ip"]] = device.get("host", "myPV")

        if user_input is not None:
            dev_ip = user_input[DEV_IP]
            can_connect, ips_found, fetched_name = await self._check_host(dev_ip)

            if can_connect:
                if self._all_hosts_in_configuration_exist(ips_found):
                    self._errors[DEV_IP] = "host_exists"
                else:
                    await self.async_set_unique_id(f"mypv_{dev_ip}")
                    if fetched_name and fetched_name != "myPV":
                        display_name = fetched_name
                    else:
                        display_name = self._discovered_devices.get(dev_ip, "myPV")
                    final_title = (
                        f"{display_name} ({dev_ip})"
                        if display_name != "myPV"
                        else f"myPV ({dev_ip})"
                    )
                    return self.async_create_entry(
                        title=final_title,
                        data={DEV_IP: dev_ip, CONF_HOSTS: ips_found},
                    )
            else:
                self._errors[DEV_IP] = "could_not_connect"

        available_ips = [
            ip
            for ip in self._discovered_devices
            if not self._all_hosts_in_configuration_exist([ip])
        ]
        if available_ips:
            ip_field: Any = vol.In(available_ips)
            default_ip = available_ips[0]
        else:
            ip_field = str
            default_ip = user_input.get(DEV_IP, "") if user_input else ""

        setup_schema = vol.Schema({vol.Required(DEV_IP, default=default_ip): ip_field})

        return self.async_show_form(
            step_id="user", data_schema=setup_schema, errors=self._errors
        )
