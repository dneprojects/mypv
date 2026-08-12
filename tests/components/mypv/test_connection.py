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

from aiohttp.client_exceptions import ClientConnectionError, ClientConnectorError
import pytest

from custom_components.mypv.connection import (
    MyPVAuthenticationError,
    MyPVConnectionError,
    MypvHttpConnection,
    MypvHttpsConnection,
    _encode_form,
    create_connection,
    describe_error,
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
        self.posts: list[dict[str, object]] = []
        self.responses: list[_FakeResponse] = []
        self.closed = False  # queried by the library's is_open()

    async def close(self) -> None:
        """Mark the session closed, as aiohttp does on a connection failure."""
        self.closed = True

    def get(self, url: str, ssl: object = None) -> _FakeResponse:
        self.calls.append((url, ssl))
        response = self._factory()
        self.responses.append(response)
        return response

    def post(
        self,
        url: str,
        data: object = None,
        headers: object = None,
        ssl: object = None,
    ) -> _FakeResponse:
        self.posts.append({"url": url, "data": data, "ssl": ssl})
        response = self._factory()
        self.responses.append(response)
        return response


def _connection(session: _FakeSession) -> MypvHttpConnection:
    """A real connection wired to a fake session, without opening the network."""
    conn = MypvHttpConnection("1.2.3.4")
    conn._session = session  # inject the transport under test
    conn.open = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return conn


def _https_connection(session: _FakeSession, password: str) -> MypvHttpsConnection:
    """A real HTTPS connection wired to a fake session, without opening it."""
    conn = MypvHttpsConnection("1.2.3.4", password)
    conn._session = session  # inject the transport under test
    conn.open = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return conn


def test_create_connection_picks_transport_by_password() -> None:
    """No password -> plain HTTP; a password -> authenticated HTTPS."""
    assert isinstance(create_connection("1.2.3.4", None), MypvHttpConnection)
    assert isinstance(create_connection("1.2.3.4", "secret"), MypvHttpsConnection)


def test_encode_form_matches_encodeuricomponent() -> None:
    """The password is encoded like the browser: !*'() stay literal, / and space do not."""
    assert _encode_form({"pw": "d-Um0y!wxKLMNP4-"}) == "pw=d-Um0y!wxKLMNP4-"
    assert _encode_form({"pw": "a*b'(c)~"}) == "pw=a*b'(c)~"
    assert _encode_form({"x": "a b/c&d"}) == "x=a%20b%2Fc%26d"


async def test_https_send_posts_password_browser_encoded() -> None:
    """A HTTPS write POSTs the params plus the literal-encoded password."""
    session = _FakeSession(lambda: _FakeResponse(body="{}"))
    conn = _https_connection(session, "d-Um0y!wxKLMNP4-")

    await conn.send("/setup.jsn", {"ww1target": 555})

    assert session.posts[0]["url"] == "https://1.2.3.4/setup.jsn"
    # The '!' must stay literal (not %21) or the device rejects the password.
    assert session.posts[0]["data"] == "ww1target=555&pw=d-Um0y!wxKLMNP4-"


async def test_https_command_gets_control_html_without_password() -> None:
    """Power steering GETs control.html; the password never lands in the URL."""
    session = _FakeSession(lambda: _FakeResponse(body="OK"))
    conn = _https_connection(session, "d-Um0y!wxKLMNP4-")

    await conn.command("/control.html", {"power": 1500})

    assert session.calls[0][0] == "https://1.2.3.4/control.html?power=1500"
    assert "pw=" not in session.calls[0][0]


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


async def test_non_200_serves_cached_body() -> None:
    """A 429 (rate limit) returns the last good body instead of crashing."""
    responses = iter(
        [
            _FakeResponse(status=200, body='{"a": 1}'),
            _FakeResponse(status=429, body="Too Many Requests"),
        ]
    )
    session = _FakeSession(lambda: next(responses))
    conn = _connection(session)

    assert await conn.get_json("/data.jsn") == {"a": 1}  # populates the cache
    assert await conn.get_json("/data.jsn") == {"a": 1}  # 429 -> cached value


async def test_non_200_with_intact_body_is_used() -> None:
    """A non-200 carrying a usable body is accepted (sloppy firmware status).

    A parameter-less ``control.html`` read is answered with a non-200 by some
    firmware while the state payload itself is fine; rejecting it would disable
    the control entities (boost buttons, power) for the whole entry.
    """
    session = _FakeSession(lambda: _FakeResponse(status=404, body="power=1500\n"))
    conn = _connection(session)

    assert await conn.get_text("/control.html") == "power=1500\n"


async def test_non_200_with_empty_body_raises_connection_error() -> None:
    """A non-200 with nothing usable and no cache is a connection error."""
    session = _FakeSession(lambda: _FakeResponse(status=429, body="   "))
    conn = _connection(session)

    with pytest.raises(MyPVConnectionError):
        await conn.get_json("/data.jsn")


async def test_non_200_body_is_not_cached() -> None:
    """An error-page body must never be served later as if it were state."""
    responses = iter(
        [
            _FakeResponse(status=404, body="power=1500\n"),
            _FakeResponse(status=429, body="  "),
        ]
    )
    session = _FakeSession(lambda: next(responses))
    conn = _connection(session)

    assert await conn.get_text("/control.html") == "power=1500\n"
    with pytest.raises(MyPVConnectionError):
        await conn.get_text("/control.html")


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


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        # The reported issue: both log lines ended at the colon because these
        # all stringify to "".
        (TimeoutError(), "TimeoutError"),
        (ClientConnectionError(), "ClientConnectionError"),
        (MyPVConnectionError(), "MyPVConnectionError"),
        # A message, where there is one, is kept.
        (MyPVConnectionError("no route"), "MyPVConnectionError: no route"),
    ],
)
def test_describe_error_names_a_silent_error(
    error: BaseException, expected: str
) -> None:
    """An error with no message still identifies itself in the log."""
    assert describe_error(error) == expected


def test_describe_error_unwraps_the_cause() -> None:
    """The transport wraps the real error, so the chain has to be reported.

    ``_request`` raises ``MyPVConnectionError from exc``; without the cause the
    log names the wrapper and loses the only informative part.
    """
    cause = TimeoutError()
    err = MyPVConnectionError()
    err.__cause__ = cause

    assert describe_error(err) == "MyPVConnectionError <- TimeoutError"


def test_describe_error_survives_a_cycle() -> None:
    """A self-referential cause must not loop forever."""
    err = MyPVConnectionError("outer")
    err.__cause__ = err

    assert describe_error(err) == "MyPVConnectionError: outer"


async def test_refused_http_downgrade_falls_back_to_https() -> None:
    """A device that refuses port 80 while reporting mode 0 is not left broken.

    Reported in issue #54: the transport downgraded ``control.html`` to plain
    HTTP because ``sec_level`` read 0, and the device answered with
    ``ConnectionRefusedError`` -- which our own field data identifies as the
    signature of encryption mode 1/2. Since the HTTPS server runs in every mode,
    drop the downgrade instead of failing every poll until someone reloads.
    """
    refused = ClientConnectorError(None, OSError(111, "refused"))
    attempts = [_FakeResponse(enter_exc=refused)]
    session = _FakeSession(lambda: attempts.pop(0) if attempts else _FakeResponse())
    conn = _https_connection(session, "secret")
    conn.set_sec_level(0)

    async def _reopen() -> bool:
        # The real ``open()`` reinstalls the session the failure closed.
        conn._session = session
        session.closed = False
        return True

    conn.open = _reopen  # type: ignore[method-assign]

    assert await conn.get_text("/control.html") == "OK"

    # First attempt downgraded, the retry used the connection's own protocol.
    assert session.calls[0][0].startswith("http://")
    assert session.calls[1][0].startswith("https://")

    # And it does not downgrade again.
    session.calls.clear()
    assert await conn.get_text("/control.html") == "OK"
    assert session.calls[0][0].startswith("https://")


async def test_refused_https_still_raises() -> None:
    """A refusal that is not the mode-0 downgrade stays a connection error."""
    session = _FakeSession(
        lambda: _FakeResponse(
            enter_exc=ClientConnectorError(None, OSError(111, "refused"))
        )
    )
    conn = _https_connection(session, "secret")
    conn.set_sec_level(1)  # no downgrade in this mode

    with pytest.raises(MyPVConnectionError):
        await conn.get_text("/control.html")


def test_describe_error_survives_an_unprintable_error() -> None:
    """Formatting an error must never raise -- it runs inside except handlers.

    ``ClientConnectorError.__str__`` dereferences its connection key, which is
    not always populated; a raise here would turn a handled connection error
    into a crash.
    """

    class _Unprintable(Exception):
        def __str__(self) -> str:
            raise AttributeError("no connection key")

    assert describe_error(_Unprintable()) == "_Unprintable: <unprintable>"


def test_connection_error_names_the_url_and_mode() -> None:
    """The error carries the scheme actually used and the reported mode.

    Issue #54 needed both to be diagnosable: a plain-HTTP URL together with
    ``sec_level 0`` is what shows the reported mode to be wrong.
    """
    conn = _https_connection(_FakeSession(_FakeResponse), "secret")
    conn.set_sec_level(0)

    err = conn._connection_error("http://1.2.3.4/control.html")
    assert str(err) == "http://1.2.3.4/control.html (sec_level 0)"

    conn._http_refused = True
    err = conn._connection_error("https://1.2.3.4/control.html", "HTTP 404")
    assert (
        str(err) == "https://1.2.3.4/control.html (sec_level 0, http refused): HTTP 404"
    )
