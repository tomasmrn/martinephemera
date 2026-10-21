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

    def to_dict(self) -> dict:
        return {"scene_id": self.scene_id, "hold": self.hold}

    @classmethod
    def from_dict(cls, data: dict) -> "PlaylistItem":
        return cls(scene_id=int(data["scene_id"]), hold=max(0.0, float(data.get("hold", 0.0))))


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
        self._item_started = time.monotonic()

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
            self.position = position
            self._item_started = time.monotonic()
            scene = self._scenes[self._playlist[position].scene_id]
        self._apply(scene)
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

    def _apply(self, scene: Scene) -> None:
        self.version += 1
        fixtures = self._engine.fixtures
        for index, state in enumerate(scene.fixtures[:len(fixtures)]):
            self._engine.replace_fixture(
                index, replace(fixtures[index], state=FixtureState.from_dict(state))
            )
        self._engine.master = scene.master
