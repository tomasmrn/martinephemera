"""A tall 2D silhouette of the puppet, with the body lit by the fixture's light.

The drawing is a simple silhouette: the headpiece, head, eyes, shoulders, arms hanging at the sides,
and the skirt. Only the skirt takes colour. The shoulder piece sits over the top of the skirt and stays dark.
The body's light is the beam colour at the beam intensity, scaled by the master dimmer. Blackout turns
it off. The glow spills softly past the body's edges.

puppet_levels also returns the aura levels, but the drawing does not use them.
Built-in effects are not animated, because their timing isn't known from the manual.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .effects import COLOR_PRESET_RGB, FX_NAMES
from .fixture import FixtureState

PUPPET_SIZE = (300, 600)   # width and height in pixels
PUPPET_WIDTH_SCALE = 1.05  # the whole figure is drawn 5% wider than the drawing coordinates
SILHOUETTE = QColor(14, 16, 22)
EYE = QColor(38, 42, 54)
BACKGROUND = QColor(78, 82, 90)   # flat grey, so the dark silhouette reads

# Shapes in normalised coordinates (0.0 to 1.0 across the widget, top-left origin).
HEAD = [(0.50, 0.185), (0.575, 0.205), (0.61, 0.265), (0.605, 0.33), (0.58, 0.39),
        (0.54, 0.425), (0.50, 0.435), (0.46, 0.425), (0.42, 0.39), (0.395, 0.33),
        (0.39, 0.265), (0.425, 0.205)]
# The bust piece: a broad block with sloping shoulders, dark, sitting over the top of the skirt.
SHOULDERS = [(0.431, 0.40), (0.50, 0.395), (0.569, 0.40), (0.637, 0.42), (0.696, 0.47),
             (0.711, 0.55), (0.696, 0.62), (0.304, 0.62), (0.289, 0.55), (0.304, 0.47), (0.363, 0.42)]
SKIRT = [(0.333, 0.58), (0.667, 0.58), (0.721, 0.90), (0.279, 0.90)]
CART = [(0.30, 0.90), (0.70, 0.90), (0.70, 0.93), (0.30, 0.93)]
LEFT_ARM = [(0.355, 0.46), (0.31, 0.58), (0.30, 0.70)]     # hanging down at the side
RIGHT_ARM = [(0.645, 0.46), (0.69, 0.58), (0.70, 0.70)]
LEFT_HAND = (0.30, 0.72)
RIGHT_HAND = (0.70, 0.72)


def _polygon(points, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(points[0][0] * w, points[0][1] * h)
    for x, y in points[1:]:
        path.lineTo(x * w, y * h)
    path.closeSubpath()
    return path


def _smooth_closed(points, w: float, h: float) -> QPainterPath:
    """A smooth closed outline through the points (curves between the midpoints of each edge)."""
    count = len(points)
    mids = [((points[i][0] + points[(i + 1) % count][0]) / 2,
             (points[i][1] + points[(i + 1) % count][1]) / 2) for i in range(count)]
    path = QPainterPath()
    path.moveTo(mids[-1][0] * w, mids[-1][1] * h)
    for i in range(count):
        path.quadTo(points[i][0] * w, points[i][1] * h, mids[i][0] * w, mids[i][1] * h)
    path.closeSubpath()
    return path


def _ellipse(cx: float, cy: float, rx: float, ry: float, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QRectF((cx - rx) * w, (cy - ry) * h, 2 * rx * w, 2 * ry * h))
    return path


def _polyline(points, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(points[0][0] * w, points[0][1] * h)
    for x, y in points[1:]:
        path.lineTo(x * w, y * h)
    return path


def puppet_levels(state: FixtureState, blackout: bool, master: float):
    """Return (body_rgb, body_level, aura_rgb, aura_level), each level 0.0 to 1.0.
    The body uses the beam colour and intensity."""
    beam = COLOR_PRESET_RGB[state.beam_color_preset - 1] if state.beam_color_preset else tuple(state.beam_rgb)
    aura = COLOR_PRESET_RGB[state.aura_color_preset - 1] if state.aura_color_preset else tuple(state.aura_rgb)
    if blackout:
        return beam, 0.0, aura, 0.0
    body_level = max(0.0, min(1.0, state.beam_intensity * master))
    aura_level = max(0.0, min(1.0, state.aura_intensity * master))
    return beam, body_level, aura, aura_level


def _colour(rgb, level: float, alpha: float = 1.0) -> QColor:
    channels = [round(max(0.0, min(1.0, c * level)) * 255) for c in rgb]
    colour = QColor(*channels)
    colour.setAlphaF(max(0.0, min(1.0, alpha)))
    return colour


class PuppetView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rgb = ((0.0, 0.0, 0.0), 0.0, (0.0, 0.0, 0.0), 0.0)
        self._effect = ""
        # Fixed size: the puppet keeps its size when the window is resized.
        self.setFixedSize(*PUPPET_SIZE)

    def show_state(self, state: FixtureState, blackout: bool, master: float) -> None:
        levels = puppet_levels(state, blackout, master)
        effect = FX_NAMES.get(state.fx, "") if state.fx else ""
        if (levels, effect) != (self._rgb, self._effect):
            self._rgb = levels
            self._effect = effect
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        body_rgb, body_level, _aura_rgb, _aura_level = self._rgb
        w, h = float(self.width()), float(self.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(self.rect(), BACKGROUND)
        # Widen the figure from its centre line. The background and caption are not affected.
        painter.translate(w / 2, 0)
        painter.scale(PUPPET_WIDTH_SCALE, 1.0)
        painter.translate(-w / 2, 0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(SILHOUETTE)
        painter.drawEllipse(QRectF(0.18 * w, 0.92 * h, 0.64 * w, 0.06 * h))          # ground
        painter.drawPath(_polygon(CART, w, h))                                       # cart base
        for wheel_x in (0.34, 0.66):
            painter.drawEllipse(QRectF((wheel_x - 0.04) * w, 0.90 * h, 0.08 * w, 0.08 * h))

        # Headpiece: a thick crescent behind the head
        # A crescent: an outer arc with a larger inner arc taken out of it. The inner arc touches the top of
        # the head, and curves away at the sides, so the tips reach down beside the head.
        headpiece = _ellipse(0.5, 0.30, 0.21, 0.22, w, h).subtracted(_ellipse(0.5, 0.36, 0.19, 0.175, w, h))
        painter.drawPath(headpiece)

        # Arms hanging down at the sides
        arm_pen = QPen(SILHOUETTE, 0.05 * w)
        arm_pen.setCapStyle(Qt.RoundCap)
        arm_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(arm_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_polyline(LEFT_ARM, w, h))
        painter.drawPath(_polyline(RIGHT_ARM, w, h))
        painter.setPen(Qt.NoPen)
        painter.setBrush(SILHOUETTE)
        for hand_x, hand_y in (LEFT_HAND, RIGHT_HAND):
            painter.drawEllipse(QRectF((hand_x - 0.03) * w, (hand_y - 0.04) * h, 0.06 * w, 0.08 * h))

        # Skirt: the only lit part. The shoulder piece sits over its top, in dark.
        skirt = _polygon(SKIRT, w, h)
        self._draw_glow(painter, skirt, body_rgb, body_level, w)
        gradient = QLinearGradient(0, 0.58 * h, 0, 0.90 * h)
        gradient.setColorAt(0.0, _colour(body_rgb, max(0.15, body_level * 0.65)))
        gradient.setColorAt(0.5, _colour(body_rgb, max(0.2, body_level)))
        gradient.setColorAt(1.0, _colour(body_rgb, max(0.25, body_level * 0.9)))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(skirt)

        # Shoulder piece (dark) over the top of the skirt, then the neck and head
        painter.setBrush(SILHOUETTE)
        painter.drawPath(_smooth_closed(SHOULDERS, w, h))

        # Neck and head (silhouette), with the eyes as lighter almond shapes
        painter.setBrush(SILHOUETTE)
        painter.drawRect(QRectF(0.47 * w, 0.40 * h, 0.06 * w, 0.04 * h))
        painter.drawPath(_smooth_closed(HEAD, w, h))
        painter.setBrush(EYE)
        for cx in (0.455, 0.545):
            eye = QPainterPath()
            eye.moveTo((cx - 0.028) * w, 0.31 * h)
            eye.quadTo(cx * w, 0.292 * h, (cx + 0.028) * w, 0.31 * h)
            eye.quadTo(cx * w, 0.328 * h, (cx - 0.028) * w, 0.31 * h)
            painter.drawPath(eye)

        # Caption (drawn without the widening)
        painter.resetTransform()
        painter.setPen(QColor(150, 158, 175))
        font = painter.font()
        font.setPointSize(max(9, font.pointSize()))
        painter.setFont(font)
        caption = f"Effect: {self._effect}" if self._effect else "No effect"
        painter.drawText(QRectF(0, 0.955 * h, w, 0.045 * h), Qt.AlignHCenter | Qt.AlignVCenter, caption)
        painter.end()

    def _draw_glow(self, painter: QPainter, body: QPainterPath, rgb, level: float, w: float) -> None:
        """Soft light spilling past the body's edges, as wide strokes that fade outwards."""
        if level <= 0:
            return
        painter.setBrush(Qt.NoBrush)
        for width, alpha in ((0.05, 0.05), (0.03, 0.08), (0.015, 0.14)):
            pen = QPen(_colour(rgb, level, alpha), width * w)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(body)
