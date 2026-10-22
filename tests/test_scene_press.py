import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture
from martin_controller.osc_server import OscServer
from martin_controller.scenes import SceneManager


class ScenePressTests(unittest.TestCase):
    PORT = 18191

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture()])
        self.scenes = SceneManager(self.engine)
        for number in (3, 4):
            self.engine.update_fixture(0, fx=number)
            self.scenes.store(number, f"S{number}")
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1", scenes=self.scenes)
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def _settle(self):
        time.sleep(0.15)

    def test_repeated_press_values_recall_only_once(self):
        self.client.send_message("/martin/scene/press", [1.0, 3])
        self._settle()
        self.engine.update_fixture(0, fx=99)           # a manual change after the scene
        for _ in range(20):                            # the button keeps reporting "pressed"
            self.client.send_message("/martin/scene/press", [1.0, 3])
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 99)

    def test_each_press_recalls_again(self):
        self.client.send_message("/martin/scene/press", [1.0, 3])
        self._settle()
        self.client.send_message("/martin/scene/press", [0.0, 3])     # release
        self._settle()
        self.engine.update_fixture(0, fx=99)
        self.client.send_message("/martin/scene/press", [1.0, 3])     # next press
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 3)

    def test_buttons_do_not_block_each_other(self):
        self.client.send_message("/martin/scene/press", [1.0, 3])
        self._settle()
        self.client.send_message("/martin/scene/press", [0.0, 3])
        self.client.send_message("/martin/scene/press", [1.0, 4])     # a different button
        self._settle()
        self.assertEqual(self.engine.fixtures[0].state.fx, 4)


if __name__ == "__main__":
    unittest.main()
