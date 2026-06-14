"""Numbers of myPV integration."""

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
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
    """Add all myPV number entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.controls)


class MpvPowerControl(MpvEntity, NumberEntity):
    """Representation of myPV power control."""

    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind
        if device.model == "AC-THOR 9s":
            self._attr_native_max_value = 9000
        elif device.model == "AC ELWA 2":
            self._attr_native_max_value = 3500
        else:
            self._attr_native_max_value = 3000

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.device.data[self._key]
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        await self.comm.set_power(self.device, int(value))


class MpvPidPowerControl(MpvPowerControl):
    """Representation of myPV pid power control."""

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, key, info)
        self._attr_name = f"PID {info.name}"
        self._attr_unique_id = f"{device.serial_number}_PID {info.name}"
        self._attr_native_min_value = -8388607
        self._attr_native_max_value = 8388607

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.device.pid_power_set in (1, 2):
            # wait for update in power status
            self.device.pid_power_set += 1
        elif self.device.data[self._key] == 0:
            # power is switched off
            self._attr_native_value = 0
            self.device.pid_power = 0
            self.device.pid_power_set = 0
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        self.device.pid_power = value
        self.device.pid_power_set = 1
        http_control_mode = self.device.state_dict["Control State"] == "HTTP"
        while not http_control_mode:
            await self.comm.set_pid_power(self.device, int(value))
            await asyncio.sleep(1)
            http_control_mode = self.device.state_dict["Control State"] == "HTTP"
        await self.comm.set_pid_power(self.device, int(value))


class MpvSetupControl(MpvEntity, NumberEntity):
    """Representation of myPV setup value control."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = 40
    _attr_native_max_value = 80
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind

    @property
    def icon(self) -> str:
        """Return icon."""
        if self._attr_name is not None and self._attr_name.startswith("Boost"):
            return "mdi:water-thermometer-outline"
        return "mdi:water-thermometer"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.device.setup[self._key] / 10
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        await self.comm.set_number(self.device, self._key, int(value * 10))


class MpvToutControl(MpvEntity, NumberEntity):
    """Representation of the control value timeout setting."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_min_value = 10
    _attr_native_max_value = 180
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:camera-timer"

    def __init__(self, device: MpyDevice, key: str) -> None:
        """Initialize the control."""
        super().__init__(device, "Control Value Timeout")
        self._key = key

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.device.setup[self._key]
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        await self.comm.set_number(self.device, self._key, int(value))
