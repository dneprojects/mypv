"""Platform for select integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMM_HUB, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add all myPV select entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        _LOGGER.info(f"Adding {len(device.selects)} select entities for device {device.name}")
        async_add_entities(device.selects)


class MpvCtrlTypeSelect(CoordinatorEntity, SelectEntity):
    """Return control type state as select entity."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default = True

    def __init__(self, device, key: str, info: list) -> None:
        """Initialize the select."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self.hass = device.comm.hass
        self._key = key
        self._name = info[0]
        self._type = info[2]
        self._last_value = 0
        self._enum = {
            0: "Auto Detect",
            1: "HTTP",
            2: "Modbus TCP",
            3: "Fronius Auto",
            4: "Fronius Manual",
            5: "SMA Home Manager",
            6: "Steca Auto",
            7: "Varta Auto",
            8: "Varta Manual",
            10: "RCT Power Manual",
            12: "my-PV Meter Auto",
            13: "my-PV Meter Manual",
            14: "my-PV Power Meter Direct",
            15: "SMA Direct meter communication Auto",
            16: "SMA Direct meter communication Manual",
            19: "Digital Meter P1",
            20: "Frequency",
            21: "my-PV API",
            100: "Fronius Sunspec Manual",
            102: "Kostal PIKO IQ Plenticore plus Manual",
            103: "Kostal Smart Energy Meter Manual",
            104: "MEC electronics Manual",
            105: "SolarEdge Manual",
            106: "Victron Energy 1ph Manual",
            107: "Victron Energy 3ph Manual",
            108: "Huawei (Modbus TCP) Manual",
            109: "Carlo Gavazzi EM24 Manual",
            111: "Sungrow Manual",
            112: "Fronius Gen24 Manual",
            119: "Solax Manual",
            200: "Huawei (Modbus RTU)",
            201: "Growatt (Modbus RTU)",
            202: "Solax (Modbus RTU)",
            203: "Qcells (Modbus RTU)",
            204: "IME Conto D4 Modbus MID (Modbus RTU)",
            211: "my-PV WiFi Meter (Modbus RTU)",
        }

    @property
    def name(self):
        """Return the name of the select."""
        return self._name

    @property
    def options(self) -> list[str]:
        """Return list of options."""
        return list(self._enum.values())

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        try:
            state = self.device.setup[self._key]
            self._last_value = state
            return self._enum.get(state)
        except Exception:  # noqa: BLE001
            return self._enum.get(self._last_value)

    @property
    def icon(self):
        """Return icon."""
        return "mdi:format-list-bulleted-type"

    @property
    def unique_id(self):
        """Return unique id based on device serial and variable."""
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

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        # Update _last_value for current_option property
        try:
            state = self.device.setup[self._key]
            if state != self._last_value:
                self._last_value = state
                self.async_write_ha_state()
        except Exception:  # noqa: BLE001
            pass

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Find the key for the selected option
        for key, value in self._enum.items():
            if value == option:
                await self.comm.set_number(self.device, self._key, key)
                # Update setup data after setting
                resp = await self.comm.setup_update(self.device)
                if resp:
                    self.device.setup = resp
                self.async_write_ha_state()
                break
