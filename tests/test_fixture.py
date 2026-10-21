import unittest

from martin_controller.effects import COLOR_PRESET_NAMES, FX_NAMES
from martin_controller.engine import DmxEngine
from martin_controller.config import NetworkSettings
from martin_controller.fixture import (
    BASIC_CHANNEL_COUNT,
    Fixture,
    FixtureState,
    color_preset_to_dmx,
    kelvin_to_ctc,
)


def channel(frame: bytes, number: int) -> int:
    return frame[number - 1]


def channel16(frame: bytes, number: int) -> int:
    return frame[number - 1] * 256 + frame[number]


class BasicModeChannelTests(unittest.TestCase):
    def test_default_frame_is_27_bytes_and_lit(self):
        frame = FixtureState().to_dmx()
        self.assertEqual(len(frame), BASIC_CHANNEL_COUNT)
        self.assertEqual(channel16(frame, 1), 65535)   # beam flash intensity, 0 would be blackout
        self.assertEqual(channel16(frame, 6), 65535)   # beam red
        self.assertEqual(channel16(frame, 20), 65535)  # aura dimmer
        self.assertEqual(channel(frame, 22), 255)      # aura red, 8-bit

    def test_blackout_zeroes_both_intensities(self):
        frame = FixtureState().to_dmx(blackout=True)
        self.assertEqual(channel16(frame, 1), 0)
        self.assertEqual(channel16(frame, 20), 0)

    def test_fx_and_speed_channels(self):
        frame = FixtureState(fx=96, fx_speed=200).to_dmx()
        self.assertEqual(channel(frame, 16), 96)
        self.assertEqual(channel(frame, 17), 200)

    def test_colour_presets_map_to_documented_values(self):
        self.assertEqual(color_preset_to_dmx(0), 0)
        self.assertEqual(color_preset_to_dmx(1), 11)    # Color 1 - LEE 790
        self.assertEqual(color_preset_to_dmx(48), 105)  # Color 48 - LEE 015
        self.assertEqual(len(COLOR_PRESET_NAMES), 48)
        frame = FixtureState(beam_color_preset=36).to_dmx()
        self.assertEqual(channel(frame, 13), 81)        # Color 36 - Pure White

    def test_ctc_mapping(self):
        self.assertEqual(kelvin_to_ctc(2000), 11)
        self.assertEqual(kelvin_to_ctc(6500), 101)
        self.assertEqual(kelvin_to_ctc(11000), 191)
        frame = FixtureState(beam_ctc_kelvin=6500).to_dmx()
        self.assertEqual(channel(frame, 12), 101)
        self.assertEqual(channel(frame, 12), kelvin_to_ctc(6500))

    def test_state_round_trips_through_dict(self):
        state = FixtureState(beam_rgb=(0.1, 0.2, 0.3), beam_ctc_kelvin=3200, fx=12)
        self.assertEqual(FixtureState.from_dict(state.to_dict()), state)

    def test_effect_names_cover_manual_numbers(self):
        self.assertEqual(FX_NAMES[0], "No Effect")
        self.assertEqual(FX_NAMES[1], "Beam Wave")
        self.assertEqual(FX_NAMES[208], "Full Thunderstorm")
        self.assertEqual(FX_NAMES[158], "Aura Split Rotate Rotateable")


class FixtureAddressingTests(unittest.TestCase):
    def test_rejects_address_that_overruns_the_universe(self):
        with self.assertRaises(ValueError):
            Fixture(address=512)  # 512 + 27 - 1 > 512
        Fixture(address=486)  # last valid start address (486..512 is 27 channels)

    def test_frames_place_fixtures_at_their_addresses(self):
        engine = DmxEngine(NetworkSettings(), [
            Fixture(address=1, universe=0),
            Fixture(address=28, universe=0, state=FixtureState(fx=5)),
            Fixture(address=1, universe=3),
        ])
        frames = engine.build_frames()
        self.assertEqual(set(frames), {0, 3})
        self.assertEqual(len(frames[0]), 512)
        self.assertEqual(frames[0][27 + 15], 5)  # channel 16 of the second fixture


if __name__ == "__main__":
    unittest.main()
