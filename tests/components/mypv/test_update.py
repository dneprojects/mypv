"""Unit tests for the myPV firmware update entity."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.mypv import update as update_module
from custom_components.mypv.update import MpvFwUpdate, supports_remote_install
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError


class _FakeDevice:
    """Minimal stand-in for MpyDevice."""

    model = "AC ELWA 2"

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class _FakeComm:
    """Records the firmware commands and drives the device state."""

    def __init__(self, device: _FakeDevice, script: dict[str, list[int]]) -> None:
        self.device = device
        self.script = script
        self.commands: list[str] = []
        self.accept = True
        self._pending: list[int] = []

    async def firmware_command(self, device: _FakeDevice, command: str) -> bool:
        self.commands.append(command)
        if not self.accept:
            return False
        self._pending = list(self.script.get(command, []))
        return True

    async def async_refresh(self) -> None:
        """Stand in for the coordinator poll: apply the next scripted state."""
        if self._pending:
            self.device.data["upd_state"] = self._pending.pop(0)


def _update(data: dict[str, Any], comm: _FakeComm | None = None) -> MpvFwUpdate:
    entity = MpvFwUpdate.__new__(MpvFwUpdate)
    entity.device = _FakeDevice(data)  # type: ignore[assignment]
    if comm is not None:
        comm.device = entity.device  # type: ignore[assignment]
        entity.comm = comm  # type: ignore[assignment]
        entity.coordinator = comm  # type: ignore[assignment]
    entity._installed_key = "fwversion"
    entity._latest_key = "fwversionlatest"
    entity._state_key = "upd_state"
    entity._installing = False
    entity._can_install = True
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
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


def test_update_percentage_only_while_downloading() -> None:
    """The percentage is reported for the download states only."""
    entity = _update({"upd_state": 3, "upd_percentage": 42})
    assert entity.update_percentage == 42

    # Downloaded and waiting for the installation: no percentage.
    entity.device.data["upd_state"] = 10
    assert entity.update_percentage is None

    # Garbage from the device does not raise.
    entity.device.data.update({"upd_state": 3, "upd_percentage": "bad"})
    assert entity.update_percentage is None


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("e0002500", True),  # the AC ELWA 2 this was captured from
        ("e0002410", False),  # older ELWA: below the minimum for its series
        ("a0021700", True),
        ("a0020000", True),  # the documented AC.THOR minimum itself
        ("a0019999", False),
        ("s0005555", False),  # Solthor: no minimum known, stays report-only
        ("a002170", False),  # malformed (too short)
        ("axxxxxxx", False),
        (None, False),
    ],
)
def test_remote_install_gate_by_series(version: str | None, supported: bool) -> None:
    """Each device series has its own minimum; unknown series stay report-only."""
    data: dict[str, Any] = {"upd_percentage": 0}
    if version is not None:
        data["fwversion"] = version
    assert supports_remote_install(data) is supported


@pytest.mark.parametrize(
    ("data", "supported"),
    [
        # Nothing but the version: not enough, the minimum for this series is
        # inferred from captures rather than documented.
        ({"fwversion": "e0002500"}, False),
        # AC ELWA 2: counts percent.
        ({"fwversion": "e0002500", "upd_percentage": 0}, True),
        # AC.THOR a0022401: no percentage at all, a file counter instead
        # (issue #52) -- requiring the percentage locked this family out.
        ({"fwversion": "a0022401", "upd_files_left": 0}, True),
        ({"fwversion": "a0022401"}, False),
    ],
    ids=["elwa_bare", "elwa_percentage", "acthor_files_left", "acthor_bare"],
)
def test_remote_install_needs_a_progress_indicator(
    data: dict[str, Any], supported: bool
) -> None:
    """Firmware new enough but without any update indicator is not offered.

    The version number cannot be compared across series, so the device also has
    to report that it knows the flow -- and which key it uses for that differs
    between the AC ELWA 2 and the AC.THOR.
    """
    assert supports_remote_install(data) is supported


def _real_device(data: dict[str, Any]) -> MagicMock:
    """A device stub complete enough to run the entity constructor."""
    device = MagicMock()
    device.comm = MagicMock()
    device.serial_number = "SN1"
    device.name = "AC ELWA 2"
    device.model = "AC ELWA 2"
    device.data = data
    return device


def test_install_feature_follows_the_version() -> None:
    """INSTALL is only advertised where the device supports it; PROGRESS always.

    PROGRESS has to be set even on the report-only parts: without it Home
    Assistant ignores the ``in_progress`` property and a download started at
    the device itself never shows up.
    """
    old = MpvFwUpdate(
        _real_device({"fwversion": "e0002410", "upd_percentage": 0}),
        "Control Unit Firmware",
        "fwversion",
        "fwversionlatest",
        "upd_state",
    )
    assert old.supported_features is UpdateEntityFeature.PROGRESS

    new = MpvFwUpdate(
        _real_device({"fwversion": "e0002500", "upd_percentage": 0}),
        "Control Unit Firmware",
        "fwversion",
        "fwversionlatest",
        "upd_state",
    )
    assert new.supported_features == (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    # The other parts are report-only even on new firmware.
    power_unit = MpvFwUpdate(
        _real_device(
            {"fwversion": "e0002500", "upd_percentage": 0, "psversion": "ep109"}
        ),
        "Power Unit Firmware",
        "psversion",
        "psversionlatest",
        "ps_upd_state",
    )
    assert power_unit.supported_features is UpdateEntityFeature.PROGRESS


async def test_install_downloads_then_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pending update is downloaded first, then installed."""
    monkeypatch.setattr(update_module, "_POLL_INTERVAL", 0)
    comm = _FakeComm(
        _FakeDevice({}),
        # Download reports its progress, then "downloaded"; the install ends
        # back at "no update available".
        {"firmware_download": [3, 3, 10], "firmware_update": [10, 0]},
    )
    entity = _update({"upd_state": 1}, comm)

    await entity.async_install(None, False)

    assert comm.commands == ["firmware_download", "firmware_update"]
    assert entity.device.data["upd_state"] == 0
    assert entity._installing is False


async def test_install_skips_the_download_when_already_downloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Firmware waiting on the device is installed without downloading again."""
    monkeypatch.setattr(update_module, "_POLL_INTERVAL", 0)
    comm = _FakeComm(_FakeDevice({}), {"firmware_update": [0]})
    entity = _update({"upd_state": 10}, comm)

    await entity.async_install(None, False)

    assert comm.commands == ["firmware_update"]


async def test_install_without_a_pending_update_raises() -> None:
    """Nothing to install is an error, not a silent no-op."""
    comm = _FakeComm(_FakeDevice({}), {})
    entity = _update({"upd_state": 0}, comm)

    with pytest.raises(HomeAssistantError):
        await entity.async_install(None, False)

    assert comm.commands == []


async def test_install_raises_when_the_device_rejects_the_command() -> None:
    """A refused command surfaces instead of waiting for the timeout."""
    comm = _FakeComm(_FakeDevice({}), {})
    comm.accept = False
    entity = _update({"upd_state": 10}, comm)

    with pytest.raises(HomeAssistantError):
        await entity.async_install(None, False)

    assert entity._installing is False


async def test_install_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """A device that never finishes the download reports a timeout."""
    monkeypatch.setattr(update_module, "_POLL_INTERVAL", 0)
    monkeypatch.setattr(update_module, "_STEP_TIMEOUT", 0.05)
    comm = _FakeComm(_FakeDevice({}), {"firmware_download": []})
    entity = _update({"upd_state": 1}, comm)

    with pytest.raises(HomeAssistantError):
        await entity.async_install(None, False)

    assert entity._installing is False


async def test_install_on_old_firmware_raises() -> None:
    """The entity refuses when the firmware does not know the commands."""
    comm = _FakeComm(_FakeDevice({}), {})
    entity = _update({"upd_state": 1}, comm)
    entity._can_install = False

    with pytest.raises(HomeAssistantError):
        await entity.async_install(None, False)

    assert comm.commands == []


def test_in_progress_while_installing() -> None:
    """The entity stays in progress across the reboot, when states are odd."""
    entity = _update({"upd_state": 0})
    assert entity.in_progress is False
    entity._installing = True
    assert entity.in_progress is True
