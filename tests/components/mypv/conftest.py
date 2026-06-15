"""Pytest fixtures for the myPV integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.core import HomeAssistant

from .const import CONTROL_HTML, DATA_JSN, MOCK_IP, MOCK_NAME, MYPV_DEV_JSN, SETUP_JSN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable myPV as a custom integration in every test."""
    return


@pytest.fixture(autouse=True)
def mock_discovery() -> Generator[None]:
    """Stub the UDP discovery so tests never touch the network or sleep."""
    with (
        patch(
            "custom_components.mypv.async_discover_mypv_devices",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.mypv.config_flow.async_discover_mypv_devices",
            new=AsyncMock(return_value=[]),
        ),
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a ready-to-add myPV config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"{MOCK_NAME} ({MOCK_IP})",
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]},
    )


@pytest.fixture
def mock_device(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Register the myPV HTTP endpoints with mocked JSON/text responses."""
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", json=MYPV_DEV_JSN)
    aioclient_mock.get(f"http://{MOCK_IP}/data.jsn", json=DATA_JSN)
    aioclient_mock.get(f"http://{MOCK_IP}/setup.jsn", json=SETUP_JSN)
    aioclient_mock.get(f"http://{MOCK_IP}/control.html?", text=CONTROL_HTML)
    return aioclient_mock


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Patch async_setup_entry to isolate config-flow tests from setup."""
    with patch("custom_components.mypv.async_setup_entry", return_value=True) as mock:
        yield mock


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: AiohttpClientMocker,
) -> MockConfigEntry:
    """Add and set up a myPV config entry, returning the entry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
