"""PySide6 user interface: control, strobe and flash, settings, Extended pixels, presets,
fixtures, and network (Art-Net / sACN and OSC)."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QListWidgetItem,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import NetworkSettings, Settings, load_project, save_project, save_settings
from .controls import (
    BEAM_SPECIAL_EFFECTS,
    CONTROL_NO_FUNCTION,
    CONTROL_SETTINGS,
    PIXEL_COUNT,
    aura_strobe_value,
    flash_duration_ms,
    flash_rate_hz,
    parse_aura_strobe,
)
from .effects import COLOR_PRESET_NAMES, FX_GROUPS, FX_NAMES
from .engine import DmxEngine
from .fixture import Fixture, FixtureState
from .mapping import PARAMETERS, Mapping, MappingTable
from .preview import FixturePreview
from .osc_server import OscServer
from .presets import describe, make_preset, preset_state, swatch_hex
from .scenes import MAX_SCENE_ID, PlaylistItem, SceneManager
from .preview import FixturePreview, speed_text

STOPPED_SPEED = 128  # DMX value for a stopped effect (channel 17)

PROTOCOL_CHOICES = [("Art-Net", "artnet"), ("sACN (E1.31)", "sacn")]
MODE_CHOICES = [("Basic (27 channels)", "basic"), ("Extended (243 channels)", "extended")]
AURA_STROBE_KINDS = [
    ("No strobe", "none"),
    ("Shutter closed", "shutter"),
    ("Strobe, slow to fast", "strobe"),
    ("Random strobe, slow to fast", "random"),
]
FX_SYNC_CHOICES = [
    ("No sync", 0),
    ("Fixture offset 10 degrees", 1),
    ("Synchronized", 36),
    ("Random start", 110),
    ("Random duration", 130),
]


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, engine: DmxEngine, settings_path=None):
        super().__init__()
        self.setWindowTitle("Martin VDO Atomic Bold control")
        self.resize(820, 700)

        self._settings = settings
        self._engine = engine
        self._settings_path = settings_path
        self._index = 0
        self._pixel = 1            # selected aura pixel, 1-72
        self._loading = False      # True while widgets are being filled from state
        self._osc: OscServer | None = None
        self._pulse_index = 0
        self._mapping_table = MappingTable(settings.mappings)
        self._scenes = SceneManager(engine, settings.scenes, settings.playlist)
        self._seen_scene_version = self._scenes.version
        self._loading_mapping = False
        self._learn_start_count = 0

        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(), "Control")
        tabs.addTab(self._build_effects_tab(), "Effects")
        tabs.addTab(self._build_strobe_tab(), "Strobe and flash")
        tabs.addTab(self._build_settings_tab(), "Settings")
        tabs.addTab(self._build_pixels_tab(), "Pixels")
        tabs.addTab(self._build_presets_tab(), "Presets")
        tabs.addTab(self._build_mapping_tab(), "OSC mapping")
        tabs.addTab(self._build_scenes_tab(), "Scenes")
        tabs.addTab(self._build_fixtures_tab(), "Fixtures")
        tabs.addTab(self._build_network_tab(), "Network")

        self._project_path: Path | None = None
        self._build_menu()

        self.preview = FixturePreview()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(self._build_top_bar())
        layout.addWidget(self.preview)
        layout.addWidget(tabs, 1)
        self.setCentralWidget(central)
        self.statusBar()

        # One-shot timer for Control/Settings pulses (reset, scene record, curves, fan...).
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.timeout.connect(self._end_pulse)

        self._refresh_fixture_list()
        self._load_controls()
        self._refresh_presets()
        self._refresh_fixtures_table()
        self._refresh_mapping_table()
        self._refresh_scenes()

        self._scene_timer = QTimer(self)
        self._scene_timer.timeout.connect(self._update_scene_playback)
        self._scene_timer.start(100)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(500)

        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._update_preview)
        self._preview_timer.start(50)

    # --- layout ----------------------------------------------------------------

    def _build_top_bar(self) -> QHBoxLayout:
        self.fixture_combo = QComboBox()
        self.fixture_combo.currentIndexChanged.connect(self._on_fixture_selected)
        self.blackout_box = QCheckBox("Blackout")
        self.blackout_box.toggled.connect(lambda on: setattr(self._engine, "blackout", on))
        self.master_slider = QSlider(Qt.Horizontal)
        self.master_slider.setRange(0, 100)
        self.master_slider.setValue(round(self._engine.master * 100))
        self.master_slider.setFixedWidth(160)
        self.master_slider.valueChanged.connect(self._on_master_changed)
        self.master_slider.sliderReleased.connect(self._persist)
        self.master_label = QLabel()
        self.master_label.setFixedWidth(48)

        row = QHBoxLayout()
        row.addWidget(QLabel("Fixture:"))
        row.addWidget(self.fixture_combo, 1)
        row.addWidget(QLabel("Master:"))
        row.addWidget(self.master_slider)
        row.addWidget(self.master_label)
        row.addWidget(self.blackout_box)
        return row

    def _on_master_changed(self, value: int) -> None:
        self._engine.master = value / 100
        self.master_label.setText(f"{value} %")

    def _sync_top_bar(self) -> None:
        """Show master and blackout as the engine has them, which includes OSC and mapping changes."""
        if not self.master_slider.isSliderDown():
            target = round(self._engine.master * 100)
            if self.master_slider.value() != target:
                self.master_slider.blockSignals(True)
                self.master_slider.setValue(target)
                self.master_slider.blockSignals(False)
            self.master_label.setText(f"{target} %")
        if self.blackout_box.isChecked() != self._engine.blackout:
            self.blackout_box.blockSignals(True)
            self.blackout_box.setChecked(self._engine.blackout)
            self.blackout_box.blockSignals(False)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for label, shortcut, handler in (
            ("&Open project...", "Ctrl+O", self.open_project),
            ("&Save project", "Ctrl+S", self.save_project),
            ("Save project &as...", "Ctrl+Shift+S", self.save_project_as),
        ):
            action = file_menu.addAction(label)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)

    def _slider(self, lo: int, hi: int, on_change) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.valueChanged.connect(on_change)
        return slider

    def _combo(self, items, on_change) -> QComboBox:
        """Combo of (label, data) pairs. Changes are sent unless the window is loading state."""
        combo = QComboBox()
        for label, data in items:
            combo.addItem(label, data)
        combo.currentIndexChanged.connect(lambda _: None if self._loading else on_change(combo.currentData()))
        return combo

    def _build_control_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        beam = QGroupBox("Beam (main LED)")
        form = QFormLayout(beam)
        self.beam_intensity = self._slider(0, 100, lambda v: self._change(beam_intensity=v / 100))
        form.addRow("Intensity (beam shutter: 0 = closed)", self.beam_intensity)
        self.beam_rgb = [
            self._slider(0, 100, lambda v, i=i: self._set_rgb("beam_rgb", i, v)) for i in range(3)
        ]
        for name, slider in zip(("Red", "Green", "Blue"), self.beam_rgb):
            form.addRow(name, slider)
        self.beam_preset = self._preset_combo(lambda n: self._change(beam_color_preset=n))
        form.addRow("Colour preset", self.beam_preset)
        self.beam_ctc_on, self.beam_ctc = self._ctc_row(lambda k: self._change(beam_ctc_kelvin=k))
        form.addRow(self.beam_ctc_on, self.beam_ctc)
        layout.addWidget(beam)

        aura = QGroupBox("Aura (backlight)")
        form = QFormLayout(aura)
        self.aura_intensity = self._slider(0, 100, lambda v: self._change(aura_intensity=v / 100))
        form.addRow("Intensity", self.aura_intensity)
        self.aura_rgb = [
            self._slider(0, 100, lambda v, i=i: self._set_rgb("aura_rgb", i, v)) for i in range(3)
        ]
        for name, slider in zip(("Red", "Green", "Blue"), self.aura_rgb):
            form.addRow(name, slider)
        self.aura_preset = self._preset_combo(lambda n: self._change(aura_color_preset=n))
        form.addRow("Colour preset", self.aura_preset)
        self.aura_ctc_on, self.aura_ctc = self._ctc_row(lambda k: self._change(aura_ctc_kelvin=k))
        form.addRow(self.aura_ctc_on, self.aura_ctc)
        layout.addWidget(aura)

        layout.addStretch(1)
        return page

    def _preset_combo(self, on_change) -> QComboBox:
        items = [("None (mix via RGB)", 0)]
        items += [(f"{n:2d}  {name}", n) for n, name in enumerate(COLOR_PRESET_NAMES, start=1)]
        return self._combo(items, on_change)

    def _ctc_row(self, on_change):
        """A checkbox that enables colour temperature control, and a slider for the kelvin value."""
        box = QCheckBox("Colour temperature (K)")
        slider = QSlider(Qt.Horizontal)
        slider.setRange(2000, 11000)
        slider.setSingleStep(50)
        slider.setPageStep(500)
        slider.setValue(6500)
        slider.setEnabled(False)

        def toggled(on: bool) -> None:
            slider.setEnabled(on)
            if not self._loading:
                on_change(slider.value() if on else None)

        def moved(value: int) -> None:
            if box.isChecked() and not self._loading:
                on_change(value)

        box.toggled.connect(toggled)
        slider.valueChanged.connect(moved)
        return box, slider

    def _build_effects_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        effect = QGroupBox("Built-in effects")
        form = QFormLayout(effect)
        self.fx_combos: list[QComboBox] = []
        for title, numbers in FX_GROUPS:
            items = [("None", 0)] + [(f"{n:3d}  {FX_NAMES[n]}", n) for n in numbers]
            combo = self._combo(items, self._select_effect)
            self.fx_combos.append(combo)
            form.addRow(title, combo)

        self.fx_speed_label = QLabel()
        self.fx_speed = self._slider(0, 255, self._on_fx_speed)
        stop = QPushButton("Stop")
        stop.setToolTip("Set the speed back to the stopped position (128)")
        stop.clicked.connect(lambda: self.fx_speed.setValue(STOPPED_SPEED))
        speed_row = QHBoxLayout()
        speed_row.addWidget(self.fx_speed, 1)
        speed_row.addWidget(stop)
        form.addRow(self.fx_speed_label, speed_row)

        self.fx_sync = self._combo(FX_SYNC_CHOICES, lambda v: self._change(fx_sync=v))
        form.addRow("Sync", self.fx_sync)
        layout.addWidget(effect)

        note = QLabel(
            "All five groups use the same effect channel, so only one effect runs at a time. "
            "Choosing an effect in one group sets the others to None.\n"
            "Speed: left = reverse fast, centre = stopped, right = forward fast.\n"
            "Effects only run while the fixture has a non-zero intensity."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_strobe_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        strobe = QGroupBox("Strobe and shutter effects")
        form = QFormLayout(strobe)
        self.beam_special = self._combo(BEAM_SPECIAL_EFFECTS, lambda v: self._change(beam_special_effect=v))
        form.addRow("Beam special effect (ch 5)", self.beam_special)

        self.strobe_kind = self._combo(AURA_STROBE_KINDS, lambda _: self._on_strobe_changed())
        self.strobe_speed = self._slider(0, 100, lambda _: self._on_strobe_changed())
        self.strobe_speed_label = QLabel()
        form.addRow("Aura strobe / shutter (ch 19)", self.strobe_kind)
        form.addRow("Aura strobe speed", self.strobe_speed)
        form.addRow("", self.strobe_speed_label)
        layout.addWidget(strobe)

        flash = QGroupBox("Beam flash timing")
        form = QFormLayout(flash)
        self.flash_duration_label = QLabel()
        self.flash_duration = self._slider(0, 255, self._on_flash_duration)
        self.flash_rate_label = QLabel()
        self.flash_rate = self._slider(0, 255, self._on_flash_rate)
        form.addRow("Duration (ch 3)", self.flash_duration)
        form.addRow("", self.flash_duration_label)
        form.addRow("Rate (ch 4)", self.flash_rate)
        form.addRow("", self.flash_rate_label)
        layout.addWidget(flash)

        note = QLabel(
            "Beam shutter is the beam intensity on the Control tab (0 = closed). "
            "The manual has no separate aura flash duration or rate channel; "
            "the aura strobe speed above sets its flash rate. "
            "Check the flash and strobe timing on the fixture."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        group = QGroupBox("Control and settings (channel 15)")
        form = QFormLayout(group)
        self.setting_combo = QComboBox()
        for label, value, hold in CONTROL_SETTINGS:
            self.setting_combo.addItem(label, (value, hold))
        form.addRow("Function", self.setting_combo)

        apply_button = QPushButton("Send to fixture")
        apply_button.clicked.connect(self._send_setting)
        form.addRow("", apply_button)
        layout.addWidget(group)

        note = QLabel(
            "The fixture runs one control function at a time, so each choice is sent as a short pulse "
            "and then channel 15 returns to 'no function'. Reset and scene record are held for 5 seconds "
            "as the manual requires. Settings apply to the selected fixture only."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_pixels_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.pixel_note = QLabel()
        self.pixel_note.setWordWrap(True)
        layout.addWidget(self.pixel_note)

        body = QHBoxLayout()
        grid = QGridLayout()
        self._pixel_buttons: list[QPushButton] = []
        for n in range(1, PIXEL_COUNT + 1):
            button = QPushButton(str(n))
            button.setCheckable(True)
            button.setFixedSize(46, 30)
            button.clicked.connect(lambda _=False, n=n: self._select_pixel(n))
            grid.addWidget(button, (n - 1) // 9, (n - 1) % 9)
            self._pixel_buttons.append(button)
        body.addLayout(grid)

        side = QVBoxLayout()
        selected = QGroupBox("Selected pixel")
        form = QFormLayout(selected)
        self.pixel_title = QLabel()
        form.addRow(self.pixel_title)
        self.pixel_rgb = [
            self._slider(0, 100, lambda v, i=i: self._set_pixel_component(i, v)) for i in range(3)
        ]
        for name, slider in zip(("Red", "Green", "Blue"), self.pixel_rgb):
            form.addRow(name, slider)
        side.addWidget(selected)

        fill = QGroupBox("All pixels")
        vbox = QVBoxLayout(fill)
        for label, handler in (
            ("Fill all with aura colour", self._fill_pixels_with_aura),
            ("Clear all pixels to black", self._clear_pixels),
            ("Pixels only: set aura RGB to black", self._zero_aura_rgb),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            vbox.addWidget(button)
        side.addWidget(fill)
        side.addStretch(1)
        body.addLayout(side)
        layout.addLayout(body)

        note = QLabel(
            "Pixel numbers run 1-72 left to right, row by row, so they do not match the physical "
            "layout in the manual diagram. Pixel values are combined with the aura RGB on the Control tab "
            "using HTP (highest value wins). For pixel-only colour, set the aura RGB to black."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self._select_pixel(1, update_state=False)
        return page

    def _build_mapping_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.monitor_label = QLabel("No OSC messages yet. Enable the OSC listener in the Network tab.")
        self.monitor_label.setWordWrap(True)
        self.learn_button = QPushButton("Learn address")
        self.learn_button.setCheckable(True)
        self.learn_button.setToolTip("Press, then move a control in TouchDesigner or TouchOSC. Its address fills in below.")
        self.learn_button.toggled.connect(self._on_learn_toggled)
        top.addWidget(self.monitor_label, 1)
        top.addWidget(self.learn_button)
        layout.addLayout(top)

        self.mapping_table = QTableWidget(0, 5)
        self.mapping_table.setHorizontalHeaderLabels(
            ["OSC address", "Fixture", "Parameter", "Input range", "Output range"]
        )
        self.mapping_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mapping_table.setSelectionMode(QTableWidget.SingleSelection)
        self.mapping_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        self.mapping_table.itemSelectionChanged.connect(self._load_selected_mapping)
        layout.addWidget(self.mapping_table, 1)

        group = QGroupBox("Mapping")
        form = QFormLayout(group)
        self.map_address = QLineEdit()
        self.map_address.setPlaceholderText("/td/fader1")
        self.map_fixture = QComboBox()
        self.map_param = QComboBox()
        for key, param in PARAMETERS.items():
            self.map_param.addItem(param.label, key)
        self.map_param.currentIndexChanged.connect(self._on_map_param_changed)
        form.addRow("OSC address", self.map_address)
        form.addRow("Fixture", self.map_fixture)
        form.addRow("Parameter", self.map_param)

        ranges = QHBoxLayout()
        self.in_min_spin, self.in_max_spin = self._range_spin(0.0), self._range_spin(1.0)
        self.out_min_spin, self.out_max_spin = self._range_spin(0.0), self._range_spin(1.0)
        ranges.addWidget(QLabel("Input"))
        ranges.addWidget(self.in_min_spin)
        ranges.addWidget(QLabel("to"))
        ranges.addWidget(self.in_max_spin)
        ranges.addSpacing(20)
        ranges.addWidget(QLabel("Output"))
        ranges.addWidget(self.out_min_spin)
        ranges.addWidget(QLabel("to"))
        ranges.addWidget(self.out_max_spin)
        ranges.addStretch(1)
        form.addRow("Range", ranges)
        layout.addWidget(group)

        buttons = QHBoxLayout()
        for label, handler in (
            ("Add mapping", self._add_mapping),
            ("Update selected", self._update_mapping),
            ("Remove selected", self._remove_mapping),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        note = QLabel(
            "Each OSC value is scaled from the input range to the output range and clamped to the input range. "
            "Set the input range to the values TouchDesigner sends (for example 0 to 1), and the output range to "
            "the parameter's range. Colour presets and effects are rounded to whole numbers. Blackout turns on when "
            "the output is 0.5 or more. Mappings are saved with the settings."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _range_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-100000, 100000)
        spin.setDecimals(3)
        spin.setValue(value)
        return spin

    def _build_scenes_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        columns = QHBoxLayout()

        # Left: the scene library
        library = QGroupBox("Scenes")
        vbox = QVBoxLayout(library)
        self.scene_table = QTableWidget(0, 4)
        self.scene_table.setHorizontalHeaderLabels(["ID", "Name", "Fixtures", "Master"])
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scene_table.setSelectionMode(QTableWidget.SingleSelection)
        self.scene_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.scene_table.horizontalHeader().setStretchLastSection(True)
        vbox.addWidget(self.scene_table, 1)

        form = QFormLayout()
        self.scene_id_spin = QSpinBox()
        self.scene_id_spin.setRange(0, MAX_SCENE_ID)
        self.scene_name_edit = QLineEdit()
        self.scene_name_edit.setPlaceholderText("Name (optional)")
        form.addRow("Scene ID", self.scene_id_spin)
        form.addRow("Name", self.scene_name_edit)
        self.fade_spin = QDoubleSpinBox()
        self.fade_spin.setRange(0, 120)
        self.fade_spin.setDecimals(1)
        self.fade_spin.setSuffix(" s")
        self.fade_spin.setToolTip(
            "Crossfade for direct recalls (the Recall button and /martin/scene). "
            "Playlist items have their own fade time."
        )
        self.fade_spin.setValue(self._scenes.fade_time)
        self.fade_spin.valueChanged.connect(self._on_fade_changed)
        form.addRow("Fade (direct)", self.fade_spin)
        vbox.addLayout(form)

        row = QHBoxLayout()
        for label, handler, tip in (
            ("Store current look", self._store_scene, "Save the current look as this ID. Replaces any scene with the same ID."),
            ("Recall", self._recall_scene, "Play the selected scene now."),
            ("Rename", self._rename_scene, "Change the name of the selected scene."),
            ("Delete", self._delete_scene, "Delete the selected scene and remove it from the playlist."),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            row.addWidget(button)
        vbox.addLayout(row)
        columns.addWidget(library, 1)

        # Right: the playlist and playback
        playlist_box = QGroupBox("Playlist")
        vbox = QVBoxLayout(playlist_box)
        self.playlist_list = QListWidget()
        vbox.addWidget(self.playlist_list, 1)

        form = QFormLayout()
        self.playlist_scene_combo = QComboBox()
        self.playlist_hold = QDoubleSpinBox()
        self.playlist_hold.setRange(0, 3600)
        self.playlist_hold.setDecimals(1)
        self.playlist_hold.setSuffix(" s")
        self.playlist_hold.setToolTip("Time before auto-advance. 0 = wait for Next.")
        self.playlist_fade = QDoubleSpinBox()
        self.playlist_fade.setRange(0, 120)
        self.playlist_fade.setDecimals(1)
        self.playlist_fade.setSuffix(" s")
        self.playlist_fade.setToolTip("Crossfade into this scene. 0 = cut straight to it.")
        form.addRow("Scene", self.playlist_scene_combo)
        form.addRow("Hold", self.playlist_hold)
        form.addRow("Fade", self.playlist_fade)
        self.playlist_list.currentRowChanged.connect(self._load_playlist_row)
        vbox.addLayout(form)

        edit = QHBoxLayout()
        for label, handler in (
            ("Add", self._playlist_add),
            ("Update", self._playlist_update),
            ("Remove", self._playlist_remove),
            ("Up", lambda: self._playlist_move(-1)),
            ("Down", lambda: self._playlist_move(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            edit.addWidget(button)
        vbox.addLayout(edit)

        play = QHBoxLayout()
        for label, handler in (
            ("Previous", lambda: self._playlist_step(-1)),
            ("Go", self._playlist_go),
            ("Next", lambda: self._playlist_step(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            play.addWidget(button)
        vbox.addLayout(play)

        self.auto_advance_box = QCheckBox("Auto-advance (uses hold times)")
        self.auto_advance_box.toggled.connect(lambda on: setattr(self._scenes, "auto_advance", on))
        vbox.addWidget(self.auto_advance_box)
        self.now_playing_label = QLabel("Nothing playing.")
        self.now_playing_label.setWordWrap(True)
        vbox.addWidget(self.now_playing_label)
        columns.addWidget(playlist_box, 1)

        layout.addLayout(columns, 1)
        note = QLabel(
            "OSC: /martin/scene <id> recalls a scene (send the ID as the value). "
            "/martin/playlist/next, /martin/playlist/prev and /martin/playlist/go <position> step through the playlist. "
            "A scene stores every fixture's settings and the master level, not blackout. "
            "Recall is instant (no fade)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _build_presets_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        self.preset_list = QListWidget()
        self.preset_list.setIconSize(QPixmap(14, 14).size())
        self.preset_list.currentItemChanged.connect(lambda cur, _prev: self._show_preset(cur))
        layout.addWidget(self.preset_list, 1)

        details = QVBoxLayout()
        self.preset_preview = FixturePreview()
        self.preset_details = QLabel("Select a preset to see its details.")
        self.preset_details.setWordWrap(True)
        self.preset_details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        details.addWidget(self.preset_preview)
        details.addWidget(self.preset_details, 1)
        layout.addLayout(details, 2)

        buttons = QVBoxLayout()
        for label, handler in (
            ("Save current as...", self._save_preset),
            ("Load to fixture", self._load_preset),
            ("Delete", self._delete_preset),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_fixtures_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.fixture_table = QTableWidget(0, 4)
        self.fixture_table.setHorizontalHeaderLabels(
            ["Name", "Art-Net universe / sACN universe", "DMX start address", "DMX mode"]
        )
        self.fixture_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.fixture_table, 1)

        buttons = QHBoxLayout()
        for label, handler in (
            ("Add fixture", self._add_fixture_row),
            ("Remove selected", self._remove_fixture_row),
            ("Apply", self._apply_fixtures),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        hint = QLabel(
            "Universe, start address and mode must match the fixture's own settings "
            "(set over RDM with the Martin Companion app). Art-Net universes are 0-32767; "
            "sACN universes are 1-63999. Extended mode uses 243 channels, so its start address "
            "must be 270 or lower."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return page

    def _build_network_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        net = self._settings.network

        artnet = QGroupBox("DMX output")
        form = QFormLayout(artnet)
        self.protocol_combo = QComboBox()
        for label, value in PROTOCOL_CHOICES:
            self.protocol_combo.addItem(label, value)
        self.protocol_combo.setCurrentIndex(max(0, self.protocol_combo.findData(net.protocol)))
        self.target_edit = QLineEdit(net.target_ip)
        self.target_edit.setToolTip(
            "Art-Net: broadcast (255.255.255.255) or a node IP.\n"
            "sACN: leave blank to use multicast, or enter a unicast IP."
        )
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(net.artnet_port)
        self.refresh_spin = QDoubleSpinBox()
        self.refresh_spin.setRange(1, 44)
        self.refresh_spin.setValue(net.refresh_hz)
        form.addRow("Protocol", self.protocol_combo)
        form.addRow("Target IP", self.target_edit)
        form.addRow("UDP port (6454 Art-Net, 5568 sACN)", self.port_spin)
        form.addRow("Refresh rate (Hz)", self.refresh_spin)
        layout.addWidget(artnet)

        osc = QGroupBox("OSC input (TouchOSC)")
        form = QFormLayout(osc)
        self.osc_on = QCheckBox("Enable OSC listener")
        self.osc_on.setChecked(net.osc_enabled)
        self.osc_host_edit = QLineEdit(net.osc_host)
        self.osc_host_edit.setToolTip(
            "0.0.0.0 accepts OSC from any device on the network (TouchOSC on a tablet).\n"
            "127.0.0.1 accepts only from this computer (TouchDesigner running here)."
        )
        self.osc_port_spin = QSpinBox()
        self.osc_port_spin.setRange(1, 65535)
        self.osc_port_spin.setValue(net.osc_port)
        form.addRow(self.osc_on)
        form.addRow("Listen address", self.osc_host_edit)
        form.addRow("Listen port", self.osc_port_spin)
        layout.addWidget(osc)

        apply_button = QPushButton("Apply and save")
        apply_button.clicked.connect(self._apply_network)
        layout.addWidget(apply_button)

        self.network_status = QLabel()
        self.network_status.setWordWrap(True)
        layout.addWidget(self.network_status)
        layout.addStretch(1)
        return page

    # --- fixture selection and state changes ----------------------------------

    @property
    def _fixture(self) -> Fixture:
        return self._engine.fixtures[self._index]

    def _refresh_fixture_list(self) -> None:
        self.fixture_combo.blockSignals(True)
        self.fixture_combo.clear()
        for fixture in self._engine.fixtures:
            self.fixture_combo.addItem(f"{fixture.name} (ch {fixture.address}, {fixture.mode})")
        self._index = min(self._index, len(self._engine.fixtures) - 1)
        self.fixture_combo.setCurrentIndex(self._index)
        self.fixture_combo.blockSignals(False)
        self._refresh_map_fixture_choices()

    def _refresh_map_fixture_choices(self) -> None:
        current = self.map_fixture.currentData() if hasattr(self, "map_fixture") else None
        self.map_fixture.clear()
        self.map_fixture.addItem("All fixtures", None)
        for i, fixture in enumerate(self._engine.fixtures):
            self.map_fixture.addItem(f"{i + 1}: {fixture.name}", i)
        self.map_fixture.setCurrentIndex(max(0, self.map_fixture.findData(current)))

    def _on_fixture_selected(self, index: int) -> None:
        if 0 <= index < len(self._engine.fixtures):
            self._index = index
            self._load_controls()

    def _change(self, **changes) -> None:
        if self._loading:
            return
        self._engine.update_fixture(self._index, **changes)
        self._sync_speed_label()

    def _set_rgb(self, field: str, component: int, value: int) -> None:
        if self._loading:
            return
        rgb = list(getattr(self._fixture.state, field))
        rgb[component] = value / 100
        self._change(**{field: tuple(rgb)})

    def _select_effect(self, number: int) -> None:
        """A user picked an effect in one group: send it and clear the other groups."""
        self._change(fx=number)
        self._show_effect(number)

    def _show_effect(self, number: int) -> None:
        """Show `number` in the group that holds it, and None in the others."""
        was_loading = self._loading
        self._loading = True
        try:
            for combo, (_, numbers) in zip(self.fx_combos, FX_GROUPS):
                combo.setCurrentIndex(max(0, combo.findData(number)) if number in numbers else 0)
        finally:
            self._loading = was_loading

    def _on_fx_speed(self, value: int) -> None:
        self._change(fx_speed=value)
        self._sync_speed_label()

    def _sync_speed_label(self) -> None:
        self.fx_speed_label.setText(speed_text(self._fixture.state.fx_speed))

    def _on_strobe_changed(self) -> None:
        if self._loading:
            return
        kind = self.strobe_kind.currentData()
        speed = self.strobe_speed.value() / 100
        self.strobe_speed.setEnabled(kind in ("strobe", "random"))
        self._change(aura_strobe=aura_strobe_value(kind, speed))
        self._sync_strobe_label()

    def _sync_strobe_label(self) -> None:
        kind = self.strobe_kind.currentData()
        self.strobe_speed_label.setText(
            "Speed applies to strobe modes" if kind not in ("strobe", "random")
            else f"{self.strobe_speed.value()} % of the range (slow to fast)"
        )

    def _on_flash_duration(self, value: int) -> None:
        self._change(beam_flash_duration=value)
        self.flash_duration_label.setText(f"{flash_duration_ms(value):.0f} ms")

    def _on_flash_rate(self, value: int) -> None:
        self._change(beam_flash_rate=value)
        self.flash_rate_label.setText(f"{flash_rate_hz(value):.2f} Hz")

    def _set_pixel_component(self, component: int, value: int) -> None:
        if self._loading:
            return
        pixels = list(self._fixture.state.aura_pixels)
        rgb = list(pixels[self._pixel - 1])
        rgb[component] = value / 100
        pixels[self._pixel - 1] = tuple(rgb)
        self._change(aura_pixels=tuple(pixels))
        self._paint_pixel_button(self._pixel)

    def _select_pixel(self, number: int, update_state: bool = True) -> None:
        self._pixel = number
        for n, button in enumerate(self._pixel_buttons, start=1):
            button.setChecked(n == number)
        self.pixel_title.setText(f"Pixel {number} (channels {28 + 3 * (number - 1)}-{30 + 3 * (number - 1)})")
        if update_state:
            self._load_pixel_sliders()

    def _load_pixel_sliders(self) -> None:
        rgb = self._fixture.state.aura_pixels[self._pixel - 1]
        self._loading = True
        try:
            for slider, value in zip(self.pixel_rgb, rgb):
                slider.setValue(round(value * 100))
        finally:
            self._loading = False

    def _paint_pixel_button(self, number: int) -> None:
        rgb = self._fixture.state.aura_pixels[number - 1]
        color = QColor(*(round(c * 255) for c in rgb))
        text = "white" if color.lightness() < 128 else "black"
        self._pixel_buttons[number - 1].setStyleSheet(
            f"background-color: {color.name()}; color: {text};"
        )

    def _paint_all_pixels(self) -> None:
        for number in range(1, PIXEL_COUNT + 1):
            self._paint_pixel_button(number)

    def _fill_pixels_with_aura(self) -> None:
        self._change(aura_pixels=(tuple(self._fixture.state.aura_rgb),) * PIXEL_COUNT)
        self._load_controls()

    def _clear_pixels(self) -> None:
        self._change(aura_pixels=((0.0, 0.0, 0.0),) * PIXEL_COUNT)
        self._load_controls()

    def _zero_aura_rgb(self) -> None:
        self._change(aura_rgb=(0.0, 0.0, 0.0))
        self._load_controls()

    def _send_setting(self) -> None:
        value, hold = self.setting_combo.currentData()
        self._pulse_index = self._index
        self._engine.update_fixture(self._pulse_index, control=value)
        self._pulse_timer.start(int(hold * 1000))
        self.statusBar().showMessage(
            f"Sending {self.setting_combo.currentText()} for {hold:.0f} s", 3000
        )

    def _end_pulse(self) -> None:
        if self._pulse_index < len(self._engine.fixtures):
            self._engine.update_fixture(self._pulse_index, control=CONTROL_NO_FUNCTION)

    def _load_controls(self) -> None:
        """Fill every control from the selected fixture's state, without sending anything."""
        fixture = self._fixture
        state = fixture.state
        self._loading = True
        try:
            self.beam_intensity.setValue(round(state.beam_intensity * 100))
            for slider, value in zip(self.beam_rgb, state.beam_rgb):
                slider.setValue(round(value * 100))
            self.beam_preset.setCurrentIndex(self.beam_preset.findData(state.beam_color_preset))
            self._load_ctc(self.beam_ctc_on, self.beam_ctc, state.beam_ctc_kelvin)

            self.aura_intensity.setValue(round(state.aura_intensity * 100))
            for slider, value in zip(self.aura_rgb, state.aura_rgb):
                slider.setValue(round(value * 100))
            self.aura_preset.setCurrentIndex(self.aura_preset.findData(state.aura_color_preset))
            self._load_ctc(self.aura_ctc_on, self.aura_ctc, state.aura_ctc_kelvin)

            self._show_effect(state.fx)
            self.fx_speed.setValue(state.fx_speed)
            self.fx_sync.setCurrentIndex(max(0, self.fx_sync.findData(state.fx_sync)))

            self.beam_special.setCurrentIndex(max(0, self.beam_special.findData(state.beam_special_effect)))
            kind, speed = parse_aura_strobe(state.aura_strobe)
            self.strobe_kind.setCurrentIndex(max(0, self.strobe_kind.findData(kind)))
            self.strobe_speed.setValue(round(speed * 100))
            self.strobe_speed.setEnabled(kind in ("strobe", "random"))
            self.flash_duration.setValue(state.beam_flash_duration)
            self.flash_rate.setValue(state.beam_flash_rate)
        finally:
            self._loading = False
        self.flash_duration_label.setText(f"{flash_duration_ms(state.beam_flash_duration):.0f} ms")
        self.flash_rate_label.setText(f"{flash_rate_hz(state.beam_flash_rate):.2f} Hz")
        self._sync_speed_label()
        self._sync_strobe_label()

        self._load_pixel_sliders()
        self._paint_all_pixels()
        self.pixel_note.setText(
            "" if fixture.mode == "extended"
            else "This fixture is in Basic mode, so pixel values are not sent. "
                 "Set it to Extended in the Fixtures tab to use them."
        )

    def _load_ctc(self, box: QCheckBox, slider: QSlider, kelvin) -> None:
        box.setChecked(kelvin is not None)
        slider.setEnabled(kelvin is not None)
        if kelvin is not None:
            slider.setValue(kelvin)

    # --- presets ---------------------------------------------------------------

    def _refresh_presets(self, select: str | None = None) -> None:
        self.preset_list.clear()
        for name in sorted(self._settings.presets):
            item = QListWidgetItem(self._swatch_icon(self._settings.presets[name]), name)
            self.preset_list.addItem(item)
            if name == select:
                self.preset_list.setCurrentItem(item)
        if self.preset_list.currentItem() is None:
            self._show_preset(None)

    def _swatch_icon(self, data: dict) -> QIcon:
        pixmap = QPixmap(14, 14)
        pixmap.fill(QColor(swatch_hex(data)))
        return QIcon(pixmap)

    def _show_preset(self, item) -> None:
        if item is None or item.text() not in self._settings.presets:
            self.preset_details.setText("Select a preset to see its details.")
            self.preset_preview.show_state(FixtureState(beam_intensity=0.0, aura_intensity=0.0), False)
            return
        data = self._settings.presets[item.text()]
        state = preset_state(data)
        self.preset_preview.show_state(state, False, data.get("mode") == "extended")
        self.preset_details.setText("\n".join(describe(data)))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
        name = name.strip()
        if not ok or not name:
            return
        self._settings.presets[name] = make_preset(self._fixture.state, self._fixture.mode)
        self._refresh_presets(select=name)
        self._persist()

    def _load_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        state = preset_state(self._settings.presets[item.text()])
        self._engine.replace_fixture(self._index, replace(self._fixture, state=state))
        self._load_controls()

    def _delete_preset(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            return
        del self._settings.presets[item.text()]
        self._refresh_presets()
        self._persist()

    # --- fixtures table --------------------------------------------------------

    def _refresh_fixtures_table(self) -> None:
        self.fixture_table.setRowCount(0)
        for fixture in self._engine.fixtures:
            self._append_fixture_row(fixture.name, fixture.universe, fixture.address, fixture.mode)

    def _append_fixture_row(self, name: str, universe: int, address: int, mode: str) -> None:
        row = self.fixture_table.rowCount()
        self.fixture_table.insertRow(row)
        for column, value in enumerate((name, str(universe), str(address))):
            self.fixture_table.setItem(row, column, QTableWidgetItem(value))
        combo = QComboBox()
        for label, value in MODE_CHOICES:
            combo.addItem(label, value)
        combo.setCurrentIndex(max(0, combo.findData(mode)))
        self.fixture_table.setCellWidget(row, 3, combo)

    def _add_fixture_row(self) -> None:
        self._append_fixture_row("VDO Atomic Bold", 0, 1, "basic")

    def _remove_fixture_row(self) -> None:
        row = self.fixture_table.currentRow()
        if row >= 0 and self.fixture_table.rowCount() > 1:
            self.fixture_table.removeRow(row)

    def _apply_fixtures(self) -> None:
        existing = self._engine.fixtures
        fixtures = []
        try:
            for row in range(self.fixture_table.rowCount()):
                name = self.fixture_table.item(row, 0).text().strip() or "VDO Atomic Bold"
                universe = int(self.fixture_table.item(row, 1).text())
                address = int(self.fixture_table.item(row, 2).text())
                mode = self.fixture_table.cellWidget(row, 3).currentData()
                base = existing[row] if row < len(existing) else Fixture()
                # replace() re-runs Fixture validation, so bad addresses or modes raise ValueError here.
                fixtures.append(replace(base, name=name, universe=universe, address=address, mode=mode))
        except (ValueError, AttributeError) as exc:
            QMessageBox.warning(self, "Invalid fixture", f"Check the table values.\n\n{exc}")
            return
        if not fixtures:
            return
        self._engine.set_fixtures(fixtures)
        self._refresh_fixture_list()
        self._load_controls()
        self._persist()

    # --- network ---------------------------------------------------------------

    def _apply_network(self) -> None:
        network = NetworkSettings(
            protocol=self.protocol_combo.currentData(),
            target_ip=self.target_edit.text().strip(),
            artnet_port=self.port_spin.value(),
            refresh_hz=self.refresh_spin.value(),
            osc_enabled=self.osc_on.isChecked(),
            osc_host=self.osc_host_edit.text().strip() or "0.0.0.0",
            osc_port=self.osc_port_spin.value(),
        )
        self._settings.network = network
        self._engine.reconfigure(network)
        self._restart_osc()
        self._persist()

    def _restart_osc(self) -> None:
        if self._osc is not None:
            self._osc.stop()
            self._osc = None
        if self._settings.network.osc_enabled:
            try:
                net = self._settings.network
                self._osc = OscServer(self._engine, net.osc_port, host=net.osc_host,
                                      mappings=self._mapping_table, scenes=self._scenes)
                self._osc.start()
            except OSError as exc:
                self.network_status.setText(f"OSC could not start: {exc}")

    def start_outputs(self) -> None:
        self._engine.start()
        self._scenes.start()
        self._restart_osc()

    def _update_status(self) -> None:
        if self._engine.last_error:
            self.statusBar().showMessage(self._engine.last_error)
        else:
            net = self._settings.network
            target = net.target_ip or ("multicast" if net.protocol == "sacn" else "broadcast")
            osc = f", OSC on port {net.osc_port}" if self._osc else ""
            label = "Art-Net" if net.protocol == "artnet" else "sACN"
            self.statusBar().showMessage(f"{label} to {target}:{net.artnet_port}{osc}")

    def _update_preview(self) -> None:
        fixture = self._fixture
        self.preview.show_state(fixture.state, self._engine.blackout, fixture.mode == "extended",
                                self._engine.master)
        self._sync_top_bar()
        self._update_monitor()

    def _update_monitor(self) -> None:
        if self._osc is None:
            return
        count, address, value = self._osc.monitor.snapshot()
        if address is None:
            self.monitor_label.setText("No OSC messages yet.")
        else:
            shown = "" if value is None else f" = {value:.3f}"
            self.monitor_label.setText(f"Last OSC: {address}{shown}   ({count} received)")
        if self.learn_button.isChecked() and count > self._learn_start_count and address:
            self.map_address.setText(address)
            self.learn_button.setChecked(False)

    def _on_learn_toggled(self, on: bool) -> None:
        if not on:
            return
        if self._osc is None:
            self.learn_button.setChecked(False)
            self.statusBar().showMessage("Enable the OSC listener in the Network tab first.", 5000)
            return
        self._learn_start_count = self._osc.monitor.snapshot()[0]
        self.statusBar().showMessage("Learning: move a control in TouchDesigner or TouchOSC", 5000)

    # --- OSC mappings ----------------------------------------------------------

    def _form_mapping(self) -> Mapping | None:
        address = self.map_address.text().strip()
        if not address.startswith("/"):
            self.statusBar().showMessage("The OSC address must start with /", 5000)
            return None
        return Mapping(
            address=address,
            parameter=self.map_param.currentData(),
            fixture=self.map_fixture.currentData(),
            in_min=self.in_min_spin.value(),
            in_max=self.in_max_spin.value(),
            out_min=self.out_min_spin.value(),
            out_max=self.out_max_spin.value(),
        )

    def _add_mapping(self) -> None:
        mapping = self._form_mapping()
        if mapping is not None:
            self._commit_mappings(self._settings.mappings + [mapping])

    def _update_mapping(self) -> None:
        row = self.mapping_table.currentRow()
        mapping = self._form_mapping()
        if mapping is None or not 0 <= row < len(self._settings.mappings):
            return
        mappings = list(self._settings.mappings)
        mappings[row] = mapping
        self._commit_mappings(mappings)

    def _remove_mapping(self) -> None:
        row = self.mapping_table.currentRow()
        if 0 <= row < len(self._settings.mappings):
            mappings = list(self._settings.mappings)
            del mappings[row]
            self._commit_mappings(mappings)

    def _commit_mappings(self, mappings: list[Mapping]) -> None:
        self._settings.mappings = mappings
        self._mapping_table.set(mappings)
        self._refresh_mapping_table()
        self._persist()

    def _refresh_mapping_table(self) -> None:
        self.mapping_table.setRowCount(0)
        for mapping in self._settings.mappings:
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            fixture = "All fixtures" if mapping.fixture is None else f"{mapping.fixture + 1}"
            param = PARAMETERS[mapping.parameter].label if mapping.parameter in PARAMETERS else mapping.parameter
            cells = [
                mapping.address,
                fixture,
                param,
                f"{mapping.in_min:g} to {mapping.in_max:g}",
                f"{mapping.out_min:g} to {mapping.out_max:g}",
            ]
            for column, text in enumerate(cells):
                self.mapping_table.setItem(row, column, QTableWidgetItem(text))

    def _load_selected_mapping(self) -> None:
        row = self.mapping_table.currentRow()
        if not 0 <= row < len(self._settings.mappings):
            return
        m = self._settings.mappings[row]
        self._loading_mapping = True
        try:
            self.map_address.setText(m.address)
            self.map_fixture.setCurrentIndex(max(0, self.map_fixture.findData(m.fixture)))
            self.map_param.setCurrentIndex(max(0, self.map_param.findData(m.parameter)))
            self.in_min_spin.setValue(m.in_min)
            self.in_max_spin.setValue(m.in_max)
            self.out_min_spin.setValue(m.out_min)
            self.out_max_spin.setValue(m.out_max)
        finally:
            self._loading_mapping = False

    def _on_map_param_changed(self, _index: int) -> None:
        if self._loading_mapping:
            return
        param = PARAMETERS[self.map_param.currentData()]
        self.out_min_spin.setValue(param.lo)
        self.out_max_spin.setValue(param.hi)

    # --- persistence -----------------------------------------------------------

    def _snapshot(self) -> Settings:
        """The whole project as it is right now."""
        return Settings(
            network=self._engine.network,
            fixtures=self._engine.fixtures,
            presets=self._settings.presets,
            mappings=self._settings.mappings,
            master=self._engine.master,
            scenes=self._scenes.scenes,
            playlist=self._scenes.playlist,
            fade_time=self._scenes.fade_time,
        )

    def _persist(self) -> None:
        self._settings = self._snapshot()
        if self._settings_path is None:
            return
        try:
            save_settings(self._settings, self._settings_path)
        except OSError as exc:
            self.statusBar().showMessage(f"Could not save settings: {exc}")

    # --- projects --------------------------------------------------------------

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Martin project (*.json)")
        if not path:
            return
        try:
            settings = load_project(Path(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "Could not open project", str(exc))
            return
        self._project_path = Path(path)
        self._apply_settings(settings)
        self.statusBar().showMessage(f"Opened {path}", 5000)

    def save_project(self) -> None:
        if self._project_path is None:
            self.save_project_as()
            return
        self._write_project(self._project_path)

    def save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", "martin_project.json",
                                              "Martin project (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self._project_path = Path(path)
        self._write_project(self._project_path)

    def _write_project(self, path: Path) -> None:
        try:
            save_project(self._snapshot(), path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save project", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}", 5000)

    def _apply_settings(self, settings: Settings) -> None:
        """Replace the whole working state with `settings` and refresh every tab."""
        self._settings = settings
        self._engine.blackout = False
        self._engine.master = settings.master
        self._engine.reconfigure(settings.network)
        self._engine.set_fixtures(settings.fixtures)
        self._mapping_table.set(settings.mappings)
        self._scenes.set_content(settings.scenes, settings.playlist)
        self._scenes.fade_time = settings.fade_time
        self.fade_spin.blockSignals(True)
        self.fade_spin.setValue(settings.fade_time)
        self.fade_spin.blockSignals(False)
        self._index = 0
        self._refresh_fixture_list()
        self._load_controls()
        self._refresh_presets()
        self._refresh_fixtures_table()
        self._refresh_mapping_table()
        self._refresh_scenes()
        self._load_network_widgets(settings.network)
        self._sync_top_bar()
        self._restart_osc()
        self._persist()

    # --- scenes and playlist ---------------------------------------------------

    def _refresh_scenes(self) -> None:
        scenes = self._scenes.scenes
        self.scene_table.setRowCount(0)
        for scene in scenes:
            row = self.scene_table.rowCount()
            self.scene_table.insertRow(row)
            cells = [str(scene.id), scene.name, str(len(scene.fixtures)), f"{round(scene.master * 100)} %"]
            for column, text in enumerate(cells):
                self.scene_table.setItem(row, column, QTableWidgetItem(text))

        self.playlist_scene_combo.clear()
        for scene in scenes:
            self.playlist_scene_combo.addItem(f"{scene.id}  {scene.name}".rstrip(), scene.id)

        self.playlist_list.clear()
        for number, item in enumerate(self._scenes.playlist, start=1):
            name = self._scene_name(item.scene_id)
            hold = f"  hold {item.hold:g} s" if item.hold > 0 else ""
            fade = f"  fade {item.fade:g} s" if item.fade > 0 else ""
            self.playlist_list.addItem(f"{number}. #{item.scene_id} {name}{hold}{fade}")
        self._update_now_playing()

    def _scene_name(self, scene_id: int) -> str:
        scene = self._scenes.get(scene_id)
        return scene.name if scene else "(missing)"

    def _selected_scene_id(self) -> int | None:
        row = self.scene_table.currentRow()
        if row < 0:
            return None
        return int(self.scene_table.item(row, 0).text())

    def _on_fade_changed(self, value: float) -> None:
        self._scenes.fade_time = value
        self._persist()

    def _store_scene(self) -> None:
        scene_id = self.scene_id_spin.value()
        name = self.scene_name_edit.text().strip() or f"Scene {scene_id}"
        self._scenes.store(scene_id, name)
        self._refresh_scenes()
        self._persist()
        self.statusBar().showMessage(f"Stored scene {scene_id}: {name}", 4000)

    def _recall_scene(self) -> None:
        scene_id = self._selected_scene_id()
        if scene_id is None:
            scene_id = self.scene_id_spin.value()
        if not self._scenes.recall(scene_id):
            self.statusBar().showMessage(f"No scene with ID {scene_id}", 4000)
        self._update_now_playing()

    def _rename_scene(self) -> None:
        scene_id = self._selected_scene_id()
        if scene_id is None:
            self.statusBar().showMessage("Select a scene in the table first", 4000)
            return
        current = self._scene_name(scene_id)
        name, ok = QInputDialog.getText(self, "Rename scene", f"New name for scene #{scene_id}:", text=current)
        name = name.strip()
        if not ok or not name:
            return
        self._scenes.rename(scene_id, name)
        self._refresh_scenes()
        self._persist()

    def _delete_scene(self) -> None:
        scene_id = self._selected_scene_id()
        if scene_id is None:
            return
        self._scenes.delete(scene_id)
        self._refresh_scenes()
        self._persist()

    def _playlist_items(self) -> list[PlaylistItem]:
        return self._scenes.playlist

    def _commit_playlist(self, items: list[PlaylistItem], select: int | None = None) -> None:
        self._scenes.set_playlist(items)
        self._refresh_scenes()
        if select is not None and 0 <= select < self.playlist_list.count():
            self.playlist_list.setCurrentRow(select)
        self._persist()

    def _playlist_add(self) -> None:
        scene_id = self.playlist_scene_combo.currentData()
        if scene_id is None:
            return
        items = self._playlist_items() + [
            PlaylistItem(scene_id, self.playlist_hold.value(), self.playlist_fade.value())
        ]
        self._commit_playlist(items, select=len(items) - 1)

    def _load_playlist_row(self, row: int) -> None:
        """Show the selected item's hold and fade in the editor, so they can be changed."""
        items = self._playlist_items()
        if 0 <= row < len(items):
            self.playlist_hold.setValue(items[row].hold)
            self.playlist_fade.setValue(items[row].fade)

    def _playlist_update(self) -> None:
        row = self.playlist_list.currentRow()
        items = self._playlist_items()
        if 0 <= row < len(items):
            items[row] = PlaylistItem(items[row].scene_id, self.playlist_hold.value(), self.playlist_fade.value())
            self._commit_playlist(items, select=row)

    def _playlist_remove(self) -> None:
        row = self.playlist_list.currentRow()
        items = self._playlist_items()
        if 0 <= row < len(items):
            del items[row]
            self._commit_playlist(items, select=min(row, len(items) - 1))

    def _playlist_move(self, delta: int) -> None:
        row = self.playlist_list.currentRow()
        items = self._playlist_items()
        target = row + delta
        if 0 <= row < len(items) and 0 <= target < len(items):
            items[row], items[target] = items[target], items[row]
            self._commit_playlist(items, select=target)

    def _playlist_step(self, delta: int) -> None:
        self._scenes.step(delta)
        self._update_now_playing()

    def _playlist_go(self) -> None:
        row = self.playlist_list.currentRow()
        if row < 0:
            row = 0
        self._scenes.go(row)
        self._update_now_playing()

    def _update_now_playing(self) -> None:
        position = self._scenes.position
        items = self._scenes.playlist
        if position is None or position >= len(items):
            self.now_playing_label.setText("Nothing playing.")
            return
        item = items[position]
        self.now_playing_label.setText(
            f"Now playing: {position + 1} of {len(items)}, scene #{item.scene_id} {self._scene_name(item.scene_id)}"
        )

    def _update_scene_playback(self) -> None:
        self._scenes.tick()
        if self._scenes.version != self._seen_scene_version or self._scenes.fading:
            # A scene was applied, or a fade is moving: show the fixture's current settings.
            self._seen_scene_version = self._scenes.version
            self._load_controls()
            self._update_now_playing()
        if self.isVisible() and self.playlist_list.count() != len(self._scenes.playlist):
            self._refresh_scenes()

    def _load_network_widgets(self, net: NetworkSettings) -> None:
        self.protocol_combo.setCurrentIndex(max(0, self.protocol_combo.findData(net.protocol)))
        self.target_edit.setText(net.target_ip)
        self.port_spin.setValue(net.artnet_port)
        self.refresh_spin.setValue(net.refresh_hz)
        self.osc_on.setChecked(net.osc_enabled)
        self.osc_host_edit.setText(net.osc_host)
        self.osc_port_spin.setValue(net.osc_port)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._status_timer.stop()
        self._preview_timer.stop()
        self._scene_timer.stop()
        self._scenes.stop()
        self._pulse_timer.stop()
        if self._osc is not None:
            self._osc.stop()
        self._engine.stop()
        self._persist()
        super().closeEvent(event)
