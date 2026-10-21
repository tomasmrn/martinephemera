import unittest

from martin_controller.effects import (AURA_COLOUR_FX, AURA_INTENSITY_FX, BEAM_COLOUR_FX,
                                       BEAM_INTENSITY_FX, COMBINED_FX, FX_GROUPS, FX_NAMES)
from martin_controller.fixture import FixtureState
from martin_controller.mapping import PARAMETERS


class EffectGroupTests(unittest.TestCase):
    def test_groups_cover_every_named_effect_once(self):
        grouped = [n for _, numbers in FX_GROUPS for n in numbers]
        self.assertEqual(sorted(grouped), sorted(n for n in FX_NAMES if n != 0))
        self.assertEqual(len(grouped), len(set(grouped)))

    def test_group_boundaries_follow_manual_headings(self):
        self.assertTrue(all(1 <= n <= 47 for n in BEAM_INTENSITY_FX))
        self.assertTrue(all(48 <= n <= 95 for n in BEAM_COLOUR_FX))
        self.assertTrue(all(96 <= n <= 159 for n in AURA_INTENSITY_FX))
        self.assertTrue(all(160 <= n <= 207 for n in AURA_COLOUR_FX))
        self.assertTrue(all(208 <= n <= 254 for n in COMBINED_FX))

    def test_no_pwm_adjust_in_groups(self):
        self.assertNotIn(255, [n for _, ns in FX_GROUPS for n in ns])

    def test_group_parameter_snaps_to_valid_effect(self):
        state = FixtureState()
        self.assertEqual(PARAMETERS["fx_aura_colour"].changes_for(state, 170.4), {"fx": 170})
        self.assertEqual(PARAMETERS["fx_aura_colour"].changes_for(state, 999), {"fx": 187})
        self.assertEqual(PARAMETERS["fx_beam_intensity"].changes_for(state, -5), {"fx": 1})

    def test_group_parameters_share_the_fx_field(self):
        for key in ("fx_beam_intensity", "fx_beam_colour", "fx_aura_intensity", "fx_aura_colour", "fx_combined"):
            self.assertEqual(PARAMETERS[key].field, "fx")


if __name__ == "__main__":
    unittest.main()
