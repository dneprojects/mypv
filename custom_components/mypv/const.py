"""Constants for the myPV integration."""

from typing import NamedTuple

from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

DOMAIN = "mypv"

COMM_HUB = "mpv_comm"

CONF_HOSTS = "conf_hosts"
DEV_IP = "dev_ip"


class MpvDescription(NamedTuple):
    """Static description of a myPV data point.

    name: Friendly (English) name used for the entity and unique id.
    unit: Unit of measurement, or None.
    kind: Discriminator selecting the entity platform/behaviour.
    """

    name: str
    unit: str | None
    kind: str


SENSOR_TYPES: dict[str, MpvDescription] = {
    "device": MpvDescription("Device", None, "text"),
    "acthor9s": MpvDescription("Acthor 9s", None, "text"),
    "fwversion": MpvDescription("Control Unit Fw Version", None, "version"),
    "psversion": MpvDescription("Power Unit Fw Version", None, "version"),
    "p9sversion": MpvDescription("Power Unit Fw Version Acthor 9", None, "version"),
    "screen_mode_flag": MpvDescription("Screen mode", None, "sensor"),
    "status": MpvDescription("Status", None, "dev_stat"),
    "power": MpvDescription("Power", UnitOfPower.WATT, "control"),
    "power_elwa2": MpvDescription("Power ELWA-2", UnitOfPower.WATT, "control"),
    "power_ac9": MpvDescription("Power AC9", UnitOfPower.WATT, "control"),
    "power_ac9s": MpvDescription("Power AC9s", UnitOfPower.WATT, "control"),
    "power_act": MpvDescription("Power", UnitOfPower.WATT, "control"),
    "power_max": MpvDescription("Power max", UnitOfPower.WATT, "sensor"),
    "int_power": MpvDescription(
        "Energy consumption", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "int_power_elwa2": MpvDescription(
        "Energy consumption", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "int_power_ac9": MpvDescription(
        "Energy consumption", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "int_power_ac9s": MpvDescription(
        "Energy consumption", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "int_power_act": MpvDescription(
        "Energy consumption", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intd_power": MpvDescription(
        "Energy consumption daily", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intd_power_elwa2": MpvDescription(
        "Energy consumption daily", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intd_power_ac9": MpvDescription(
        "Energy consumption daily", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intd_power_ac9s": MpvDescription(
        "Energy consumption daily", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intd_power_act": MpvDescription(
        "Energy consumption daily", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intm_power": MpvDescription(
        "Energy consumption monthly", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intm_power_elwa2": MpvDescription(
        "Energy consumption monthly", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intm_power_ac9": MpvDescription(
        "Energy consumption monthly", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intm_power_ac9s": MpvDescription(
        "Energy consumption monthly", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "intm_power_act": MpvDescription(
        "Energy consumption monthly", UnitOfEnergy.KILO_WATT_HOUR, "sensor"
    ),
    "power_solar": MpvDescription("Power Solar", UnitOfPower.WATT, "sensor"),
    "power_grid": MpvDescription("Power Grid", UnitOfPower.WATT, "sensor"),
    "boostpower": MpvDescription("Boost Power", UnitOfPower.WATT, "sensor"),
    "power_solar_act": MpvDescription("Power from solar", UnitOfPower.WATT, "sensor"),
    "power_grid_act": MpvDescription("Power from grid", UnitOfPower.WATT, "sensor"),
    "power_solar_ac9": MpvDescription(
        "Power from solar Acthor 9", UnitOfPower.WATT, "sensor"
    ),
    "power_grid_ac9": MpvDescription(
        "Power from grid Acthor 9", UnitOfPower.WATT, "sensor"
    ),
    "power1_solar": MpvDescription("power1_solar", UnitOfPower.WATT, "sensor"),
    "power1_grid": MpvDescription("power1_grid", UnitOfPower.WATT, "sensor"),
    "power2_solar": MpvDescription("power2_solar", UnitOfPower.WATT, "sensor"),
    "power2_grid": MpvDescription("power2_grid", UnitOfPower.WATT, "sensor"),
    "power3_solar": MpvDescription("power3_solar", UnitOfPower.WATT, "sensor"),
    "power3_grid": MpvDescription("power3_grid", UnitOfPower.WATT, "sensor"),
    "load_state": MpvDescription("load_state", None, "sensor"),
    "load_nom": MpvDescription("load_nom", UnitOfPower.WATT, "sensor"),
    "rel1_out": MpvDescription("Relais", None, "binary_sensor"),
    "relay_boost": MpvDescription("Boost relais", None, "binary_sensor"),
    "relay_alarm": MpvDescription("Alarm relais", None, "binary_sensor"),
    "ww1target": MpvDescription(
        "Target temperature", UnitOfTemperature.CELSIUS, "sensor"
    ),
    "temp1": MpvDescription("Temperatur 1", UnitOfTemperature.CELSIUS, "sensor"),
    "temp2": MpvDescription("Temperatur 2", UnitOfTemperature.CELSIUS, "sensor"),
    "temp3": MpvDescription("Temperatur 3", UnitOfTemperature.CELSIUS, "sensor"),
    "temp4": MpvDescription("Temperatur 4", UnitOfTemperature.CELSIUS, "sensor"),
    "boostactive": MpvDescription("Start Boost", None, "button"),
    "boostactiveoff": MpvDescription("Stop Boost", None, "button"),
    "legboostnext": MpvDescription("legboostnext", None, "sensor"),
    "date": MpvDescription("Date", None, "sensor"),
    "loctime": MpvDescription("Loctime", None, "sensor"),
    "unixtime": MpvDescription("Unix time", None, "sensor"),
    "wp_flag": MpvDescription("wp_flag", None, "binary_sensor"),
    "wp_time1_ctr": MpvDescription("wp_time1_ctr", None, "sensor"),
    "wp_time2_ctr": MpvDescription("wp_time2_ctr", None, "sensor"),
    "wp_time3_ctr": MpvDescription("wp_time3_ctr", None, "sensor"),
    "pump_pwm": MpvDescription("Pump PWM", None, "sensor"),
    "schicht_flag": MpvDescription("Schicht", None, "binary_sensor"),
    "act_night_flag": MpvDescription("Night flag", None, "binary_sensor"),
    "ctrlstate": MpvDescription("Control source", None, "sensor"),
    "blockactive": MpvDescription("Block active", None, "binary_sensor"),
    "error_state": MpvDescription("Error state", None, "sensor"),
    "meter1_id": MpvDescription("meter1_id", None, "sensor"),
    "meter1_ip": MpvDescription("meter1_ip", None, "sensor"),
    "meter2_id": MpvDescription("meter2_id", None, "sensor"),
    "meter2_ip": MpvDescription("meter2_ip", None, "sensor"),
    "meter3_id": MpvDescription("meter3_id", None, "sensor"),
    "meter3_ip": MpvDescription("meter3_ip", None, "sensor"),
    "meter4_id": MpvDescription("meter4_id", None, "sensor"),
    "meter4_ip": MpvDescription("meter4_ip", None, "sensor"),
    "meter5_id": MpvDescription("meter5_id", None, "sensor"),
    "meter5_ip": MpvDescription("meter5_ip", None, "sensor"),
    "meter6_id": MpvDescription("meter6_id", None, "sensor"),
    "meter6_ip": MpvDescription("meter6_ip", None, "sensor"),
    "surplus": MpvDescription("Surplus", None, "sensor_always"),
    "m0sum": MpvDescription("m0sum", None, "sensor"),
    "m0l1": MpvDescription("m0l1", None, "sensor"),
    "m0l2": MpvDescription("m0l2", None, "sensor"),
    "m0l3": MpvDescription("m0l3", None, "sensor"),
    "m0bat": MpvDescription("m0bat", None, "sensor"),
    "m1sum": MpvDescription("m1sum", None, "sensor"),
    "m1l1": MpvDescription("m1l1", None, "sensor"),
    "m1l2": MpvDescription("m1l2", None, "sensor"),
    "m1l3": MpvDescription("m1l3", None, "sensor"),
    "m1devstate": MpvDescription("m1devstate", None, "sensor"),
    "m2sum": MpvDescription("m2sum", None, "sensor"),
    "m2l1": MpvDescription("m2l1", None, "sensor"),
    "m2l2": MpvDescription("m2l2", None, "sensor"),
    "m2l3": MpvDescription("m2l3", None, "sensor"),
    "m2soc": MpvDescription("m2soc", None, "sensor"),
    "m2state": MpvDescription("m2state", None, "sensor"),
    "m2devstate": MpvDescription("m2devstate", None, "sensor"),
    "m3sum": MpvDescription("m3sum", None, "sensor"),
    "m3l1": MpvDescription("m3l1", None, "sensor"),
    "m3l2": MpvDescription("m3l2", None, "sensor"),
    "m3l3": MpvDescription("m3l3", None, "sensor"),
    "m3soc": MpvDescription("m3soc", None, "sensor"),
    "m3devstate": MpvDescription("m3devstate", None, "sensor"),
    "m4sum": MpvDescription("m4sum", None, "sensor"),
    "m4l1": MpvDescription("m4l1", None, "sensor"),
    "m4l2": MpvDescription("m4l2", None, "sensor"),
    "m4l3": MpvDescription("m4l3", None, "sensor"),
    "m4devstate": MpvDescription("m4devstate", None, "sensor"),
    "ecarstate": MpvDescription("ecarstate", None, "sensor"),
    "ecarboostctr": MpvDescription("ecarboostctr", None, "sensor"),
    "mss2": MpvDescription("mss2", None, "sensor"),
    "mss3": MpvDescription("mss3", None, "sensor"),
    "mss4": MpvDescription("mss4", None, "sensor"),
    "mss5": MpvDescription("mss5", None, "sensor"),
    "mss6": MpvDescription("mss6", None, "sensor"),
    "mss7": MpvDescription("mss7", None, "sensor"),
    "mss8": MpvDescription("mss8", None, "sensor"),
    "mss9": MpvDescription("mss9", None, "sensor"),
    "mss10": MpvDescription("mss10", None, "sensor"),
    "mss11": MpvDescription("mss11", None, "sensor"),
    "volt_mains": MpvDescription("Volt L1", UnitOfElectricPotential.VOLT, "sensor"),
    "curr_mains": MpvDescription("Current L1", UnitOfElectricCurrent.AMPERE, "sensor"),
    "volt_L2": MpvDescription("Volt L2", UnitOfElectricPotential.VOLT, "sensor"),
    "curr_L2": MpvDescription("Current L2", UnitOfElectricCurrent.AMPERE, "sensor"),
    "volt_L3": MpvDescription("Volt L3", UnitOfElectricPotential.VOLT, "sensor"),
    "curr_L3": MpvDescription("Current L3", UnitOfElectricCurrent.AMPERE, "sensor"),
    "volt_out": MpvDescription("Volt out", UnitOfElectricPotential.VOLT, "sensor"),
    "freq": MpvDescription("Frequency", UnitOfFrequency.HERTZ, "sensor"),
    "temp_ps": MpvDescription("Temp Power Unit", UnitOfTemperature.CELSIUS, "sensor"),
    "fan_speed": MpvDescription("Fan speed", None, "sensor"),
    "ps_state": MpvDescription("Power supply state", None, "sensor"),
    "cur_ip": MpvDescription("IP", None, "ip_string"),
    "cur_sn": MpvDescription("Subnet mask", None, "ip_string"),
    "cur_gw": MpvDescription("Gateway", None, "ip_string"),
    "cur_dns": MpvDescription("DNS", None, "ip_string"),
    "fwversionlatest": MpvDescription(
        "latest Control Unit Fw Version", None, "version"
    ),
    "psversionlatest": MpvDescription("latest Power Unit Fw Version", None, "version"),
    "p9sversionlatest": MpvDescription(
        "latest Power Unit Fw Version Acthor 9", None, "version"
    ),
    "upd_state": MpvDescription("Control Unit Update State", None, "upd_stat"),
    "upd_files_left": MpvDescription("Update files left", None, "sensor"),
    "ps_upd_state": MpvDescription("Power Unit Update State", None, "upd_stat"),
    "p9s_upd_state": MpvDescription(
        "Acthor 9 Power Unit Update State", None, "upd_stat"
    ),
    "volt_solar": MpvDescription("Volt solar", UnitOfElectricPotential.VOLT, "sensor"),
}
SETUP_TYPES: dict[str, MpvDescription] = {
    "devmode": MpvDescription("Enable Device", None, "switch"),
    "bstmode": MpvDescription("Enable Boost Mode", None, "switch"),
    "ww1target": MpvDescription("Target Temperature", None, "number"),
    "ww1boost": MpvDescription("Boost Min Temperature", None, "number"),
    "ctrl": MpvDescription("Control type", None, "ctrl_type"),
    "sec_level": MpvDescription("Encryption", None, "enc_stat"),
}
