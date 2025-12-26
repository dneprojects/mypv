"""Switches of myPV integration."""

import logging
from typing import Any, Final

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMM_HUB, DOMAIN

_LOGGER = logging.getLogger(__name__)

PID_POWER_ON_VALUE: Final = 3000
PID_POWER_OFF_VALUE: Final = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add all myPV switch entities."""
    # Retrieve communication hub from hass data
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.switches)


class MpvSetupSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of myPV setup switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, device: Any, key: str, info: list[Any]) -> None:
        """Initialize the switch."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self._key = key
        self._attr_name = info[0]
        self._type = info[2]
        self._attr_unique_id = f"{self.device.serial_number}_{self._attr_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number)},
            name=self.device.name,
            manufacturer="myPV",
            model=self.device.model,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.device.setup.get(self._key) == 1
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        await self.comm.switch(self.device, self._key, True)
        await self.device.update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        await self.comm.switch(self.device, self._key, False)
        await self.device.update()


class MpvBoostSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of myPV boost switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, device: Any, key: str, info: list[Any]) -> None:
        """Initialize the switch."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self._key = key
        self._attr_name = info[0]
        self._type = info[2]
        self._attr_unique_id = f"{self.device.serial_number}_{self._attr_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number)},
            name=self.device.name,
            manufacturer="myPV",
            model=self.device.model,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.device.data.get(self._key) == 1
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        await self.comm.switch_boost(self.device, True)
        await self.device.update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        await self.comm.switch_boost(self.device, False)
        await self.device.update()


class MpvHttpSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of myPV HTTP enable switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, device: Any, key: str) -> None:
        """Initialize the switch."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self._key = key
        self._attr_name = "Enable HTTP"
        self._attr_unique_id = f"{self.device.serial_number}_{self._attr_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number)},
            name=self.device.name,
            manufacturer="myPV",
            model=self.device.model,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.device.setup.get(self._key) == 1
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        await self.comm.set_control_mode(self.device, 1)
        await self.device.update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
