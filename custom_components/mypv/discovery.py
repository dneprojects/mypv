"""UDP Discovery for myPV devices."""

import asyncio
import logging
import socket
import struct
from typing import Any

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PORT = 16124


def calc_modbus_crc16(data: bytes) -> int:
    """Calculate the Modbus CRC-16 for a given byte string."""
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def build_mypv_payload(name: str, prefix: str) -> bytes:
    """Build the exact 32-byte UDP payload for any my-PV device."""

    id_str = prefix[:2] + prefix[3:]
    device_id = int(id_str)
    payload_30 = (
        struct.pack(">H", device_id) + name.encode().ljust(16, b"\x00") + (b"\x00" * 12)
    )
    crc_value = calc_modbus_crc16(payload_30)
    return struct.pack(">H", crc_value) + payload_30


DEVICE_MODELS = {
    20300: "AC-THOR 9s",
    20100: "AC-THOR",
    20103: "AC-THOR i",
    20101: "AC-THOR CH",
    16150: "AC ELWA 2",
    16151: "AC ELWA 2 e-unit",
    16152: "AC ELWA 2 e-E",
    16124: "AC ELWA-E",
    16140: "AC ELWA-E CH",
    16129: "AC ELWA-E unit",
    16142: "AC ELWA-E CH uni",
    14100: "SOL-THOR",
    21300: "HEA-THOR IoT 3.5",
    21900: "HEA-THOR IoT 9kW",
    20110: "my-PV Meter",
}

DISCOVERY_MESSAGES = [
    build_mypv_payload("AC-THOR 9s", "200300"),
    build_mypv_payload("AC-THOR", "200100"),
    build_mypv_payload("AC-THOR i", "200103"),
    build_mypv_payload("AC ELWA 2", "160150"),
    build_mypv_payload("AC ELWA-E", "160124"),
    build_mypv_payload("SOL-THOR", "140100"),
    build_mypv_payload("my-PV Meter", "200110"),
]


class UDPDiscoveryProtocol(asyncio.DatagramProtocol):
    """Protocol to discover myPV devices via UDP."""

    def __init__(self) -> None:
        """Initialize the protocol and prepare to store found devices."""
        self.found_devices: list[dict[str, Any]] = []
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Set up the transport and send discovery messages."""
        self.transport = transport  # type: ignore  # noqa: PGH003
        sock = transport.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        if self.transport:
            _LOGGER.debug("Sending UDP broadcast to discover myPV devices")
            for msg in DISCOVERY_MESSAGES:
                self.transport.sendto(msg, ("255.255.255.255", DISCOVERY_PORT))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming UDP responses from devices."""
        _LOGGER.debug(
            "Received UDP packet from %s with length %s bytes", addr[0], len(data)
        )

        if len(data) == 64:
            device_id = struct.unpack(">H", data[2:4])[0]
            device_name = DEVICE_MODELS.get(device_id, "myPV Device")
            real_ip = socket.inet_ntoa(data[4:8])

            if not any(d.get("ip") == real_ip for d in self.found_devices):
                _LOGGER.info("Discovered %s at %s", device_name, real_ip)
                self.found_devices.append({"ip": real_ip, "host": device_name})


async def async_discover_mypv_devices() -> list[dict[str, Any]]:
    """Fire UDP broadcast and return discovered devices."""
    _LOGGER.info("Starting myPV UDP discovery process")
    loop = asyncio.get_running_loop()

    try:
        transport, protocol = await loop.create_datagram_endpoint(
            UDPDiscoveryProtocol,
            local_addr=("0.0.0.0", DISCOVERY_PORT),
            allow_broadcast=True,
        )
        # Give devices a bit more time to answer
        await asyncio.sleep(3)
        transport.close()

        if not protocol.found_devices:
            _LOGGER.warning("The myPV discovery finished but no devices responded")

        return protocol.found_devices  # noqa: TRY300
    except Exception as ex:  # noqa: BLE001
        _LOGGER.error("Error during myPV UDP discovery: %s", ex)
        return []
