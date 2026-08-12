"""Numbers of myPV integration."""

import logging
from typing import TYPE_CHECKING, NamedTuple

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


class MpvSetupNumber(NamedTuple):
    """How one writable ``setup.jsn`` value is presented and scaled.

    scale: device units per displayed unit. The temperatures are stored in
    tenths of a degree, everything else is stored as it is shown.
    """

    device_class: NumberDeviceClass
    unit: str
    min_value: float
    max_value: float
    step: float
    scale: int = 1


SETUP_NUMBERS: dict[str, MpvSetupNumber] = {
    "ww1target": MpvSetupNumber(
        NumberDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 40, 80, 1, scale=10
    ),
    "ww1boost": MpvSetupNumber(
        NumberDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 40, 80, 1, scale=10
    ),
    # ``ptarget`` is the setpoint the device's own controller regulates the grid
    # power to, so it decides how much of the surplus is left unused: on an AC
    # ELWA 2, -50 parked the reported surplus at ~77 W and -500 at ~531 W.
    # Negative means feed-in, positive means drawn from the grid.
    "ptarget": MpvSetupNumber(
        NumberDeviceClass.POWER, UnitOfPower.WATT, -1000, 1000, 10
    ),
    "tout": MpvSetupNumber(NumberDeviceClass.DURATION, UnitOfTime.SECONDS, 10, 180, 10),
}


class MpvSetupControl(MpvEntity, NumberEntity):
    """Representation of a writable ``setup.jsn`` value.

    Everything that differs between these settings -- bounds, step, unit and
    whether the device stores tenths -- comes from ``SETUP_NUMBERS``, so a new
    one is a table entry rather than a class.
    """

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the control."""
        super().__init__(device, info.name)
        self._key = key
        spec = SETUP_NUMBERS[key]
        self._scale = spec.scale
        self._attr_device_class = spec.device_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step

    def _displayed(self, stored: float) -> float:
        """Convert a value as the device stores it to the one shown.

        Both the poll and a write go through this, so a written value cannot
        change shape ("50" -> "50.0") at the next poll.
        """
        return stored / self._scale if self._scale != 1 else stored

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            stored = self.device.setup[self._key]
        except KeyError, TypeError:
            # Not every model reports every setting -- the control value timeout
            # is created for each non-Solthor device but not sent by all of
            # them. Without this the very first update raises while the entity
            # is being added, so it never appears at all.
            _LOGGER.debug("%s does not report %s", self.device.name, self._key)
            return
        self._attr_native_value = self._displayed(stored)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the new value.

        The shown value is only adopted once the device has taken the write, so
        a failed command leaves the entity on the last value the device
        actually received instead of claiming one it never saw.
        """
        stored = int(value * self._scale)
        if not await self.comm.set_number(self.device, self._key, stored):
            return
        self._attr_native_value = self._displayed(stored)
        self.async_write_ha_state()
