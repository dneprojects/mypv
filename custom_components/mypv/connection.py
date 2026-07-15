"""HTTP transport for the myPV integration, built on the my-pv library.

The my-pv library is used only to establish the connection and to authenticate
(including HTTPS access with a password on newer firmware). Device *values* are
kept raw on purpose: the myPV entities apply their own scaling (tenths of a
degree, milli-hertz, ...) and read the ``data.jsn`` / ``setup.jsn`` keys
verbatim, so the library's value/config layer (``MyPVDevice`` plus the bundled
``configs``) is deliberately bypassed.

Only the connection classes from ``my_pv.connection`` are reused, extended with
the raw JSON/text access the entities and the ``control.html`` power steering
need.
"""

import asyncio
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlunsplit

from aiohttp.client_exceptions import ClientConnectionError
from my_pv.connection import MyPVHTTPConnection, MyPVHTTPSConnection
from my_pv.exceptions import MyPVAuthenticationError, MyPVConnectionError

if TYPE_CHECKING:
    from aiohttp import ClientSession


class _RawAccessMixin:
    """Raw ``*.jsn`` and ``control.html`` access on top of a library connection.

    The library only returns parsed/normalised JSON and lowercases the
    ``data.jsn`` keys, which would break keys such as ``volt_L2``. The entities
    need the untouched dict as well as plain-text access to ``control.html``.
    myPV serves a single connection at a time, so every request of one device is
    serialised through ``_io_lock``.
    """

    if TYPE_CHECKING:
        # Provided by the my_pv.connection base classes at runtime.
        _session: ClientSession | None
        _PROTOCOL: str
        _SSL_CHECK: bool
        _host: str

        def is_open(self) -> bool: ...
        async def open(self) -> bool: ...
        async def close(self) -> bool: ...

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialise the connection and its per-device request lock."""
        super().__init__(*args, **kwargs)
        self._io_lock = asyncio.Lock()

    async def _request(self, path: str, query: dict[str, Any] | None) -> str:
        """Open the connection if needed and perform a serialised GET.

        Returns the response body as text. The response is always released via
        the ``async with`` block, including on the 401 (auth-required) path,
        which previously leaked the connection until garbage collection.
        """
        if not self.is_open() and not await self.open():
            raise MyPVConnectionError
        assert self._session is not None
        url = urlunsplit(
            [self._PROTOCOL, self._host, path, urlencode(query or {}), None]
        )
        try:
            async with self._session.get(url, ssl=self._SSL_CHECK) as response:
                if response.status == 401:
                    raise MyPVAuthenticationError
                return await response.text()
        except ClientConnectionError as exc:
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


class MypvHttpConnection(_RawAccessMixin, MyPVHTTPConnection):
    """Plain-HTTP connection for older firmware without authentication."""


class MypvHttpsConnection(_RawAccessMixin, MyPVHTTPSConnection):
    """HTTPS connection with password authentication for newer firmware."""


def create_connection(
    host: str, password: str | None
) -> MypvHttpConnection | MypvHttpsConnection:
    """Return the connection type matching the given host and password."""
    if password:
        return MypvHttpsConnection(host, password)
    return MypvHttpConnection(host)
