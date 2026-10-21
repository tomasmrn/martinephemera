"""sACN (ANSI E1.31) DMX sender, no third-party dependencies.

Packet layout: root layer (38 bytes), framing layer (77 bytes), DMP layer
(11 bytes + start code + slots). A full 512-slot packet is 638 bytes.
"""

import socket
import struct
import uuid

SACN_PORT = 5568
_ACN_ID = b"ASC-E1.17\x00\x00\x00"
_SOURCE_NAME = b"Martin VDO controller"
_PRIORITY = 100
_CID = uuid.uuid4().bytes  # per-process component ID
_BROADCAST = "255.255.255.255"


def multicast_address(universe: int) -> str:
    return f"239.255.{universe >> 8}.{universe & 0xFF}"


def build_sacn_packet(data: bytes, universe: int, sequence: int = 0, cid: bytes = _CID) -> bytes:
    """Build one E1.31 data packet. `universe` is 1-63999 (sACN has no universe 0)."""
    if not 1 <= universe <= 63999:
        raise ValueError(f"sACN universe must be 1-63999, got {universe}")
    if not 1 <= len(data) <= 512:
        raise ValueError(f"DMX data must be 1-512 bytes, got {len(data)}")

    slots = bytes(data)
    count = len(slots) + 1  # property count includes the DMX start code
    total = 126 + len(slots)

    root = (
        struct.pack(">HH", 0x0010, 0x0000)              # preamble size, postamble size
        + _ACN_ID
        + struct.pack(">H", 0x7000 | (total - 16))      # flags and length
        + struct.pack(">I", 0x00000004)                 # root vector: E1.31 data
        + cid
    )
    framing = (
        struct.pack(">H", 0x7000 | (total - 38))
        + struct.pack(">I", 0x00000002)                 # framing vector: data packet
        + _SOURCE_NAME.ljust(64, b"\x00")
        + bytes([_PRIORITY])
        + struct.pack(">H", 0)                          # synchronization address
        + bytes([sequence & 0xFF, 0])                   # sequence, options
        + struct.pack(">H", universe)
    )
    dmp = (
        struct.pack(">H", 0x7000 | (total - 115))
        + bytes([0x02, 0xA1])                           # set property, address/data types
        + struct.pack(">HHH", 0x0000, 0x0001, count)    # first address, increment, count
        + b"\x00"                                       # DMX start code
        + slots
    )
    packet = root + framing + dmp
    assert len(root) == 38 and len(framing) == 77 and len(packet) == total
    return packet


class SacnSender:
    """Sends E1.31 packets to a unicast IP, or to the universe's multicast group if no IP is given."""

    def __init__(self, target_ip: str | None = None, port: int = SACN_PORT):
        self._target_ip = None if target_ip in (None, "", _BROADCAST) else target_ip
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        self._sequence = 0

    def send(self, universe: int, data: bytes) -> None:
        self._sequence = (self._sequence + 1) % 256
        packet = build_sacn_packet(data, universe, self._sequence)
        destination = self._target_ip or multicast_address(universe)
        self._sock.sendto(packet, (destination, self._port))

    def close(self) -> None:
        self._sock.close()
