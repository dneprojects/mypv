"""Binary sensors of myPV integration."""

import logging
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COMM_HUB, DOMAIN, MpvDescription
from .entity import MpvEntity

if TYPE_CHECKING:
    from .mypv_device import MpyDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add all myPV binary sensor entities."""
    comm = hass.data[DOMAIN][entry.entry_id][COMM_HUB]

    for device in comm.devices:
        async_add_entities(device.binary_sensors)


class MpvBinSensor(MpvEntity, BinarySensorEntity):
    """Representation of a myPV binary sensor."""

    def __init__(
        self,
        device: MpyDevice,
        key: str,
        info: MpvDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(device, info.name)
        self._key = key

    @override
    def _handle_coordinator_update(self) -> None:
        try:
            value = self.device.data[self._key]
        except KeyError, TypeError:
            _LOGGER.warning(
                "Update for %s failed, key %s not found", self.entity_id, self._key
            )
        else:
            self._attr_is_on = self.map_bool_value(value)
            super()._handle_coordinator_update()

    def map_bool_value(self, value: Any) -> bool:
        """Help to map the value to a boolean."""
        match value:
            case "1" | 1 | True:
                return True
            case "0" | 0 | False:
                return False
            case _:
                _LOGGER.warning("Unexpected value for binary sensor: %r", value)
                return False


class MpvBin1Sensor(MpvBinSensor):
    """Representation of a myPV binary sensor for AC-Thor 9s."""

    _digit = 0

    def map_bool_value(self, value: Any) -> bool:
        """Help to map the value to a boolean."""
        if isinstance(value, int):
            str_number = str(value).zfill(4)
        elif isinstance(value, str):
            str_number = str(int(value)).zfill(4)  # Ensure it's zero-padded
        else:
            _LOGGER.warning("Unexpected type for binary sensor value: %r", value)
            return False
        return str_number[self._digit] == "1"


class MpvBin2Sensor(MpvBin1Sensor):
    """Representation of a myPV binary sensor for AC-Thor 9s."""

    _digit = 1


class MpvBin3Sensor(MpvBin1Sensor):
    """Representation of a myPV binary sensor for AC-Thor 9s."""

    _digit = 2
