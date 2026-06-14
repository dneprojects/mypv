"""myPV device model."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .binary_sensor import MpvBin1Sensor, MpvBin2Sensor, MpvBin3Sensor, MpvBinSensor
from .button import MpvBoostButton, MpvBoostOffButton
from .const import DOMAIN, SENSOR_TYPES, SETUP_TYPES, MpvDescription
from .number import MpvPidPowerControl, MpvPowerControl, MpvSetupControl, MpvToutControl
from .select import MpvCtrlTypeSelect
from .sensor import (
    MpvDevStatSensor,
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
        self.control_enabled = True

    async def initialize(self) -> None:
        """Get setup information, find sensors."""
        self.setup, self.data = await asyncio.gather(
            self.comm.setup_update(self), self.comm.data_update(self)
        )
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
        data_keys = [key for key in self.data if key not in _IGNORED_DATA_KEYS]

        if self.model != "Solthor":
            self.sensors.append(
                MpvDevStatSensor(
                    self,
                    "control_state",
                    MpvDescription("Control state", None, "sensor"),
                )
            )
        for key, desc in SENSOR_TYPES.items():
            # use only keys included in data with valid values
            if (
                desc.kind
                in (
                    "binary_sensor",
                    "sensor",
                    "version",
                    "ip_string",
                    "upd_stat",
                    "dev_stat",
                    "button",
                    "switch",
                    "control",
                    "text",
                )
                and key in data_keys
                and self.data[key] is not None
                and self.data[key] != "null"
            ):
                self.logger.debug("Sensor Key: %s: %s", key, self.data[key])
                if desc.kind in ("sensor", "text", "ip_string", "version"):
                    self.sensors.append(MpvSensor(self, key, desc))
                elif desc.kind == "dev_stat":
                    self.sensors.append(MpvDevStatSensor(self, key, desc))
                elif desc.kind == "upd_stat":
                    self.sensors.append(MpvUpdateSensor(self, key, desc))
                elif desc.kind == "binary_sensor":
                    if self.model == "AC-THOR 9s" and desc.name == "Relais":
                        self.binary_sensors.append(MpvBin1Sensor(self, key, desc))
                        self.binary_sensors.append(
                            MpvBin2Sensor(self, key, desc._replace(name="Out 3"))
                        )
                        self.binary_sensors.append(
                            MpvBin3Sensor(self, key, desc._replace(name="Out 2"))
                        )
                        self.sensors.append(
                            MpvOutStatSensor(
                                self, key, desc._replace(name="Output status")
                            )
                        )
                    else:
                        self.binary_sensors.append(MpvBinSensor(self, key, desc))
                elif desc.kind == "button" and self.control_enabled:
                    self.buttons.append(MpvBoostButton(self, key, desc))
                    self.buttons.append(
                        MpvBoostOffButton(self, key + "off", SENSOR_TYPES[key + "off"])
                    )
                elif desc.kind == "control":
                    if self.control_enabled:
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
            if desc.kind == "sensor_always":
                # Sensor value might not be available at startup
                self.sensors.append(MpvSensor(self, key, desc))
        for key, desc in SETUP_TYPES.items():
            # use only keys included in setup with valid values
            if (
                desc.kind
                in (
                    "binary_sensor",
                    "button",
                    "ctrl_type",
                    "number",
                    "sensor",
                    "switch",
                    "control",
                )
                and key in self.setup
                and self.setup[key] is not None
                and self.setup[key] != "null"
            ):
                self.logger.debug("Setup Key: %s: %s", key, self.setup[key])
                if desc.kind in ("sensor", "text", "ip_string"):
                    self.sensors.append(MpvSensor(self, key, desc))
                elif desc.kind == "ctrl_type":
                    self.logger.debug("Creating select entity for %s", key)
                    self.selects.append(MpvCtrlTypeSelect(self, key, desc))
                elif desc.kind == "binary_sensor":
                    self.binary_sensors.append(MpvBinSensor(self, key, desc))
                elif desc.kind == "switch":
                    self.switches.append(MpvSetupSwitch(self, key, desc))
                elif desc.kind == "number":
                    self.controls.append(MpvSetupControl(self, key, desc))
        if self.model != "Solthor":
            self.switches.append(MpvHttpSwitch(self, "ctrl"))
            self.controls.append(MpvToutControl(self, "tout"))

    async def update(self) -> None:
        """Update all sensors."""
        for en_sensor in self.energy_sensors:
            await en_sensor.async_update()
        self.data, self.setup = await asyncio.gather(
            self.comm.data_update(self), self.comm.setup_update(self)
        )
        if self.control_enabled and await self.comm.state_update(self):
            if "State" in self.state_dict:
                self.state = int(self.state_dict["State"])
            else:
                self.state = -1
