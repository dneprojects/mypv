"""Constants and mock device payloads for the myPV test suite."""

from typing import Any, Final

MOCK_IP: Final = "192.168.1.123"
MOCK_SERIAL: Final = "230100123456"
MOCK_MODEL: Final = "AC ELWA 2"
MOCK_NAME: Final = f"{MOCK_MODEL} 123456"

# Response of http://<ip>/mypv_dev.jsn (device identification).
MYPV_DEV_JSN: Final[dict[str, Any]] = {
    "device": MOCK_MODEL,
    "sn": MOCK_SERIAL,
    "fwversion": "a0001234",
    "number": "123456",
}

# Response of http://<ip>/data.jsn (live values).
DATA_JSN: Final[dict[str, Any]] = {
    "device": MOCK_MODEL,
    "fwversion": "a0001234",
    "fwversionlatest": "a0001234",
    "psversion": "d0005678",
    "psversionlatest": "d0005678",
    "power_elwa2": 1200,
    "temp1": 452,
    "status": 2,
    "rel1_out": 1,
    "load_nom": 3500,
    "volt_mains": 2301,
    "curr_mains": 85,
    "ctrlstate": "No Control",
    "upd_state": 0,
    "surplus": 0,
    "boostactive": 0,
}

# Response of http://<ip>/setup.jsn (configuration values).
SETUP_JSN: Final[dict[str, Any]] = {
    "devmode": 1,
    "bstmode": 0,
    "ww1target": 500,
    "ww1boost": 450,
    "ctrl": 1,
}

# Response of http://<ip>/control.html? (control state, line based).
CONTROL_HTML: Final = "Power=1200\r\nState=2\r\nControl State=HTTP\r\n"

# --- AC-THOR 9s device (exercises split relay outputs + Acthor 9 firmware) ---
MYPV_DEV_9S: Final[dict[str, Any]] = {
    "device": "AC-THOR",
    "acthor9s": 2,
    "sn": "203000999999",
    "fwversion": "a0009999",
    "number": "999999",
}
DATA_9S: Final[dict[str, Any]] = {
    "device": "AC-THOR",
    "acthor9s": 2,
    "fwversion": "a0009999",
    "fwversionlatest": "a0009999",
    "psversion": "d0008888",
    "psversionlatest": "d0008888",
    "p9sversion": "e0007777",
    "p9sversionlatest": "e0007777",
    "power_ac9s": 6000,
    "temp1": 480,
    "status": 2,
    "rel1_out": 101,
    "load_nom": 9000,
    "upd_state": 1,
    "ps_upd_state": 0,
    "p9s_upd_state": 0,
}
SETUP_9S: Final[dict[str, Any]] = {
    "devmode": 1,
    "bstmode": 1,
    "ww1target": 600,
    "ww1boost": 500,
    "ctrl": 2,
}

# --- Solthor device (exercises the offset enums and skipped entities) ---
MYPV_DEV_SOLTHOR: Final[dict[str, Any]] = {
    "device": "Solthor",
    "sn": "141000555555",
    "fwversion": "s0005555",
    "number": "555555",
}
DATA_SOLTHOR: Final[dict[str, Any]] = {
    "device": "Solthor",
    "fwversion": "s0005555",
    "fwversionlatest": "s0005555",
    "power": 1500,
    "temp1": 470,
    "status": 3,
    "upd_state": 2,
}
SETUP_SOLTHOR: Final[dict[str, Any]] = {
    "ww1target": 550,
    "ctrl": 21,
}
