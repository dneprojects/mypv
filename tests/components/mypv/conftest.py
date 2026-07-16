"""Pytest fixtures for the myPV integration tests.

The integration talks to the device through the my-pv library connection
classes in ``connection.py``; every connection is created via
``create_connection()``. The tests therefore seam at that factory: a
``FakeWorld`` holds one ``DeviceSpec`` per IP and hands out ``FakeConnection``
objects, so no real HTTP (nor the my-pv transport) is ever exercised outside of
``test_connection.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv.connection import (
    MyPVAuthenticationError,
    MyPVConnectionError,
)
from custom_components.mypv.const import CONF_HOSTS, DEV_IP, DOMAIN
from homeassistant.core import HomeAssistant

from .const import CONTROL_HTML, DATA_JSN, MOCK_IP, MOCK_NAME, MYPV_DEV_JSN, SETUP_JSN


@dataclass
class DeviceSpec:
    """Behaviour of one fake myPV device, keyed by IP in the FakeWorld."""

    dev: dict[str, Any] | None = None
    json: dict[str, dict[str, Any]] = field(default_factory=dict)
    text: dict[str, str] = field(default_factory=dict)
    reachable: bool = True
    # Protected reads (setup.jsn/data.jsn) are served over plain HTTP. True for
    # old firmware and encryption modes 0/1; False in mode 2 (HTTP is redirected
    # to HTTPS). ``mypv_dev.jsn`` stays plain-HTTP in every mode regardless.
    http_reads_open: bool = True
    https: bool = False  # device serves HTTPS (new firmware, any encryption mode)
    # setup.jsn's encryption level (0 HTTP / 1 HTTPS / 2 HTTPS+password). None
    # models old firmware without the field; when set it is injected into the
    # setup.jsn payload (drives both detection and the encryption sensor).
    sec_level: int | None = None
    needs_auth: bool = False
    password: str | None = None
    # Protected reads (setup.jsn/data.jsn) require the password on every channel
    # -- models a freshly updated device still locked in its initial state, which
    # answers only mypv_dev.jsn until a password is supplied.
    reads_require_auth: bool = False
    # When set, every get_json/get_text raises this (the device answers
    # identification but not data — models a mid-session drop-out).
    error: Exception | None = None


class FakeConnection:
    """Drop-in for a my-pv library connection, driven by a FakeWorld.

    Implements exactly the surface the integration uses: ``open``/``close``/
    ``is_open``/``mypv_dev`` plus the raw ``get_json``/``get_text`` access added
    by ``connection._RawAccessMixin``.
    """

    def __init__(
        self,
        host: str,
        password: str | None,
        world: FakeWorld,
        *,
        use_https: bool = False,
    ) -> None:
        """Register the connection with its world and start closed."""
        self._host = host
        self._password = password
        self._world = world
        # create_connection() picks HTTPS when use_https or a password is set.
        self._is_https = use_https or password is not None
        self._open = False
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        world.connections.append(self)

    @property
    def _spec(self) -> DeviceSpec | None:
        return self._world.devices.get(self._host)

    async def open(self) -> bool:
        """Open the connection, raising an auth error when the password is wrong."""
        spec = self._spec
        if spec is None or not spec.reachable:
            return False
        if self._is_https:
            if not spec.https:
                return False  # no HTTPS server (old firmware)
            # A password is only checked when one is supplied (mode-2 verify);
            # password-less HTTPS reads stay open in every mode.
            if (
                self._password is not None
                and spec.needs_auth
                and self._password != spec.password
            ):
                raise MyPVAuthenticationError
            self._open = True
            return True
        # Plain HTTP: mypv_dev.jsn (opened here) is served in every mode, so a
        # reachable device always opens over HTTP. Protected reads may still be
        # redirected (mode 2) -- that surfaces in get_json, not here.
        self._open = True
        return True

    async def close(self) -> bool:
        """Mark the connection closed."""
        self.closed = True
        self._open = False
        return True

    def is_open(self) -> bool:
        """Return whether the connection is currently open."""
        return self._open

    @property
    def is_https(self) -> bool:
        """Return whether this connection uses HTTPS transport."""
        return self._is_https

    @property
    def mypv_dev(self) -> dict[str, Any] | None:
        """Return the device identification dict once open."""
        spec = self._spec
        return spec.dev if (self._open and spec is not None) else None

    async def get_json(
        self, path: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Record the request and return the canned JSON payload for ``path``."""
        spec = self._spec
        # Encryption mode 2 redirects protected reads over plain HTTP to HTTPS;
        # the plain-HTTP probe fails. mypv_dev.jsn stays open in every mode.
        if (
            not self._is_https
            and spec is not None
            and not spec.http_reads_open
            and path != "/mypv_dev.jsn"
        ):
            raise MyPVConnectionError
        # A locked device gates protected reads behind the password on every
        # channel; only a connection carrying the right password may read them.
        if (
            spec is not None
            and spec.reads_require_auth
            and path != "/mypv_dev.jsn"
            and self._password != spec.password
        ):
            raise MyPVAuthenticationError
        self._record(path, query)
        payload = self._spec.json[path]
        if path == "/setup.jsn" and spec is not None and spec.sec_level is not None:
            payload = {**payload, "sec_level": spec.sec_level}
        return payload

    async def get_text(self, path: str, query: dict[str, Any] | None = None) -> str:
        """Record the request and return the canned text body for ``path``."""
        self._record(path, query)
        return self._spec.text.get(path, CONTROL_HTML)

    async def send(self, path: str, params: dict[str, Any]) -> str:
        """Record a write and return the canned text body for ``path``."""
        self._record(path, params)
        return self._spec.text.get(path, CONTROL_HTML)

    async def command(self, path: str, params: dict[str, Any]) -> str:
        """Record a control command and return the canned text body for ``path``."""
        self._record(path, params)
        return self._spec.text.get(path, CONTROL_HTML)

    def _record(self, path: str, query: dict[str, Any] | None) -> None:
        self.requests.append((path, dict(query or {})))
        if self._spec is not None and self._spec.error is not None:
            raise self._spec.error


class FakeWorld:
    """Registry of fake devices shared across every connection in a test."""

    def __init__(self) -> None:
        """Start with no devices and no handed-out connections."""
        self.devices: dict[str, DeviceSpec] = {}
        self.connections: list[FakeConnection] = []

    def add(self, ip: str, spec: DeviceSpec) -> None:
        """Register (or replace) the device answering at ``ip``."""
        self.devices[ip] = spec

    def spec(self, ip: str = MOCK_IP) -> DeviceSpec:
        """Return the mutable spec for ``ip`` (defaults to the seeded device)."""
        return self.devices[ip]

    def make(
        self, host: str, password: str | None = None, *, use_https: bool = False
    ) -> FakeConnection:
        """``create_connection`` stand-in."""
        return FakeConnection(host, password, self, use_https=use_https)

    @property
    def requested(self) -> list[str]:
        """All requests as ``path?query`` strings, across every connection."""
        return [
            f"{path}?{urlencode(query)}" if query else path
            for conn in self.connections
            for path, query in conn.requests
        ]


def healthy_spec() -> DeviceSpec:
    """A reachable, no-auth AC ELWA 2 returning the standard payloads."""
    return DeviceSpec(
        dev=MYPV_DEV_JSN,
        json={"/data.jsn": DATA_JSN, "/setup.jsn": SETUP_JSN},
        text={"/control.html": CONTROL_HTML},
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable myPV as a custom integration in every test."""
    return


@pytest.fixture(autouse=True)
def mock_discovery() -> Generator[None]:
    """Stub the UDP discovery so tests never touch the network or sleep."""
    with (
        patch(
            "custom_components.mypv.async_discover_mypv_devices",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "custom_components.mypv.config_flow.async_discover_mypv_devices",
            new=AsyncMock(return_value=[]),
        ),
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a ready-to-add myPV config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"{MOCK_NAME} ({MOCK_IP})",
        unique_id=f"mypv_{MOCK_IP}",
        data={DEV_IP: MOCK_IP, CONF_HOSTS: [MOCK_IP]},
    )


@pytest.fixture
def mock_device() -> Generator[FakeWorld]:
    """Seam ``create_connection`` to a fake world with one healthy device.

    Yields the :class:`FakeWorld`; tests mutate ``world.spec()`` (or ``add`` a
    different device) to model unreachable / auth-protected / dropping devices.
    """
    world = FakeWorld()
    world.add(MOCK_IP, healthy_spec())
    with (
        patch(
            "custom_components.mypv.communicate.create_connection",
            side_effect=world.make,
        ),
        patch(
            "custom_components.mypv.config_flow.create_connection",
            side_effect=world.make,
        ),
    ):
        yield world


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Patch async_setup_entry to isolate config-flow tests from setup."""
    with patch("custom_components.mypv.async_setup_entry", return_value=True) as mock:
        yield mock


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_device: FakeWorld,
) -> MockConfigEntry:
    """Add and set up a myPV config entry, returning the entry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
