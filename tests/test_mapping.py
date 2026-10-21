import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture, FixtureState
from martin_controller.mapping import PARAMETERS, Mapping, MappingTable
from martin_controller.osc_server import OscServer


class MappingScaleTests(unittest.TestCase):
    def test_scales_input_range_to_output_range(self):
        m = Mapping("/x", "fx", in_min=0, in_max=1, out_min=0, out_max=255)
        self.assertAlmostEqual(m.scale(0.5), 127.5)
        self.assertAlmostEqual(m.scale(1.0), 255)

    def test_clamps_outside_input_range(self):
        m = Mapping("/x", "fx", in_min=0, in_max=1, out_min=0, out_max=255)
        self.assertEqual(m.scale(-3), 0)
        self.assertEqual(m.scale(9), 255)

    def test_inverted_input_range(self):
        m = Mapping("/x", "beam_intensity", in_min=1, in_max=0, out_min=0, out_max=1)
        self.assertAlmostEqual(m.scale(0.0), 1.0)
        self.assertAlmostEqual(m.scale(1.0), 0.0)

    def test_zero_span_does_not_divide_by_zero(self):
        m = Mapping("/x", "fx", in_min=0.5, in_max=0.5, out_min=10, out_max=20)
        self.assertEqual(m.scale(0.7), 10)

    def test_round_trip_dict(self):
        m = Mapping("/td/fader1", "aura_red", fixture=1, in_min=0, in_max=127, out_min=0, out_max=1)
        self.assertEqual(Mapping.from_dict(m.to_dict()), m)


class ParameterTests(unittest.TestCase):
    def test_float_rgb_component_keeps_other_channels(self):
        state = FixtureState(beam_rgb=(0.1, 0.2, 0.3))
        changes = PARAMETERS["beam_green"].changes_for(state, 0.9)
        self.assertEqual(changes, {"beam_rgb": (0.1, 0.9, 0.3)})

    def test_int_parameter_rounds_and_clamps(self):
        state = FixtureState()
        self.assertEqual(PARAMETERS["beam_color_preset"].changes_for(state, 36.4), {"beam_color_preset": 36})
        self.assertEqual(PARAMETERS["fx"].changes_for(state, 900), {"fx": 255})

    def test_every_parameter_targets_a_real_field(self):
        state = FixtureState()
        for param in PARAMETERS.values():
            if param.field is not None:
                self.assertTrue(hasattr(state, param.field), param.field)
                param.changes_for(state, param.lo)


class MappingTableTests(unittest.TestCase):
    def test_lookup_by_address(self):
        table = MappingTable([Mapping("/a", "fx"), Mapping("/a", "fx_speed"), Mapping("/b", "fx")])
        self.assertEqual(len(table.lookup("/a")), 2)
        self.assertEqual(table.lookup("/missing"), ())

    def test_set_replaces_all(self):
        table = MappingTable([Mapping("/a", "fx")])
        table.set([Mapping("/b", "fx")])
        self.assertEqual(table.lookup("/a"), ())
        self.assertEqual(len(table.lookup("/b")), 1)


class OscEndToEndTests(unittest.TestCase):
    PORT = 18101

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture(address=1), Fixture(address=28)])
        self.table = MappingTable([
            Mapping("/td/fader1", "beam_intensity", fixture=0, in_min=0, in_max=1, out_min=0, out_max=1),
            Mapping("/td/fx", "fx", fixture=None, in_min=0, in_max=127, out_min=0, out_max=255),
            Mapping("/td/blackout", "blackout", in_min=0, in_max=1, out_min=0, out_max=1),
        ])
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1", mappings=self.table)
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def _wait(self, predicate):
        deadline = time.time() + 2
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def test_mapped_address_changes_one_fixture(self):
        self.client.send_message("/td/fader1", 0.25)
        self.assertTrue(self._wait(lambda: self.engine.fixtures[0].state.beam_intensity == 0.25))
        self.assertEqual(self.engine.fixtures[1].state.beam_intensity, 1.0)

    def test_mapping_to_all_fixtures_and_scaling(self):
        self.client.send_message("/td/fx", 127)
        self.assertTrue(self._wait(lambda: all(f.state.fx == 255 for f in self.engine.fixtures)))

    def test_blackout_mapping(self):
        self.client.send_message("/td/blackout", 1)
        self.assertTrue(self._wait(lambda: self.engine.blackout))
        self.client.send_message("/td/blackout", 0)
        self.assertTrue(self._wait(lambda: not self.engine.blackout))

    def test_monitor_records_unmapped_messages(self):
        self.client.send_message("/unknown/thing", 0.7)
        self.assertTrue(self._wait(lambda: self.server.monitor.snapshot()[1] == "/unknown/thing"))
        count, address, value = self.server.monitor.snapshot()
        self.assertAlmostEqual(value, 0.7, places=5)
        self.assertGreaterEqual(count, 1)

    def test_builtin_martin_addresses_still_work(self):
        self.client.send_message("/martin/2/fx", 12)
        self.assertTrue(self._wait(lambda: self.engine.fixtures[1].state.fx == 12))


if __name__ == "__main__":
    unittest.main()
