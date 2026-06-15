"""Unit tests for myPV sensor value handling not reachable via setup."""

from datetime import UTC, datetime
from typing import Any

from custom_components.mypv.sensor import (
    UPDATE_STATE_ENUM,
    MpvEnergyDailySensor,
    MpvEnergyMonthlySensor,
    MpvEnergySensor,
    MpvOutStatSensor,
    MpvSensor,
    MpvUpdateSensor,
)
from homeassistant.const import UnitOfFrequency
from homeassistant.util import slugify


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
