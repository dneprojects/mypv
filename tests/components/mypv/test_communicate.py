"""Tests for the myPV communicator error handling."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv.communicate import (
    _CONTROL_FAILURES_BEFORE_BACKOFF,
    _CONTROL_RETRY_CYCLES,
    MypvCommunicator,
)
from custom_components.mypv.connection import MyPVAuthenticationError
from custom_components.mypv.const import COMM_HUB, DOMAIN
from custom_components.mypv.mypv_device import MpyDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import FakeWorld


def _comm_device(
    hass: HomeAssistant, entry: MockConfigEntry
) -> tuple[MypvCommunicator, MpyDevice]:
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]
    return comm, comm.devices[0]


def _reauth_started(hass: HomeAssistant) -> bool:
    """Return True if a reauth flow is in progress for the myPV integration."""
    return any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )


async def test_commands_return_false_on_error(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Every device command returns False (and does not raise) on failure."""
    comm, device = _comm_device(hass, setup_integration)

    mock_device.spec().error = TimeoutError()

    assert await comm.set_number(device, "ww1target", 500) is False
    assert await comm.set_power(device, 1000) is False
    assert await comm.set_control_mode(device, 1) is False
    assert await comm.set_pid_power(device, 1000) is False
    assert await comm.switch(device, "devmode", True) is False
    assert await comm.activate_boost(device, 1) is False


async def test_update_fetches_endpoints_sequentially(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update() must hit the single-connection device one request at a time.

    The myPV web server serves only one connection; fetching data/setup/state
    concurrently makes requests collide and time out. Guard against a regression
    that re-introduces concurrent fetching.
    """
    comm, device = _comm_device(hass, setup_integration)
    device.energy_sensors = []  # isolate the test to the HTTP fetches

    active = 0
    max_active = 0

    async def _tracked_dict(*args: object, **kwargs: object) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)  # yield so any overlap becomes observable
        active -= 1
        return {}

    async def _tracked_state(*args: object, **kwargs: object) -> bool:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return True

    monkeypatch.setattr(comm, "data_update", _tracked_dict)
    monkeypatch.setattr(comm, "setup_update", _tracked_dict)
    monkeypatch.setattr(comm, "state_update", _tracked_state)

    await device.update()

    assert max_active == 1


async def test_state_update_failure_backs_off_then_recovers(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A failing control read backs off but is never disabled for good."""
    comm, device = _comm_device(hass, setup_integration)
    assert device.control_failures == 0

    mock_device.spec().error = TimeoutError()

    # The first failures are retried at the full poll rate...
    for expected in range(1, _CONTROL_FAILURES_BEFORE_BACKOFF + 1):
        assert await comm.state_update(device) is False
        assert device.control_failures == expected
    assert device.control_skip == 0

    # ...then the read backs off and the following polls are skipped.
    assert await comm.state_update(device) is False
    assert device.control_skip == _CONTROL_RETRY_CYCLES
    assert await comm.state_update(device) is False
    assert device.control_skip == _CONTROL_RETRY_CYCLES - 1

    # A recovered device is picked up again once the backoff has elapsed.
    mock_device.spec().error = None
    device.control_skip = 0
    assert await comm.state_update(device) is True
    assert device.control_failures == 0


async def test_boost_buttons_exist_when_the_control_read_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A device that will not serve control.html still gets its boost buttons.

    Regression guard for 1.6.4: a failing ``control.html`` read at setup used to
    latch control off *before* the entities were built, which silently stripped
    the boost buttons and power controls while everything fed from setup.jsn
    (the "Enable Boost Mode" switch) stayed. Entity existence is the device's
    own capability — the ``data.jsn`` keys — not the health of one read.
    """
    mock_device.spec().text_errors["/control.html"] = TimeoutError()

    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_get(hass).entities
    assert any(entity.domain == "button" for entity in entities.values())
    assert [
        entity.entity_id
        for entity in entities.values()
        if entity.entity_id.startswith("button.")
    ] == [
        "button.ac_elwa_2_123456_start_boost",
        "button.ac_elwa_2_123456_stop_boost",
    ]


async def test_command_auth_error_starts_reauth(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Every command that hits a 401 returns False and starts a reauth flow."""
    comm, device = _comm_device(hass, setup_integration)

    mock_device.spec().error = MyPVAuthenticationError()

    commands = [
        comm.set_number(device, "ww1target", 500),
        comm.set_power(device, 1000),
        comm.set_control_mode(device, 1),
        comm.set_pid_power(device, 1000),
        comm.switch(device, "devmode", True),
        comm.activate_boost(device, 1),
    ]
    for command in commands:
        assert await command is False

    await hass.async_block_till_done()
    assert _reauth_started(hass)


async def test_poll_auth_error_starts_reauth(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """An auth failure during the cyclic poll fails the update and starts reauth."""
    comm, _ = _comm_device(hass, setup_integration)

    mock_device.spec().error = MyPVAuthenticationError()

    await comm.async_refresh()
    await hass.async_block_till_done()

    assert comm.last_update_success is False
    assert _reauth_started(hass)
