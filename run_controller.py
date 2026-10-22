"""Launcher for the Martin VDO Atomic Bold controller. Used by the packaged .exe, and runnable directly:

    .venv\Scripts\python run_controller.py
"""

import sys

from martin_controller.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
