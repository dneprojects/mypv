"""Unit tests for the myPV binary sensor value mapping."""

from typing import Any

import pytest

from custom_components.mypv.binary_sensor import (
    MpvBin1Sensor,
    MpvBin2Sensor,
    MpvBin3Sensor,
    MpvBinSensor,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, True),
        ("1", True),
        (True, True),
        (0, False),
        ("0", False),
        (False, False),
        ("unexpected", False),
        (None, False),
    ],
)
def test_bin_sensor_map(value: Any, expected: bool) -> None:
    """The base mapping handles truthy, falsy and unexpected values."""
    sensor = MpvBinSensor.__new__(MpvBinSensor)
    assert sensor.map_bool_value(value) is expected


@pytest.mark.parametrize(
    ("cls", "expected"),
    [(MpvBin1Sensor, True), (MpvBin2Sensor, False), (MpvBin3Sensor, True)],
)
def test_acthor9s_digit_map(cls: type[MpvBin1Sensor], expected: bool) -> None:
    """Each AC-THOR 9s output reads its own digit of the zero-padded value."""
    sensor = cls.__new__(cls)
    # "1011" -> digit0=1, digit1=0, digit2=1
    assert sensor.map_bool_value(1011) is expected
    assert sensor.map_bool_value("1011") is expected


def test_acthor9s_digit_map_unexpected_type() -> None:
    """A non-int/str value maps to False."""
    sensor = MpvBin1Sensor.__new__(MpvBin1Sensor)
    assert sensor.map_bool_value(None) is False
