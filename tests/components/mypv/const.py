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
    "ctrlstate": "No Control",
    "upd_state": 0,
    "surplus": 0,
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
