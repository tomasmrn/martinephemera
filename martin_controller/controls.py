"""Option tables and unit conversions for the strobe, flash and settings controls.

Values come from the Martin VDO Atomic Bold user guide, DMX modes Basic and Extended:
- Beam special effects: channel 5 (page 43)
- Beam flash duration and rate: channels 3 and 4 (page 41 for the 3/4-channel modes, page 43 for Basic)
- Aura strobe/shutter: channel 19 (page 46)
- Control/Settings: channel 15 (pages 45-46)
"""

# Channel 5: beam special effects (ramps, random, lightning, spikes).
BEAM_SPECIAL_EFFECTS = [
    ("No effect", 0),
    ("Ramp up", 6),
    ("Ramp down", 43),
    ("Ramp up and down", 86),
    ("Random", 129),
    ("Lightning", 172),
    ("Spikes (flash over low light)", 215),
]

# Channel 3: beam flash duration, 0-255 maps linearly from 7 ms to 650 ms.
# Channel 4: beam flash rate, 0-255 maps linearly from 0.289 Hz to 16.67 Hz.
FLASH_DURATION_MIN_MS, FLASH_DURATION_MAX_MS = 7.0, 650.0
FLASH_RATE_MIN_HZ, FLASH_RATE_MAX_HZ = 0.289, 16.67


def flash_duration_ms(value: int) -> float:
    return FLASH_DURATION_MIN_MS + value * (FLASH_DURATION_MAX_MS - FLASH_DURATION_MIN_MS) / 255


def flash_rate_hz(value: int) -> float:
    return FLASH_RATE_MIN_HZ + value * (FLASH_RATE_MAX_HZ - FLASH_RATE_MIN_HZ) / 255


def _unit(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# Channel 19: aura strobe/shutter.
#   0-19 shutter closed, 20-49 no strobe, 50-200 strobe slow to fast,
#   201-210 no strobe, 211-255 random strobe slow to fast.
AURA_NO_STROBE = 30
AURA_SHUTTER_CLOSED = 0


def aura_strobe_value(kind: str, speed: float = 0.5) -> int:
    """Build a channel 19 value. kind: 'none', 'shutter', 'strobe' or 'random'. speed 0.0 (slow) to 1.0 (fast)."""
    speed = _unit(speed)
    if kind == "shutter":
        return AURA_SHUTTER_CLOSED
    if kind == "strobe":
        return 50 + round(speed * 150)
    if kind == "random":
        return 211 + round(speed * 44)
    return AURA_NO_STROBE


def parse_aura_strobe(value: int) -> tuple[str, float]:
    """Inverse of aura_strobe_value: return (kind, speed) for a channel 19 value."""
    if value <= 19:
        return "shutter", 0.0
    if 50 <= value <= 200:
        return "strobe", (value - 50) / 150
    if 211 <= value <= 255:
        return "random", (value - 211) / 44
    return "none", 0.0


# Channel 15: Control/Settings. Only one function can be active at a time, so the
# UI sends each one as a short pulse and then returns the channel to 0 (no function).
# Each entry: (label, DMX value, hold time in seconds). Hold times follow the manual.
CONTROL_SETTINGS = [
    ("Reset fixture (5 s)", 10, 6.0),
    ("Linear dimming curve (default)", 23, 2.0),
    ("Square law dimming curve", 24, 2.0),
    ("Inverse square law dimming curve", 25, 2.0),
    ("S-curve dimming curve", 26, 2.0),
    ("Enable video tracking (P3 only)", 36, 2.0),
    ("Disable video tracking (default)", 37, 2.0),
    ("Extended colour mode (default)", 38, 2.0),
    ("Calibrated colour mode", 39, 2.0),
    ("Fan: regulated, fixed output (default)", 54, 2.0),
    ("Fan: full speed", 55, 2.0),
    ("Fan: medium speed", 56, 2.0),
    ("Fan: low speed", 57, 2.0),
    ("Fan: ultra-low speed", 58, 2.0),
    ("Beam behaviour: LED (default)", 59, 2.0),
    ("Beam behaviour: Xenon", 60, 2.0),
    ("Scene capture: record current DMX (5 s)", 74, 6.0),
    ("Scene capture: playback on (5 s)", 75, 6.0),
    ("Scene capture: playback off (default)", 76, 2.0),
]

CONTROL_NO_FUNCTION = 0

# Extended mode: aura pixels 1-72 use channels 28-243, three channels (R, G, B) each.
PIXEL_COUNT = 72
PIXEL_FIRST_CHANNEL = 28


def pixel_start_channel(pixel: int) -> int:
    """First (red) channel for pixel 1-72."""
    if not 1 <= pixel <= PIXEL_COUNT:
        raise ValueError(f"pixel must be 1-{PIXEL_COUNT}, got {pixel}")
    return PIXEL_FIRST_CHANNEL + 3 * (pixel - 1)
