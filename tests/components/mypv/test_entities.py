"""Tests for the myPV entities and their states."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import FakeWorld
from .const import MOCK_IP, MOCK_SERIAL

PREFIX = "ac_elwa_2_123456"


async def test_sensor_states(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Sensor values are scaled and translated as expected."""
    # Temperature is reported in tenths of a degree -> scaled by 10.
    temp = hass.states.get(f"sensor.{PREFIX}_temperatur_1")
    assert temp is not None
    assert temp.state == "45.2"

    # Device state enum: control.html State=2 -> "boost_heat" (the raw myPV
    # operation-state value indexes the enum directly; 2 = boost backup).
    control_state = hass.states.get(f"sensor.{PREFIX}_control_state")
    assert control_state is not None
    assert control_state.state == "boost_heat"

    # Non-numeric sensor no longer raises; it keeps its raw string value.
    control_source = hass.states.get(f"sensor.{PREFIX}_control_source")
    assert control_source is not None
    assert control_source.state == "No Control"


async def test_control_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Number, switch, select and binary sensor reflect the device setup."""
    target = hass.states.get(f"number.{PREFIX}_target_temperature")
    assert target is not None
    assert target.state == "50.0"  # ww1target 500 -> /10

    enable = hass.states.get(f"switch.{PREFIX}_enable_device")
    assert enable is not None
    assert enable.state == "on"  # devmode 1

    ctrl_type = hass.states.get(f"select.{PREFIX}_control_type")
    assert ctrl_type is not None
    assert ctrl_type.state == "http"  # ctrl 1 -> "HTTP"

    relais = hass.states.get(f"binary_sensor.{PREFIX}_relais")
    assert relais is not None
    assert relais.state == "on"  # rel1_out 1


async def test_energy_sensor_name_is_translated(
    hass: HomeAssistant,
    mock_device: FakeWorld,
    entity_registry: er.EntityRegistry,
) -> None:
    """Energy sensors resolve their name via translation_key, not _attr_name.

    IntegrationSensor sets an explicit name; unless it is removed Home
    Assistant skips the translation and the name stays English.
    """
    hass.config.language = "de"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MOCK_SERIAL}_Energy consumption"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == "AC ELWA 2 123456 Energieverbrauch"


async def test_diagnostic_sensors_disabled_by_default(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Noisy/redundant sensors are registered but disabled by default."""
    entity_id = f"sensor.{PREFIX}_volt_l1"
    entry = entity_registry.async_get(entity_id)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    # Disabled entities have no state.
    assert hass.states.get(entity_id) is None
