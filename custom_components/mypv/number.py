"""Numbers of myPV integration."""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

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
        # Set while the device is known to ignore control writes, so the
        # warning is logged once per mode change instead of once per write --
        # an automation may write several times per second.
        self._reported_no_http = False
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

    def _check_http_control(self) -> None:
        """Warn once when the device silently discards control values.

        ``control.html`` values only take effect while the device is in HTTP
        control mode; in any other control type the device answers the write
        normally and drops the value. The control page comes back in the
        write's own response, so this costs no extra request. A missing entry
        means ``control.html`` has never been read successfully -- that is
        unknown, not wrong, and must not produce a warning.
        """
        control_state = self.device.state_dict.get("Control State")
        if control_state is None:
            return
        if control_state != "HTTP":
            if not self._reported_no_http:
                _LOGGER.warning(
                    "%s discards the value written to %s: the device is in "
                    "'%s' control, not HTTP control. Turn on the 'Enable HTTP' "
                    "switch or set the control type in the device setup",
                    self.device.name,
                    self._mpv_name,
                    control_state,
                )
            self._reported_no_http = True
            return
        self._reported_no_http = False

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value.

        The shown value is only adopted once the device has taken the write,
        so a failed command leaves the entity on the last value the device
        actually received instead of claiming one it never saw.
        """
        # Show the integer the device was given, so the value does not change
        # shape ("2500.0" -> "2500") at the next poll.
        power = int(value)
        if not await self.comm.set_power(self.device, power):
            return
        self._attr_native_value = power
        self.async_write_ha_state()
        self._check_http_control()


class MpvPidPowerControl(MpvPowerControl):
    """Representation of myPV pid power control."""

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, key, info)
        self._mpv_name = f"PID {info.name}"
        self._attr_translation_key = slugify(self._mpv_name)
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
        """Set the new value.

        Exactly one request per call. This used to keep writing once a second
        until the device reported HTTP control, which made a single service
        call run unbounded -- and it could not reach its goal anyway: repeating
        a ``control.html`` write never changes the control type, only a setup
        write does (the 'Enable HTTP' switch). Whether the device took the
        value is reported by ``_check_http_control`` instead.
        """
        pid_power = int(value)
        if not await self.comm.set_pid_power(self.device, pid_power):
            return
        self._attr_native_value = pid_power
        self.device.pid_power = pid_power
        self.device.pid_power_set = 1
        self.async_write_ha_state()
        self._check_http_control()


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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.device.setup[self._key] / 10
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        await self.comm.set_number(self.device, self._key, int(value * 10))


class MpvGridTargetControl(MpvEntity, NumberEntity):
    """Representation of the target power at the grid connection point.

    ``ptarget`` is the setpoint the device's own controller regulates the grid
    power to, so it is what decides how much of the surplus is left unused: on
    an AC ELWA 2, ``ptarget`` -50 parked the reported surplus at ~77 W and
    -500 at ~531 W. Negative means feed-in, positive means drawn from the grid.

    Unlike the temperature setup values this is written unscaled -- the device
    reports and takes plain watts.
    """

    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = -1000
    _attr_native_max_value = 1000
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, info.name)
        self._key = key
        self._type = info.kind

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.device.setup[self._key]
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value.

        The shown value is only adopted once the device has taken the write, so
        a failed command leaves the entity on the last value the device
        actually received.
        """
        target = int(value)
        if not await self.comm.set_number(self.device, self._key, target):
            return
        self._attr_native_value = target
        self.async_write_ha_state()


class MpvToutControl(MpvEntity, NumberEntity):
    """Representation of the control value timeout setting."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_min_value = 10
    _attr_native_max_value = 180
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, device: MpyDevice, key: str) -> None:
        """Initialize the control."""
        super().__init__(device, "Control Value Timeout")
        self._key = key

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            self._attr_native_value = self.device.setup[self._key]
        except KeyError, TypeError:
            # The entity is created for every non-Solthor device, but not every
            # model reports a control value timeout. Without this the very
            # first update raises while the entity is being added, so it never
            # appears at all.
            _LOGGER.debug("%s does not report %s", self.device.name, self._key)
            return
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value."""
        self._attr_native_value = value
        await self.comm.set_number(self.device, self._key, int(value))
