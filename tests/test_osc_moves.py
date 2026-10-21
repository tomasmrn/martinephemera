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

    def test_steady_master_stream_does_not_overwrite_a_scene(self):
        self.client.send_message("/martin/master", 0.5)   # the master is at 0.5 from the controller
        self._settle()
        self.engine.master = 1.0
        self.scenes.store(2, "Full")                      # the scene holds master 1.0
        self.scenes.recall(2)
        for _ in range(20):
            self.client.send_message("/martin/master", 0.5)
        self._settle()
        self.assertAlmostEqual(self.engine.master, 1.0)


if __name__ == "__main__":
    unittest.main()
