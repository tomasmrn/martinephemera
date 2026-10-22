import time
import unittest

from pythonosc.udp_client import SimpleUDPClient

from martin_controller.config import NetworkSettings
from martin_controller.engine import DmxEngine
from martin_controller.fixture import Fixture
from martin_controller.osc_server import OscServer


class SingleChannelOscTests(unittest.TestCase):
    PORT = 18181

    def setUp(self):
        self.engine = DmxEngine(NetworkSettings(), [Fixture()])
        self.engine.update_fixture(0, beam_rgb=(0.1, 0.2, 0.3), aura_rgb=(0.0, 0.0, 0.0))
        self.server = OscServer(self.engine, self.PORT, host="127.0.0.1")
        self.server.start()
        self.client = SimpleUDPClient("127.0.0.1", self.PORT)

    def tearDown(self):
        self.server.stop()

    def _wait(self, check):
        deadline = time.time() + 2
        while time.time() < deadline:
            if check():
                return True
            time.sleep(0.02)
        return False

    def test_beam_green_changes_only_green(self):
        self.client.send_message("/martin/1/beam/green", 0.9)
        # OSC floats are single precision, so compare with a tolerance.
        self.assertTrue(self._wait(lambda: abs(self.engine.fixtures[0].state.beam_rgb[1] - 0.9) < 1e-5))
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_rgb[0], 0.1, places=5)
        self.assertAlmostEqual(self.engine.fixtures[0].state.beam_rgb[2], 0.3, places=5)

    def test_aura_red_channel(self):
        self.client.send_message("/martin/1/aura/red", 0.5)
        self.assertTrue(self._wait(lambda: abs(self.engine.fixtures[0].state.aura_rgb[0] - 0.5) < 1e-5))

    def test_flash_strobe_and_special_addresses(self):
        self.client.send_message("/martin/1/beam/flash/duration", 120)
        self.client.send_message("/martin/1/beam/flash/rate", 40)
        self.client.send_message("/martin/1/beam/special", 172)
        self.client.send_message("/martin/1/aura/strobe", 150)
        self.client.send_message("/martin/1/aura/preset", 36)
        self.assertTrue(self._wait(lambda: self.engine.fixtures[0].state.aura_color_preset == 36))
        state = self.engine.fixtures[0].state
        self.assertEqual((state.beam_flash_duration, state.beam_flash_rate), (120, 40))
        self.assertEqual((state.beam_special_effect, state.aura_strobe), (172, 150))


if __name__ == "__main__":
    unittest.main()
