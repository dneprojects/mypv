"""Sensors of myPV integration."""

from datetime import datetime, timedelta
from decimal import Decimal
import logging
from typing import Any

import pytz

from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMM_HUB, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Add all myPV sensor entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.sensors)


class MpvSensor(CoordinatorEntity, SensorEntity):
    """Representation of myPV sensors."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = True

    def __init__(self, device, key: str, info: list[Any]) -> None:
        """Initialize the sensor."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self.hass = device.comm.hass
        self._key = key
        self._name = info[0]
        self._unit_of_measurement = info[1]
        self._type = info[2]
        self._last_value = None
        if key.split("_")[0] in ["power1", "power2", "power3"]:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = (
                False  # Entity will initally be disabled
            )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._last_value

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def device_class(self):
        """Return device class of sensor."""
        if self._unit_of_measurement == UnitOfTemperature.CELSIUS:
            return SensorDeviceClass.TEMPERATURE
        if self._unit_of_measurement == UnitOfElectricCurrent.AMPERE:
            return SensorDeviceClass.CURRENT
        if self._unit_of_measurement == UnitOfElectricPotential.VOLT:
            return SensorDeviceClass.VOLTAGE
        if self._unit_of_measurement == UnitOfPower.WATT:
            return SensorDeviceClass.POWER
        if self._unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR:
            return SensorDeviceClass.ENERGY
        if self._unit_of_measurement == UnitOfFrequency.HERTZ:
            return SensorDeviceClass.FREQUENCY
        return SensorDeviceClass.ENUM

    @property
    def state_class(self):
        """Return device state class of sensor."""
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self):
        """Return icon."""
        if self._name in ["IP", "DNS", "Gateway", "Subnet mask"]:
            return "mdi:ip-network"
        if self._name.split()[-1] == "Version":
            return "mdi:numeric"
        if self._name.split()[-1] == "Surplus":
            return "mdi:octagram-plus-outline"
        if self._name in ["Screen mode", "Power supply state"]:
            return "mdi:state-machine"
        if self._name in ["Fan speed"]:
            return "mdi:fan"
        return None

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
        try:
            state = self.device.data[self._key]
            if self._type == "power_act":
                relOut = int(self.comm.data["rel1_out"])
                loadNom = int(self.comm.data["load_nom"])
                state = (relOut * loadNom) + int(state)
        except Exception:  # noqa: BLE001
            state = self._last_value
        if state is None:
            return state
        if self._unit_of_measurement == UnitOfFrequency.HERTZ:
            state = state / 1000
        if self._unit_of_measurement == UnitOfTemperature.CELSIUS:
            state = state / 10
        if self._unit_of_measurement == UnitOfElectricCurrent.AMPERE:
            state = state / 10
        self._last_value = state
        self._attr_native_value = state
        self.async_write_ha_state()
        return None


class MpvOutStatSensor(MpvSensor):
    """Return output state from last digit for AC-Thor 9s."""

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        value = self.device.data[self._key]
        if isinstance(value, int):
            str_number = str(value).zfill(4)
        elif isinstance(value, str):
            str_number = value
        else:
            _LOGGER.warning("Unexpected type for output status sensor value: %r", value)
            str_number = "0000"
        state = int(str_number[-1])  # Get the last digit
        self._last_value = state
        self._attr_native_value = state
        self.async_write_ha_state()

    @property
    def icon(self):
        """Return icon."""
        return "mdi:format-list-numbered"


class MpvCtrlTypeSensor(MpvSensor):
    """Return control type state."""

    def __init__(self, device, key, info) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info)
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
            200: "Huawei (Modbus RTU)",
            201: "Growatt (Modbus RTU)",
            202: "Solax (Modbus RTU)",
            203: "Qcells (Modbus RTU)",
            204: "IME Conto D4 Modbus MID (Modbus RTU)",
            211: "my-PV WiFi Meter (Modbus RTU)",
        }

    @property
    def icon(self):
        """Return icon."""
        return "mdi:format-list-bulleted-type"

    @property
    def state(self):
        """Return the state of the device."""

        try:
            state = self.device.setup[self._key]
            self._last_value = state
            return self._enum[state]
        except Exception:  # noqa: BLE001
            state = self._last_value
        return "Unknown"


class MpvUpdateSensor(MpvSensor):
    """Return update state from enum."""

    def __init__(self, device, key, info) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info)
        self._last_value = 0
        if device.model == "Solthor":
            self._enum = {
                0: "State not available",
                1: "No new fw available",
                2: "New fw available",
                3: "Download started (ini)",
                4: "Download started (bin)",
                5: "Download started (other)",
                6: "Download interrupted",
                7: "Download finished, waiting for installation",
            }
        else:
            self._enum = {
                0: "No new fw available",
                1: "New fw available",
                2: "Download started (ini)",
                3: "Download started (bin)",
                4: "Download started (other)",
                5: "Download interrupted",
                10: "Download finished, waiting for installation",
            }

    @property
    def icon(self):
        """Return icon."""
        match self._enum[self._last_value]:
            case "No new fw available":
                return "mdi:clock-check-outline"
            case "New fw available":
                return "mdi:update"
            case "Download interrupted":
                return "mdi:download-off"
            case "Download finished, waiting for installation":
                return "mdi:cellphone-arrow-down"
            case _:
                return "mdi:download"

    @property
    def state(self):
        """Return the state of the device."""

        try:
            state = self.device.data[self._key]
            self._last_value = state
        except Exception:  # noqa: BLE001
            state = self._last_value
        return self._enum[state]


class MpvDevStatSensor(MpvSensor):
    """Return device state from enum."""

    def __init__(self, device, key, info) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info)
        self._last_value = 1
        if device.model == "Solthor":
            self._enum = {
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
        else:
            self._enum = {
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

    @property
    def icon(self):
        """Return icon."""
        if self._last_value == 1:
            return "mdi:water-boiler-off"
        if self._last_value == 3:
            return "mdi:water-boiler-auto"
        if self._last_value == 5:
            return "mdi:water-boiler-off"
        if self._last_value > 200:
            return "mdi:water-boiler-alert"
        return "mdi:water-boiler"

    @property
    def state(self):
        """Return the state of the device."""

        try:
            state = self.device.state
            self._last_value = state + 1
        except Exception:  # noqa: BLE001
            pass
        return self._enum[self._last_value]


class MpvEnergySensor(IntegrationSensor, MpvSensor):
    """Return energy state by integrating power consumption."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, device, key, info, source, tz) -> None:
        """Initialize the sensor."""
        self._last_value = 0
        self._last_reset = None
        # Get name_by_user from device registry if available
        devreg = dr.async_get(device.comm.hass)
        for dev_id in devreg.devices.data:
            dev = devreg.devices.get(dev_id)
            if dev is not None:
                if (DOMAIN, device.serial_number) in dev.identifiers:
                    self.name_by_user = dev.name_by_user
                    break
        if not self.name_by_user:
            self.name_by_user = device.name
        self.ha_timezone = tz

        # Explicitly initialize both superclasses
        IntegrationSensor.__init__(
            self,
            device.comm.hass,
            source_entity=f"sensor.{(self.name_by_user + '_' + source[0]).replace(' ', '_').replace('-', '_').lower()}",
            name=info[0],
            round_digits=1,
            integration_method="trapezoidal",
            unit_prefix="k",
            unit_time=UnitOfTime.HOURS,
            unique_id=f"{device.serial_number}_{info[0]}",
            max_sub_interval=timedelta(seconds=10),
        )
        MpvSensor.__init__(self, device, key, info)

    @property
    def icon(self):
        """Return icon."""
        return "mdi:meter-electric"

    @property
    def state_class(self):
        """Return device state class of sensor."""
        return SensorStateClass.TOTAL

    @property
    def device_class(self):
        """Return device class of sensor."""
        return SensorDeviceClass.ENERGY

    @property
    def state(self):
        """Return the state of the device."""
        return Decimal(self._last_value)

    @property
    def last_reset(self):
        """Return last reset of sensor."""
        return self._last_reset

    @property
    def unique_id(self):
        """Return unique id based on device serial and variable."""
        return f"{self.device.serial_number}_{self._name}"

    async def async_update(self):
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
        self._last_reset = datetime.now(pytz.utc)
        self.async_write_ha_state()


class MpvEnergyDailySensor(MpvEnergySensor):
    """Return energy state by integrating power consumption."""

    def __init__(self, device, key, info, source, tz) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info, source, tz)
        self._last_reset = datetime.now(self.ha_timezone)

    async def async_update(self):
        """Update the sensor state."""
        await self.async_get_last_sensor_data()
        if datetime.now(self.ha_timezone).date() != self._last_reset.date():
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
    """Return energy state by integrating power consumption."""

    def __init__(self, device, key, info, source, tz) -> None:
        """Initialize the sensor."""
        super().__init__(device, key, info, source, tz)
        self._last_reset = datetime.now(self.ha_timezone)

    async def async_update(self):
        """Update the sensor state."""
        await self.async_get_last_sensor_data()
        if datetime.now(self.ha_timezone).month != self._last_reset.month:
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
