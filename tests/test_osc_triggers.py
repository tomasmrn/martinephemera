import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture
from martin_controller.osc_server import OscServer
from martin_controller.scenes import PlaylistItem, SceneManager


class OscTriggerTests(unittest.TestCase):
    PORT = 18161

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture()])
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, beam_intensity=0.2, fx=1)
        self.scenes.store(1, "One")
        self.engine.update_fixture(0, beam_intensity=0.8, fx=2)
        self.scenes.store(2, "Two")
        self.scenes.set_playlist([PlaylistItem(1), PlaylistItem(2), PlaylistItem(1)])
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1", scenes=self.scenes)
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def _settle(self):
        time.sleep(0.15)

    def test_steady_scene_stream_recalls_once_and_keeps_manual_changes(self):
        self.client.send_message("/martin/scene", 2)
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 2)
        self.engine.update_fixture(0, beam_intensity=0.5)      # a manual change after the scene
        for _ in range(20):                                    # TouchDesigner keeps sending "2"
            self.client.send_message("/martin/scene", 2)
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.5)

    def test_scene_id_change_recalls(self):
        self.client.send_message("/martin/scene", 1)
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 1)
        self.client.send_message("/martin/scene", 2)
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 2)

    def test_recall_address_always_recalls(self):
        self.client.send_message("/martin/scene", 2)
        self._settle()
        self.engine.update_fixture(0, beam_intensity=0.5)
        self.client.send_message("/martin/scene/recall", 2)
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.8)

    def test_next_fires_once_per_press(self):
        self.client.send_message("/martin/playlist/next", 1.0)
        self._settle()
        self.assertEqual(self.scenes.position, 0)
        for _ in range(10):                                    # held or streamed high: no more steps
            self.client.send_message("/martin/playlist/next", 1.0)
        self._settle()
        self.assertEqual(self.scenes.position, 0)
        self.client.send_message("/martin/playlist/next", 0.0)  # release
        self._settle()
        self.client.send_message("/martin/playlist/next", 1.0)  # next press
        self._settle()
        self.assertEqual(self.scenes.position, 1)

    def test_previous_fires_once_per_press(self):
        self.client.send_message("/martin/playlist/prev", 1.0)
        self._settle()
        self.assertEqual(self.scenes.position, 2)              # wraps back to the end

    def test_playlist_go_fires_on_change_only(self):
        self.client.send_message("/martin/playlist/go", 1)
        self._settle()
        self.assertEqual(self.scenes.position, 1)
        self.engine.update_fixture(0, beam_intensity=0.4)
        self.client.send_message("/martin/playlist/go", 1)
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.4)


if __name__ == "__main__":
    unittest.main()
