"""Martin VDO Atomic Bold model, DMX modes Basic (27 channels) and Extended (243 channels).

Channel numbers are 1-based, as printed in the user guide (DMX modes Basic and Extended,
pages 43-54). 16-bit values are sent coarse (high byte) first. Extended mode is Basic mode
plus 72 individually addressable aura pixels on channels 28-243.
"""

from dataclasses import asdict, dataclass, field, fields, replace

from .controls import PIXEL_COUNT, pixel_start_channel

BASIC_CHANNEL_COUNT = 27
EXTENDED_CHANNEL_COUNT = 243
MAX_DMX_ADDRESS = 512
MODES = {"basic": BASIC_CHANNEL_COUNT, "extended": EXTENDED_CHANNEL_COUNT}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def unit_to_u16(x: float) -> int:
    return round(_clamp01(x) * 65535)


def unit_to_u8(x: float) -> int:
    return round(_clamp01(x) * 255)


def kelvin_to_ctc(kelvin: int) -> int:
    """Colour temperature (2000-11000 K) to DMX value 11-191, 1 step per 50 K."""
    kelvin = max(2000, min(11000, int(kelvin)))
    return 11 + (kelvin - 2000) // 50


def color_preset_to_dmx(preset: int) -> int:
    """Colour preset 0 (none, mix via RGB) or 1-48 to DMX value 0 or 11-105."""
    if not 0 <= preset <= 48:
        raise ValueError(f"colour preset must be 0-48, got {preset}")
    return 0 if preset == 0 else 9 + 2 * preset


def _black_pixels() -> tuple:
    return tuple((0.0, 0.0, 0.0) for _ in range(PIXEL_COUNT))


@dataclass
class FixtureState:
    """Everything the UI or OSC can set on one fixture. Defaults are sensible for DMX use."""

    # Beam (main LED)
    beam_intensity: float = 1.0              # ch 1-2, 0 = blackout, 65535 = full
    beam_flash_duration: int = 0             # ch 3, 0-255 (7 ms to 650 ms)
    beam_flash_rate: int = 0                 # ch 4, 0-255 (0.289 Hz to 16.67 Hz)
    beam_special_effect: int = 0             # ch 5, see controls.BEAM_SPECIAL_EFFECTS
    beam_rgb: tuple = (1.0, 1.0, 1.0)        # ch 6-11, 16-bit each
    beam_ctc_kelvin: int | None = None       # ch 12, None = CTC disabled
    beam_color_preset: int = 0               # ch 13, 0 = none, 1-48 = LEE/pure presets
    beam_p3_mix: int = 0                     # ch 14, 0 = DMX-mode colour
    # Control and effects
    control: int = 0                         # ch 15, one function at a time (see controls.py)
    fx: int = 0                              # ch 16, 0 = no effect, see effects.FX_NAMES
    fx_speed: int = 128                      # ch 17, 128 = stopped
    fx_sync: int = 36                        # ch 18, 36 = synchronized
    # Aura (backlight)
    aura_strobe: int = 30                    # ch 19, see controls.aura_strobe_value
    aura_intensity: float = 1.0              # ch 20-21, 16-bit
    aura_rgb: tuple = (1.0, 1.0, 1.0)        # ch 22-24, 8-bit each
    aura_ctc_kelvin: int | None = None       # ch 25
    aura_color_preset: int = 0               # ch 26
    aura_p3_mix: int = 0                     # ch 27
    # Extended mode only: per-pixel aura colour, pixels 1-72 as (r, g, b) in 0.0-1.0
    aura_pixels: tuple = field(default_factory=_black_pixels)

    def to_dmx(self, blackout: bool = False, extended: bool = False, master: float = 1.0) -> bytes:
        ch = bytearray(EXTENDED_CHANNEL_COUNT if extended else BASIC_CHANNEL_COUNT)

        def put8(channel: int, value: int) -> None:
            ch[channel - 1] = max(0, min(255, int(value)))

        def put16(channel: int, value: int) -> None:
            value = max(0, min(65535, int(value)))
            ch[channel - 1], ch[channel] = divmod(value, 256)

        beam_level = 0 if blackout else unit_to_u16(self.beam_intensity * master)
        aura_level = 0 if blackout else unit_to_u16(self.aura_intensity * master)

        put16(1, beam_level)
        put8(3, self.beam_flash_duration)
        put8(4, self.beam_flash_rate)
        put8(5, self.beam_special_effect)
        put16(6, unit_to_u16(self.beam_rgb[0]))
        put16(8, unit_to_u16(self.beam_rgb[1]))
        put16(10, unit_to_u16(self.beam_rgb[2]))
        put8(12, 0 if self.beam_ctc_kelvin is None else kelvin_to_ctc(self.beam_ctc_kelvin))
        put8(13, color_preset_to_dmx(self.beam_color_preset))
        put8(14, self.beam_p3_mix)
        put8(15, self.control)
        put8(16, self.fx)
        put8(17, self.fx_speed)
        put8(18, self.fx_sync)
        put8(19, self.aura_strobe)
        put16(20, aura_level)
        put8(22, unit_to_u8(self.aura_rgb[0]))
        put8(23, unit_to_u8(self.aura_rgb[1]))
        put8(24, unit_to_u8(self.aura_rgb[2]))
        put8(25, 0 if self.aura_ctc_kelvin is None else kelvin_to_ctc(self.aura_ctc_kelvin))
        put8(26, color_preset_to_dmx(self.aura_color_preset))
        put8(27, self.aura_p3_mix)

        if extended:
            for pixel, rgb in enumerate(self.aura_pixels, start=1):
                start = pixel_start_channel(pixel)
                for offset, component in enumerate(rgb):
                    put8(start + offset, 0 if blackout else unit_to_u8(component * master))
        return bytes(ch)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FixtureState":
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        for key in ("beam_rgb", "aura_rgb"):
            if key in values:
                values[key] = tuple(values[key])
        if "aura_pixels" in values:
            pixels = [tuple(p) for p in values["aura_pixels"]]
            if len(pixels) != PIXEL_COUNT:
                pixels = list(_black_pixels())
            values["aura_pixels"] = tuple(pixels)
        return cls(**values)


@dataclass
class Fixture:
    """One physical fixture: where it listens on the network, its DMX mode and its state."""

    name: str = "VDO Atomic Bold"
    universe: int = 0                        # Art-Net port-address, 0-32767 (sACN: 1-63999)
    address: int = 1                         # DMX start address
    mode: str = "basic"                      # "basic" (27 ch) or "extended" (243 ch)
    state: FixtureState = field(default_factory=FixtureState)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be 'basic' or 'extended', got {self.mode!r}")
        last_address = MAX_DMX_ADDRESS - self.channel_count + 1
        if not 1 <= self.address <= last_address:
            raise ValueError(f"start address must be 1-{last_address} in {self.mode} mode, got {self.address}")
        if not 0 <= self.universe <= 0x7FFF:
            raise ValueError(f"universe must be 0-32767, got {self.universe}")

    @property
    def channel_count(self) -> int:
        return MODES[self.mode]

    def to_dmx(self, blackout: bool = False, master: float = 1.0) -> bytes:
        return self.state.to_dmx(blackout=blackout, extended=self.mode == "extended", master=master)

    def to_dict(self) -> dict:
        return {"name": self.name, "universe": self.universe, "address": self.address,
                "mode": self.mode, "state": self.state.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "Fixture":
        return cls(name=data.get("name", "VDO Atomic Bold"),
                   universe=int(data.get("universe", 0)),
                   address=int(data.get("address", 1)),
                   mode=data.get("mode", "basic"),
                   state=FixtureState.from_dict(data.get("state", {})))


def with_state(fixture: Fixture, **changes) -> Fixture:
    """Return a copy of the fixture with some FixtureState fields changed."""
    return replace(fixture, state=replace(fixture.state, **changes))
