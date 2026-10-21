import unittest

from martin_controller.artnet import build_artdmx


class ArtDmxPacketTests(unittest.TestCase):
    def test_header_and_opcode(self):
        packet = build_artdmx(bytes(512), universe=0)
        self.assertEqual(packet[:8], b"Art-Net\x00")
        self.assertEqual(packet[8:10], b"\x00\x50")   # OpCode 0x5000, little-endian
        self.assertEqual(packet[10:12], b"\x00\x0e")  # protocol version 14, big-endian

    def test_length_is_big_endian_and_even(self):
        packet = build_artdmx(bytes([1, 2, 3]), universe=0)
        self.assertEqual(packet[16:18], b"\x00\x04")  # 3 bytes padded to 4
        self.assertEqual(packet[18:], b"\x01\x02\x03\x00")

    def test_universe_split_into_subuni_and_net(self):
        packet = build_artdmx(bytes(2), universe=0x1234)
        self.assertEqual(packet[14], 0x34)  # SubUni
        self.assertEqual(packet[15], 0x12)  # Net
        self.assertEqual(packet[14:16], bytes([0x34, 0x12]))

    def test_sequence_byte(self):
        self.assertEqual(build_artdmx(bytes(2), 0, sequence=7)[12], 7)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            build_artdmx(bytes(2), universe=0x8000)
        with self.assertRaises(ValueError):
            build_artdmx(b"", universe=0)
        with self.assertRaises(ValueError):
            build_artdmx(bytes(513), universe=0)


if __name__ == "__main__":
    unittest.main()
