"""Tests for the myPV config flow."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_DISCOVERY, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .conftest import FakeWorld
from .const import MOCK_IP, MOCK_MODEL


async def test_user_flow_success(
    hass: HomeAssistant,
    mock_device: FakeWorld,
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


async def test_user_flow_https_no_password(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """A HTTPS-without-password device (encryption mode 1) stores the ssl flag."""
    spec = mock_device.spec()
    spec.https = True  # new firmware serves HTTPS, no password
    spec.sec_level = 1  # encryption mode 1

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        DEV_IP: MOCK_IP,
        CONF_HOSTS: [MOCK_IP],
        CONF_SSL: True,
    }


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """An unreachable device shows an error, then recovers."""
    mock_device.spec().reachable = False

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {DEV_IP: "could_not_connect"}

    # Device becomes reachable -> flow completes.
    mock_device.spec().reachable = True

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
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


async def test_user_flow_locked_device_requires_password(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """A reachable device whose config is unreadable routes to the password step.

    Models a freshly updated device still locked in its initial state: it answers
    mypv_dev.jsn (so discovery finds it) but gates setup.jsn behind a login on
    every channel, so the encryption mode cannot be read.
    """
    spec = mock_device.spec()
    spec.https = True
    spec.http_reads_open = False  # HTTP reads redirected
    spec.reads_require_auth = True  # HTTPS reads also gated (no sec_level readable)
    spec.needs_auth = True
    spec.password = "devicekey"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    # Not a silent "no myPV device responded": the user is asked for a password.
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "password"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "devicekey"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        DEV_IP: MOCK_IP,
        CONF_HOSTS: [MOCK_IP],
        CONF_PASSWORD: "devicekey",
    }


async def test_user_flow_requires_password(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """Newer firmware that demands a password routes through the password step."""
    spec = mock_device.spec()
    spec.https = True
    spec.http_reads_open = False  # mode 2 redirects protected HTTP reads to HTTPS
    spec.sec_level = 2  # encryption mode 2
    spec.needs_auth = True
    spec.password = "secret"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "password"

    # Wrong password -> shown again with an error.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "password"
    assert result["errors"] == {"base": "invalid_auth"}

    # Correct password -> entry created and password stored.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "secret"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        DEV_IP: MOCK_IP,
        CONF_HOSTS: [MOCK_IP],
        CONF_PASSWORD: "secret",
    }


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """A stored password that stops working can be replaced via reauth."""
    spec = mock_device.spec()
    spec.https = True
    spec.http_reads_open = False
    spec.needs_auth = True
    spec.password = "newpass"

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP], CONF_PASSWORD: "stale"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Wrong password is rejected.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "still-wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    # Correct password updates the entry and aborts successfully.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "newpass"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "newpass"


async def test_dhcp_discovery_flow(
    hass: HomeAssistant,
    mock_device: FakeWorld,
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


async def test_discovery_flow(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """A device found by the background scanner can be confirmed and added."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DISCOVERY}, data={"ip": MOCK_IP}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]}


async def test_discovery_cannot_connect(
    hass: HomeAssistant, mock_device: FakeWorld
) -> None:
    """A discovery for an unreachable device aborts."""
    mock_device.spec().reachable = False

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DISCOVERY}, data={"ip": MOCK_IP}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
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


async def test_dhcp_cannot_connect(
    hass: HomeAssistant, mock_device: FakeWorld
) -> None:
    """A DHCP discovery for an unreachable device aborts."""
    mock_device.spec().reachable = False

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip=MOCK_IP, hostname="mypv", macaddress="986d35000000"),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_confirm_cannot_connect(
    hass: HomeAssistant,
    mock_device: FakeWorld,
) -> None:
    """If the device drops out before confirmation, the flow aborts."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DISCOVERY}, data={"ip": MOCK_IP}
    )
    assert result["step_id"] == "confirm"

    mock_device.spec().reachable = False

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_user_flow_with_discovered_devices(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """The user step offers discovered devices and adds the chosen one."""
    with patch(
        "custom_components.mypv.config_flow.async_discover_mypv_devices",
        new=AsyncMock(return_value=[{"ip": MOCK_IP, "host": "AC ELWA 2"}]),
    ):
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
    assert result["data"] == {DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]}


async def test_user_flow_unnamed_device(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    mock_setup_entry: AsyncMock,
) -> None:
    """A device that reports no name falls back to the generic title."""
    mock_device.spec().dev = {"sn": "x", "fwversion": "y"}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {DEV_IP: MOCK_IP}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"myPV ({MOCK_IP})"
