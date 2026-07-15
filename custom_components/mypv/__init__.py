"""Integration ELWA myPV."""

import json
import logging

import aiohttp
from my_pv.exceptions import MyPVConnectionError

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.helpers.typing import ConfigType

from .communicate import MypvCommunicator
from .const import COMM_HUB, DEV_IP, DOMAIN
from .discovery import async_discover_mypv_devices

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_RESET_ENERGY = "reset_energy_sensor"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration and launch background discovery."""
    hass.data.setdefault(DOMAIN, {})

    async def _async_run_discovery() -> None:
        """Background task to discover devices via UDP."""
        try:
            devices = await async_discover_mypv_devices()
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("Failed to run myPV UDP discovery: %s", ex)
            return
        for device in devices:
            # Trigger the 'async_step_discovery' in config_flow.py
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_DISCOVERY},
                    data={"ip": device["ip"]},
                )
            )

    # Launch the discovery task without blocking HA startup
    hass.async_create_background_task(_async_run_discovery(), "mypv-discovery")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up myPV from a config entry."""

    async def async_reset_sensor(call: ServiceCall) -> None:
        """Service call handler to reset an energy sensor."""
        entity_ids = await async_extract_entity_ids(call)
        sensor_component = hass.data.get("sensor")
        if not sensor_component:
            _LOGGER.error("Sensor component not loaded")
            return

        for entity_id in entity_ids:
            sensor_entity = sensor_component.get_entity(entity_id)
            if sensor_entity is not None and hasattr(sensor_entity, "async_reset"):
                _LOGGER.debug("Calling async_reset for %s", entity_id)
                await sensor_entity.async_reset()
            else:
                _LOGGER.warning("Entity %s could not be reset", entity_id)

    comm = MypvCommunicator(hass, entry)
    try:
        await comm.initialize()
    except (
        TimeoutError,
        aiohttp.ClientError,
        json.JSONDecodeError,
        MyPVConnectionError,
    ) as ex:
        raise ConfigEntryNotReady(
            f"Error connecting to myPV device at {entry.data[DEV_IP]}"
        ) from ex

    if not comm.devices:
        raise ConfigEntryNotReady(f"No myPV device responded at {entry.data[DEV_IP]}")

    await comm.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {COMM_HUB: comm}

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_ENERGY):
        hass.services.async_register(DOMAIN, SERVICE_RESET_ENERGY, async_reset_sensor)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data is not None:
            await data[COMM_HUB].async_close()

    return unload_ok
