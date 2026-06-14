"""Buttons of myPV integration."""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Add all myPV button entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.buttons)


class MpvBoostButton(MpvEntity, ButtonEntity):
    """Representation of myPV button."""

    _attr_icon = "mdi:heat-wave"

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the button."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind

    async def async_press(self) -> None:
        """Instruct the button to activate."""
        await self.comm.activate_boost(self.device, 1)  # 1 to activate boost


class MpvBoostOffButton(MpvBoostButton):
    """Representation of myPV button to shut off boost."""

    async def async_press(self) -> None:
        """Instruct the button to deactivate."""
        await self.comm.activate_boost(self.device, 0)  # 0 to deactivate boost
