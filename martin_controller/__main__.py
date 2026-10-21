"""Run with: python -m martin_controller"""

import sys

from PySide6.QtWidgets import QApplication

from .config import SETTINGS_PATH, load_settings
from .engine import DmxEngine
from .ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    settings = load_settings(SETTINGS_PATH)
    engine = DmxEngine(settings.network, settings.fixtures)
    window = MainWindow(settings, engine, settings_path=SETTINGS_PATH)
    window.show()
    window.start_outputs()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
