"""Tests for myPV entity actions and the reset service."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv.const import DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant

from .conftest import FakeWorld
from .test_entities import PREFIX


async def test_number_set_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Setting a temperature writes setup.jsn with the value in tenths."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_target_temperature", ATTR_VALUE: 55},
        blocking=True,
    )
    assert any("ww1target=550" in url for url in mock_device.requested)


async def test_grid_target_set_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Setting the grid target writes setup.jsn with the plain watt value."""
    entity_id = f"number.{PREFIX}_target_grid_power"
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: -500},
        blocking=True,
    )
    assert any("ptarget=-500" in url for url in mock_device.requested)
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == -500


async def test_grid_target_keeps_value_on_command_error(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A failed write leaves the entity on the value the device last took."""
    entity_id = f"number.{PREFIX}_target_grid_power"
    mock_device.spec().error = TimeoutError()

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: -500},
        blocking=True,
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == -50


async def test_switch_turn_on_off(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Toggling a setup switch writes setup.jsn with 1/0."""
    entity_id = f"switch.{PREFIX}_enable_device"
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert any("devmode=0" in url for url in mock_device.requested)

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert any("devmode=1" in url for url in mock_device.requested)


async def test_select_option(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Selecting a control type writes setup.jsn with the matching index."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: f"select.{PREFIX}_control_type", ATTR_OPTION: "modbus_tcp"},
        blocking=True,
    )
    assert any("ctrl=2" in url for url in mock_device.requested)


async def test_button_press(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Pressing the boost button triggers the boost endpoint."""
    await hass.services.async_call(
        "button",
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: f"button.{PREFIX}_start_boost"},
        blocking=True,
    )
    assert any("bststrt=1" in url for url in mock_device.requested)


async def test_power_control_set_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Setting the power control writes the control.html power endpoint."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_power_elwa_2", ATTR_VALUE: 2500},
        blocking=True,
    )
    assert any("power=2500" in url for url in mock_device.requested)


async def test_timeout_set_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Setting the control value timeout writes setup.jsn with the value."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_control_value_timeout", ATTR_VALUE: 120},
        blocking=True,
    )
    assert any("tout=120" in url for url in mock_device.requested)


async def test_pid_power_set_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """Setting the PID power writes the pid_power control endpoint."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_pid_power_elwa_2", ATTR_VALUE: 2000},
        blocking=True,
    )
    assert any("pid_power=2000" in url for url in mock_device.requested)


async def test_power_control_publishes_written_value(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """The written value is published at once, not only at the next poll."""
    entity_id = f"number.{PREFIX}_power_elwa_2"
    assert hass.states.get(entity_id).state == "1200"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 2500},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "2500"


async def test_power_control_keeps_value_when_write_fails(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A failed write leaves the value the device actually received."""
    entity_id = f"number.{PREFIX}_power_elwa_2"
    mock_device.spec().error = TimeoutError()

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 2500},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "1200"


async def test_pid_power_set_value_without_control_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A control page without a control state is written once, not crashed on."""
    # Some devices/firmwares never yield a "Control State" line, and a control
    # read that has always failed leaves it missing too.
    mock_device.spec().text["/control.html"] = "Power=1200\r\nState=2\r\n"
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_pid_power_elwa_2", ATTR_VALUE: 2000},
        blocking=True,
    )
    assert [url for url in mock_device.requested if "pid_power=" in url] == [
        "/control.html?pid_power=2000"
    ]


async def test_pid_power_set_value_outside_http_control(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Outside HTTP control the value is written once and reported, not retried."""
    mock_device.spec().text["/control.html"] = (
        "Power=0\r\nState=2\r\nControl State=Modbus\r\n"
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = f"number.{PREFIX}_pid_power_elwa_2"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 2000},
        blocking=True,
    )
    assert len([url for url in mock_device.requested if "pid_power=" in url]) == 1
    assert "'Modbus' control" in caplog.text

    # The device keeps discarding the value, but the warning is not repeated --
    # an automation may write several times per second.
    caplog.clear()
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: 1000},
        blocking=True,
    )
    assert len([url for url in mock_device.requested if "pid_power=" in url]) == 2
    assert "discards the value" not in caplog.text


async def test_number_set_value_handles_command_error(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A failing command is swallowed and does not raise."""
    mock_device.spec().error = TimeoutError()

    # Must not raise even though the device call fails.
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: f"number.{PREFIX}_target_temperature", ATTR_VALUE: 60},
        blocking=True,
    )


async def test_reset_energy_service(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The reset_energy_sensor service is registered and runs without error."""
    assert hass.services.has_service(DOMAIN, "reset_energy_sensor")
    await hass.services.async_call(
        DOMAIN,
        "reset_energy_sensor",
        {ATTR_ENTITY_ID: f"sensor.{PREFIX}_energy_consumption"},
        blocking=True,
    )
