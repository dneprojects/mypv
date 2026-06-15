"""Verify every entity translation key (and enum state) exists in strings.json."""

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONTROL_HTML,
    DATA_9S,
    DATA_JSN,
    DATA_SOLTHOR,
    MOCK_IP,
    MYPV_DEV_9S,
    MYPV_DEV_JSN,
    MYPV_DEV_SOLTHOR,
    SETUP_9S,
    SETUP_JSN,
    SETUP_SOLTHOR,
)

ENTITY_STRINGS = json.loads(
    Path("custom_components/mypv/strings.json").read_text(encoding="utf-8")
)["entity"]

MODELS = [
    pytest.param(MYPV_DEV_JSN, DATA_JSN, SETUP_JSN, id="elwa2"),
    pytest.param(MYPV_DEV_9S, DATA_9S, SETUP_9S, id="acthor9s"),
    pytest.param(MYPV_DEV_SOLTHOR, DATA_SOLTHOR, SETUP_SOLTHOR, id="solthor"),
]


@pytest.mark.parametrize(("dev", "data", "setup"), MODELS)
async def test_translation_coverage(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    dev: dict[str, Any],
    data: dict[str, Any],
    setup: dict[str, Any],
) -> None:
    """Every created entity has a name (and states) defined in strings.json."""
    aioclient_mock.get(f"http://{MOCK_IP}/mypv_dev.jsn", json=dev)
    aioclient_mock.get(f"http://{MOCK_IP}/data.jsn", json=data)
    aioclient_mock.get(f"http://{MOCK_IP}/setup.jsn", json=setup)
    aioclient_mock.get(f"http://{MOCK_IP}/control.html?", text=CONTROL_HTML)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert entries

    for registry_entry in entries:
        platform = registry_entry.entity_id.split(".")[0]
        translation_key = registry_entry.translation_key
        assert translation_key, f"{registry_entry.entity_id} has no translation_key"

        platform_strings = ENTITY_STRINGS.get(platform, {})
        assert translation_key in platform_strings, (
            f"missing translation: entity.{platform}.{translation_key}.name"
        )

        state = hass.states.get(registry_entry.entity_id)
        if state is None:
            continue
        options = state.attributes.get("options")
        if options:
            state_strings = platform_strings[translation_key].get("state", {})
            missing = [opt for opt in options if opt not in state_strings]
            assert not missing, (
                f"missing state translations for {platform}.{translation_key}: {missing}"
            )
