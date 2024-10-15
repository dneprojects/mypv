"""myPV integration."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .binary_sensor import MpvBinSensor
from .const import DOMAIN, SENSOR_TYPES
from .number import MpvPowerControl3500
from .sensor import MpvDevStatSensor, MpvSensor, MpvUpdateSensor
from .switch import MpvPidControlSwitch, MpvSwitch

# from .text import MpvTxtSensor

_LOGGER = logging.getLogger(__name__)


class MpyDevice(CoordinatorEntity):
    """Class definition of an myPV device."""

    def __init__(self, comm, ip, info) -> None:
        """Initialize the sensor."""
        super().__init__(comm)
        self._hass: HomeAssistant = comm.hass
        self._entry = comm.config_entry
        self._info = info
        self._ip = ip
        self._id = info["number"]
        self.comm = comm
        self.serial_number = info["sn"]
        self.fw = info["fwversion"]
        self.model = info["device"]
        self._name = f"{self.model} {self._id}"
        self.state = 0
        self.setup = []
        self.data = []
        self.sensors = []
        self.binary_sensors = []
        self.controls = []
        self.switches = []
        self.text_sensors = []
        self.state_dict = {}
        self.max_power = 3600
        self.pid_power = 0
        self.pid_power_set = 0
        self.logger = _LOGGER

    async def initialize(self):
        """Get setup information, find sensors."""
        self.setup = await self.comm.setup_update(self)
        self.data = await self.comm.data_update(self)
        await self.init_sensors()
        dr.async_get(self._hass).async_get_or_create(
            config_entry_id=self._entry.entry_id,
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer="my-PV GmbH",
            name=self._name,
            model=self.model,
            sw_version=self.fw,
            hw_version=self.serial_number,
        )

    @property
    def unique_id(self):
        """Return unique id based on device serial."""
        return self.serial_number

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def ip(self):
        """Return the ip address of the device."""
        return self._ip

    async def init_sensors(self):
        """Take sensors from data and init HA sensors."""
        data_keys = list(self.data.keys())
        defined_keys = list(SENSOR_TYPES.keys())
        data_keys.remove("device")
        data_keys.remove("fwversion")
        data_keys.remove("psversion")
        data_keys.remove("coversion")
        data_keys.remove("fsetup")
        data_keys.remove("date")
        data_keys.remove("loctime")
        data_keys.remove("unixtime")
        data_keys.remove("screen_mode_flag")
        data_keys.remove("wifi_list")
        self.sensors.append(
            MpvDevStatSensor(self, "control_state", ["Control state", None, "sensor"])
        )
        for key in defined_keys:
            # use only keys included in data with valid values
            if (
                SENSOR_TYPES[key][2]
                in [
                    "binary_sensor",
                    "sensor",
                    "version",
                    "ip_string",
                    "upd_stat",
                    "dev_stat",
                    "switch",
                    "control",
                    "text",
                ]
                and key in data_keys
                and self.data[key] is not None
                and self.data[key] != "null"
            ):
                self.logger.info(f"Sensor Key: {key}: {self.data[key]}")  # noqa: G004
                if SENSOR_TYPES[key][2] in ["sensor", "text", "ip_string", "version"]:
                    self.sensors.append(MpvSensor(self, key, SENSOR_TYPES[key]))
                elif SENSOR_TYPES[key][2] in ["dev_stat"]:
                    self.sensors.append(MpvDevStatSensor(self, key, SENSOR_TYPES[key]))
                elif SENSOR_TYPES[key][2] in ["upd_stat"]:
                    self.sensors.append(MpvUpdateSensor(self, key, SENSOR_TYPES[key]))
                elif SENSOR_TYPES[key][2] in ["binary_sensor"]:
                    self.binary_sensors.append(
                        MpvBinSensor(self, key, SENSOR_TYPES[key])
                    )
                elif SENSOR_TYPES[key][2] in ["switch"]:
                    self.switches.append(MpvSwitch(self, key, SENSOR_TYPES[key]))
                elif SENSOR_TYPES[key][2] in ["control"]:
                    self.controls.append(
                        MpvPowerControl3500(self, key, SENSOR_TYPES[key])
                    )
                    # PID controller is turned on, control power by itself
                    self.switches.append(
                        MpvPidControlSwitch(self, key, SENSOR_TYPES[key])
                    )

    async def update(self):
        """Update all sensors."""
        resp = await self.comm.data_update(self)
        if resp:
            self.data = resp
        if await self.comm.state_update(self):
            self.state = int(self.state_dict["State"])
