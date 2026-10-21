"""Presets: saved fixture looks, stored with a little information so they can be recognised.

A preset is stored as {"state": FixtureState dict, "mode": "basic" | "extended", "saved": "YYYY-MM-DD HH:MM"}.
Presets saved by earlier versions are a bare FixtureState dict; they still load, with mode "basic" and no date.
"""

from datetime import datetime

from .effects import COLOR_PRESET_NAMES, COLOR_PRESET_RGB, FX_NAMES
from .fixture import FixtureState


def make_preset(state: FixtureState, mode: str, saved: datetime | None = None) -> dict:
    when = (saved or datetime.now()).strftime("%Y-%m-%d %H:%M")
    return {"state": state.to_dict(), "mode": mode, "saved": when}


def preset_state(data: dict) -> FixtureState:
    return FixtureState.from_dict(data["state"] if "state" in data else data)


def preset_mode(data: dict) -> str:
    return data.get("mode", "basic") if "state" in data else "basic"


def preset_saved(data: dict) -> str:
    return data.get("saved", "")


def beam_colour(state: FixtureState) -> tuple[float, float, float]:
    """The beam colour the fixture will show, before intensity: a colour preset overrides the RGB sliders."""
    if state.beam_color_preset:
        return COLOR_PRESET_RGB[state.beam_color_preset - 1]
    return tuple(state.beam_rgb)


def swatch_hex(data: dict) -> str:
    """A '#rrggbb' colour for the list swatch: beam colour scaled by beam intensity."""
    state = preset_state(data)
    level = max(0.0, min(1.0, state.beam_intensity))
    return "#" + "".join(f"{round(c * level * 255):02x}" for c in beam_colour(state))


def scene_swatch_hex(fixture_states: list[dict]) -> str:
    """One colour for a scene: the average swatch of its fixtures. Grey when the scene has no fixtures."""
    if not fixture_states:
        return "#555555"
    colours = [[int(swatch_hex(state)[i:i + 2], 16) for i in (1, 3, 5)] for state in fixture_states]
    average = [round(sum(c[channel] for c in colours) / len(colours)) for channel in range(3)]
    return "#" + "".join(f"{value:02x}" for value in average)


def describe(data: dict) -> list[str]:
    """Short, human-readable lines for the details panel."""
    state = preset_state(data)
    lines = [f"Mode: {preset_mode(data).capitalize()}"]
    if preset_saved(data):
        lines.append(f"Saved: {preset_saved(data)}")
    lines.append(f"Beam {round(state.beam_intensity * 100)} %   Aura {round(state.aura_intensity * 100)} %")

    if state.beam_color_preset:
        lines.append(f"Beam colour: {COLOR_PRESET_NAMES[state.beam_color_preset - 1]}")
    else:
        r, g, b = (round(c * 100) for c in state.beam_rgb)
        lines.append(f"Beam RGB: {r} % / {g} % / {b} %")
    if state.aura_color_preset:
        lines.append(f"Aura colour: {COLOR_PRESET_NAMES[state.aura_color_preset - 1]}")
    else:
        r, g, b = (round(c * 100) for c in state.aura_rgb)
        lines.append(f"Aura RGB: {r} % / {g} % / {b} %")

    if state.fx:
        lines.append(f"Effect: {FX_NAMES.get(state.fx, f'#{state.fx}')} (speed {state.fx_speed})")
    else:
        lines.append("Effect: none")
    return lines
