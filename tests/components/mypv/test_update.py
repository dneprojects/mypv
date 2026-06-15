"""Unit tests for the myPV firmware update entity."""

from typing import Any

from custom_components.mypv.update import MpvFwUpdate


class _FakeDevice:
    """Minimal stand-in for MpyDevice."""

    model = "AC ELWA 2"

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


def _update(data: dict[str, Any]) -> MpvFwUpdate:
    entity = MpvFwUpdate.__new__(MpvFwUpdate)
    entity.device = _FakeDevice(data)  # type: ignore[assignment]
    entity._installed_key = "fwversion"
    entity._latest_key = "fwversionlatest"
    entity._state_key = "upd_state"
    return entity


def test_versions_and_progress() -> None:
    """installed/latest versions and in_progress reflect the device data."""
    entity = _update({"fwversion": "a1", "fwversionlatest": "a2", "upd_state": 2})
    assert entity.installed_version == "a1"
    assert entity.latest_version == "a2"
    assert entity.in_progress is True


def test_latest_falls_back_to_installed() -> None:
    """An empty latest version falls back to the installed one."""
    entity = _update({"fwversion": "a1", "fwversionlatest": "", "upd_state": 0})
    assert entity.latest_version == "a1"
    assert entity.in_progress is False


def test_missing_data_is_handled() -> None:
    """Missing keys yield None / not-in-progress instead of raising."""
    entity = _update({})
    assert entity.installed_version is None
    assert entity.in_progress is False
