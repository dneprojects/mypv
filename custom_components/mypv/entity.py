"""Base entity for the myPV integration."""

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .communicate import MypvCommunicator
from .const import DOMAIN

if TYPE_CHECKING:
    from .mypv_device import MpyDevice


class MpvEntity(CoordinatorEntity[MypvCommunicator]):
    """Base class shared by all myPV entities.

    Provides the common translation key, unique id and device info wiring so
    the individual platforms only have to deal with their own behaviour. The
    display name is resolved through ``translation_key`` (derived from the
    English name) while the unique id keeps using the raw name for backwards
    compatibility with already registered entities.
    """

    _attr_has_entity_name = True

    def __init__(self, device: MpyDevice, name: str) -> None:
        """Initialize the entity for a myPV device."""
        super().__init__(device.comm)
        self.device = device
        self.comm = device.comm
        self._mpv_name = name
        self._attr_translation_key = slugify(name)
        self._attr_unique_id = f"{device.serial_number}_{name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.serial_number)},
            name=device.name,
            manufacturer="my-PV GmbH",
            model=device.model,
        )

    async def async_added_to_hass(self) -> None:
        """Populate the initial state from the already fetched data.

        The coordinator's first refresh happens before the entities are
        added, so without this the ``_attr_*`` based entities would stay
        ``unknown`` until the next update interval.
        """
        await super().async_added_to_hass()
        self._handle_coordinator_update()
