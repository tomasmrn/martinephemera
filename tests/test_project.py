import json
import tempfile
import unittest
from pathlib import Path

from martin_controller.config import NetworkSettings, Settings, load_project, save_project
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture, FixtureState
from martin_controller.mapping import PARAMETERS, Mapping


class MasterDimmerTests(unittest.TestCase):
    def test_master_halves_beam_and_aura_intensity(self):
        state = FixtureState(beam_intensity=1.0, aura_intensity=1.0)
        frame = state.to_dmx(master=0.5)
        self.assertEqual(frame[0:2], bytes([128, 0]))      # beam 65535 * 0.5 rounds to 32768
        self.assertEqual(frame[19:21], bytes([128, 0]))    # aura dimmer, channels 20-21

    def test_master_scales_extended_pixels(self):
        pixels = tuple((1.0, 1.0, 1.0) for _ in range(72))
        frame = Fixture(mode="extended", state=FixtureState(aura_pixels=pixels)).to_dmx(master=0.5)
        self.assertEqual(frame[27], 128)

    def test_master_default_is_full(self):
        self.assertEqual(FixtureState().to_dmx(), FixtureState().to_dmx(master=1.0))

    def test_engine_master_is_clamped_and_used(self):
        engine = DmxEngine(NetworkSettings(), [Fixture()], master=2.0)
        self.assertEqual(engine.master, 1.0)
        engine.master = -1
        self.assertEqual(engine.master, 0.0)
        engine.master = 0.25
        self.assertEqual(engine.build_frames()[0][0], 64)

    def test_master_parameter_is_global(self):
        self.assertIsNone(PARAMETERS["master"].field)
        self.assertEqual(Mapping("/x", "master").scale(0.5), 0.5)


class ProjectFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "show.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_round_trip_keeps_everything(self):
        settings = Settings(
            network=NetworkSettings(protocol="sacn", target_ip="10.0.0.5", artnet_port=5568,
                                    osc_enabled=True, osc_host="127.0.0.1", osc_port=9000),
            fixtures=[Fixture(name="Stage L", universe=1, address=10, mode="extended",
                              state=FixtureState(fx=96, beam_rgb=(0.1, 0.2, 0.3)))],
            presets={"warm": FixtureState(beam_color_preset=5).to_dict()},
            mappings=[Mapping("/td/fader1", "beam_intensity", fixture=0, in_min=0, in_max=127,
                              out_min=0, out_max=1)],
            master=0.7,
        )
        save_project(settings, self.path)
        loaded = load_project(self.path)
        # Compare as JSON, since tuples come back from the file as lists.
        self.assertEqual(json.loads(json.dumps(loaded.to_dict())),
                         json.loads(json.dumps(settings.to_dict())))

    def test_file_has_format_and_version(self):
        save_project(Settings(), self.path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["format"], "martin-vdo-project")
        self.assertEqual(data["version"], 1)

    def test_rejects_other_json(self):
        self.path.write_text(json.dumps({"hello": 1}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_project(self.path)

    def test_rejects_newer_version(self):
        self.path.write_text(json.dumps({"format": "martin-vdo-project", "version": 99}), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_project(self.path)

    def test_rejects_invalid_fixture_in_project(self):
        data = {"format": "martin-vdo-project", "version": 1,
                "fixtures": [{"name": "bad", "universe": 0, "address": 900, "mode": "basic"}]}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_project(self.path)


if __name__ == "__main__":
    unittest.main()
