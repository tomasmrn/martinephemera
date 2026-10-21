"""Settings file: network options, fixtures and user presets, stored as JSON."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .artnet import ARTNET_PORT
from .fixture import Fixture
from .mapping import Mapping

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"


@dataclass
class NetworkSettings:
    protocol: str = "artnet"               # "artnet" or "sacn"
    target_ip: str = "255.255.255.255"     # Art-Net: broadcast or node IP. sACN: blank = multicast
    artnet_port: int = ARTNET_PORT         # UDP port for Art-Net (6454) or sACN (5568)
    refresh_hz: float = 30.0               # how often the full DMX frame is re-sent
    osc_enabled: bool = False
    osc_host: str = "0.0.0.0"              # 0.0.0.0 = any device; 127.0.0.1 = this computer only
    osc_port: int = 8000                   # TouchOSC / TouchDesigner send to this port


@dataclass
class Settings:
    network: NetworkSettings = field(default_factory=NetworkSettings)
    fixtures: list[Fixture] = field(default_factory=lambda: [Fixture()])
    presets: dict[str, dict] = field(default_factory=dict)  # name -> FixtureState dict
    mappings: list[Mapping] = field(default_factory=list)   # OSC address -> parameter
    master: float = 1.0                                       # master dimmer, 0.0-1.0

    def to_dict(self) -> dict:
        return {
            "network": asdict(self.network),
            "fixtures": [f.to_dict() for f in self.fixtures],
            "presets": self.presets,
            "mappings": [m.to_dict() for m in self.mappings],
            "master": self.master,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        network = NetworkSettings(**data.get("network", {}))
        fixtures = [Fixture.from_dict(f) for f in data.get("fixtures", [])] or [Fixture()]
        mappings = [Mapping.from_dict(m) for m in data.get("mappings", [])]
        return cls(network=network, fixtures=fixtures, presets=data.get("presets", {}), mappings=mappings,
                   master=float(data.get("master", 1.0)))


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """Load settings, or return defaults if the file is missing or unreadable."""
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")


# --- project files: a whole show (network, fixtures, presets, mappings, master) in one JSON file ---

PROJECT_FORMAT = "martin-vdo-project"
PROJECT_VERSION = 1


def save_project(settings: Settings, path: Path) -> None:
    data = {"format": PROJECT_FORMAT, "version": PROJECT_VERSION, **settings.to_dict()}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project(path: Path) -> Settings:
    """Load a project file. Raises ValueError if it isn't a project file this version can read."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != PROJECT_FORMAT:
        raise ValueError("This is not a Martin VDO project file.")
    if data.get("version", 0) > PROJECT_VERSION:
        raise ValueError("This project was saved by a newer version of the controller.")
    return Settings.from_dict(data)
