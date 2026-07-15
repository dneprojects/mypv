"""Self-contained HTTP(S) transport for the myPV integration.

Talks to the myPV local API (``mypv_dev.jsn`` / ``data.jsn`` / ``setup.jsn`` /
``control.html``) directly over aiohttp. Device *values* are kept raw: the
entities apply their own scaling and read the keys verbatim.

Supports every encryption mode of the newer firmware:

- **HTTP** (``sec_level`` 0): plain HTTP, no authentication.
- **HTTPS without password** (``sec_level`` 1): HTTPS (self-signed), no auth.
- **HTTPS with password** (``sec_level`` 2): the password gates ``/auth.jsn``
  (login) and is attached to ``/setup.jsn`` config writes.

Reads and ``control.html`` power steering are open (no password) in every mode.
The device serves a single connection at a time, so every request of one
connection is serialised through ``_io_lock``.
"""

import asyncio
import json
from typing import Any
from urllib.parse import quote, urlencode, urlunsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

_REQUEST_TIMEOUT = ClientTimeout(total=5)
# Characters JavaScript's encodeURIComponent leaves unescaped on top of the
# always-safe alphanumerics/``-_.~``. The firmware compares the raw ``pw`` field
# without URL-decoding, so aiohttp's default encoding (``!`` -> ``%21``) would
# make a correct password fail. Encoding form bodies like the device web app
# avoids that.
_ENCODE_URI_SAFE = "!*'()"
_FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


class MyPVConnectionError(Exception):
    """Raised when the device cannot be reached."""


class MyPVAuthenticationError(Exception):
    """Raised when authentication with the device fails."""


def _encode_form(params: dict[str, Any]) -> str:
    """Encode a form body the way the device web app does (encodeURIComponent)."""
    return "&".join(
        f"{quote(str(key), safe=_ENCODE_URI_SAFE)}"
        f"={quote(str(value), safe=_ENCODE_URI_SAFE)}"
        for key, value in params.items()
    )


class _Connection:
    """Base transport: aiohttp session lifecycle plus raw endpoint access.

    Subclasses set ``_PROTOCOL`` (``http``/``https``) and ``_SSL`` (the aiohttp
    ``ssl`` argument: ``True`` verifies, ``False`` skips verification for the
    device's self-signed certificate).
    """

    _PROTOCOL: str = "http"
    _SSL: bool = True

    def __init__(self, host: str) -> None:
        """Store the host and prepare the per-device request lock."""
        self._host = host
        self._session: ClientSession | None = None
        self._mypv_dev: dict[str, Any] | None = None
        self._io_lock = asyncio.Lock()

    def _url(self, path: str, query: str = "") -> str:
        return urlunsplit([self._PROTOCOL, self._host, path, query, None])

    async def open(self) -> bool:
        """Open a fresh session, read the device identification, authenticate.

        Returns ``False`` (instead of raising) when the device is unreachable or
        does not answer ``mypv_dev.jsn`` with a 200, so callers can fall back.
        Raises ``MyPVAuthenticationError`` when a required login is rejected.
        """
        await self.close()
        session = ClientSession(timeout=_REQUEST_TIMEOUT)
        try:
            async with session.get(self._url("/mypv_dev.jsn"), ssl=self._SSL) as resp:
                if resp.status != 200:
                    await session.close()
                    return False
                self._mypv_dev = json.loads(await resp.text())
            if not await self._authenticate(session):
                await session.close()
                return False
        except MyPVAuthenticationError:
            await session.close()
            raise
        except (ClientError, TimeoutError, OSError):
            await session.close()
            return False
        self._session = session
        return True

    async def _authenticate(self, session: ClientSession) -> bool:
        """No authentication for plain HTTP / HTTPS-without-password."""
        return True

    def is_open(self) -> bool:
        """Return whether the session is currently open."""
        return self._session is not None and not self._session.closed

    async def close(self) -> None:
        """Close the session if it is open."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def mypv_dev(self) -> dict[str, Any] | None:
        """Return the device identification dict (``mypv_dev.jsn``)."""
        return self._mypv_dev

    async def _request(self, path: str, query: dict[str, Any] | None) -> str:
        """Open if needed and perform a serialised GET, returning the body."""
        if not self.is_open() and not await self.open():
            raise MyPVConnectionError
        assert self._session is not None
        url = self._url(path, urlencode(query or {}))
        try:
            async with self._session.get(url, ssl=self._SSL) as response:
                if response.status == 401:
                    raise MyPVAuthenticationError
                return await response.text()
        except (ClientError, TimeoutError) as exc:
            await self.close()
            raise MyPVConnectionError from exc

    async def get_json(
        self, path: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET a ``*.jsn`` endpoint and return the parsed JSON unchanged."""
        async with self._io_lock:
            return json.loads(await self._request(path, query))

    async def get_text(self, path: str, query: dict[str, Any] | None = None) -> str:
        """GET an endpoint (e.g. ``control.html``) and return the raw body."""
        async with self._io_lock:
            return await self._request(path, query)

    async def send(self, path: str, params: dict[str, Any]) -> str:
        """Write config to the device. Plain HTTP passes the values in a GET."""
        return await self.get_text(path, params)

    async def command(self, path: str, params: dict[str, Any]) -> str:
        """Real-time control command (``control.html``): GET query, no password."""
        return await self.get_text(path, params)


class MypvHttpConnection(_Connection):
    """Plain-HTTP connection for older firmware (or encryption mode 0)."""

    _PROTOCOL = "http"
    _SSL = True  # no TLS on http; the value is irrelevant there


class MypvHttpsConnection(_Connection):
    """HTTPS connection (self-signed) with an optional login password.

    Covers encryption modes 1 (no password) and 2 (password). The password gates
    ``/auth.jsn`` and is attached to ``/setup.jsn`` writes; reads and
    ``control.html`` stay open. The firmware is stateless — no session cookie.
    """

    _PROTOCOL = "https"
    _SSL = False  # accept the device's self-signed certificate

    def __init__(self, host: str, password: str | None = None) -> None:
        """Initialise an HTTPS connection with an optional password."""
        super().__init__(host)
        self._pw = password

    async def _authenticate(self, session: ClientSession) -> bool:
        """Log in via ``/auth.jsn`` when a password is set; otherwise a no-op.

        The password is browser-encoded (encodeURIComponent) because the firmware
        compares the raw ``pw`` field without URL-decoding.
        """
        if not self._pw:
            return True
        async with session.post(
            self._url("/auth.jsn"),
            data=_encode_form({"pw": self._pw}),
            headers=_FORM_HEADERS,
            ssl=self._SSL,
        ) as response:
            payload: dict[str, Any] = {}
            if response.content_type == "application/json":
                payload = json.loads(await response.text())
        if payload.get("auth", 0) == 1:
            return True
        raise MyPVAuthenticationError

    async def send(self, path: str, params: dict[str, Any]) -> str:
        """Write config over HTTPS: POST, attaching the password only when set."""
        async with self._io_lock:
            if not self.is_open() and not await self.open():
                raise MyPVConnectionError
            assert self._session is not None
            body = _encode_form({**params, "pw": self._pw} if self._pw else params)
            try:
                async with self._session.post(
                    self._url(path),
                    data=body,
                    headers=_FORM_HEADERS,
                    ssl=self._SSL,
                ) as response:
                    if response.status == 401:
                        raise MyPVAuthenticationError
                    return await response.text()
            except (ClientError, TimeoutError) as exc:
                await self.close()
                raise MyPVConnectionError from exc


def create_connection(
    host: str, password: str | None = None, *, use_https: bool = False
) -> MypvHttpConnection | MypvHttpsConnection:
    """Return the connection type for the device.

    HTTPS is used when the device speaks it (``use_https``) or a password is set
    (which implies the HTTPS-with-password firmware). Plain HTTP is used only for
    old firmware that has no HTTPS server.
    """
    if use_https or password:
        return MypvHttpsConnection(host, password)
    return MypvHttpConnection(host)
