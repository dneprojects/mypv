"""Tests for the myPV communicator error handling."""

import asyncio
from typing import Self

import pytest
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


async def test_device_io_is_serialized(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All device HTTP I/O is serialized: the device allows one connection.

    A user command (e.g. set_power) overlapping the cyclic poll otherwise opens
    a second connection, which the device refuses ("Connect call failed" on :80).
    """
    comm, _ = _comm_device(hass, setup_integration)

    active = 0
    max_active = 0

    class _Resp:
        async def __aenter__(self) -> Self:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)  # yield so any overlap becomes observable
            return self

        async def __aexit__(self, *exc: object) -> None:
            nonlocal active
            active -= 1

        async def text(self) -> str:
            return "OK"

    class _Session:
        def get(self, url: str, timeout: object = None) -> _Resp:
            return _Resp()

    monkeypatch.setattr(
        "custom_components.mypv.communicate.async_get_clientsession",
        lambda hass: _Session(),
    )

    await asyncio.gather(
        comm.do_get_request("http://x/a"),
        comm.do_get_request("http://x/b"),
        comm.do_get_request("http://x/c"),
    )

    assert max_active == 1


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
