import importlib.util
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from martin_controller.osc_server import _OSC_COMPONENTS, _OSC_PARAMS

TOOL = Path(__file__).resolve().parent.parent / "tools" / "make_touchosc_layout.py"
spec = importlib.util.spec_from_file_location("make_touchosc_layout", TOOL)
layout_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout_tool)

GLOBAL_ADDRESSES = {"/martin/blackout", "/martin/master", "/martin/scene/press"}


def _pages(root):
    """The pages inside the layout's PAGER control, in tab order."""
    return root.findall("./node/children/node[@type='PAGER']/children/node")


def _frame(node):
    value = node.find("properties/property[key='frame']/value")
    return tuple(int(value.find(k).text) for k in ("x", "y", "w", "h"))


def _layout_root():
    return ET.fromstring(zlib.decompress(zlib.compress(
        ET.tostring(layout_tool.build(), encoding="UTF-8"))))


class TouchOscLayoutTests(unittest.TestCase):
    def test_three_pages_in_landscape_canvas(self):
        root = _layout_root()
        pages = _pages(root)
        labels = [p.find("properties/property[key='tabLabel']/value").text for p in pages]
        self.assertEqual(labels, ["Manual", "Light", "Scenes"])
        frame = root.find("./node/properties/property[key='frame']/value")
        self.assertEqual((frame.find("w").text, frame.find("h").text), ("1920", "1080"))

    def test_scene_grid_has_16_buttons_for_ids_1_to_16(self):
        root = _layout_root()
        scenes = _pages(root)[2].findall("children/node")
        recall_ids = []
        for node in scenes:
            if node.get("type") != "BUTTON":
                continue
            osc = node.find("messages/osc")
            if osc.find("path/partial/value").text != "/martin/scene/press":
                continue
            recall_ids.append(int(osc.find("arguments/partial[2]/value").text))
        self.assertEqual(sorted(recall_ids), list(range(1, 17)))

    def test_every_generated_address_is_handled_by_the_app(self):
        root = _layout_root()
        addresses = {el.text for el in root.iter("path") for el in el.iter("value")}
        for address in addresses:
            if address in GLOBAL_ADDRESSES:
                continue
            parts = address.strip("/").split("/")
            self.assertEqual(parts[0], "martin", address)
            param = "/".join(parts[2:])
            self.assertTrue(param in _OSC_PARAMS or param in _OSC_COMPONENTS, address)

    def test_right_column_faders_on_every_page(self):
        root = _layout_root()
        for page in _pages(root):
            paths = {el.find("messages/osc/path/partial/value").text
                     for el in page.findall("children/node") if el.find("messages/osc") is not None}
            for expected in ("/martin/1/aura/intensity", "/martin/1/intensity", "/martin/master", "/martin/blackout"):
                self.assertIn(expected, paths)

    def test_sliders_are_big_enough_to_use_on_a_phone(self):
        root = _layout_root()
        for page in _pages(root):
            for fader in page.findall("children/node"):
                if fader.get("type") != "FADER":
                    continue
                x, y, w, h = _frame(fader)
                orientation = fader.find("properties/property[key='orientation']/value").text
                if orientation == "0":          # vertical: the right-hand column
                    self.assertGreaterEqual(w, 100)
                    self.assertGreaterEqual(h, 800)
                else:                           # horizontal: the Manual and Light rows
                    self.assertGreaterEqual(h, 70)
                    self.assertGreaterEqual(w, 1000)

    def test_pager_draws_the_tab_bar(self):
        root = _layout_root()
        pager = root.find("./node/children/node[@type='PAGER']")
        props = {p.find("key").text: p.find("value").text for p in pager.findall("properties/property")}
        self.assertEqual(props["tabbar"], "1")
        self.assertEqual(props["tabLabels"], "1")

    def test_every_slider_and_button_has_a_label_on_its_page(self):
        root = _layout_root()
        for page in _pages(root):
            children = page.findall("children/node")
            labels = {n.find("properties/property[key='name']/value").text
                      for n in children if n.get("type") == "LABEL"}
            for control in children:
                if control.get("type") not in ("FADER", "BUTTON"):
                    continue
                name = control.find("properties/property[key='name']/value").text
                self.assertIn(name, labels, f"no label for {name!r}")


if __name__ == "__main__":
    unittest.main()
