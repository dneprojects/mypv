"""Tests for the myPV config flow."""

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import MOCK_IP, MOCK_MODEL, MYPV_DEV_JSN


async def test_user_flow_success(
    hass: HomeAssistant,
    mock_device: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
) -> None:
    """A reachable device can be added via the user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{MOCK_MODEL} ({MOCK_IP})"
    assert result["data"] == {DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]}
    assert result["result"].unique_id == f"mypv_{MOCK_IP}"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_device: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
) -> None:
    """An unreachable device shows an error, then recovers."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", exc=TimeoutError())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {DEV_IP: "could_not_connect"}

    # Device becomes reachable -> flow completes.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", json=MYPV_DEV_JSN)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
) -> None:
    """Adding an already configured host is rejected with host_exists."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {DEV_IP: "host_exists"}


async def test_dhcp_discovery_flow(
    hass: HomeAssistant,
    mock_device: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
) -> None:
    """A device discovered via DHCP can be confirmed and added."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip=MOCK_IP, hostname="mypv", macaddress="986d35000000"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]}
    assert result["result"].unique_id == f"mypv_{MOCK_IP}"


async def test_dhcp_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: AiohttpClientMocker,
) -> None:
    """A DHCP discovery for a configured device aborts."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip=MOCK_IP, hostname="mypv", macaddress="986d35000000"),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
