import json
import unittest

from martin_controller.config import NetworkSettings, Settings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture, FixtureState
from martin_controller.scenes import SceneManager, interpolate_state


class InterpolateTests(unittest.TestCase):
    def setUp(self):
        self.a = FixtureState(beam_intensity=0.0, aura_intensity=0.2, beam_rgb=(0.0, 0.0, 0.0),
                              aura_rgb=(0.0, 0.0, 0.0), fx=5, beam_flash_rate=0, fx_speed=128)
        self.b = FixtureState(beam_intensity=1.0, aura_intensity=1.0, beam_rgb=(1.0, 0.5, 0.0),
                              aura_rgb=(1.0, 1.0, 1.0), fx=99, beam_flash_rate=200, fx_speed=0)

    def test_endpoints(self):
        self.assertEqual(interpolate_state(self.a, self.b, 0.0).beam_intensity, 0.0)
        self.assertEqual(interpolate_state(self.a, self.b, 1.0), self.b)

    def test_midpoint_blends_continuous_values(self):
        mid = interpolate_state(self.a, self.b, 0.5)
        self.assertAlmostEqual(mid.beam_intensity, 0.5)
        self.assertAlmostEqual(mid.aura_intensity, 0.6)
        self.assertEqual(mid.beam_rgb, (0.5, 0.25, 0.0))
        self.assertEqual(mid.beam_flash_rate, 100)
        self.assertEqual(mid.fx_speed, 64)

    def test_discrete_values_switch_immediately(self):
        self.assertEqual(interpolate_state(self.a, self.b, 0.0).fx, 99)
        self.assertEqual(interpolate_state(self.a, self.b, 0.5).fx, 99)

    def test_ctc_blends_only_when_both_set(self):
        a = FixtureState(beam_ctc_kelvin=2000)
        b = FixtureState(beam_ctc_kelvin=4000)
        self.assertEqual(interpolate_state(a, b, 0.5).beam_ctc_kelvin, 3000)
        self.assertEqual(interpolate_state(FixtureState(), b, 0.5).beam_ctc_kelvin, 4000)


class FadeManagerTests(unittest.TestCase):
    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture(address=1)])
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, beam_intensity=0.3, fx=12)
        self.scenes.store(1, "Scene one")
        self.engine.update_fixture(0, beam_intensity=1.0, fx=0)
        self.scenes.fade_time = 2.0

    def test_fade_moves_gradually_then_lands_on_target(self):
        self.scenes.recall(1)
        self.assertTrue(self.scenes.fading)
        started = self.scenes._fade["started"]
        self.scenes.update_fade(started + 1.0)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.65, places=3)
        self.assertEqual(self.engine.fixtures[0].state.fx, 12)   # discrete value already switched
        self.scenes.update_fade(started + 2.5)
        self.assertFalse(self.scenes.fading)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_zero_fade_time_is_instant(self):
        self.scenes.fade_time = 0
        self.scenes.recall(1)
        self.assertFalse(self.scenes.fading)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_new_recall_during_fade_starts_from_current_look(self):
        self.scenes.recall(1)
        started = self.scenes._fade["started"]
        self.scenes.update_fade(started + 1.0)                    # halfway, beam at 0.65
        self.scenes.store(2, "Scene two")                          # beam 0.65 is now shown; store it as 2
        self.engine.update_fixture(0, beam_intensity=0.0)
        self.scenes.recall(2)
        self.assertAlmostEqual(self.scenes._fade["starts"][0].beam_intensity, 0.0)

    def test_fade_thread_runs_and_finishes(self):
        import time
        self.scenes.fade_time = 0.2
        self.scenes.start()
        try:
            self.scenes.recall(1)
            deadline = time.time() + 2
            while self.scenes.fading and time.time() < deadline:
                time.sleep(0.01)
            self.assertFalse(self.scenes.fading)
            self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)
        finally:
            self.scenes.stop()


class FadeSettingsTests(unittest.TestCase):
    def test_fade_time_round_trip_and_clamp(self):
        loaded = Settings.from_dict(json.loads(json.dumps(Settings(fade_time=3.5).to_dict())))
        self.assertEqual(loaded.fade_time, 3.5)
        self.assertEqual(Settings.from_dict({"fade_time": -4}).fade_time, 0.0)


if __name__ == "__main__":
    unittest.main()


class PlaylistFadeTests(unittest.TestCase):
    def setUp(self):
        from martin_controller.scenes import PlaylistItem
        self.PlaylistItem = PlaylistItem
        self.engine = DmxEngine(NetworkSettings(), [Fixture(address=1)])
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, beam_intensity=0.3)
        self.scenes.store(1, "A")
        self.engine.update_fixture(0, beam_intensity=1.0)
        self.scenes.store(2, "B")
        self.engine.update_fixture(0, beam_intensity=0.0)

    def test_item_fade_round_trips(self):
        item = self.PlaylistItem(1, hold=4.0, fade=2.5)
        self.assertEqual(self.PlaylistItem.from_dict(json.loads(json.dumps(item.to_dict()))), item)

    def test_playlist_item_fade_is_used_when_playing(self):
        self.scenes.set_playlist([self.PlaylistItem(1, fade=2.0)])
        self.scenes.fade_time = 0.0
        self.scenes.go(0)
        self.assertTrue(self.scenes.fading)

    def test_item_with_zero_fade_cuts_even_if_direct_fade_is_set(self):
        self.scenes.set_playlist([self.PlaylistItem(1, fade=0.0)])
        self.scenes.fade_time = 5.0
        self.scenes.go(0)
        self.assertFalse(self.scenes.fading)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_direct_recall_still_uses_global_fade(self):
        self.scenes.fade_time = 5.0
        self.scenes.recall(2)
        self.assertTrue(self.scenes.fading)
