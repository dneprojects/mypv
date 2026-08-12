"""myPV device model."""

from collections.abc import Callable
from datetime import tzinfo
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import UnitOfTime
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .binary_sensor import MpvBin1Sensor, MpvBin2Sensor, MpvBin3Sensor, MpvBinSensor
from .button import MpvBoostButton, MpvBoostOffButton
from .const import DOMAIN, SENSOR_TYPES, SETUP_TYPES, MpvDescription
from .number import MpvPidPowerControl, MpvPowerControl, MpvSetupControl
from .select import MpvCtrlTypeSelect
from .sensor import (
    MpvDevStatSensor,
    MpvEncSensor,
    MpvEnergyDailySensor,
    MpvEnergyMonthlySensor,
    MpvEnergySensor,
    MpvOutStatSensor,
    MpvSensor,
    MpvUpdateSensor,
)
from .switch import MpvHttpSwitch, MpvSetupSwitch

if TYPE_CHECKING:
    from .communicate import MypvCommunicator

_LOGGER = logging.getLogger(__name__)

# data.jsn keys that never map to an entity.
_IGNORED_DATA_KEYS = (
    "device",
    "fwversionlatest",
    "psversionlatest",
    "p9sversionlatest",
    "fsetup",
    "date",
    "loctime",
    "unixtime",
    "wifi_list",
    "freq",
)


def _reports(values: dict[str, Any], key: str) -> bool:
    """Return whether the device sends a usable value for this key.

    A key the device does not know is absent; one it knows but has no value for
    comes back as ``None`` or the string ``"null"``. Either way there is nothing
    to build an entity on.
    """
    value = values.get(key)
    return value is not None and value != "null"


class MpyDevice:
    """Representation of a single myPV device behind the coordinator."""

    def __init__(self, comm: MypvCommunicator, ip: str, info: dict[str, Any]) -> None:
        """Initialize the device."""
        self.comm = comm
        self._hass = comm.hass
        assert comm.config_entry is not None
        self._entry = comm.config_entry
        self._ip = ip
        self._id = info.get("number", info["sn"])
        self.serial_number = info["sn"]
        self.fw = info["fwversion"]
        self.model = info["device"]
        if info.get("acthor9s") == 2:
            self.model += " 9s"
        self._name = f"{self.model} {self._id}"
        self.state = 0
        self.setup: dict[str, Any] = {}
        self.data: dict[str, Any] = {}
        self.sensors: list[SensorEntity] = []
        self.binary_sensors: list[BinarySensorEntity] = []
        self.controls: list[NumberEntity] = []
        self.buttons: list[ButtonEntity] = []
        self.switches: list[SwitchEntity] = []
        self.selects: list[SelectEntity] = []
        self.energy_sensors: list[MpvEnergySensor] = []
        self.state_dict: dict[str, str] = {}
        self.pid_power: float = 0
        self.pid_power_set = 0
        self.logger = _LOGGER
        # ``control.html`` health. Consecutive failures back the read off (see
        # ``MypvCommunicator.state_update``) but never disable it for good, and
        # they never decide which entities exist -- that is the device's own
        # capability, read from the ``data.jsn`` keys.
        self.control_failures = 0
        self.control_skip = 0
        # Polls left before ``setup.jsn`` is read again; 0 means "read now".
        self.setup_skip = 0

    async def initialize(self) -> None:
        """Get setup information, find sensors."""
        # Fetch sequentially: the myPV web server serves one connection at a
        # time, so concurrent requests collide and make setup look unreachable.
        self.setup = await self.comm.setup_update(self)
        self.data = await self.comm.data_update(self)
        dr.async_get(self._hass).async_get_or_create(
            config_entry_id=self._entry.entry_id,
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer="my-PV GmbH",
            name=self._name,
            model=self.model,
            sw_version=self.fw,
            hw_version=self.serial_number,
        )
        await self.comm.state_update(self)
        await self.init_entities()

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def ip(self) -> str:
        """Return the ip address of the device."""
        return self._ip

    async def init_entities(self) -> None:
        """Take sensors from data and init HA sensors."""
        tz = await dt_util.async_get_time_zone(self.comm.hass.config.time_zone)

        if self.model != "Solthor":
            self.sensors.append(
                MpvDevStatSensor(
                    self,
                    "control_state",
                    MpvDescription("Control state", None, "sensor"),
                )
            )

        # ``kind`` -> the collection the entity joins and the class to build.
        # Only for keys that stand for exactly one entity; the ones that stand
        # for several are in ``bundles`` below, and a kind in neither table is
        # not exposed at all.
        data_entities: dict[str, tuple[list[Any], type[Any]]] = {
            "sensor": (self.sensors, MpvSensor),
            "text": (self.sensors, MpvSensor),
            "ip_string": (self.sensors, MpvSensor),
            "version": (self.sensors, MpvSensor),
            "dev_stat": (self.sensors, MpvDevStatSensor),
            "upd_stat": (self.sensors, MpvUpdateSensor),
        }
        bundles: dict[str, Callable[[str, MpvDescription], None]] = {
            "binary_sensor": self._add_binary_sensor,
            "button": self._add_boost_buttons,
            "control": lambda key, desc: self._add_power_controls(key, desc, tz),
        }
        setup_entities: dict[str, tuple[list[Any], type[Any]]] = {
            "sensor": (self.sensors, MpvSensor),
            "text": (self.sensors, MpvSensor),
            "ip_string": (self.sensors, MpvSensor),
            "binary_sensor": (self.binary_sensors, MpvBinSensor),
            "ctrl_type": (self.selects, MpvCtrlTypeSelect),
            "enc_stat": (self.sensors, MpvEncSensor),
            "switch": (self.switches, MpvSetupSwitch),
            "number": (self.controls, MpvSetupControl),
        }

        for key, desc in SENSOR_TYPES.items():
            if desc.kind == "sensor_always":
                # Sensor value might not be available at startup, so this one is
                # created without asking whether the device reports it yet.
                self.sensors.append(MpvSensor(self, key, desc))
                continue
            # use only keys included in data with valid values
            if key in _IGNORED_DATA_KEYS or not _reports(self.data, key):
                continue
            self.logger.debug("Sensor Key: %s: %s", key, self.data[key])
            if (target := data_entities.get(desc.kind)) is not None:
                collection, entity_cls = target
                collection.append(entity_cls(self, key, desc))
            elif (add_bundle := bundles.get(desc.kind)) is not None:
                add_bundle(key, desc)

        for key, desc in SETUP_TYPES.items():
            # use only keys included in setup with valid values
            if not _reports(self.setup, key):
                continue
            if (target := setup_entities.get(desc.kind)) is None:
                continue
            self.logger.debug("Setup Key: %s: %s", key, self.setup[key])
            collection, entity_cls = target
            collection.append(entity_cls(self, key, desc))

        if self.model != "Solthor":
            self.switches.append(MpvHttpSwitch(self, "ctrl"))
            # Unlike the table-driven settings this one is created whether or
            # not the device reports it: some models only send ``tout`` once it
            # has been written, and the entity has to exist to write it.
            self.controls.append(
                MpvSetupControl(
                    self,
                    "tout",
                    MpvDescription(
                        "Control Value Timeout", UnitOfTime.SECONDS, "number"
                    ),
                )
            )

    def _add_binary_sensor(self, key: str, desc: MpvDescription) -> None:
        """Add the relay entities, which an AC-THOR 9s splits into its outputs."""
        if self.model != "AC-THOR 9s" or desc.name != "Relais":
            self.binary_sensors.append(MpvBinSensor(self, key, desc))
            return
        self.binary_sensors.append(MpvBin1Sensor(self, key, desc))
        self.binary_sensors.append(
            MpvBin2Sensor(self, key, desc._replace(name="Out 3"))
        )
        self.binary_sensors.append(
            MpvBin3Sensor(self, key, desc._replace(name="Out 2"))
        )
        self.sensors.append(
            MpvOutStatSensor(self, key, desc._replace(name="Output status"))
        )

    def _add_boost_buttons(self, key: str, desc: MpvDescription) -> None:
        """Add the start/stop pair a single boost key stands for."""
        self.buttons.append(MpvBoostButton(self, key, desc))
        self.buttons.append(
            MpvBoostOffButton(self, key + "off", SENSOR_TYPES[key + "off"])
        )

    def _add_power_controls(
        self, key: str, desc: MpvDescription, tz: tzinfo | None
    ) -> None:
        """Add both controls, the reading and the energy meters of a power key."""
        self.controls.append(MpvPowerControl(self, key, desc))
        self.controls.append(MpvPidPowerControl(self, key, desc))
        # Setup as sensor, too
        self.sensors.append(MpvSensor(self, key, desc))  # power
        for prefix, energy_cls in (
            ("int", MpvEnergySensor),
            ("intm", MpvEnergyMonthlySensor),
            ("intd", MpvEnergyDailySensor),
        ):
            energy = energy_cls(
                self,
                f"{prefix}_{key}",
                SENSOR_TYPES[f"{prefix}_{key}"],
                desc,
                tz,
            )
            self.sensors.append(energy)
            self.energy_sensors.append(energy)

    async def update(self) -> None:
        """Update all sensors."""
        for en_sensor in self.energy_sensors:
            await en_sensor.async_update()
        # Fetch sequentially: the myPV web server serves one connection at a
        # time, so concurrent requests collide and time out — which would flip
        # every entity to "unknown" on each failing cycle.
        self.data = await self.comm.data_update(self)
        # ``setup.jsn`` is configuration, not measurement: reading it every
        # cycle tripled the request count against a device that serves one
        # connection at a time. A write that changes it resets the counter, so
        # the UI still confirms a user's change on the next poll.
        if self.setup_skip > 0:
            self.setup_skip -= 1
        else:
            self.setup = await self.comm.setup_update(self)
        if await self.comm.state_update(self):
            if "State" in self.state_dict:
                self.state = int(self.state_dict["State"])
            else:
                self.state = -1
