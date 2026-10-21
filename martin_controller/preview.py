"""Virtual fixture preview: draws the beam and aura colour from a FixtureState.

It shows RGB colour, intensity and blackout. Built-in effects and colour presets
are shown as text, because the manual doesn't give their exact colours or timing.
"""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .effects import COLOR_PRESET_NAMES, COLOR_PRESET_RGB, FX_NAMES
from .fixture import FixtureState


def _effective_rgb(preset: int, rgb) -> tuple:
    """A colour preset overrides the RGB channels on the fixture, so the preview does the same."""
    return COLOR_PRESET_RGB[preset - 1] if preset else rgb


def _color(rgb, level: float) -> QColor:
    """Scale an (r, g, b) tuple of 0.0-1.0 by a brightness level, to a QColor."""
    return QColor(*(round(max(0.0, min(1.0, c * level)) * 255) for c in rgb))


class FixturePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: FixtureState | None = None
        self._blackout = False
        self._extended = False
        self._master = 1.0
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def show_state(self, state: FixtureState, blackout: bool, extended: bool = False,
                   master: float = 1.0) -> None:
        key = (state, blackout, extended, master)
        if key != (self._state, self._blackout, self._extended, self._master):
            self._state = state
            self._blackout = blackout
            self._extended = extended
            self._master = master
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().window())
        if self._state is None:
            return

        state = self._state
        beam_level = 0.0 if self._blackout else state.beam_intensity * self._master
        aura_level = 0.0 if self._blackout else state.aura_intensity * self._master
        beam = _color(_effective_rgb(state.beam_color_preset, state.beam_rgb), beam_level)
        aura = _color(_effective_rgb(state.aura_color_preset, state.aura_rgb), aura_level)

        # Layout: the fixture drawing on the left, text on the right.
        height = self.height()
        cx, cy = height * 0.5 + 10, height * 0.5
        radius = height * 0.42

        painter.setPen(Qt.NoPen)
        painter.setBrush(aura)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        if self._extended:
            # Pixels 1-72 drawn around the ring in number order (not the physical layout).
            ring = radius * 0.86
            dot = max(3.0, radius * 0.08)
            for pixel, rgb in enumerate(state.aura_pixels):
                angle = 2 * math.pi * pixel / len(state.aura_pixels)
                x = cx + ring * math.cos(angle)
                y = cy + ring * math.sin(angle)
                painter.setBrush(_color(_effective_rgb(0, rgb), aura_level))
                painter.drawEllipse(QRectF(x - dot / 2, y - dot / 2, dot, dot))

        painter.setPen(QPen(QColor(40, 40, 40), 2))
        painter.setBrush(beam)
        inner = radius * 0.55
        painter.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))

        painter.setPen(self.palette().windowText().color())
        text_x = cx + radius + 24
        lines = self._text_lines(state)
        font = QFont(self.font())
        font.setPointSize(font.pointSize() + 1)
        painter.setFont(font)
        line_height = painter.fontMetrics().height() + 4
        y = cy - (len(lines) * line_height) / 2 + painter.fontMetrics().ascent()
        for line in lines:
            painter.drawText(int(text_x), int(y), line)
            y += line_height
        painter.end()

    def _text_lines(self, state: FixtureState) -> list[str]:
        lines = []
        if self._blackout:
            lines.append("BLACKOUT")
        lines.append("Mode: Extended (243 ch)" if self._extended else "Mode: Basic (27 ch)")
        lines.append(f"Beam {round(state.beam_intensity * 100)}%   Aura {round(state.aura_intensity * 100)}%")
        if state.beam_color_preset:
            lines.append(f"Beam preset: {COLOR_PRESET_NAMES[state.beam_color_preset - 1]}")
        if state.aura_color_preset:
            lines.append(f"Aura preset: {COLOR_PRESET_NAMES[state.aura_color_preset - 1]}")
        if state.fx:
            lines.append(f"Effect: {FX_NAMES.get(state.fx, f'#{state.fx}')}")
            lines.append(speed_text(state.fx_speed))
        return lines


def speed_text(value: int) -> str:
    """Describe an FX speed value (0-255, 128 = stopped) in words."""
    if value == 128:
        return "Speed: stopped"
    direction = "reverse" if value < 128 else "forward"
    return f"Speed: {direction} {value}"
