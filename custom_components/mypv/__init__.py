"""Integration ELWA myPV."""

from httpcore import TimeoutException

from homeassistant import config_entries
from homeassistant.components.config import entity_registry
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import _LOGGER, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.service import async_extract_entity_ids

from .communicate import MypvCommunicator
from .const import COMM_HUB, DEV_IP, DOMAIN
from .discovery import async_discover_mypv_devices

# List of platforms to support. There should be a matching .py file for each
PLATFORMS: list[str] = [
    "binary_sensor",
    "button",
    "number",
    "select",
    "sensor",
    "switch",
]


async def async_setup(hass: HomeAssistant, config):
    """Platform setup, do nothing."""
    hass.data.setdefault(DOMAIN, {})

    # Start network scan in the background to find new myPV devices
    async def _async_run_discovery():
        """Background task to discover devices via UDP."""
        try:
            devices = await async_discover_mypv_devices()
            for device in devices:
                # Trigger the 'async_step_discovery' in config_flow.py
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": config_entries.SOURCE_DISCOVERY},
                        data={"ip": device["ip"]},
                    )
                )
        except Exception as ex:
            _LOGGER.error("Failed to run myPV UDP discovery: %s", ex)

    # Launch the discovery task without blocking HA startup
    hass.async_create_background_task(_async_run_discovery(), "mypv-discovery")

    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=dict(config[DOMAIN])
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Load the saved entities."""

    async def async_reset_sensor(call):
        """Service call handler to reset a sensor."""
        entity_ids = await async_extract_entity_ids(hass, call)

        sensor_component = hass.data.get("sensor")
        if not sensor_component:
            _LOGGER.error("Sensor component not loaded")
            return

        # looping all entities
        for entity_id in entity_ids:
            sensor_entity = sensor_component.get_entity(entity_id)

            if sensor_entity and hasattr(sensor_entity, "async_reset"):
                _LOGGER.info("Calling async_reset for %s", entity_id)
                await sensor_entity.async_reset()
            else:
                _LOGGER.warning("Entity %s could not be reset", entity_id)

    hass.services.async_register(DOMAIN, "reset_energy_sensor", async_reset_sensor)

    try:
        comm = MypvCommunicator(hass, entry)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = comm
        await comm.initialize()

        await comm.async_refresh()

        if not comm.last_update_success:
            raise ConfigEntryNotReady(
                f"Update of myPV device at {entry.data[DEV_IP]} failed"
            )

        hass.data[DOMAIN][entry.entry_id] = {
            COMM_HUB: comm,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (TimeoutError, TimeoutException) as ex:
        raise ConfigEntryNotReady(
            f"Timeout while connecting to myPV device at {entry.data[DEV_IP]}"
        ) from ex
    else:
        return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
