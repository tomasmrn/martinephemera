import json
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from martin_controller.config import PREVIEW_MODES, Settings
from martin_controller.puppet import PUPPET_SIZE


class PreviewSettingTests(unittest.TestCase):
    def test_preview_mode_round_trips(self):
        for mode in PREVIEW_MODES:
            loaded = Settings.from_dict(json.loads(json.dumps(Settings(preview_mode=mode).to_dict())))
            self.assertEqual(loaded.preview_mode, mode)

    def test_unknown_preview_mode_falls_back_to_popout(self):
        self.assertEqual(Settings.from_dict({"preview_mode": "sideways"}).preview_mode, "popout")
        self.assertEqual(Settings.from_dict({}).preview_mode, "popout")


class PuppetSizeTests(unittest.TestCase):
    def test_puppet_has_a_fixed_size(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from martin_controller.puppet import PuppetView
        view = PuppetView()
        self.assertEqual((view.minimumSize().width(), view.minimumSize().height()), PUPPET_SIZE)
        self.assertEqual((view.maximumSize().width(), view.maximumSize().height()), PUPPET_SIZE)


if __name__ == "__main__":
    unittest.main()
