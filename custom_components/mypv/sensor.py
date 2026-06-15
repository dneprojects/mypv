"""Sensors of myPV integration."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.integration.sensor import IntegrationSensor, UnitOfTime
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import COMM_HUB, DOMAIN, MpvDescription
from .entity import MpvEntity

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)

# Map a unit of measurement to the matching sensor device class.
_DEVICE_CLASS_BY_UNIT: dict[str, SensorDeviceClass] = {
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    UnitOfElectricCurrent.AMPERE: SensorDeviceClass.CURRENT,
    UnitOfElectricPotential.VOLT: SensorDeviceClass.VOLTAGE,
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    UnitOfEnergy.KILO_WATT_HOUR: SensorDeviceClass.ENERGY,
    UnitOfFrequency.HERTZ: SensorDeviceClass.FREQUENCY,
}

# Sensors that are added as diagnostic and disabled by default. Network
# addresses, screen/fan diagnostics, the firmware versions and update states
# (already represented by the update entities), the power-unit temperature and
# the L1 mains voltage.
_DIAGNOSTIC_DISABLED_KEYS = frozenset(
    {
        "cur_ip",
        "cur_sn",
        "cur_gw",
        "cur_dns",
        "screen_mode_flag",
        "fan_speed",
        "fwversion",
        "psversion",
        "p9sversion",
        "upd_state",
        "ps_upd_state",
        "p9s_upd_state",
        "temp_ps",
        "volt_mains",
    }
)

# Device state enums, keyed by the raw device value. The values are translated
# through the entity ``state`` translations (keyed by the slugified value).
DEV_STATE_ENUM_SOLTHOR: dict[int, str] = {
    0: "State not available",
    1: "No control",
    2: "Heat",
    3: "Standby",
    4: "Boost heat",
    5: "Heat finished",
    7: "Startup DC-heating",
    21: "Legionella-Boost active",
    22: "Device disabled",
    23: "Device blocked",
}
DEV_STATE_ENUM: dict[int, str] = {
    0: "State not available",
    1: "No control",
    2: "Heat",
    3: "Standby",
    4: "Boost heat",
    5: "Heat finished",
    20: "Legionella-Boost active",
    21: "Device disabled",
    22: "Device blocked",
    201: "STL triggered",
    202: "Power stage overtemp",
    203: "Power stage PCB temp probe fault",
    204: "Hardware fault",
    205: "ELWA Temp Sensor fault",
    209: "Mainboard Error",
}
UPDATE_STATE_ENUM_SOLTHOR: dict[int, str] = {
    0: "State not available",
    1: "No new fw available",
    2: "New fw available",
    3: "Download started (ini)",
    4: "Download started (bin)",
    5: "Download started (other)",
    6: "Download interrupted",
    7: "Download finished, waiting for installation",
}
UPDATE_STATE_ENUM: dict[int, str] = {
    0: "No new fw available",
    1: "New fw available",
    2: "Download started (ini)",
    3: "Download started (bin)",
    4: "Download started (other)",
    5: "Download interrupted",
    10: "Download finished, waiting for installation",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add all myPV sensor entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.sensors)


class MpvSensor(MpvEntity, SensorEntity):
    """Representation of myPV sensors."""

    _attr_state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the sensor."""
        super().__init__(device, info.name)
        self._key = key
        self._unit = info.unit
        self._type = info.kind
        self._last_value: Any = None
        self._attr_native_unit_of_measurement = info.unit
        self._attr_device_class = (
            _DEVICE_CLASS_BY_UNIT.get(info.unit) if info.unit else None
        )
        # Only sensors with a unit are guaranteed numeric; everything else
        # (text, versions, string enums like "Control source") must not carry
        # a measurement state class or HA rejects their non-numeric value.
        if info.unit is None:
            self._attr_state_class = None
        if (
            key.split("_", maxsplit=1)[0] in ("power1", "power2", "power3")
            or key in _DIAGNOSTIC_DISABLED_KEYS
        ):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            # Entity will initially be disabled
            self._attr_entity_registry_enabled_default = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            state = self.device.data[self._key]
        except KeyError, TypeError:
            state = self._last_value
        if state is None:
            return
        if self._unit == UnitOfFrequency.HERTZ:
            state = state / 1000
        if self._unit == UnitOfTemperature.CELSIUS:
            state = state / 10
        if self._unit == UnitOfElectricCurrent.AMPERE:
            state = state / 10
        self._last_value = state
        self._attr_native_value = state
        self.async_write_ha_state()


class MpvOutStatSensor(MpvSensor):
    """Return output state from last digit for AC-Thor 9s."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        value = self.device.data[self._key]
        if isinstance(value, int):
            str_number = str(value).zfill(4)
        elif isinstance(value, str):
            str_number = value
        else:
            _LOGGER.warning("Unexpected type for output status sensor value: %r", value)
            str_number = "0000"
        self._attr_native_value = int(str_number[-1])  # Get the last digit
        self.async_write_ha_state()


class MpvUpdateSensor(MpvSensor):
    """Return firmware update state as an enum sensor."""

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info)
        self._last_value = 0
        self._enum = (
            UPDATE_STATE_ENUM_SOLTHOR
            if device.model == "Solthor"
            else UPDATE_STATE_ENUM
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_state_class = None
        self._attr_options = [slugify(value) for value in self._enum.values()]

    @property
    def native_value(self) -> str | None:
        """Return the state of the device."""
        value = self.device.data.get(self._key)
        if value is not None:
            self._last_value = value
        display = self._enum.get(self._last_value)
        return slugify(display) if display is not None else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class MpvDevStatSensor(MpvSensor):
    """Return device state as an enum sensor."""

    def __init__(self, device: MpyDevice, key: str, info: MpvDescription) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info)
        self._last_value = 1
        self._enum = (
            DEV_STATE_ENUM_SOLTHOR if device.model == "Solthor" else DEV_STATE_ENUM
        )
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_state_class = None
        self._attr_options = [slugify(value) for value in self._enum.values()]

    @property
    def native_value(self) -> str | None:
        """Return the state of the device."""
        if self.device.state is not None:
            self._last_value = self.device.state + 1
        display = self._enum.get(self._last_value)
        return slugify(display) if display is not None else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class MpvEnergySensor(IntegrationSensor, MpvSensor):
    """Return energy state by integrating power consumption."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        device: MpyDevice,
        key: str,
        info: MpvDescription,
        source: MpvDescription,
        tz: Any,
    ) -> None:
        """Initialize the sensor."""
        self._last_value: float = 0
        self._last_reset: datetime | None = None
        self.name_by_user: str | None = None
        # Get name_by_user from device registry if available
        devreg = dr.async_get(device.comm.hass)
        for dev_id in devreg.devices.data:
            dev = devreg.devices.get(dev_id)
            if dev is not None and (DOMAIN, device.serial_number) in dev.identifiers:
                self.name_by_user = dev.name_by_user
                break
        if not self.name_by_user:
            self.name_by_user = device.name
        self.ha_timezone = tz

        # Explicitly initialize both superclasses
        IntegrationSensor.__init__(
            self,
            device.comm.hass,
            source_entity=f"sensor.{slugify(self.name_by_user + '_' + source.name)}",
            name=info.name,
            round_digits=1,
            integration_method="trapezoidal",
            unit_prefix="k",
            unit_time=UnitOfTime.HOURS,
            unique_id=f"{device.serial_number}_{info.name}",
            max_sub_interval=timedelta(seconds=10),
        )
        MpvSensor.__init__(self, device, key, info)

    @property
    def native_value(self) -> Decimal:
        """Return the state of the device."""
        return Decimal(self._last_value)

    @property
    def last_reset(self) -> datetime | None:
        """Return last reset of sensor."""
        return self._last_reset

    async def async_update(self) -> None:
        """Update the sensor state."""
        await self.async_get_last_sensor_data()
        if self._state is None:
            self._state = Decimal("0.0")
            self._last_value = 0.0
            return
        try:
            self._last_value = float(self._state)
        except ValueError:
            _LOGGER.error("Failed to convert state to float: %s", self._state)
            self._last_value = 0.0

    async def async_reset(self) -> None:
        """Reset the sensor's state."""
        _LOGGER.info("Resetting energy sensor %s", self.entity_id)
        self._state = Decimal("0.0")
        self._last_reset = datetime.now(UTC)
        self.async_write_ha_state()


class MpvEnergyDailySensor(MpvEnergySensor):
    """Return energy state by integrating power consumption, reset daily."""

    def __init__(
        self,
        device: MpyDevice,
        key: str,
        info: MpvDescription,
        source: MpvDescription,
        tz: Any,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info, source, tz)
        self._last_reset = datetime.now(self.ha_timezone)

    async def async_update(self) -> None:
        """Update the sensor state."""
        await self.async_get_last_sensor_data()
        if (
            self._last_reset is None
            or datetime.now(self.ha_timezone).date() != self._last_reset.date()
        ):
            await self.async_reset()
        if self._state is None:
            self._state = Decimal("0.0")
            self._last_value = 0.0
            return
        try:
            self._last_value = float(self._state)
        except ValueError:
            _LOGGER.error("Failed to convert state to float: %s", self._state)
            self._last_value = 0.0


class MpvEnergyMonthlySensor(MpvEnergySensor):
    """Return energy state by integrating power consumption, reset monthly."""

    def __init__(
        self,
        device: MpyDevice,
        key: str,
        info: MpvDescription,
        source: MpvDescription,
        tz: Any,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info, source, tz)
        self._last_reset = datetime.now(self.ha_timezone)

    async def async_update(self) -> None:
        """Update the sensor state."""
        await self.async_get_last_sensor_data()
        if (
            self._last_reset is None
            or datetime.now(self.ha_timezone).month != self._last_reset.month
        ):
            await self.async_reset()
        if self._state is None:
            self._state = Decimal("0.0")
            self._last_value = 0.0
            return
        try:
            self._last_value = float(self._state)
        except ValueError:
            _LOGGER.error("Failed to convert state to float: %s", self._state)
            self._last_value = 0.0
