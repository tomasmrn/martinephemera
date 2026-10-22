import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture
from martin_controller.mapping import Mapping, MappingTable
from martin_controller.osc_server import OscServer
from martin_controller.scenes import SceneManager


class SteadyStreamTests(unittest.TestCase):
    PORT = 18171

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture()])
        self.scenes = SceneManager(self.engine)
        self.engine.update_fixture(0, beam_intensity=0.3)
        self.scenes.store(1, "Scene")
        self.engine.update_fixture(0, beam_intensity=0.8)
        table = MappingTable([Mapping("/td/fader", "beam_intensity", fixture=0, in_min=0, in_max=1, out_min=0, out_max=1)])
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1", mappings=table, scenes=self.scenes)
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def _settle(self):
        time.sleep(0.15)

    def test_steady_stream_does_not_overwrite_a_scene(self):
        self.client.send_message("/td/fader", 0.5)             # the fader is at 0.5 when the scene starts
        self._settle()
        self.scenes.recall(1)                                  # scene sets beam to 0.3
        for _ in range(30):                                    # TouchDesigner keeps sending 0.5
            self.client.send_message("/td/fader", 0.5)
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_moving_the_fader_overrides_the_scene(self):
        self.client.send_message("/td/fader", 0.5)
        self._settle()
        self.scenes.recall(1)
        self.client.send_message("/td/fader", 0.5)
        self.client.send_message("/td/fader", 0.6)              # the fader really moves
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.6, places=3)

    def test_builtin_steady_stream_does_not_overwrite_a_scene(self):
        self.client.send_message("/martin/1/intensity", 0.5)
        self._settle()
        self.scenes.recall(1)
        for _ in range(30):
            self.client.send_message("/martin/1/intensity", 0.5)
        self._settle()
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_intensity, 0.3, places=3)

    def test_scene_recall_does_not_change_the_master(self):
        self.client.send_message("/martin/master", 0.5)
        self._settle()
        self.scenes.recall(1)
        self.assertAlmostEqual(self.engine.master, 0.5)
        self.client.send_message("/martin/master", 0.7)  # OSC still moves the master after a scene
        self._settle()
        self.assertAlmostEqual(self.engine.master, 0.7, places=5)


if __name__ == "__main__":
    unittest.main()


class LastChangedMonitorTests(unittest.TestCase):
    PORT = 18172

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture()])
        table = MappingTable([
            Mapping("/td/a", "beam_intensity", fixture=0, in_min=0, in_max=1, out_min=0, out_max=1),
            Mapping("/td/b", "aura_intensity", fixture=0, in_min=0, in_max=1, out_min=0, out_max=1),
        ])
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1", mappings=table)
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def test_last_changed_is_the_moving_channel_not_the_last_in_the_stream(self):
        self.client.send_message("/td/a", 0.2)
        self.client.send_message("/td/b", 0.5)
        time.sleep(0.1)
        self.client.send_message("/td/a", 0.7)                 # channel a moves
        for _ in range(20):                                    # channel b keeps streaming its steady value
            self.client.send_message("/td/b", 0.5)
            self.client.send_message("/td/a", 0.7)
        time.sleep(0.15)
        _, address, value = self.server.monitor.change_snapshot()
        self.assertEqual(address, "/td/a")
        self.assertAlmostEqual(value, 0.7, places=3)
