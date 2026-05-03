"""Config flow for ELWA myPV integration."""
# import logging

import json
from json import JSONDecodeError
from typing import Any

import requests
from requests.exceptions import ConnectTimeout, HTTPError
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.components import dhcp
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_DEFAULT_INTERVAL,
    CONF_HOSTS,
    CONF_MAX_INTERVAL,
    CONF_MIN_INTERVAL,
    DEV_IP,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .discovery import async_discover_mypv_devices


@callback
def mypv_entries(hass: HomeAssistant):
    """Return the hosts for the domain."""
    try:
        return hass.config_entries.async_entries(DOMAIN)[0].data[CONF_HOSTS]
    except:  # noqa: E722
        return []


class MpvConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ELWA myPV config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod  # type: ignore  # noqa: PGH003
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return MpvOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors = {}
        self._info = {}
        self._discovered_devices: dict[str, str] = {}
        self._discovery_ip: str | None = None
        self._discovery_name: str | None = None

    def _all_hosts_in_configuration_exist(self, ip_list) -> bool:
        """Return True if all hosts found already exist in configuration."""
        return all(ip in mypv_entries(self.hass) for ip in ip_list)

    def _check_host(self, dev_ip: str) -> tuple[bool, list[str], str]:
        """Check if connect to myPV device with given ip address works and fetch name."""
        host_list: list[str] = []
        device_name = "myPV"

        try:
            response = requests.get(f"http://{dev_ip}/mypv_dev.jsn", timeout=0.5)
            data = json.loads(response.text)
            host_list.append(dev_ip)
            if isinstance(data, dict) and "device" in data:
                device_name = str(data["device"])

        except ConnectTimeout, HTTPError, TypeError, JSONDecodeError:
            pass

        return len(host_list) > 0, host_list, device_name

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery via dhcp."""
        dev_ip = discovery_info.ip

        can_connect, ips_found, fetched_name = await self.hass.async_add_executor_job(
            self._check_host, dev_ip
        )

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

        can_connect, ips_found, fetched_name = await self.hass.async_add_executor_job(
            self._check_host, dev_ip
        )
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
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Confirm setup of a discovered device (IP input hidden)."""
        if user_input is not None:
            update_interval = user_input[UPDATE_INTERVAL]

            if not (isinstance(update_interval, int)):
                self._errors[UPDATE_INTERVAL] = "invalid_interval"
            elif update_interval < CONF_MIN_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_short"
            elif update_interval > CONF_MAX_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_long"

            if not self._errors:
                can_connect, ips_found, _ = await self.hass.async_add_executor_job(
                    self._check_host, self._discovery_ip
                )

                if can_connect:
                    final_title = (
                        f"{self._discovery_name} ({self._discovery_ip})"
                        if self._discovery_name != "myPV"
                        else f"myPV ({self._discovery_ip})"
                    )
                    return self.async_create_entry(
                        title=final_title,
                        data={
                            DEV_IP: self._discovery_ip,
                            UPDATE_INTERVAL: update_interval,
                            CONF_HOSTS: ips_found,
                        },
                    )
                else:
                    return self.async_abort(reason="cannot_connect")

        setup_schema = vol.Schema(
            {
                vol.Required(UPDATE_INTERVAL, default=CONF_DEFAULT_INTERVAL): int,
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=setup_schema,
            description_placeholders={
                "name": self._discovery_name,
                "ip": self._discovery_ip,
            },
            errors=self._errors,
        )

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the manual addition step (with IP dropdown)."""

        if not self._discovered_devices and user_input is None:
            devices = await async_discover_mypv_devices()
            for device in devices:
                if device["ip"] not in self._discovered_devices:
                    self._discovered_devices[device["ip"]] = device.get("host", "myPV")

        if user_input is not None:
            dev_ip = user_input[DEV_IP]
            update_interval = user_input[UPDATE_INTERVAL]

            if not (isinstance(update_interval, int)):
                self._errors[UPDATE_INTERVAL] = "invalid_interval"

            if update_interval < CONF_MIN_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_short"

            if update_interval > CONF_MAX_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_long"

            (
                can_connect,
                ips_found,
                fetched_name,
            ) = await self.hass.async_add_executor_job(
                self._check_host,
                dev_ip,
            )

            if can_connect and not self._errors:
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
                        data={
                            DEV_IP: dev_ip,
                            UPDATE_INTERVAL: update_interval,
                            CONF_HOSTS: ips_found,
                        },
                    )
            elif not can_connect:
                self._errors[DEV_IP] = "could_not_connect"

        default_interval = CONF_DEFAULT_INTERVAL

        if user_input is None:
            if self._discovered_devices:
                available_ips = [
                    ip
                    for ip in self._discovered_devices
                    if not self._all_hosts_in_configuration_exist([ip])
                ]

                if available_ips:
                    setup_schema = vol.Schema(
                        {
                            vol.Required(DEV_IP, default=available_ips[0]): vol.In(
                                available_ips
                            ),
                            vol.Required(
                                UPDATE_INTERVAL, default=default_interval
                            ): int,
                        }
                    )
                else:
                    setup_schema = vol.Schema(
                        {
                            vol.Required(DEV_IP): str,
                            vol.Required(
                                UPDATE_INTERVAL, default=default_interval
                            ): int,
                        }
                    )
            else:
                setup_schema = vol.Schema(
                    {
                        vol.Required(DEV_IP): str,
                        vol.Required(UPDATE_INTERVAL, default=default_interval): int,
                    }
                )
        else:
            setup_schema = vol.Schema(
                {
                    vol.Required(DEV_IP, default=user_input.get(DEV_IP, "")): str,
                    vol.Required(
                        UPDATE_INTERVAL,
                        default=user_input.get(UPDATE_INTERVAL, CONF_DEFAULT_INTERVAL),
                    ): int,
                }
            )

        return self.async_show_form(
            step_id="user", data_schema=setup_schema, errors=self._errors
        )


class MpvOptionsFlow(config_entries.OptionsFlow, MpvConfigFlow):
    """Allow to change options of integration while running."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self.config_entry = config_entry
        self._errors = {}
        self._info = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        self._errors = {}

        if user_input is None:
            default_dev_ip = self.config_entry.data[DEV_IP]
            default_interval = self.config_entry.data[UPDATE_INTERVAL]
        else:
            default_dev_ip = user_input[DEV_IP]
            default_interval = user_input[UPDATE_INTERVAL]

        opt_schema = vol.Schema(
            {
                vol.Required(DEV_IP, default=default_dev_ip): str,
                vol.Required(
                    "update_interval",
                    default=default_interval,
                ): int,
            }
        )

        if user_input is not None:
            dev_ip = user_input[DEV_IP]
            update_interval = user_input[UPDATE_INTERVAL]

            if not (isinstance(update_interval, int)):
                self._errors[UPDATE_INTERVAL] = "invalid_interval"

            if update_interval < CONF_MIN_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_short"

            if update_interval > CONF_MAX_INTERVAL:
                self._errors[UPDATE_INTERVAL] = "interval_too_long"

            can_connect, ips_found, _ = await self.hass.async_add_executor_job(
                self._check_host,
                dev_ip,
            )

            conf_data = {
                DEV_IP: dev_ip,
                UPDATE_INTERVAL: update_interval,
                CONF_HOSTS: ips_found,
            }

            if can_connect and not self._errors:
                return self.async_update_reload_and_abort(
                    self.config_entry,
                    data=conf_data,
                    title="myPV",
                    reason="options_updated",
                    reload_even_if_entry_is_unchanged=False,
                )
            if not can_connect:
                self._errors[DEV_IP] = "could_not_connect"

        return self.async_show_form(
            step_id="init", data_schema=opt_schema, errors=self._errors
        )
