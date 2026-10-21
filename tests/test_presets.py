import json
import unittest
from datetime import datetime

from martin_controller.fixture import FixtureState
from martin_controller.presets import beam_colour, describe, make_preset, preset_mode, preset_saved, preset_state, swatch_hex


class PresetTests(unittest.TestCase):
    def test_new_preset_records_mode_and_date(self):
        data = make_preset(FixtureState(), "extended", saved=datetime(2026, 10, 21, 14, 5))
        self.assertEqual(preset_mode(data), "extended")
        self.assertEqual(preset_saved(data), "2026-10-21 14:05")
        self.assertEqual(preset_state(json.loads(json.dumps(data))), FixtureState())

    def test_old_format_preset_still_loads(self):
        old = FixtureState(fx=12).to_dict()          # a bare state dict, as saved by earlier versions
        self.assertEqual(preset_state(old).fx, 12)
        self.assertEqual(preset_mode(old), "basic")
        self.assertEqual(preset_saved(old), "")
        self.assertEqual(describe(old)[0], "Mode: Basic")

    def test_swatch_uses_colour_preset_and_intensity(self):
        self.assertEqual(swatch_hex(make_preset(FixtureState(beam_rgb=(1, 0, 0)), "basic")), "#ff0000")
        dim = make_preset(FixtureState(beam_rgb=(1, 1, 1), beam_intensity=0.5), "basic")
        self.assertEqual(swatch_hex(dim), "#808080")
        preset = make_preset(FixtureState(beam_color_preset=37), "basic")   # Pure Red
        self.assertEqual(beam_colour(preset_state(preset)), (1.0, 0.0, 0.0))

    def test_describe_mentions_effect_and_colour_preset(self):
        lines = describe(make_preset(FixtureState(fx=96, fx_speed=200, aura_color_preset=36), "extended"))
        self.assertIn("Effect: Aura Wave (speed 200)", lines)
        self.assertTrue(any(line.startswith("Aura colour: ") for line in lines))
        self.assertIn("Mode: Extended", lines)

    def test_describe_no_effect(self):
        self.assertIn("Effect: none", describe(make_preset(FixtureState(), "basic")))


if __name__ == "__main__":
    unittest.main()
