"""Unit tests for myPV sensor value handling not reachable via setup."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from custom_components.mypv.const import MpvDescription
from custom_components.mypv.sensor import (
    UPDATE_STATE_ENUM,
    MpvEnergyDailySensor,
    MpvEnergyMonthlySensor,
    MpvEnergySensor,
    MpvOutStatSensor,
    MpvSensor,
    MpvUpdateSensor,
)
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfFrequency, UnitOfPower
from homeassistant.util import slugify


def _full_device(
    data: dict[str, Any], setup: dict[str, Any] | None = None
) -> MagicMock:
    """A device stub complete enough to run MpvSensor.__init__."""
    dev = MagicMock()
    dev.comm = MagicMock()
    dev.serial_number = "SN1"
    dev.name = "AC ELWA 2"
    dev.model = "AC ELWA 2"
    dev.data = data
    dev.setup = setup or {}
    return dev


def test_numeric_unitless_sensor_keeps_measurement() -> None:
    """A numeric reading without a unit (e.g. meter sum) keeps MEASUREMENT."""
    dev = _full_device({"m0sum": 1234})
    sensor = MpvSensor(dev, "m0sum", MpvDescription("Meter 0 sum", None, "sensor"))
    assert sensor.state_class is SensorStateClass.MEASUREMENT


def test_string_unitless_sensor_has_no_state_class() -> None:
    """A non-numeric value (firmware version) must not carry a state class."""
    dev = _full_device({"psversion": "a0021700"})
    sensor = MpvSensor(
        dev, "psversion", MpvDescription("Power Unit Fw Version", None, "version")
    )
    assert sensor.state_class is None


def test_unit_sensor_keeps_measurement() -> None:
    """A sensor with a unit keeps MEASUREMENT regardless of the cached value."""
    dev = _full_device({"power_solar": 500})
    sensor = MpvSensor(
        dev, "power_solar", MpvDescription("Solar power", UnitOfPower.WATT, "sensor")
    )
    assert sensor.state_class is SensorStateClass.MEASUREMENT


class _Dev:
    """Minimal MpyDevice stand-in."""

    model = "AC ELWA 2"

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


def _noop() -> None:
    pass


async def _anoop() -> None:
    pass


def test_sensor_scaling_and_missing_key() -> None:
    """Frequency is scaled and a missing key falls back to the last value."""
    sensor = MpvSensor.__new__(MpvSensor)
    sensor._key = "freq"
    sensor._unit = UnitOfFrequency.HERTZ
    sensor._last_value = None
    sensor.async_write_ha_state = _noop  # type: ignore[method-assign]

    sensor.device = _Dev({"freq": 50000})  # type: ignore[assignment]
    sensor._handle_coordinator_update()
    assert sensor._attr_native_value == 50.0

    # Missing key -> keeps the previous value (here None -> early return).
    sensor.device = _Dev({})  # type: ignore[assignment]
    sensor._last_value = None
    sensor._handle_coordinator_update()


def test_outstat_handles_value_types() -> None:
    """The AC-THOR 9s output sensor accepts int, str and unexpected values."""
    sensor = MpvOutStatSensor.__new__(MpvOutStatSensor)
    sensor._key = "rel1_out"
    sensor.async_write_ha_state = _noop  # type: ignore[method-assign]

    sensor.device = _Dev({"rel1_out": 1010})  # type: ignore[assignment]
    sensor._handle_coordinator_update()
    assert sensor._attr_native_value == 0

    sensor.device = _Dev({"rel1_out": "0101"})  # type: ignore[assignment]
    sensor._handle_coordinator_update()
    assert sensor._attr_native_value == 1

    sensor.device = _Dev({"rel1_out": None})  # type: ignore[assignment]
    sensor._handle_coordinator_update()
    assert sensor._attr_native_value == 0


def test_update_sensor_native_value() -> None:
    """The update enum sensor resolves, remembers and falls back to None."""
    sensor = MpvUpdateSensor.__new__(MpvUpdateSensor)
    sensor._key = "upd_state"
    sensor._enum = UPDATE_STATE_ENUM
    sensor._last_value = 0
    sensor.async_write_ha_state = _noop  # type: ignore[method-assign]

    sensor.device = _Dev({"upd_state": 1})  # type: ignore[assignment]
    assert sensor.native_value == slugify(UPDATE_STATE_ENUM[1])

    # Missing value keeps the last known state.
    sensor.device = _Dev({})  # type: ignore[assignment]
    assert sensor.native_value == slugify(UPDATE_STATE_ENUM[1])

    # Unknown value maps to None.
    sensor.device = _Dev({"upd_state": 999})  # type: ignore[assignment]
    assert sensor.native_value is None

    sensor._handle_coordinator_update()


async def test_energy_update_value_error() -> None:
    """A non-numeric restored state falls back to 0."""
    sensor = MpvEnergySensor.__new__(MpvEnergySensor)
    sensor._state = "bad"
    sensor._last_value = 1.0
    sensor.async_get_last_sensor_data = _anoop  # type: ignore[method-assign]

    await sensor.async_update()
    assert sensor._last_value == 0.0


async def test_energy_daily_reset_and_error() -> None:
    """Daily sensor resets when the day changed and tolerates bad values."""
    sensor = MpvEnergyDailySensor.__new__(MpvEnergyDailySensor)
    sensor.ha_timezone = UTC
    sensor.entity_id = "sensor.daily"
    sensor.async_get_last_sensor_data = _anoop  # type: ignore[method-assign]
    sensor.async_write_ha_state = _noop  # type: ignore[method-assign]

    sensor._state = None
    sensor._last_value = 0.0
    sensor._last_reset = None
    await sensor.async_update()
    assert sensor._last_reset is not None

    sensor._last_reset = datetime.now(UTC)
    sensor._state = "bad"
    await sensor.async_update()
    assert sensor._last_value == 0.0


async def test_energy_monthly_reset_and_error() -> None:
    """Monthly sensor resets when the month changed and tolerates bad values."""
    sensor = MpvEnergyMonthlySensor.__new__(MpvEnergyMonthlySensor)
    sensor.ha_timezone = UTC
    sensor.entity_id = "sensor.monthly"
    sensor.async_get_last_sensor_data = _anoop  # type: ignore[method-assign]
    sensor.async_write_ha_state = _noop  # type: ignore[method-assign]

    sensor._state = None
    sensor._last_value = 0.0
    sensor._last_reset = None
    await sensor.async_update()
    assert sensor._last_reset is not None

    sensor._last_reset = datetime.now(UTC)
    sensor._state = "bad"
    await sensor.async_update()
    assert sensor._last_value == 0.0
