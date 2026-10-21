"""Minimal Art-Net ArtDMX sender (no third-party dependencies).

Packet layout follows the Art-Net 4 specification: an 18-byte header followed by
up to 512 bytes of DMX data.
"""

import socket

ARTNET_PORT = 6454
_ID = b"Art-Net\x00"
_OPCODE_DMX = 0x5000  # little-endian on the wire
_PROTOCOL_VERSION = 14


def build_artdmx(data: bytes, universe: int, sequence: int = 0) -> bytes:
    """Build one ArtDMX packet.

    `universe` is the 15-bit Art-Net port-address (Net bits 8-14, SubUni bits 0-7).
    `sequence` 0 disables sequencing; 1-255 lets nodes discard out-of-order packets.
    """
    if not 0 <= universe <= 0x7FFF:
        raise ValueError(f"universe must be 0-32767, got {universe}")
    if not 1 <= len(data) <= 512:
        raise ValueError(f"DMX data must be 1-512 bytes, got {len(data)}")

    # Length must be an even number of bytes, so pad odd-length data with a zero.
    length = len(data) + (len(data) & 1)
    payload = bytes(data).ljust(length, b"\x00")

    header = (
        _ID
        + _OPCODE_DMX.to_bytes(2, "little")
        + _PROTOCOL_VERSION.to_bytes(2, "big")
        + bytes([sequence & 0xFF, 0])          # sequence, physical port
        + bytes([universe & 0xFF, (universe >> 8) & 0x7F])  # SubUni, Net
        + length.to_bytes(2, "big")
    )
    return header + payload


class ArtNetSender:
    """Sends ArtDMX packets to one target (a unicast node IP or the broadcast address)."""

    def __init__(self, target_ip: str = "255.255.255.255", port: int = ARTNET_PORT):
        self.target = (target_ip, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sequence = 0

    def send(self, universe: int, data: bytes) -> None:
        self._sequence = self._sequence % 255 + 1  # cycles 1..255
        self._sock.sendto(build_artdmx(data, universe, self._sequence), self.target)

    def close(self) -> None:
        self._sock.close()
