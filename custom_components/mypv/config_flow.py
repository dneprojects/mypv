"""Config flow for ELWA myPV integration."""

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .connection import MyPVAuthenticationError, MyPVConnectionError, create_connection
from .const import CONF_HOSTS, DEV_IP, DOMAIN
from .discovery import async_discover_mypv_devices


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
        # State carried into the password step when the device needs auth.
        self._pending_ip: str | None = None
        self._pending_hosts: list[str] = []
        self._pending_title: str = ""
        self._pending_name: str | None = None

    def _all_hosts_in_configuration_exist(self, ip_list: list[str]) -> bool:
        """Return True if all hosts found already exist in configuration."""
        return all(ip in mypv_entries(self.hass) for ip in ip_list)

    async def _check_host(self, dev_ip: str) -> tuple[bool, list[str], str, bool]:
        """Check a myPV device and detect its transport.

        Returns ``(reachable, host_list, device_name, auth_required)``.

        HTTPS is tried first. A working HTTPS connection means new firmware, and
        new firmware always has a login password (it cannot be removed, only
        changed): the integration's initial login opens the device's grace
        window so reads and writes work afterwards, so a password is always
        required (``auth_required`` True). Plain HTTP means old firmware without
        authentication (no password). ``sec_level`` is not needed here -- it is
        read at runtime, after the login, from ``setup.jsn``.
        """
        https = create_connection(dev_ip, None, use_https=True)
        if await self._try_open(https):
            name = self._device_name(https)
            await https.close()
            return True, [dev_ip], name, True
        await https.close()

        # No HTTPS server: old firmware. Use plain HTTP for the whole exchange.
        http = create_connection(dev_ip, None)
        if await self._try_open(http):
            name = self._device_name(http)
            await http.close()
            return True, [dev_ip], name, False
        await http.close()

        return False, [], "myPV", False

    @staticmethod
    async def _try_open(connection: Any) -> bool:
        """Open a probe connection, treating any failure as unreachable."""
        try:
            return await connection.open()
        except (MyPVAuthenticationError, MyPVConnectionError):
            return False

    @staticmethod
    def _device_name(connection: Any) -> str:
        """Return the device name from a probed connection."""
        dev = connection.mypv_dev
        return str(dev.get("device", "myPV")) if dev else "myPV"

    async def _verify_password(self, dev_ip: str, password: str) -> tuple[bool, str]:
        """Verify a password against the device. Returns ``(ok, device_name)``."""
        connection = create_connection(dev_ip, password)
        try:
            opened = await connection.open()
        except MyPVAuthenticationError:
            await connection.close()
            return False, "myPV"
        device_name = "myPV"
        if opened and connection.mypv_dev:
            device_name = str(connection.mypv_dev.get("device", "myPV"))
        await connection.close()
        return opened, device_name

    def _entry_data(self, password: str | None = None) -> dict[str, Any]:
        """Build the config entry data for the pending device."""
        data: dict[str, Any] = {
            DEV_IP: self._pending_ip,
            CONF_HOSTS: self._pending_hosts,
        }
        if password:
            data[CONF_PASSWORD] = password
        return data

    async def _create_or_auth(
        self, dev_ip: str, hosts: list[str], title: str, name: str, auth_required: bool
    ) -> config_entries.ConfigFlowResult:
        """Create the entry, or route to the password step if auth is needed."""
        self._pending_ip = dev_ip
        self._pending_hosts = hosts
        self._pending_title = title
        self._pending_name = name
        if auth_required:
            return await self.async_step_password()
        return self.async_create_entry(title=title, data=self._entry_data())

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery via dhcp."""
        dev_ip = discovery_info.ip

        can_connect, _ips_found, fetched_name, _auth = await self._check_host(dev_ip)
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

        can_connect, _ips_found, fetched_name, _auth = await self._check_host(dev_ip)
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

            can_connect, ips_found, _, auth_required = await self._check_host(
                self._discovery_ip
            )
            if not can_connect:
                return self.async_abort(reason="cannot_connect")

            final_title = (
                f"{self._discovery_name} ({self._discovery_ip})"
                if self._discovery_name != "myPV"
                else f"myPV ({self._discovery_ip})"
            )
            return await self._create_or_auth(
                self._discovery_ip,
                ips_found,
                final_title,
                self._discovery_name or "myPV",
                auth_required,
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
            (
                can_connect,
                ips_found,
                fetched_name,
                auth_required,
            ) = await self._check_host(dev_ip)

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
                    return await self._create_or_auth(
                        dev_ip, ips_found, final_title, display_name, auth_required
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

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the device password (newer firmware requires authentication)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._pending_ip is not None
            password = user_input[CONF_PASSWORD]
            ok, _name = await self._verify_password(self._pending_ip, password)
            if ok:
                return self.async_create_entry(
                    title=self._pending_title,
                    data=self._entry_data(password),
                )
            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={
                "name": self._pending_name or "myPV",
                "ip": self._pending_ip or "",
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when the stored password stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm re-authentication with a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            dev_ip = entry.data[DEV_IP]
            ok, _name = await self._verify_password(dev_ip, user_input[CONF_PASSWORD])
            if ok:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"name": entry.title},
        )
