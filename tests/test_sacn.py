import unittest

from martin_controller.sacn import build_sacn_packet, multicast_address


class SacnPacketTests(unittest.TestCase):
    def test_full_packet_is_638_bytes(self):
        packet = build_sacn_packet(bytes(512), universe=1)
        self.assertEqual(len(packet), 638)

    def test_acn_identifier_and_vectors(self):
        packet = build_sacn_packet(bytes(512), universe=1)
        self.assertEqual(packet[4:16], b"ASC-E1.17\x00\x00\x00")
        self.assertEqual(packet[18:22], b"\x00\x00\x00\x04")  # root vector
        self.assertEqual(packet[40:44], b"\x00\x00\x00\x02")  # framing vector

    def test_length_fields_count_from_their_own_layer(self):
        packet = build_sacn_packet(bytes(512), universe=1)
        self.assertEqual(packet[16:18], bytes([0x72, 0x6E]))  # 0x7000 | 622
        self.assertEqual(packet[38:40], bytes([0x72, 0x58]))  # 0x7000 | 600
        self.assertEqual(packet[115:117], bytes([0x72, 0x0B]))  # 0x7000 | 523

    def test_universe_and_dmp_fields(self):
        packet = build_sacn_packet(bytes([9, 8]), universe=0x0102)
        self.assertEqual(packet[113:115], b"\x01\x02")          # framing universe
        self.assertEqual(packet[117], 0x02)                       # DMP vector: set property
        self.assertEqual(packet[118], 0xA1)                       # DMP address/data types
        self.assertEqual(packet[123:125], b"\x00\x03")            # count = start code + 2 slots
        self.assertEqual(packet[125:], b"\x00\x09\x08")           # start code, then slots

    def test_priority_and_source_name(self):
        packet = build_sacn_packet(bytes(4), universe=5)
        self.assertEqual(packet[108], 100)
        self.assertTrue(packet[44:].startswith(b"Martin VDO controller"))

    def test_multicast_address(self):
        self.assertEqual(multicast_address(1), "239.255.0.1")
        self.assertEqual(multicast_address(0x0102), "239.255.1.2")

    def test_rejects_universe_zero_and_bad_length(self):
        with self.assertRaises(ValueError):
            build_sacn_packet(bytes(2), universe=0)
        with self.assertRaises(ValueError):
            build_sacn_packet(bytes(513), universe=1)


if __name__ == "__main__":
    unittest.main()
