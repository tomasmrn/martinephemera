import unittest

from martin_controller.effects import COLOR_PRESET_RGB
from martin_controller.fixture import FixtureState
from martin_controller.puppet import puppet_levels


class PuppetLevelTests(unittest.TestCase):
    def test_skirt_follows_beam_and_halo_follows_aura(self):
        state = FixtureState(beam_rgb=(1.0, 0.0, 0.0), beam_intensity=0.5,
                             aura_rgb=(0.0, 0.0, 1.0), aura_intensity=0.25)
        skirt_rgb, skirt, halo_rgb, halo = puppet_levels(state, blackout=False, master=1.0)
        self.assertEqual((skirt_rgb, skirt), ((1.0, 0.0, 0.0), 0.5))
        self.assertEqual((halo_rgb, halo), ((0.0, 0.0, 1.0), 0.25))

    def test_master_scales_both_levels(self):
        state = FixtureState(beam_intensity=1.0, aura_intensity=1.0)
        _, skirt, _, halo = puppet_levels(state, blackout=False, master=0.4)
        self.assertAlmostEqual(skirt, 0.4)
        self.assertAlmostEqual(halo, 0.4)

    def test_blackout_turns_both_off(self):
        state = FixtureState(beam_intensity=1.0, aura_intensity=1.0)
        _, skirt, _, halo = puppet_levels(state, blackout=True, master=1.0)
        self.assertEqual((skirt, halo), (0.0, 0.0))

    def test_colour_presets_override_rgb(self):
        state = FixtureState(beam_color_preset=37, aura_color_preset=36)
        skirt_rgb, _, halo_rgb, _ = puppet_levels(state, blackout=False, master=1.0)
        self.assertEqual(skirt_rgb, COLOR_PRESET_RGB[36])
        self.assertEqual(halo_rgb, COLOR_PRESET_RGB[35])


if __name__ == "__main__":
    unittest.main()
