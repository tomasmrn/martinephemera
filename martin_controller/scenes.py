"""Scenes (saved looks, each with an ID) and playlists (ordered scene IDs) for playback.

A scene stores every fixture's FixtureState, in fixture order, plus the master level.
Blackout is not part of a scene. Recalling a scene replaces the fixture states straight away.
"""

import threading
import time
from dataclasses import dataclass, field, replace

from .fixture import FixtureState

MAX_SCENE_ID = 9999


@dataclass
class Scene:
    id: int
    name: str = ""
    fixtures: list[dict] = field(default_factory=list)   # FixtureState dicts, in fixture order
    master: float = 1.0

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "fixtures": self.fixtures, "master": self.master}

    @classmethod
    def from_dict(cls, data: dict) -> "Scene":
        scene_id = int(data["id"])
        if not 0 <= scene_id <= MAX_SCENE_ID:
            raise ValueError(f"scene id must be 0-{MAX_SCENE_ID}, got {scene_id}")
        return cls(id=scene_id, name=str(data.get("name", "")),
                   fixtures=list(data.get("fixtures", [])), master=float(data.get("master", 1.0)))


@dataclass
class PlaylistItem:
    scene_id: int
    hold: float = 0.0   # seconds before auto-advance when auto-advance is on; 0 = wait for Next
    fade: float = 0.0   # seconds to fade into this scene; 0 = cut straight to it

    def to_dict(self) -> dict:
        return {"scene_id": self.scene_id, "hold": self.hold, "fade": self.fade}

    @classmethod
    def from_dict(cls, data: dict) -> "PlaylistItem":
        return cls(scene_id=int(data["scene_id"]),
                   hold=max(0.0, float(data.get("hold", 0.0))),
                   fade=max(0.0, float(data.get("fade", 0.0))))


# Fields that blend during a fade. Everything else (effects, presets, strobe mode, ...) switches
# to the target value as soon as the fade starts, because blending between effect numbers means nothing.
_FLOAT_FIELDS = ("beam_intensity", "aura_intensity")
_INT_FIELDS = ("beam_flash_duration", "beam_flash_rate", "fx_speed")
_RGB_FIELDS = ("beam_rgb", "aura_rgb")
FADE_FRAME_SECONDS = 1 / 30


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interpolate_state(start: FixtureState, end: FixtureState, t: float) -> FixtureState:
    """Blend the continuous settings from `start` towards `end` by t (0.0 to 1.0).
    Discrete settings take the `end` value straight away."""
    t = max(0.0, min(1.0, t))
    if t >= 1.0:
        return end
    values = {}
    for name in _FLOAT_FIELDS:
        values[name] = _mix(getattr(start, name), getattr(end, name), t)
    for name in _INT_FIELDS:
        values[name] = round(_mix(getattr(start, name), getattr(end, name), t))
    for name in _RGB_FIELDS:
        values[name] = tuple(_mix(a, b, t) for a, b in zip(getattr(start, name), getattr(end, name)))
    values["aura_pixels"] = tuple(
        tuple(_mix(a, b, t) for a, b in zip(pa, pb)) for pa, pb in zip(start.aura_pixels, end.aura_pixels)
    )
    for name in ("beam_ctc_kelvin", "aura_ctc_kelvin"):
        a, b = getattr(start, name), getattr(end, name)
        if a is not None and b is not None:
            values[name] = round(_mix(a, b, t))
    return replace(end, **values)


class SceneManager:
    """Holds the scenes and playlist, and plays them back on a fixture engine."""

    def __init__(self, engine, scenes: list[Scene] | None = None, playlist: list[PlaylistItem] | None = None):
        self._engine = engine
        self._lock = threading.Lock()
        self._scenes: dict[int, Scene] = {}
        self._playlist: list[PlaylistItem] = []
        self.set_content(scenes or [], playlist or [])
        self.position: int | None = None      # index into the playlist of the scene last played
        self.auto_advance = False
        self.version = 0                      # goes up each time a scene is applied, so the UI can refresh
        self.fade_time = 0.0                  # seconds to fade into a scene; 0 = instant
        self._item_started = time.monotonic()
        self._fade: dict | None = None        # the fade in progress, if any
        self._fade_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- content ---------------------------------------------------------------

    @property
    def scenes(self) -> list[Scene]:
        with self._lock:
            return [self._scenes[k] for k in sorted(self._scenes)]

    @property
    def playlist(self) -> list[PlaylistItem]:
        with self._lock:
            return list(self._playlist)

    def set_content(self, scenes: list[Scene], playlist: list[PlaylistItem]) -> None:
        with self._lock:
            self._scenes = {s.id: s for s in scenes}
            self._playlist = [item for item in playlist if item.scene_id in self._scenes]
            self.position = None

    def get(self, scene_id: int) -> Scene | None:
        with self._lock:
            return self._scenes.get(scene_id)

    def store(self, scene_id: int, name: str) -> Scene:
        """Save the current look as scene `scene_id`, replacing any scene with that ID."""
        if not 0 <= scene_id <= MAX_SCENE_ID:
            raise ValueError(f"scene id must be 0-{MAX_SCENE_ID}, got {scene_id}")
        scene = Scene(
            id=scene_id,
            name=name,
            fixtures=[f.state.to_dict() for f in self._engine.fixtures],
            master=self._engine.master,
        )
        with self._lock:
            self._scenes[scene_id] = scene
        return scene

    def rename(self, scene_id: int, name: str) -> bool:
        """Change a scene's name. Its look, ID and playlist position are unchanged."""
        with self._lock:
            scene = self._scenes.get(scene_id)
            if scene is None:
                return False
            self._scenes[scene_id] = replace(scene, name=name)
            return True

    def delete(self, scene_id: int) -> None:
        with self._lock:
            self._scenes.pop(scene_id, None)
            self._playlist = [item for item in self._playlist if item.scene_id != scene_id]
            self.position = None

    def set_playlist(self, items: list[PlaylistItem]) -> None:
        with self._lock:
            self._playlist = [item for item in items if item.scene_id in self._scenes]
            if self.position is not None and self.position >= len(self._playlist):
                self.position = None

    # --- playback --------------------------------------------------------------

    def recall(self, scene_id: int) -> bool:
        """Play scene `scene_id` now. If it is in the playlist, the playlist position follows it."""
        with self._lock:
            scene = self._scenes.get(scene_id)
            if scene is None:
                return False
            positions = [i for i, item in enumerate(self._playlist) if item.scene_id == scene_id]
            self.position = positions[0] if positions else None
            self._item_started = time.monotonic()
        self._apply(scene)
        return True

    def go(self, position: int) -> bool:
        """Play the playlist item at `position` (0-based)."""
        with self._lock:
            if not 0 <= position < len(self._playlist):
                return False
            item = self._playlist[position]
            self.position = position
            self._item_started = time.monotonic()
            scene = self._scenes[item.scene_id]
        self._apply(scene, fade_time=item.fade)
        return True

    def step(self, delta: int) -> bool:
        """Move forward (+1) or back (-1) through the playlist, wrapping at the ends."""
        with self._lock:
            count = len(self._playlist)
        if count == 0:
            return False
        current = -1 if self.position is None else self.position
        return self.go((current + delta) % count)

    def tick(self, now: float | None = None) -> None:
        """Call regularly. When auto-advance is on, moves on once the current item's hold time has passed."""
        if not self.auto_advance or self.position is None:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            if self.position >= len(self._playlist):
                return
            hold = self._playlist[self.position].hold
            started = self._item_started
        if hold > 0 and now - started >= hold:
            self.step(1)

    def _apply(self, scene: Scene, fade_time: float | None = None) -> None:
        """Apply a scene. `fade_time` defaults to the manager's fade time (used by direct recalls)."""
        self.version += 1
        duration = self.fade_time if fade_time is None else fade_time
        fixtures = self._engine.fixtures
        if duration <= 0 or not fixtures:
            self._cancel_fade()
            for index, state in enumerate(scene.fixtures[:len(fixtures)]):
                self._engine.replace_fixture(
                    index, replace(fixtures[index], state=FixtureState.from_dict(state))
                )
            self._engine.master = scene.master
            return

        # Start a fade from whatever is showing now (even if another fade was running).
        targets = [FixtureState.from_dict(scene.fixtures[i]) if i < len(scene.fixtures) else None
                   for i in range(len(fixtures))]
        with self._fade_lock:
            self._fade = {
                "started": time.monotonic(),
                "duration": duration,
                "starts": [f.state for f in fixtures],
                "targets": targets,
                "master_start": self._engine.master,
                "master_end": scene.master,
            }
        self.update_fade()

    def _cancel_fade(self) -> None:
        with self._fade_lock:
            self._fade = None

    @property
    def fading(self) -> bool:
        with self._fade_lock:
            return self._fade is not None

    def update_fade(self, now: float | None = None) -> None:
        """Move the fade in progress to time `now`. The fade thread calls this about 30 times a second."""
        with self._fade_lock:
            fade = self._fade
        if fade is None:
            return
        now = time.monotonic() if now is None else now
        t = (now - fade["started"]) / fade["duration"]
        fixtures = self._engine.fixtures
        for index, (start, target) in enumerate(zip(fade["starts"], fade["targets"])):
            if target is None or index >= len(fixtures):
                continue
            state = interpolate_state(start, target, t)
            self._engine.replace_fixture(index, replace(fixtures[index], state=state))
        self._engine.master = _mix(fade["master_start"], fade["master_end"], max(0.0, min(1.0, t)))
        if t >= 1.0:
            with self._fade_lock:
                if self._fade is fade:
                    self._fade = None

    def start(self) -> None:
        """Start the fade thread. Needed for fades to run; instant recalls work without it."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._fade_loop, name="scene-fade", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _fade_loop(self) -> None:
        while not self._stop.is_set():
            if self.fading:
                self.update_fade()
                self._stop.wait(FADE_FRAME_SECONDS)
            else:
                self._stop.wait(0.05)
