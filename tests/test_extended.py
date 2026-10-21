import json
import unittest

from martin_controller.controls import (
    CONTROL_SETTINGS,
    aura_strobe_value,
    flash_duration_ms,
    flash_rate_hz,
    parse_aura_strobe,
    pixel_start_channel,
)
from martin_controller.engine import DmxEngine
from martin_controller.config import NetworkSettings
from martin_controller.fixture import Fixture, FixtureState


class ExtendedModeTests(unittest.TestCase):
    def test_extended_frame_is_243_channels_and_basic_is_27(self):
        self.assertEqual(len(Fixture(mode="extended").to_dmx()), 243)
        self.assertEqual(len(Fixture(mode="basic").to_dmx()), 27)

    def test_first_27_channels_match_basic_mode(self):
        state = FixtureState(beam_rgb=(0.2, 0.5, 0.9), fx=96, aura_strobe=120)
        basic = Fixture(mode="basic", state=state).to_dmx()
        extended = Fixture(mode="extended", state=state).to_dmx()
        self.assertEqual(extended[:27], basic)

    def test_pixel_channels(self):
        self.assertEqual(pixel_start_channel(1), 28)   # Aura Red Pixel 1
        self.assertEqual(pixel_start_channel(72), 241)  # Aura Red Pixel 72; Blue is 243
        with self.assertRaises(ValueError):
            pixel_start_channel(73)

    def test_pixel_colour_lands_on_its_channels(self):
        pixels = [(0.0, 0.0, 0.0)] * 72
        pixels[0] = (1.0, 0.5, 0.0)     # pixel 1
        pixels[71] = (0.0, 0.0, 1.0)    # pixel 72
        frame = Fixture(mode="extended", state=FixtureState(aura_pixels=tuple(pixels))).to_dmx()
        self.assertEqual(frame[27:30], bytes([255, 128, 0]))
        self.assertEqual(frame[240:243], bytes([0, 0, 255]))

    def test_blackout_zeroes_pixels_too(self):
        pixels = tuple((1.0, 1.0, 1.0) for _ in range(72))
        frame = Fixture(mode="extended", state=FixtureState(aura_pixels=pixels)).to_dmx(blackout=True)
        self.assertEqual(frame[27:], bytes(216))

    def test_extended_address_limit_is_270(self):
        Fixture(mode="extended", address=270)
        with self.assertRaises(ValueError):
            Fixture(mode="extended", address=271)
        Fixture(mode="basic", address=486)  # basic still allows up to 486

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            Fixture(mode="standard")

    def test_engine_places_extended_fixture_and_next_one_after_it(self):
        engine = DmxEngine(NetworkSettings(), [
            Fixture(mode="extended", address=1),
            Fixture(mode="basic", address=244),
        ])
        frame = engine.build_frames()[0]
        self.assertEqual(len(frame), 512)
        self.assertEqual(frame[243 + 14], 0)  # channel 15 of the basic fixture is in use, value 0

    def test_state_round_trips_with_pixels(self):
        pixels = tuple((i / 72, 0.0, 1.0) for i in range(72))
        state = FixtureState(aura_pixels=pixels, beam_flash_rate=77)
        data = json.loads(json.dumps(state.to_dict()))
        self.assertEqual(FixtureState.from_dict(data), state)

    def test_fixture_round_trips_mode(self):
        fixture = Fixture(name="Stage L", universe=2, address=10, mode="extended")
        self.assertEqual(Fixture.from_dict(json.loads(json.dumps(fixture.to_dict()))), fixture)


class ControlTableTests(unittest.TestCase):
    def test_aura_strobe_round_trip(self):
        self.assertEqual(aura_strobe_value("shutter"), 0)
        self.assertEqual(aura_strobe_value("none"), 30)
        self.assertEqual(aura_strobe_value("strobe", 0.0), 50)
        self.assertEqual(aura_strobe_value("strobe", 1.0), 200)
        self.assertEqual(aura_strobe_value("random", 0.0), 211)
        self.assertEqual(aura_strobe_value("random", 1.0), 255)
        self.assertEqual(parse_aura_strobe(0), ("shutter", 0.0))
        self.assertEqual(parse_aura_strobe(30), ("none", 0.0))
        self.assertEqual(parse_aura_strobe(200), ("strobe", 1.0))
        self.assertEqual(parse_aura_strobe(255), ("random", 1.0))

    def test_flash_units_match_manual_ends(self):
        self.assertAlmostEqual(flash_duration_ms(0), 7.0)
        self.assertAlmostEqual(flash_duration_ms(255), 650.0)
        self.assertAlmostEqual(flash_rate_hz(0), 0.289)
        self.assertAlmostEqual(flash_rate_hz(255), 16.67)

    def test_control_values_match_manual(self):
        values = {label: value for label, value, _ in CONTROL_SETTINGS}
        by_value = {value: label for label, value, _ in CONTROL_SETTINGS}
        self.assertEqual(len(by_value), len(CONTROL_SETTINGS))  # no duplicate values
        self.assertEqual(by_value[10].split(" (")[0], "Reset fixture")
        self.assertEqual(by_value[74].split(" (")[0], "Scene capture: record current DMX")
        self.assertEqual(by_value[54].split(" (")[0], "Fan: regulated, fixed output")
        self.assertIn(59, values.values())
        for _, value, hold in CONTROL_SETTINGS:
            self.assertTrue(0 < value <= 255)
            self.assertGreater(hold, 0)

    def test_beam_special_effects_values(self):
        from martin_controller.controls import BEAM_SPECIAL_EFFECTS
        self.assertEqual(dict(BEAM_SPECIAL_EFFECTS)["Lightning"], 172)


if __name__ == "__main__":
    unittest.main()


class ColourPresetPreviewTests(unittest.TestCase):
    def test_preset_tables_line_up(self):
        from martin_controller.effects import COLOR_PRESET_HEX, COLOR_PRESET_NAMES, COLOR_PRESET_RGB
        self.assertEqual(len(COLOR_PRESET_HEX), 48)
        self.assertEqual(len(COLOR_PRESET_RGB), 48)
        self.assertEqual(len(COLOR_PRESET_NAMES), 48)
        self.assertEqual(COLOR_PRESET_RGB[35], (1.0, 1.0, 1.0))  # Color 36 - Pure White
        self.assertEqual(COLOR_PRESET_RGB[36], (1.0, 0.0, 0.0))  # Color 37 - Pure Red

    def test_preview_uses_preset_colour_over_rgb(self):
        from martin_controller.preview import _effective_rgb
        from martin_controller.effects import COLOR_PRESET_RGB
        self.assertEqual(_effective_rgb(37, (0.1, 0.2, 0.3)), COLOR_PRESET_RGB[36])
        self.assertEqual(_effective_rgb(0, (0.1, 0.2, 0.3)), (0.1, 0.2, 0.3))
