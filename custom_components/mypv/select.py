"""Platform for select integration."""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMM_HUB, DOMAIN, MpvDescription
from .entity import MpvEntity

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)

CTRL_TYPES: dict[int, str] = {
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add all myPV select entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        _LOGGER.debug(
            "Adding %d select entities for device %s",
            len(device.selects),
            device.name,
        )
        async_add_entities(device.selects)


class MpvCtrlTypeSelect(MpvEntity, SelectEntity):
    """Return control type state as select entity."""

    _attr_icon = "mdi:format-list-bulleted-type"

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the select."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind
        self._last_value = 0
        self._enum = CTRL_TYPES
        self._attr_options = list(self._enum.values())

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        state = self.device.setup.get(self._key)
        if state is None:
            return self._enum.get(self._last_value)
        self._last_value = state
        return self._enum.get(state)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        state = self.device.setup.get(self._key)
        if state is not None and state != self._last_value:
            self._last_value = state
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        for key, value in self._enum.items():
            if value == option:
                await self.comm.set_number(self.device, self._key, key)
                # Update setup data after setting
                resp = await self.comm.setup_update(self.device)
                if resp:
                    self.device.setup = resp
                self.async_write_ha_state()
                break
