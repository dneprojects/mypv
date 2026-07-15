"""Unit tests for the raw transport in ``connection.py``.

Unlike the rest of the suite (which seams at ``create_connection``), these
exercise the real ``MypvHttpConnection`` against a mocked aiohttp session, so
the ``_RawAccessMixin`` request handling — query encoding, JSON parsing, the
401 → auth-error path, connection-error mapping and the per-device
serialisation lock — is covered directly.
"""

import asyncio
from typing import Self
from unittest.mock import AsyncMock

from aiohttp.client_exceptions import ClientConnectionError
from my_pv.exceptions import MyPVAuthenticationError, MyPVConnectionError
import pytest

from custom_components.mypv.connection import (
    MypvHttpConnection,
    MypvHttpsConnection,
    create_connection,
)


class _Tracker:
    """Records maximum in-flight body reads to prove serialisation."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0


class _FakeResponse:
    """Async-context-manager stand-in for an aiohttp response."""

    def __init__(
        self,
        *,
        status: int = 200,
        body: str = "OK",
        enter_exc: Exception | None = None,
        tracker: _Tracker | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._enter_exc = enter_exc
        self._tracker = tracker
        self.released = False

    async def __aenter__(self) -> Self:
        if self._enter_exc is not None:
            raise self._enter_exc
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.released = True
        return False

    async def text(self) -> str:
        if self._tracker is not None:
            self._tracker.active += 1
            self._tracker.max_active = max(
                self._tracker.max_active, self._tracker.active
            )
            await asyncio.sleep(0)  # yield so any overlap becomes observable
            self._tracker.active -= 1
        return self._body


class _FakeSession:
    """Returns a pre-built (or freshly built) response per ``get`` call."""

    def __init__(self, response_factory) -> None:
        self._factory = response_factory
        self.calls: list[tuple[str, object]] = []
        self.responses: list[_FakeResponse] = []
        self.closed = False  # queried by the library's is_open()

    def get(self, url: str, ssl: object = None) -> _FakeResponse:
        self.calls.append((url, ssl))
        response = self._factory()
        self.responses.append(response)
        return response


def _connection(session: _FakeSession) -> MypvHttpConnection:
    """A real connection wired to a fake session, without opening the network."""
    conn = MypvHttpConnection("1.2.3.4")
    conn._session = session  # inject the transport under test
    conn.open = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return conn


def test_create_connection_picks_transport_by_password() -> None:
    """No password -> plain HTTP; a password -> authenticated HTTPS."""
    assert isinstance(create_connection("1.2.3.4", None), MypvHttpConnection)
    assert isinstance(create_connection("1.2.3.4", "secret"), MypvHttpsConnection)


async def test_get_json_parses_body() -> None:
    """get_json returns the parsed JSON of a 200 response."""
    session = _FakeSession(lambda: _FakeResponse(body='{"temp1": 452}'))
    conn = _connection(session)

    assert await conn.get_json("/data.jsn") == {"temp1": 452}
    assert session.calls[0][0] == "http://1.2.3.4/data.jsn"


async def test_get_text_returns_body_and_encodes_query() -> None:
    """get_text returns the raw body and encodes the query string."""
    session = _FakeSession(lambda: _FakeResponse(body="Power=1200"))
    conn = _connection(session)

    assert await conn.get_text("/setup.jsn", {"ww1target": 550}) == "Power=1200"
    assert session.calls[0][0] == "http://1.2.3.4/setup.jsn?ww1target=550"


async def test_401_raises_auth_error_and_releases_response() -> None:
    """A 401 raises MyPVAuthenticationError without leaking the response."""
    session = _FakeSession(lambda: _FakeResponse(status=401))
    conn = _connection(session)

    with pytest.raises(MyPVAuthenticationError):
        await conn.get_text("/data.jsn")

    # The response must be released (the regression this guards against left it
    # dangling until garbage collection).
    assert session.responses[0].released is True


async def test_connection_error_is_mapped_and_closes() -> None:
    """A transport error maps to MyPVConnectionError and closes the connection."""
    session = _FakeSession(
        lambda: _FakeResponse(enter_exc=ClientConnectionError("boom"))
    )
    conn = _connection(session)
    conn.close = AsyncMock(return_value=True)  # type: ignore[method-assign]

    with pytest.raises(MyPVConnectionError):
        await conn.get_text("/data.jsn")

    conn.close.assert_awaited_once()


async def test_requests_are_serialised() -> None:
    """Concurrent requests on one connection never overlap (single-connection device)."""
    tracker = _Tracker()
    session = _FakeSession(lambda: _FakeResponse(body="OK", tracker=tracker))
    conn = _connection(session)

    await asyncio.gather(
        conn.get_text("/a"),
        conn.get_text("/b"),
        conn.get_text("/c"),
    )

    assert tracker.max_active == 1
