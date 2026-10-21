import json
import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings, Settings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture, FixtureState
from martin_controller.mapping import Mapping, MappingTable
from martin_controller.osc_server import OscServer
from martin_controller.scenes import PlaylistItem, Scene, SceneManager


def make_engine():
    return DmxEngine(NetworkSettings(), [Fixture(address=1), Fixture(address=28)])


class SceneStoreTests(unittest.TestCase):
    def test_store_and_recall_restores_every_fixture_and_master(self):
        engine = make_engine()
        scenes = SceneManager(engine)
        engine.update_fixture(0, fx=12, beam_intensity=0.3)
        engine.update_fixture(1, aura_strobe=120)
        engine.master = 0.4
        scenes.store(5, "Intro")

        engine.update_fixture(0, fx=0, beam_intensity=1.0)
        engine.update_fixture(1, aura_strobe=30)
        engine.master = 1.0
        self.assertTrue(scenes.recall(5))
        self.assertEqual(engine.fixtures[0].state.fx, 12)
        self.assertAlmostEqual(engine.fixtures[0].state.beam_intensity, 0.3)
        self.assertEqual(engine.fixtures[1].state.aura_strobe, 120)
        self.assertAlmostEqual(engine.master, 0.4)

    def test_recall_unknown_id_does_nothing(self):
        self.assertFalse(SceneManager(make_engine()).recall(999))

    def test_store_replaces_same_id_and_rejects_bad_id(self):
        scenes = SceneManager(make_engine())
        scenes.store(1, "A")
        scenes.store(1, "B")
        self.assertEqual([s.name for s in scenes.scenes], ["B"])
        with self.assertRaises(ValueError):
            scenes.store(10000, "too big")

    def test_delete_removes_scene_and_playlist_entries(self):
        scenes = SceneManager(make_engine())
        scenes.store(1, "A")
        scenes.store(2, "B")
        scenes.set_playlist([PlaylistItem(1), PlaylistItem(2), PlaylistItem(1)])
        scenes.delete(1)
        self.assertEqual([item.scene_id for item in scenes.playlist], [2])


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.scenes = SceneManager(self.engine)
        for i, fx in ((1, 10), (2, 20), (3, 30)):
            self.engine.update_fixture(0, fx=fx)
            self.scenes.store(i, f"S{i}")
        self.scenes.set_playlist([PlaylistItem(1), PlaylistItem(2), PlaylistItem(3)])

    def test_next_and_previous_wrap_around(self):
        self.scenes.step(1)
        self.assertEqual(self.scenes.position, 0)
        self.assertEqual(self.engine.fixtures[0].state.fx, 10)
        self.scenes.step(-1)
        self.assertEqual(self.scenes.position, 2)
        self.assertEqual(self.engine.fixtures[0].state.fx, 30)
        self.scenes.step(1)
        self.assertEqual(self.scenes.position, 0)

    def test_go_to_position(self):
        self.assertTrue(self.scenes.go(1))
        self.assertEqual(self.engine.fixtures[0].state.fx, 20)
        self.assertFalse(self.scenes.go(7))

    def test_recall_moves_playlist_position_to_that_scene(self):
        self.scenes.recall(3)
        self.assertEqual(self.scenes.position, 2)

    def test_auto_advance_respects_hold_time(self):
        self.scenes.set_playlist([PlaylistItem(1, hold=0.05), PlaylistItem(2)])
        self.scenes.auto_advance = True
        self.scenes.go(0)
        self.scenes.tick()
        self.assertEqual(self.scenes.position, 0)   # hold not reached yet
        time.sleep(0.1)
        self.scenes.tick()
        self.assertEqual(self.scenes.position, 1)

    def test_zero_hold_waits_for_next(self):
        self.scenes.auto_advance = True
        self.scenes.go(0)
        time.sleep(0.05)
        self.scenes.tick()
        self.assertEqual(self.scenes.position, 0)

    def test_version_changes_when_a_scene_is_applied(self):
        before = self.scenes.version
        self.scenes.go(0)
        self.assertGreater(self.scenes.version, before)


class SettingsRoundTripTests(unittest.TestCase):
    def test_scenes_and_playlist_survive_json(self):
        settings = Settings(
            scenes=[Scene(id=7, name="Chorus", fixtures=[FixtureState(fx=4).to_dict()], master=0.5)],
            playlist=[PlaylistItem(7, hold=12.5)],
        )
        loaded = Settings.from_dict(json.loads(json.dumps(settings.to_dict())))
        self.assertEqual(loaded.scenes[0].id, 7)
        self.assertEqual(loaded.scenes[0].name, "Chorus")
        self.assertEqual(loaded.playlist[0], PlaylistItem(7, hold=12.5))
        self.assertEqual(FixtureState.from_dict(loaded.scenes[0].fixtures[0]).fx, 4)


class SceneOscTests(unittest.TestCase):
    PORT = 18151

    def setUp(self):
        self.engine = make_engine()
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, fx=44)
        self.scenes.store(9, "Nine")
        self.engine.update_fixture(0, fx=0)
        self.table = MappingTable([Mapping("/td/scene", "scene", in_min=0, in_max=127, out_min=0, out_max=127)])
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1",
                                mappings=self.table, scenes=self.scenes)
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

    def test_scene_address_recalls_by_id(self):
        self.client.send_message("/martin/scene", 9)
        self.assertTrue(self._wait(lambda: self.engine.fixtures[0].state.fx == 44))

    def test_mapping_recalls_only_when_id_changes(self):
        self.client.send_message("/td/scene", 9.2)
        self.assertTrue(self._wait(lambda: self.engine.fixtures[0].state.fx == 44))
        self.engine.update_fixture(0, fx=0)            # user changes something by hand
        self.client.send_message("/td/scene", 9.4)     # same ID (rounds to 9): no re-trigger
        time.sleep(0.2)
        self.assertEqual(self.engine.fixtures[0].state.fx, 0)

    def test_playlist_osc_commands(self):
        self.scenes.set_playlist([PlaylistItem(9)])
        self.client.send_message("/martin/playlist/next", 1)
        self.assertTrue(self._wait(lambda: self.scenes.position == 0))
        self.assertTrue(self._wait(lambda: self.engine.fixtures[0].state.fx == 44))


if __name__ == "__main__":
    unittest.main()


class RenameSceneTests(unittest.TestCase):
    def test_rename_keeps_look_and_playlist(self):
        engine = make_engine()
        scenes = SceneManager(engine)
        engine.update_fixture(0, fx=12)
        scenes.store(3, "Old name")
        scenes.set_playlist([PlaylistItem(3)])
        self.assertTrue(scenes.rename(3, "New name"))
        scene = scenes.get(3)
        self.assertEqual(scene.name, "New name")
        self.assertEqual(scene.fixtures, [FixtureState(fx=12).to_dict(), FixtureState().to_dict()])
        self.assertEqual([item.scene_id for item in scenes.playlist], [3])

    def test_rename_unknown_scene_returns_false(self):
        self.assertFalse(SceneManager(make_engine()).rename(42, "x"))


class SceneSwatchTests(unittest.TestCase):
    def test_scene_swatch_averages_fixtures_and_handles_empty(self):
        from martin_controller.presets import scene_swatch_hex
        red = FixtureState(beam_rgb=(1, 0, 0)).to_dict()
        blue = FixtureState(beam_rgb=(0, 0, 1)).to_dict()
        self.assertEqual(scene_swatch_hex([red]), "#ff0000")
        self.assertEqual(scene_swatch_hex([red, blue]), "#800080")
        self.assertEqual(scene_swatch_hex([]), "#555555")
