"""Tests for the myPV integration setup and unload."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mypv.const import COMM_HUB, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import MOCK_IP


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A reachable device loads and unloads cleanly."""
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_cannot_connect(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """An unreachable device results in a setup retry."""
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", exc=TimeoutError())
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_coordinator_update_failure(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A failed refresh marks the coordinator update as unsuccessful."""
    entry = setup_integration
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]
    assert comm.last_update_success

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{MOCK_IP}/data.jsn", exc=TimeoutError())
    aioclient_mock.get(f"http://{MOCK_IP}/setup.jsn", exc=TimeoutError())

    await comm.async_refresh()
    await hass.async_block_till_done()
    assert comm.last_update_success is False
