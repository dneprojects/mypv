"""Tests for the myPV integration setup and unload."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv import async_remove_config_entry_device
from custom_components.mypv.const import COMM_HUB, CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from .conftest import FakeWorld
from .const import MOCK_IP
from .test_entities import PREFIX


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
    mock_device: FakeWorld,
) -> None:
    """An unreachable device results in a setup retry."""
    mock_device.spec().reachable = False
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_data_unreadable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A device that answers identification but not data triggers a retry."""
    # Identification (open/mypv_dev) succeeds; the data fetch then fails.
    mock_device.spec().error = TimeoutError()
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_required_starts_reauth(
    hass: HomeAssistant,
    mock_device: FakeWorld,
) -> None:
    """A stored password the device rejects starts reauth on setup."""
    spec = mock_device.spec()
    spec.https = True
    spec.http_reads_open = False
    spec.needs_auth = True
    spec.password = "correct"

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP], CONF_PASSWORD: "stale"},
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )


async def test_coordinator_update_failure(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_device: FakeWorld,
) -> None:
    """A failed refresh marks the coordinator update as unsuccessful."""
    entry = setup_integration
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]
    assert comm.last_update_success

    mock_device.spec().error = TimeoutError()

    await comm.async_refresh()
    await hass.async_block_till_done()
    assert comm.last_update_success is False


async def test_async_setup_discovery_creates_flow(
    hass: HomeAssistant, mock_device: FakeWorld
) -> None:
    """The background discovery starts a config flow for each device found."""
    with patch(
        "custom_components.mypv.async_discover_mypv_devices",
        new=AsyncMock(return_value=[{"ip": MOCK_IP}]),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert any(flow["handler"] == DOMAIN for flow in flows)


async def test_async_setup_discovery_handles_error(hass: HomeAssistant) -> None:
    """A failing discovery does not break setup."""
    with patch(
        "custom_components.mypv.async_discover_mypv_devices",
        new=AsyncMock(side_effect=OSError("boom")),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()


async def test_reset_service_skips_non_energy_entity(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The reset service resets energy sensors and skips others."""
    # Energy sensor -> has async_reset.
    await hass.services.async_call(
        DOMAIN,
        "reset_energy_sensor",
        {ATTR_ENTITY_ID: f"sensor.{PREFIX}_energy_consumption"},
        blocking=True,
    )
    # Plain sensor -> no async_reset, handled gracefully.
    await hass.services.async_call(
        DOMAIN,
        "reset_energy_sensor",
        {ATTR_ENTITY_ID: f"sensor.{PREFIX}_temperatur_1"},
        blocking=True,
    )


async def test_reset_service_without_sensor_component(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The reset service logs and returns when the sensor platform is absent."""
    hass.data.pop("sensor", None)
    await hass.services.async_call(
        DOMAIN,
        "reset_energy_sensor",
        {ATTR_ENTITY_ID: f"sensor.{PREFIX}_energy_consumption"},
        blocking=True,
    )


async def test_remove_config_entry_device(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A device may always be removed from the config entry."""
    device_registry = dr.async_get(hass)
    device = next(
        device
        for device in device_registry.devices.values()
        if setup_integration.entry_id in device.config_entries
    )
    assert await async_remove_config_entry_device(hass, setup_integration, device)
