import unittest

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture
from martin_controller.scenes import SceneManager


class OverrideRecordingTests(unittest.TestCase):
    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture(address=1), Fixture(address=28)])

    def test_update_and_modify_record_changed_fields(self):
        self.engine.update_fixture(0, beam_intensity=0.5)
        self.engine.modify_fixture(0, lambda state: {"aura_rgb": (1.0, 0.0, 0.0)})
        self.assertEqual(self.engine.overrides(0), {"beam_intensity", "aura_rgb"})
        self.assertEqual(self.engine.overrides(1), frozenset())

    def test_replace_clears_that_fixture_only(self):
        self.engine.update_fixture(0, beam_intensity=0.5)
        self.engine.update_fixture(1, beam_intensity=0.5)
        self.engine.replace_fixture(0, Fixture(address=1))
        self.assertEqual(self.engine.overrides(0), frozenset())
        self.assertEqual(self.engine.overrides(1), {"beam_intensity"})

    def test_master_change_is_an_override(self):
        self.engine.master = 0.2
        self.assertTrue(self.engine.master_overridden)
        self.engine.set_master_from_scene(0.9)
        self.assertFalse(self.engine.master_overridden)
        self.assertAlmostEqual(self.engine.master, 0.9)


class SceneOverrideTests(unittest.TestCase):
    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture(address=1)])
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, beam_intensity=0.3, fx=12)
        self.scenes.store(1, "Scene")
        self.engine.update_fixture(0, beam_intensity=1.0, fx=0)
        self.scenes.fade_time = 2.0

    def test_manual_change_during_fade_wins_over_the_scene(self):
        self.scenes.recall(1)
        self.engine.update_fixture(0, beam_intensity=0.9)      # a dimmer moved by OSC mid-fade
        started = self.scenes._fade["started"]
        self.scenes.update_fade(started + 1.0)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.9)
        self.assertEqual(self.engine.fixtures[0].state.fx, 12)  # the rest of the scene still applies
        self.scenes.update_fade(started + 2.5)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.9)
        self.assertEqual(self.engine.overrides(0), {"beam_intensity"})

    def test_manual_change_before_recall_does_not_block_it(self):
        self.engine.update_fixture(0, beam_intensity=1.0)      # set by hand before the scene starts
        self.scenes.recall(1)
        self.scenes.update_fade(self.scenes._fade["started"] + 2.5)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)
        self.assertEqual(self.engine.overrides(0), frozenset())

    def test_new_scene_clears_overrides(self):
        self.engine.update_fixture(0, beam_intensity=0.9)
        self.scenes.fade_time = 0
        self.scenes.recall(1)
        self.assertEqual(self.engine.overrides(0), frozenset())
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_master_change_during_fade_wins(self):
        self.engine.master = 0.4
        self.scenes.store(2, "Full")
        self.engine.master = 1.0
        self.scenes.recall(2)
        self.engine.master = 0.2                                # manual master change mid-fade
        self.scenes.update_fade(self.scenes._fade["started"] + 2.5)
        self.assertAlmostEqual(self.engine.master, 0.2)
        self.assertTrue(self.engine.master_overridden)


if __name__ == "__main__":
    unittest.main()
