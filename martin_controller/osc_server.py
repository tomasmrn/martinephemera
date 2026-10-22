"""OSC input: built-in /martin addresses for TouchOSC, plus user mappings for TouchDesigner and others.

Built-in addresses (n = fixture number, 1-based, in the order shown in the Fixtures tab):

  /martin/blackout              i  0 or 1
  /martin/master                f  master dimmer, 0.0-1.0
  /martin/scene                 i  recall the scene with this ID every time it is received (for manual buttons)
  /martin/scene/recall          i  recall the scene with this ID every time
  /martin/scene/press           f i  (value, ID): recall the scene once per press (value rising to 0.5)
  /martin/scene/fade            f  fade time in seconds for scene recalls (0 = instant)
  /martin/playlist/next         f  next playlist item when the value rises to 0.5 or more (a button press)
  /martin/playlist/prev         f  previous playlist item when the value rises to 0.5 or more
  /martin/playlist/go           i  play playlist item at this position, when the value changes
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
    """What the UI shows about incoming OSC. Written by the OSC thread, read by the UI timer.

    `count`/`address`/`value` describe the last message received. A sender that streams every channel
    each frame makes that the same channel every time, so `change_*` describes the last value that actually
    moved, which is usually the one the user is looking for."""

    def __init__(self):
        self._lock = threading.Lock()
        self.count = 0
        self.address: str | None = None
        self.value: float | None = None
        self.time: float | None = None
        self.change_count = 0
        self.change_address: str | None = None
        self.change_value: float | None = None

    def record(self, address: str, value: float | None) -> None:
        with self._lock:
            self.count += 1
            self.address = address
            self.value = value
            self.time = time.time()

    def record_change(self, address: str, value: float | None) -> None:
        with self._lock:
            self.change_count += 1
            self.change_address = address
            self.change_value = value

    def snapshot(self) -> tuple[int, str | None, float | None]:
        with self._lock:
            return self.count, self.address, self.value

    def change_snapshot(self) -> tuple[int, str | None, float | None]:
        with self._lock:
            return self.change_count, self.change_address, self.change_value


def _first_number(args) -> float | None:
    for arg in args:
        if isinstance(arg, (int, float)) and not isinstance(arg, bool):
            return float(arg)
        if isinstance(arg, bool):
            return 1.0 if arg else 0.0
    return None


MOVE_EPSILON = 1e-4   # values closer than this count as the same (filters out sender jitter)


def _numbers(args) -> tuple:
    """All numeric arguments of a message, as floats. Used to decide whether a value has moved."""
    return tuple(float(arg) for arg in args if isinstance(arg, (int, float)))


class OscServer:
    def __init__(self, engine: DmxEngine, port: int, host: str = "0.0.0.0",
                 mappings: MappingTable | None = None, scenes: SceneManager | None = None):
        self._engine = engine
        self._mappings = mappings if mappings is not None else MappingTable()
        self._scenes = scenes
        self._last_scene_id: dict[str, int] = {}   # last ID recalled, per mapping address
        self._last_seen: dict[str, tuple] = {}     # last values, per address (for change detection)
        self._seen_lock = threading.Lock()
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
        if value is None or not self._moved(address, _numbers(args)):
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

    def _moved(self, address: str, values: tuple) -> bool:
        """True when any value differs from the last message at this address (or it is the first one).
        A sender that repeats the same value every frame therefore does not keep overwriting a scene."""
        with self._seen_lock:
            previous = self._last_seen.get(address)
            self._last_seen[address] = values
        moved = (previous is None or len(previous) != len(values)
                 or any(abs(a - b) > MOVE_EPSILON for a, b in zip(previous, values)))
        if moved:
            self.monitor.record_change(address, values[0] if values else None)
        return moved

    def _changed(self, address: str, value: float) -> bool:
        """True when the value differs from the last one seen at this address (exact match)."""
        with self._seen_lock:
            changed = self._last_seen.get(address) != (value,)
            self._last_seen[address] = (value,)
        if changed:
            self.monitor.record_change(address, float(value))
        return changed

    def _rising(self, address: str, value: float) -> bool:
        """True when the value has just risen to 0.5 or more (a button press, not a held stream)."""
        with self._seen_lock:
            previous = self._last_seen.get(address, (0.0,))[0]
            self._last_seen[address] = (value,)
        rising = value >= 0.5 and previous < 0.5
        if rising:
            self.monitor.record_change(address, value)
        return rising

    def _handle_builtin(self, address: str, args) -> None:
        parts = address.strip("/").split("/")
        if parts[1:] == ["blackout"] and args:
            if self._moved(address, _numbers(args)):
                self._engine.blackout = bool(args[0])
            return
        if parts[1:] == ["master"] and args:
            if self._moved(address, _numbers(args)):
                self._engine.master = float(args[0])
            return
        if self._scenes is not None and parts[1:] == ["scene"] and args:
            # Every message recalls the scene, so a button can recall the same scene again. A stream of the
            # same ID will keep recalling it: use /martin/scene/press or the mapping for streamed control.
            self._scenes.recall(int(args[0]))
            return
        if self._scenes is not None and parts[1:] == ["scene", "recall"] and args:
            self._scenes.recall(int(args[0]))
            return
        if self._scenes is not None and parts[1:] == ["scene", "press"] and len(args) >= 2:
            # A button: args are (value, scene id). Recall once per press (the value rising to 0.5), however
            # often the button sends. Each button is tracked separately by its scene ID.
            scene_id = int(args[1])
            if self._rising(f"{address}#{scene_id}", float(args[0])):
                self._scenes.recall(scene_id)
            return
        if self._scenes is not None and parts[1:] == ["scene", "fade"] and args:
            self._scenes.fade_time = max(0.0, float(args[0]))
            return
        if self._scenes is not None and parts[1:] == ["playlist", "next"] and args:
            if self._rising(address, float(args[0])):
                self._scenes.step(1)
            return
        if self._scenes is not None and parts[1:] == ["playlist", "prev"] and args:
            if self._rising(address, float(args[0])):
                self._scenes.step(-1)
            return
        if self._scenes is not None and parts[1:] == ["playlist", "go"] and args:
            if self._changed(address, int(args[0])):
                self._scenes.go(int(args[0]))
            return

        if len(parts) < 3 or not parts[1].isdigit():
            return
        index = int(parts[1]) - 1
        if not 0 <= index < len(self._engine.fixtures):
            return
        param = "/".join(parts[2:])
        if param in _OSC_COMPONENTS and args:
            # One colour channel at a time (for faders): the other two keep their current values.
            field_name, component = _OSC_COMPONENTS[param]
            if self._moved(address, _numbers(args)):
                self._engine.modify_fixture(index, lambda st, f=field_name, c=component, v=float(args[0]): {
                    f: _with_component(getattr(st, f), c, v)})
            return
        values = _OSC_PARAMS.get(param)
        if values is None or len(args) < values[0]:
            return
        if not self._moved(address, _numbers(args)):
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
    "aura/preset": (1, lambda v: {"aura_color_preset": max(0, min(48, int(v)))}),
    "beam/flash/duration": (1, lambda v: {"beam_flash_duration": max(0, min(255, int(v)))}),
    "beam/flash/rate": (1, lambda v: {"beam_flash_rate": max(0, min(255, int(v)))}),
    "beam/special": (1, lambda v: {"beam_special_effect": max(0, min(255, int(v)))}),
    "aura/strobe": (1, lambda v: {"aura_strobe": max(0, min(255, int(v)))}),
}

# single colour channels: param -> (FixtureState field, component index)
_OSC_COMPONENTS = {
    "beam/red": ("beam_rgb", 0), "beam/green": ("beam_rgb", 1), "beam/blue": ("beam_rgb", 2),
    "aura/red": ("aura_rgb", 0), "aura/green": ("aura_rgb", 1), "aura/blue": ("aura_rgb", 2),
}


def _with_component(rgb, index: int, value: float) -> tuple:
    values = list(rgb)
    values[index] = max(0.0, min(1.0, float(value)))
    return tuple(values)
