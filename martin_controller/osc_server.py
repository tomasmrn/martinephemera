"""OSC input: built-in /martin addresses for TouchOSC, plus user mappings for TouchDesigner and others.

Built-in addresses (n = fixture number, 1-based, in the order shown in the Fixtures tab):

  /martin/blackout              i  0 or 1
  /martin/master                f  master dimmer, 0.0-1.0
  /martin/scene                 i  recall the scene with this ID (every message recalls it)
  /martin/scene/fade            f  fade time in seconds for scene recalls (0 = instant)
  /martin/playlist/next         -  next playlist item
  /martin/playlist/prev         -  previous playlist item
  /martin/playlist/go           i  play playlist item at this position (0 = first)
  /martin/<n>/intensity         f  beam intensity, 0.0-1.0
  /martin/<n>/beam/rgb          fff  0.0-1.0 each
  /martin/<n>/beam/preset       i  0 (none) or 1-48
  /martin/<n>/aura/intensity    f  0.0-1.0
  /martin/<n>/aura/rgb          fff  0.0-1.0 each
  /martin/<n>/fx                i  0-255, see effects.FX_NAMES
  /martin/<n>/fx/speed          f  0.0-1.0 maps to DMX 0-255 (128 = stopped)

Any other address is looked up in the mapping table (see mapping.py).
"""

import threading
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from .engine import DmxEngine
from .fixture import unit_to_u8
from .mapping import PARAMETERS, MappingTable
from .scenes import SceneManager


class OscMonitor:
    """Last incoming message, for the UI. Written by the OSC thread, read by the UI timer."""

    def __init__(self):
        self._lock = threading.Lock()
        self.count = 0
        self.address: str | None = None
        self.value: float | None = None
        self.time: float | None = None

    def record(self, address: str, value: float | None) -> None:
        with self._lock:
            self.count += 1
            self.address = address
            self.value = value
            self.time = time.time()

    def snapshot(self) -> tuple[int, str | None, float | None]:
        with self._lock:
            return self.count, self.address, self.value


def _first_number(args) -> float | None:
    for arg in args:
        if isinstance(arg, (int, float)) and not isinstance(arg, bool):
            return float(arg)
        if isinstance(arg, bool):
            return 1.0 if arg else 0.0
    return None


class OscServer:
    def __init__(self, engine: DmxEngine, port: int, host: str = "0.0.0.0",
                 mappings: MappingTable | None = None, scenes: SceneManager | None = None):
        self._engine = engine
        self._mappings = mappings if mappings is not None else MappingTable()
        self._scenes = scenes
        self._last_scene_id: dict[str, int] = {}   # last ID recalled, per mapping address
        self.monitor = OscMonitor()
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle)
        self._server = ThreadingOSCUDPServer((host, port), dispatcher)
        self._thread = threading.Thread(target=self._server.serve_forever, name="osc", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handle(self, address: str, *args) -> None:
        value = _first_number(args)
        self.monitor.record(address, value)

        if address.startswith("/martin/"):
            self._handle_builtin(address, args)
            return
        if value is None:
            return
        for mapping in self._mappings.lookup(address):
            self._apply_mapping(mapping, value)

    def _apply_mapping(self, mapping, value: float) -> None:
        param = PARAMETERS.get(mapping.parameter)
        if param is None:
            return
        scaled = mapping.scale(value)
        if param.key == "blackout":
            self._engine.blackout = scaled >= 0.5
            return
        if param.key == "master":
            self._engine.master = scaled
            return
        if param.key == "scene":
            # Recall only when the ID changes, so a steady control does not keep re-applying the scene.
            scene_id = int(round(scaled))
            if self._scenes is not None and self._last_scene_id.get(mapping.address) != scene_id:
                self._last_scene_id[mapping.address] = scene_id
                self._scenes.recall(scene_id)
            return
        indices = range(len(self._engine.fixtures)) if mapping.fixture is None else [mapping.fixture]
        for index in indices:
            self._engine.modify_fixture(index, lambda state, p=param, v=scaled: p.changes_for(state, v))

    def _handle_builtin(self, address: str, args) -> None:
        parts = address.strip("/").split("/")
        if parts[1:] == ["blackout"] and args:
            self._engine.blackout = bool(args[0])
            return
        if parts[1:] == ["master"] and args:
            self._engine.master = float(args[0])
            return
        if self._scenes is not None and parts[1:] == ["scene"] and args:
            self._scenes.recall(int(args[0]))
            return
        if self._scenes is not None and parts[1:] == ["scene", "fade"] and args:
            self._scenes.fade_time = max(0.0, float(args[0]))
            return
        if self._scenes is not None and parts[1:] == ["playlist", "next"]:
            self._scenes.step(1)
            return
        if self._scenes is not None and parts[1:] == ["playlist", "prev"]:
            self._scenes.step(-1)
            return
        if self._scenes is not None and parts[1:] == ["playlist", "go"] and args:
            self._scenes.go(int(args[0]))
            return

        if len(parts) < 3 or not parts[1].isdigit():
            return
        index = int(parts[1]) - 1
        if not 0 <= index < len(self._engine.fixtures):
            return
        param = "/".join(parts[2:])
        values = _OSC_PARAMS.get(param)
        if values is None or len(args) < values[0]:
            return
        self._engine.update_fixture(index, **values[1](*args))


def _rgb(r, g, b):
    return (float(r), float(g), float(b))


# param -> (number of args needed, function turning OSC args into FixtureState fields)
_OSC_PARAMS = {
    "intensity": (1, lambda v: {"beam_intensity": float(v)}),
    "beam/rgb": (3, lambda r, g, b: {"beam_rgb": _rgb(r, g, b)}),
    "beam/preset": (1, lambda v: {"beam_color_preset": max(0, min(48, int(v)))}),
    "aura/intensity": (1, lambda v: {"aura_intensity": float(v)}),
    "aura/rgb": (3, lambda r, g, b: {"aura_rgb": _rgb(r, g, b)}),
    "fx": (1, lambda v: {"fx": max(0, min(255, int(v)))}),
    "fx/speed": (1, lambda v: {"fx_speed": unit_to_u8(float(v))}),
}
