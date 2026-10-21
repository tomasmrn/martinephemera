"""Built-in effect and colour preset tables for the VDO Atomic Bold.

Numbers and names come from the Martin VDO Atomic Bold user guide:
- FX table: "FX Table" (pages 56-61), used on DMX channel 16 in Basic mode.
- Colour presets: "DMX mode Basic" (pages 43-44), used on channels 13 (beam) and 26 (aura).
"""

# Each line is "<DMX value> <name>". 0 (No Effect) is added separately.
_FX_TABLE = """
1 Beam Wave
2 Beam Step
3 Beam Pulse
4 Beam Blackout Strobe
5 Beam 2x Strobe
6 Beam 3x Strobe
7 Beam 4x Strobe
8 Beam Up Down Flash
9 Beam Up Down Flash Second Color
10 Beam Up Flash Down Flash
11 Beam Up Flash Down Flash Second Color
12 Beam Random Levels
13 Beam Movie Flicker
14 Beam Atomic Lighting
15 Beam Thunderstorm
16 Beam HouseLight
17 Beam Threshold Strobe
18 Beam Threshold On
48 Beam Rainbow Wave
49 Beam Rainbow Step
50 Beam Rainbow Pulse
51 Beam RGB Wave
52 Beam RGB Step
53 Beam RGB Pulse
54 Beam CMY Wave
55 Beam CMY Step
56 Beam CMY Pulse
57 Beam Random Mix Wave
58 Beam Random Mix Step
59 Beam Random Mix Pulse
60 Beam Spectrum Shifter
61 Beam Dual Color Flip
62 Beam Red White Blue Fade
63 Beam Red White Blue Snap
64 Beam Fire
65 Beam Water
66 Beam Swimming Pool
67 Beam Ice
68 Beam Hot and Cold
69 Beam Warm and Fuzzy
70 Beam Silver and Gold
71 Beam Gold and Silver
72 Beam Electric Arc
73 Beam Plasma
96 Aura Wave
97 Aura Step
98 Aura Pulse
99 Aura Blackout Strobe
100 Aura 2x Strobe
101 Aura 3x Strobe
102 Aura 4x Strobe
103 Aura Up Down Flash
104 Aura Up Down Flash Second Color
105 Aura Up Flash Down Flash
106 Aura Up Flash Second Color Down Flash Second Color
107 Aura Random Levels
108 Aura SparkleStars
109 Aura SparkleStars Heavy
110 Aura Starfield
111 Aura Fiberoptic
112 Aura PixelKiller
113 Aura Build Up Down
114 Aura Ring Wave
115 Aura Ring Step
116 Aura Ring Pulse
117 Aura Waterdrop
118 Aura Radar Spinning
119 Aura Line Spinning
120 Aura Cross Spinning
121 Aura Cross Circle Wave
122 Aura Sonar 1
123 Aura Sonar 2
124 Aura Sonar 3
125 Aura Sonar 6
126 Aura Sonar 9
127 Aura NightRider
128 Aura Snowflakes
129 Aura Rain
130 Aura 1 Slice Pie Wave
131 Aura 1 Slice Pie Step
132 Aura 1 Slice Pie Pulse
133 Aura 2 Slice Pie Wave
134 Aura 2 Slice Pie Step
135 Aura 2 Slice Pie Pulse
136 Aura 3 Slice Pie Wave
137 Aura 3 Slice Pie Step
138 Aura 3 Slice Pie Pulse
139 Aura Random Slice Pie Wave
140 Aura Random Slice Pie Step
141 Aura Random Slice Pie Pulse
142 Aura Random 12 Wave
143 Aura Random 12 Step
144 Aura Random 12 Pulse
145 Aura Random 24 Wave
146 Aura Random 24 Step
147 Aura Random 24 Pulse
148 Aura Vertical Wave
149 Aura Horizontal Wave
150 Aura Vertical Bouncing Line
151 Aura Horizontal Bouncing Line
152 Aura Vertical Horizontal Bouncing Line
153 Aura Noise
154 Aura Movie Flicker
155 Aura Atomic Lighting
156 Aura Thunderstorm
157 Aura Split Rotate Indexable
158 Aura Split Rotate Rotateable
160 Aura Rainbow Wave
161 Aura Rainbow Step
162 Aura Rainbow Pulse
163 Aura RGB Wave
164 Aura RGB Step
165 Aura RGB Pulse
166 Aura CMY Wave
167 Aura CMY Step
168 Aura CMY Pulse
169 Aura Random Mix Wave
170 Aura Random Mix Step
171 Aura Random Mix Pulse
172 Aura Spectrum Shifter
173 Aura Red White Blue Fade
174 Aura Red White Blue Snap
175 Aura Fire
176 Aura Water
177 Aura Swimming Pool
178 Aura Ice
179 Aura Hot and Cold
180 Aura Warm and Fuzzy
181 Aura Silver and Gold
182 Aura Gold and Silver
183 Aura Electric Arc
184 Aura Plasma
185 Aura Police Car 1
186 Aura Police Car 2
187 Aura Police Car 3
208 Full Thunderstorm
209 Full Welding
210 Full 3 Step Strobe
211 Full Tick Tock
212 Aura Ramp Beam Flash
213 Beam Ramp Aura Flash
214 Beam-Aura Wave
215 Beam-Aura Step
216 Beam-Aura Pulse
217 Tungsten Emulation Beam+Aura
218 Tungsten Emulation Beam+Aura Decay
219 Tungsten Emulation Beam Only
220 Tungsten Emulation Beam Only Decay
221 Tungsten Emulation Aura Only
222 Tungsten Emulation Aura Only Decay
223 Police Car 4
224 Police Car 5
225 Police Car 6
226 Police Car 7
227 Police Car 8
228 Police Car 9
"""

FX_NAMES: dict[int, str] = {0: "No Effect"}
for _line in _FX_TABLE.strip().splitlines():
    _number, _name = _line.split(" ", 1)
    FX_NAMES[int(_number)] = _name

# Colour presets used on channel 13 (beam) and channel 26 (aura).
# Preset n (1-48) is sent as DMX value 9 + 2n, so preset 1 = 11 ... preset 48 = 105.
COLOR_PRESET_NAMES: list[str] = [
    "LEE 790 Moroccan pink",
    "LEE 157 Pink",
    "LEE 332 Special rose pink",
    "LEE 328 Follies pink",
    "LEE 345 Fuchsia pink",
    "LEE 194 Surprise pink",
    "LEE 181 Congo Blue",
    "LEE 071 Tokyo Blue",
    "LEE 120 Deep Blue",
    "LEE 079 Just Blue",
    "LEE 132 Medium Blue",
    "LEE 200 Double CT Blue",
    "LEE 161 Slate Blue",
    "LEE 201 Full CT Blue",
    "LEE 202 Half CT Blue",
    "LEE 117 Steel Blue",
    "LEE 353 Lighter Blue",
    "LEE 118 Light Blue",
    "LEE 116 Medium Blue Green",
    "LEE 124 Dark Green",
    "LEE 139 Primary Green",
    "LEE 089 Moss Green",
    "LEE 122 Fern Green",
    "LEE 738 JAS Green",
    "LEE 088 Lime Green",
    "LEE 100 Spring Yellow",
    "LEE 104 Deep Amber",
    "LEE 179 Chrome Orange",
    "LEE 105 Orange",
    "LEE 021 Gold Amber",
    "LEE 778 Millennium Gold",
    "LEE 135 Deep Golden Amber",
    "LEE 164 Flame Red",
    "LEE 113 Magenta",
    "LEE 343 Medium Lavender",
    "Pure White",
    "Pure Red",
    "Pure Yellow",
    "Pure Green",
    "Pure Cyan",
    "Pure Blue",
    "Pure Magenta",
    "LEE 115 Peacock Blue",
    "LEE 180 Dark Lavender",
    "LEE 287 Double CT Orange",
    "LEE 204 Full CT Orange",
    "LEE 205 Half CT Orange",
    "LEE 015 Deep Straw",
]

# Approximate display colours for the presets above, as hex (#RRGGBB).
# The manual has no RGB values. The "Pure" presets are exact. The LEE colours are
# approximations of the LEE swatches, so correct any that look wrong on the fixture.
COLOR_PRESET_HEX: list[str] = [
    "#D6337F", "#F4A9C0", "#E8669C", "#F08CB3", "#C93B8F",   # 1-5  pinks
    "#F6B2C7", "#1F4B93", "#3A7FC1", "#1B3F8B", "#3B6FC4",   # 6-10 pink, blues
    "#2E77C9", "#8EBFE6", "#5A6FA8", "#B9D7EE", "#D5E8F5",   # 11-15 blues
    "#5D8FBF", "#A9D5F0", "#8CC4EB", "#2FA7A0", "#1F6B3A",   # 16-20 blues, greens
    "#2FA24A", "#6B8A3A", "#8BB84E", "#A9CF5A", "#C2DE3F",   # 21-25 greens
    "#F6EC6A", "#F2A300", "#F28C1E", "#F47A20", "#F6B93B",   # 26-30 yellows, ambers
    "#F3C24E", "#E9962B", "#E8402A", "#D4238E", "#B58CC9",   # 31-35 golds, reds, lavender
    "#FFFFFF", "#FF0000", "#FFFF00", "#00FF00", "#00FFFF",   # 36-40 pure
    "#0000FF", "#FF00FF",                                    # 41-42 pure
    "#1C8CA6", "#6B4E9A", "#F5A35A", "#F8C07F", "#FBDCB6",   # 43-47
    "#F7E09A",                                               # 48
]

# The same colours as 0.0-1.0 (r, g, b) tuples, for the preview and the engine.
COLOR_PRESET_RGB: list[tuple[float, float, float]] = [
    tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in COLOR_PRESET_HEX
]



# The five groups from the FX table headings (user guide, pages 56-61). All of them are sent on
# DMX channel 16, so only one effect can run at a time. "PWM adjustment" (255) is not an effect and is left out.
BEAM_INTENSITY_FX: tuple[int, ...] = tuple(n for n in FX_NAMES if 1 <= n <= 47)
BEAM_COLOUR_FX: tuple[int, ...] = tuple(n for n in FX_NAMES if 48 <= n <= 95)
AURA_INTENSITY_FX: tuple[int, ...] = tuple(n for n in FX_NAMES if 96 <= n <= 159)
AURA_COLOUR_FX: tuple[int, ...] = tuple(n for n in FX_NAMES if 160 <= n <= 207)
COMBINED_FX: tuple[int, ...] = tuple(n for n in FX_NAMES if 208 <= n <= 254)

# (heading from the manual, effect numbers in that group), in the manual's order.
FX_GROUPS: list[tuple[str, tuple[int, ...]]] = [
    ("Beam intensity effects", BEAM_INTENSITY_FX),
    ("Beam colour effects", BEAM_COLOUR_FX),
    ("Aura intensity effects", AURA_INTENSITY_FX),
    ("Aura colour effects", AURA_COLOUR_FX),
    ("Beam and aura combined effects", COMBINED_FX),
]
