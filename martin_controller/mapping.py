"""Map incoming OSC addresses (for example from TouchDesigner) to fixture parameters.

A Mapping takes one OSC address, scales its first numeric argument from an input range
to an output range, and sets one parameter on one fixture (or on all fixtures).
"""

import threading
from dataclasses import asdict, dataclass

from .effects import (AURA_COLOUR_FX, AURA_INTENSITY_FX, BEAM_COLOUR_FX, BEAM_INTENSITY_FX,
                      COMBINED_FX)
from .fixture import FixtureState


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    kind: str                  # "float", "int" (rounded) or "bool" (global only)
    lo: float
    hi: float
    field: str | None = None   # FixtureState field, or None for global parameters
    index: int | None = None   # component of an RGB tuple field
    choices: tuple = ()        # if set, the value snaps to the nearest of these

    def changes_for(self, state: FixtureState, value: float) -> dict:
        """Return FixtureState changes that set this parameter to `value`."""
        if self.choices:
            value = min(self.choices, key=lambda c: abs(c - value))
        value = max(self.lo, min(self.hi, value))
        if self.kind == "int":
            value = int(round(value))
        if self.index is None:
            return {self.field: value}
        rgb = list(getattr(state, self.field))
        rgb[self.index] = value
        return {self.field: tuple(rgb)}


def _float(key, label, field, index=None):
    return Parameter(key, label, "float", 0.0, 1.0, field, index)


def _int(key, label, field, hi):
    return Parameter(key, label, "int", 0, hi, field)


def _effect_group(key, label, numbers):
    """An effect parameter: the value snaps to the nearest effect in its manual group."""
    return Parameter(key, label, "int", min(numbers), max(numbers), "fx", choices=numbers)


PARAMETERS: dict[str, Parameter] = {p.key: p for p in [
    _float("beam_intensity", "Beam intensity", "beam_intensity"),
    _float("beam_red", "Beam red", "beam_rgb", 0),
    _float("beam_green", "Beam green", "beam_rgb", 1),
    _float("beam_blue", "Beam blue", "beam_rgb", 2),
    _int("beam_color_preset", "Beam colour preset (0 = none, 1-48)", "beam_color_preset", 48),
    _float("aura_intensity", "Aura intensity", "aura_intensity"),
    _float("aura_red", "Aura red", "aura_rgb", 0),
    _float("aura_green", "Aura green", "aura_rgb", 1),
    _float("aura_blue", "Aura blue", "aura_rgb", 2),
    _int("aura_color_preset", "Aura colour preset (0 = none, 1-48)", "aura_color_preset", 48),
    _int("fx", "Built-in effect (0-255, raw)", "fx", 255),
    _effect_group("fx_beam_intensity", "Beam intensity effect", BEAM_INTENSITY_FX),
    _effect_group("fx_beam_colour", "Beam colour effect", BEAM_COLOUR_FX),
    _effect_group("fx_aura_intensity", "Aura intensity effect", AURA_INTENSITY_FX),
    _effect_group("fx_aura_colour", "Aura colour effect", AURA_COLOUR_FX),
    _effect_group("fx_combined", "Beam and aura combined effect", COMBINED_FX),
    _int("fx_speed", "Effect speed (128 = stopped)", "fx_speed", 255),
    _int("beam_flash_duration", "Beam flash duration (0-255)", "beam_flash_duration", 255),
    _int("beam_flash_rate", "Beam flash rate (0-255)", "beam_flash_rate", 255),
    _int("beam_special_effect", "Beam special effect (0-255)", "beam_special_effect", 255),
    _int("aura_strobe", "Aura strobe / shutter (0-255)", "aura_strobe", 255),
    Parameter("master", "Master dimmer (0-1)", "float", 0.0, 1.0),
    Parameter("scene", "Recall scene by ID (fires when the ID changes)", "int", 0, 9999),
    Parameter("blackout", "Blackout (on when >= 0.5)", "bool", 0.0, 1.0),
]}


@dataclass
class Mapping:
    address: str                 # OSC address, for example "/td/fader1"
    parameter: str               # key in PARAMETERS
    fixture: int | None = None   # 0-based fixture index, None = all fixtures
    in_min: float = 0.0
    in_max: float = 1.0
    out_min: float = 0.0
    out_max: float = 1.0

    def scale(self, value: float) -> float:
        """Map `value` from the input range to the output range, clamped to the input range.
        The input range may be inverted (in_min > in_max)."""
        span = self.in_max - self.in_min
        t = 0.0 if span == 0 else (value - self.in_min) / span
        t = max(0.0, min(1.0, t))
        return self.out_min + t * (self.out_max - self.out_min)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Mapping":
        known = {"address", "parameter", "fixture", "in_min", "in_max", "out_min", "out_max"}
        return cls(**{k: v for k, v in data.items() if k in known})


class MappingTable:
    """Lookup of mappings by OSC address. Replaced as a whole, so the OSC thread never sees a half update."""

    def __init__(self, mappings: list[Mapping] | None = None):
        self._lock = threading.Lock()
        self._by_address: dict[str, tuple[Mapping, ...]] = {}
        self.set(mappings or [])

    def set(self, mappings: list[Mapping]) -> None:
        by_address: dict[str, list[Mapping]] = {}
        for mapping in mappings:
            by_address.setdefault(mapping.address, []).append(mapping)
        with self._lock:
            self._by_address = {address: tuple(items) for address, items in by_address.items()}

    def lookup(self, address: str) -> tuple[Mapping, ...]:
        return self._by_address.get(address, ())

