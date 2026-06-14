"""Switches of myPV integration."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMM_HUB, DOMAIN, MpvDescription
from .entity import MpvEntity

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add all myPV switch entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.switches)


class MpvSetupSwitch(MpvEntity, SwitchEntity):
    """Representation of a myPV setup switch backed by a setup.jsn key."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the switch."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind

    @property
    def is_on(self) -> bool:
        """Return status of output."""
        return self.device.setup.get(self._key) == 1

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        await self.comm.switch(self.device, self._key, True)
        await self.device.update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        await self.comm.switch(self.device, self._key, False)
        await self.device.update()


class MpvHttpSwitch(MpvEntity, SwitchEntity):
    """Switch enabling HTTP control mode of the device."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, device: MpyDevice, key: str) -> None:
        """Initialize the switch."""
        super().__init__(device, "Enable HTTP")
        self._key = key

    @property
    def is_on(self) -> bool:
        """Return status of output."""
        return self.device.setup.get(self._key) == 1

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable HTTP control mode."""
        await self.comm.set_control_mode(self.device, 1)
        await self.device.update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable HTTP control mode (back to auto detect)."""
        await self.comm.set_control_mode(self.device, 0)
        await self.device.update()
