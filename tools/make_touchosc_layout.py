"""Generate a TouchOSC layout for the Martin VDO Atomic Bold controller (landscape, 1920 x 1080).

Run from the project folder:

    .venv\\Scripts\\python tools\\make_touchosc_layout.py

It writes tools\\Martin_VDO_Atomic_Bold.tosc, which opens in the TouchOSC editor on the desktop.
Then send it to the phone from the editor. In the phone's connection settings, set the host to this
computer's IP address and the port to 8000 (the app's OSC port).

Pages:
  Manual  - effect number and speed (with Stop), and the strobe and flash controls
  Light   - beam and aura RGB, and the colour presets
  Scenes  - 4 x 4 grid of buttons, one per scene ID (1-16)

Every page also has the three vertical faders (aura, beam and master dimmers) and a blackout toggle
on the right.
"""

import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

WIDTH, HEIGHT = 1920, 1080
FIXTURE = 1                  # fixture number used in /martin/<n>/... addresses
SCENE_IDS = range(1, 17)     # scene IDs for the 4 x 4 grid
OUTPUT = Path(__file__).resolve().parent / "Martin_VDO_Atomic_Bold.tosc"

GREY = (0.25, 0.25, 0.25, 1.0)
ACCENT = (0.30, 0.79, 0.94, 1.0)   # matches the desktop app's cyan
DARK = (0.10, 0.11, 0.14, 1.0)

TABBAR_HEIGHT = 40           # the Pager's tab bar along the top
TOP = TABBAR_HEIGHT + 20     # where page content starts

# Right-hand column: three vertical faders and the blackout toggle, on every page.
SLIDER_WIDTH = 110
RIGHT_FADERS = [
    ("Aura dimmer", 1520, f"/martin/{FIXTURE}/aura/intensity"),
    ("Beam dimmer", 1655, f"/martin/{FIXTURE}/intensity"),
    ("Master dimmer", 1790, "/martin/master"),
]
RIGHT_TOP, RIGHT_HEIGHT = TOP + 50, 840

# Left area used by the pages (ends where the right-hand column starts).
LEFT_X, LEFT_W = 20, 1470
ROW_HEIGHT = 120


# --- XML helpers ---------------------------------------------------------------------------------

def _prop(parent: ET.Element, kind: str, key: str, value) -> None:
    """Add a <property>. kind: s (string), i (integer), f (float), r (frame), c (colour)."""
    prop = ET.SubElement(parent, "property", attrib={"type": kind})
    ET.SubElement(prop, "key").text = key
    if kind == "r":
        frame = ET.SubElement(prop, "value")
        for name, number in zip(("x", "y", "w", "h"), value):
            ET.SubElement(frame, name).text = str(number)
    elif kind == "b":
        ET.SubElement(prop, "value").text = "1" if value else "0"
    elif kind == "c":
        colour = ET.SubElement(prop, "value")
        for name, number in zip(("r", "g", "b", "a"), value):
            ET.SubElement(colour, name).text = repr(float(number))
    else:
        ET.SubElement(prop, "value").text = str(value)


def _osc(messages: ET.Element, path: str, args: list[tuple], trigger: str = "ANY") -> None:
    """Add one OSC message. args: (kind, conversion, value, scale_min, scale_max) tuples.
    kind is VALUE (the control's value) or CONSTANT (the text in `value`)."""
    osc = ET.SubElement(messages, "osc")
    for name, text in (("enabled", "1"), ("send", "1"), ("receive", "1"),
                       ("feedback", "0"), ("connections", "00001")):
        ET.SubElement(osc, name).text = text

    triggers = ET.SubElement(osc, "triggers")
    trig = ET.SubElement(triggers, "trigger")
    ET.SubElement(trig, "var").text = "x"
    ET.SubElement(trig, "condition").text = trigger

    def partial(parent, kind, conversion, value, low="0", high="1"):
        part = ET.SubElement(parent, "partial")
        ET.SubElement(part, "type").text = kind
        ET.SubElement(part, "conversion").text = conversion
        ET.SubElement(part, "value").text = value
        ET.SubElement(part, "scaleMin").text = low
        ET.SubElement(part, "scaleMax").text = high

    path_el = ET.SubElement(osc, "path")
    partial(path_el, "CONSTANT", "STRING", path)
    arguments = ET.SubElement(osc, "arguments")
    for kind, conversion, value, low, high in args:
        partial(arguments, kind, conversion, value, low, high)


def _control(parent: ET.Element, ctype: str, name: str, frame: tuple, colour=GREY) -> ET.Element:
    node = ET.SubElement(parent, "node", attrib={"ID": _next_id(), "type": ctype})
    properties = ET.SubElement(node, "properties")
    _prop(properties, "s", "name", name)
    _prop(properties, "r", "frame", frame)
    _prop(properties, "c", "color", colour)
    ET.SubElement(node, "values")
    ET.SubElement(node, "messages")
    return node


def _fader(parent, name, frame, path, *, vertical: bool, kind="float", low=0, high=255):
    """A fader that sends one float (0-1) or int (low-high) argument."""
    node = _control(parent, "FADER", name, frame)
    _prop(node.find("properties"), "i", "orientation", 0 if vertical else 1)
    if kind == "float":
        args = [("VALUE", "FLOAT", "x", "0", "1")]
    else:
        args = [("VALUE", "INTEGER", "x", str(low), str(high))]
    _osc(node.find("messages"), path, args)
    return node


def _button(parent, name, frame, path, args, *, toggle=False, trigger="RISE", colour=GREY):
    """A button, with its name drawn on top of it so the purpose is readable on the phone."""
    node = _control(parent, "BUTTON", name, frame, colour)
    _prop(node.find("properties"), "i", "buttonType", 1 if toggle else 0)
    _osc(node.find("messages"), path, args, trigger=trigger)
    _text(parent, name, frame, size=22, transparent=True)
    return node


def _label(parent, text, frame):
    """A text label above a slider. Centred, with white text."""
    return _text(parent, text, frame, size=18, transparent=False)


def _text(parent, text, frame, *, size: int, transparent: bool) -> ET.Element:
    node = _control(parent, "LABEL", text, frame, colour=DARK)
    properties = node.find("properties")
    _prop(properties, "i", "textSize", size)
    _prop(properties, "c", "textColor", (1.0, 1.0, 1.0, 1.0))
    _prop(properties, "i", "textAlignH", 2)          # 2 = centre
    if transparent:
        _prop(properties, "b", "background", False)  # the label sits over the button, so it draws no box
    return node


_counter = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"{_counter:08x}-0000-4000-8000-{_counter:012x}"


# --- pages ---------------------------------------------------------------------------------------

def _right_column(page: ET.Element) -> None:
    for label, x, path in RIGHT_FADERS:
        _label(page, label, (x, TOP, SLIDER_WIDTH, 40))
        _fader(page, label, (x, RIGHT_TOP, SLIDER_WIDTH, RIGHT_HEIGHT), path, vertical=True)
    _button(page, "Blackout", (1640, 975, 260, 80),
            f"/martin/blackout", [("VALUE", "FLOAT", "x", "0", "1")],
            toggle=True, trigger="ANY", colour=ACCENT)


def _rows(page: ET.Element, rows: list[tuple[str, str, str, dict]]) -> None:
    """Stack horizontal faders with a label above each one.
    rows: (label, path, kind, options). kind is 'float' or 'int'; options are passed to _fader."""
    y = TOP
    for label, path, kind, options in rows:
        _label(page, label, (LEFT_X, y, LEFT_W, 40))
        _fader(page, label, (LEFT_X, y + 42, LEFT_W - 220, 75), path, vertical=False, kind=kind, **options)
        y += ROW_HEIGHT


def _manual_page(tabs: ET.Element) -> None:
    page = _page(tabs, "Manual")
    f = FIXTURE
    _rows(page, [
        ("Effect number (0-255)", f"/martin/{f}/fx", "int", {"low": 0, "high": 255}),
        ("Effect speed (left reverse, centre stopped, right forward)", f"/martin/{f}/fx/speed", "float", {}),
        ("Beam special effect (0-255)", f"/martin/{f}/beam/special", "int", {"low": 0, "high": 255}),
        ("Beam flash duration (0-255)", f"/martin/{f}/beam/flash/duration", "int", {"low": 0, "high": 255}),
        ("Beam flash rate (0-255)", f"/martin/{f}/beam/flash/rate", "int", {"low": 0, "high": 255}),
        ("Aura strobe / shutter (0-255)", f"/martin/{f}/aura/strobe", "int", {"low": 0, "high": 255}),
    ])
    # Stop: the speed value for "stopped" (DMX 128 = 128/255).
    _button(page, "Stop speed", (LEFT_X + LEFT_W - 200, TOP + ROW_HEIGHT + 42, 200, 75),
            f"/martin/{f}/fx/speed", [("CONSTANT", "FLOAT", repr(128 / 255), "0", "1")], trigger="RISE")
    _right_column(page)


def _light_page(tabs: ET.Element) -> None:
    page = _page(tabs, "Light")
    f = FIXTURE
    _rows(page, [
        ("Beam red", f"/martin/{f}/beam/red", "float", {}),
        ("Beam green", f"/martin/{f}/beam/green", "float", {}),
        ("Beam blue", f"/martin/{f}/beam/blue", "float", {}),
        ("Aura red", f"/martin/{f}/aura/red", "float", {}),
        ("Aura green", f"/martin/{f}/aura/green", "float", {}),
        ("Aura blue", f"/martin/{f}/aura/blue", "float", {}),
        ("Beam colour preset (0 = none, 1-48)", f"/martin/{f}/beam/preset", "int", {"low": 0, "high": 48}),
        ("Aura colour preset (0 = none, 1-48)", f"/martin/{f}/aura/preset", "int", {"low": 0, "high": 48}),
    ])
    _right_column(page)


def _scenes_page(tabs: ET.Element) -> None:
    page = _page(tabs, "Scenes")
    cell_w = (LEFT_W - 3 * 20) // 4
    cell_h = (HEIGHT - TOP - 20 - 3 * 20) // 4
    for index, scene_id in enumerate(SCENE_IDS):
        row, col = divmod(index, 4)
        x = LEFT_X + col * (cell_w + 20)
        y = TOP + row * (cell_h + 20)
        # The button sends (its value, scene ID). The app recalls once per press, so a repeating
        # message from the phone cannot keep re-triggering the scene.
        _button(page, f"Scene {scene_id}", (x, y, cell_w, cell_h),
                "/martin/scene/press",
                [("VALUE", "FLOAT", "x", "0", "1"), ("CONSTANT", "INTEGER", str(scene_id), "0", "1")],
                trigger="ANY", colour=ACCENT)
    _right_column(page)


def _page(pager_children: ET.Element, title: str) -> ET.Element:
    node = ET.SubElement(pager_children, "node", attrib={"ID": _next_id(), "type": "GROUP"})
    properties = ET.SubElement(node, "properties")
    _prop(properties, "s", "name", title)
    _prop(properties, "s", "tabLabel", title)
    _prop(properties, "r", "frame", (0, 0, WIDTH, HEIGHT))
    _prop(properties, "c", "color", GREY)
    ET.SubElement(node, "values")
    ET.SubElement(node, "messages")
    return ET.SubElement(node, "children")


def build() -> ET.Element:
    root = ET.Element("lexml", attrib={"version": "3"})
    canvas = ET.SubElement(root, "node", attrib={"ID": _next_id(), "type": "GROUP"})
    properties = ET.SubElement(canvas, "properties")
    _prop(properties, "s", "name", "Martin VDO Atomic Bold")
    _prop(properties, "r", "frame", (0, 0, WIDTH, HEIGHT))
    _prop(properties, "c", "color", DARK)
    ET.SubElement(canvas, "values")
    ET.SubElement(canvas, "messages")
    # A PAGER control holds the pages and draws the tab bar that switches between them.
    pager = ET.SubElement(ET.SubElement(canvas, "children"), "node",
                          attrib={"ID": _next_id(), "type": "PAGER"})
    pager_props = ET.SubElement(pager, "properties")
    _prop(pager_props, "s", "name", "Pages")
    _prop(pager_props, "r", "frame", (0, 0, WIDTH, HEIGHT))
    _prop(pager_props, "c", "color", GREY)
    _prop(pager_props, "b", "tabLabels", True)
    _prop(pager_props, "b", "tabbar", True)
    _prop(pager_props, "b", "tabbarDoubleTap", False)
    _prop(pager_props, "i", "tabbarSize", TABBAR_HEIGHT)
    _prop(pager_props, "i", "textSizeOff", 14)
    _prop(pager_props, "i", "textSizeOn", 14)
    pages = ET.SubElement(pager, "children")
    _manual_page(pages)
    _light_page(pages)
    _scenes_page(pages)
    return root


def write(path: Path = OUTPUT) -> Path:
    """Write the layout. A .tosc file is the XML, zlib-compressed."""
    xml = ET.tostring(build(), encoding="UTF-8", method="xml")
    path.write_bytes(zlib.compress(xml))
    return path


if __name__ == "__main__":
    print(f"wrote {write()}")
