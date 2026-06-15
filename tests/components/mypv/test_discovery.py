"""Tests for the myPV UDP discovery helpers."""

import socket
import struct
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.mypv import discovery
from custom_components.mypv.discovery import (
    DISCOVERY_MESSAGES,
    UDPDiscoveryProtocol,
    async_discover_mypv_devices,
    build_mypv_payload,
)
from homeassistant.core import HomeAssistant


def _packet(device_id: int, ip: str) -> bytes:
    """Build a 64-byte discovery response packet."""
    return (
        b"\x00\x00" + struct.pack(">H", device_id) + socket.inet_aton(ip) + b"\x00" * 56
    )


def test_build_mypv_payload() -> None:
    """The payload is 32 bytes and encodes the device id."""
    payload = build_mypv_payload("AC ELWA-E", "160124")
    assert len(payload) == 32
    # Bytes 2:4 carry the device id (160124 -> 16124 after the prefix squeeze).
    assert struct.unpack(">H", payload[2:4])[0] == 16124


def test_datagram_received_parses_and_dedupes() -> None:
    """A valid packet is parsed once; duplicates and junk are ignored."""
    proto = UDPDiscoveryProtocol()
    packet = _packet(16150, "192.168.1.50")
    assert len(packet) == 64

    proto.datagram_received(packet, ("192.168.1.50", 16124))
    assert proto.found_devices == [{"ip": "192.168.1.50", "host": "AC ELWA 2"}]

    # Duplicate IP is ignored.
    proto.datagram_received(packet, ("192.168.1.50", 16124))
    assert len(proto.found_devices) == 1

    # Wrong length is ignored.
    proto.datagram_received(b"\x00" * 10, ("192.168.1.50", 16124))
    assert len(proto.found_devices) == 1


def test_datagram_received_unknown_device() -> None:
    """An unknown device id falls back to a generic name."""
    proto = UDPDiscoveryProtocol()
    proto.datagram_received(_packet(9999, "10.0.0.9"), ("10.0.0.9", 16124))
    assert proto.found_devices == [{"ip": "10.0.0.9", "host": "myPV Device"}]


def test_connection_made_sends_discovery_messages() -> None:
    """connection_made broadcasts all discovery messages."""
    proto = UDPDiscoveryProtocol()
    transport = MagicMock()
    transport.get_extra_info.return_value = None

    proto.connection_made(transport)

    assert transport.sendto.call_count == len(DISCOVERY_MESSAGES)


async def test_async_discover_returns_devices(hass: HomeAssistant) -> None:
    """async_discover_mypv_devices returns the protocol's found devices."""
    transport = MagicMock()

    async def fake_create_datagram_endpoint(factory, **kwargs):
        proto = factory()
        proto.datagram_received(_packet(16150, "192.168.1.50"), ("192.168.1.50", 1))
        return transport, proto

    loop = MagicMock()
    loop.create_datagram_endpoint = fake_create_datagram_endpoint

    with (
        patch.object(discovery.asyncio, "get_running_loop", return_value=loop),
        patch.object(discovery.asyncio, "sleep", new=AsyncMock()),
    ):
        result = await async_discover_mypv_devices()

    assert result == [{"ip": "192.168.1.50", "host": "AC ELWA 2"}]
    transport.close.assert_called_once()
