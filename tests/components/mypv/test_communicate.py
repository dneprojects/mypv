"""Tests for the myPV communicator error handling."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mypv.communicate import MypvCommunicator
from custom_components.mypv.const import COMM_HUB, DOMAIN
from custom_components.mypv.mypv_device import MpyDevice
from homeassistant.core import HomeAssistant

from .const import MOCK_IP


def _comm_device(
    hass: HomeAssistant, entry: MockConfigEntry
) -> tuple[MypvCommunicator, MpyDevice]:
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]
    return comm, comm.devices[0]


async def test_commands_return_false_on_error(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Every device command returns False (and does not raise) on failure."""
    comm, device = _comm_device(hass, setup_integration)

    aioclient_mock.clear_requests()
    for path in ("setup.jsn", "control.html", "data.jsn"):
        aioclient_mock.get(f"http://{MOCK_IP}/{path}", exc=TimeoutError())

    assert await comm.set_number(device, "ww1target", 500) is False
    assert await comm.set_power(device, 1000) is False
    assert await comm.set_control_mode(device, 1) is False
    assert await comm.set_pid_power(device, 1000) is False
    assert await comm.switch(device, "devmode", True) is False
    assert await comm.activate_boost(device, 1) is False


async def test_state_update_failure_disables_control(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A failing control read disables control mode and returns False."""
    comm, device = _comm_device(hass, setup_integration)
    assert device.control_enabled is True

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{MOCK_IP}/control.html", exc=TimeoutError())

    assert await comm.state_update(device) is False
    assert device.control_enabled is False

    # Once control is disabled, state_update short-circuits to False.
    assert await comm.state_update(device) is False


async def test_check_ip_returns_none_on_error(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """check_ip returns None when the device cannot be reached."""
    comm, _ = _comm_device(hass, setup_integration)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", exc=TimeoutError())

    assert await comm.check_ip(MOCK_IP) is None
