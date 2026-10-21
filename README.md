# Martin VDO Atomic Bold controller

A Python desktop app that drives Martin VDO Atomic Bold fixtures over Art-Net,
with a GUI for the built-in effects and colour presets, and OSC input for TouchOSC.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m martin_controller
```

Settings (network, fixtures, saved presets) are stored in `settings.json` next to the project.

## Fixture configuration

The app sends DMX over Art-Net, but it does **not** set the fixture's own configuration.
On the fixture, the following must match what the app sends:

- Protocol set to Art-Net or sACN (matching the Network tab)
- Universe (Art-Net port-address, 0-32767)
- DMX start address
- DMX mode **Basic** (27 channels)

Set these with the Martin Companion app over RDM, or through the P3 System Controller.
Put the same universe and start address in the **Fixtures** tab.

Network notes from the user guide:

- Use a 100 Mbit switch port for each junction box or break-in cable.
- Use shielded Cat 5e or better Ethernet cable.
- Broadcast (`255.255.255.255`) works on a simple network. For a dedicated network, use the junction box's IP as the target.

## Using the app

| Tab | What it does |
|---|---|
| Control | Beam and aura intensity, RGB, colour presets, colour temperature (CTC) |
| Effects | Built-in effects in five groups from the manual (beam intensity, beam colour, aura intensity, aura colour, combined), speed, sync |
| Strobe and flash | Beam special effect, aura strobe/shutter (kind and speed), beam flash duration and rate |
| Settings | Control/Settings functions (channel 15): reset, dimming curves, fan, scene capture, and more |
| Pixels | Extended mode only: colour of the 72 aura pixels |
| OSC mapping | Map incoming OSC addresses (from TouchDesigner or any OSC sender) to light parameters |
| Scenes | Store the look as a numbered scene, build a playlist of scenes, and play it back (manually or auto-advance) |
| Presets | Save and recall the full state of a fixture |
| Fixtures | Name, universe, start address and DMX mode (Basic or Extended) for each fixture |
| Network | Protocol (Art-Net or sACN), target and port, refresh rate, OSC listener |

The fixture selector at the top picks which fixture the Control and Effects tabs edit.
Blackout is a top-bar checkbox. The **Master** slider in the top bar scales the beam and aura
intensity of every fixture (0 to 100 %). It can also be set from OSC (`/martin/master`, 0.0-1.0) or mapped
from TouchDesigner (parameter "Master dimmer").

## Projects

File menu: **Open project**, **Save project** (Ctrl+S), **Save project as**. A project file is a single
`.json` file with the network settings, fixtures and their modes, presets, OSC mappings and the master
level. Opening a project replaces the current setup in every tab. Blackout is not saved, so a project
always opens with blackout off.

The app also keeps its last state in `settings.json`, which it loads at startup.

The **preview** panel above the tabs draws the selected fixture's beam and aura colour, intensity,
blackout and effect name. It is a virtual fixture, so you can check the controls without hardware.
It shows RGB colour only; built-in effects and colour presets appear as text, because the manual
doesn't give their exact colours or timing.

## Built-in effects

The manual's FX table has five groups: beam intensity, beam colour, aura intensity, aura colour, and
beam and aura combined. All five use the same DMX channel (16), so **only one effect runs at a time**.
Choosing an effect in one group sets the other groups to None. The OSC mapping tab has one parameter
per group, and each one snaps to the nearest effect in its group.

## Scenes and playlists

A **scene** is a saved look: every fixture's settings plus the master level. Each scene has a numeric ID
(0 to 9999) and a name. Storing a scene with an existing ID replaces it. Blackout is not part of a scene.
Playlist items fade into their scene for their own fade time. Direct recalls (the Recall button and `/martin/scene`) use the **Fade (direct)** setting in the Scenes tab, which is 0 (instant) by default.
A fade blends intensities, RGB colours, the aura pixels, and the flash timing. Effect numbers, colour presets,
colour temperature, strobe mode and the special effect switch to their new value as the fade starts, since
they cannot be blended. A fade overwrites manual changes until it finishes. A new recall during a fade starts
from the look on screen.

A **playlist** is an ordered list of scenes. Each item has a hold time in seconds and its own fade time in seconds (0 = cut). Edit either one by selecting the item and pressing Update. Use **Previous**,
**Go** and **Next** to step through it. Playback wraps around at the end. Tick **Auto-advance** to move
on automatically after each item's hold time. A hold of 0 waits for Next.

OSC control (send the scene ID as the value):

| Address | Value | Action |
|---|---|---|
| `/martin/scene` | scene ID | Recall the scene when the ID changes. A steady stream of the same ID does nothing |
| `/martin/scene/recall` | scene ID | Recall the scene every time (for buttons) |
| `/martin/scene/fade` | seconds | Set the fade time for scene recalls (0 = instant) |
| `/martin/playlist/next` | 1 (button press) | Next playlist item. Fires when the value rises to 0.5 or more |
| `/martin/playlist/prev` | 1 (button press) | Previous playlist item. Fires when the value rises to 0.5 or more |
| `/martin/playlist/go` | position (0 = first) | Play that playlist item when the value changes |

From TouchDesigner, the mapping parameter **Recall scene by ID** recalls the scene only when the rounded
ID changes, so a steady control does not keep re-applying the scene.

**Manual changes after a scene.** A scene sets every parameter when it starts. OSC parameter values only count when they change, so a sender that keeps repeating the same value (for example a fader that is not being moved) does not overwrite the scene. Anything you then change
by hand (the UI, OSC, or a mapping) becomes an override and stays until the next scene starts. During a fade,
overridden parameters keep the value you set, and the rest of the scene still fades in. The Scenes tab lists
what has been changed by hand. Recalling a scene again resets everything to the scene.

Scenes and the playlist are saved in the settings file and in project files.

## DMX modes

**Basic** (27 channels): beam, aura and effect controls.

**Extended** (243 channels): everything in Basic, plus individual colour for each of the 72 aura pixels
on channels 28-243. Channels 1-27 are the same in both modes. Choose the mode per fixture in the
Fixtures tab. Extended fixtures need a start address of 270 or lower.

## Settings (channel 15)

The fixture runs one control function at a time. The Settings tab sends the chosen function as a
short pulse (2 s, or 5 s for reset and scene capture, as the manual specifies), then sets channel 15
back to 'no function'. Settings apply to the selected fixture only.

## Protocols

**Art-Net** (default): UDP port 6454. Target is broadcast (`255.255.255.255`) or a node IP.

**sACN (E1.31)**: UDP port 5568. Target is blank for multicast (`239.255.x.x`), or a unicast IP.
sACN has no universe 0, so set fixture universes to 1 or higher when using sACN. The status
bar reports any universe that's invalid for the chosen protocol.

## TouchDesigner (OSC in)

TouchDesigner receives OSC from your devices, processes it, and sends values to this app.
The app then maps each OSC address to a light parameter.

**1. Start the OSC listener in this app**
- Network tab: tick **Enable OSC listener**.
- Listen address: `127.0.0.1` (only this computer can send). Use `0.0.0.0` if TouchOSC on a tablet also sends.
- Listen port: `8000`. Click **Apply and save**.

**2. Send from TouchDesigner**
- Add an **OSC Out CHOP** (or OSC Out DAT).
- Network address: `127.0.0.1`. Port: `8000`. Protocol: OSC over UDP.
- Name the channels with the OSC addresses you want, for example `/td/fader1`, or use the address prefix option if your TouchDesigner version has one.
- Send values as floats. Faders are usually 0 to 1.

**3. Create the mapping in this app**
- OSC mapping tab: press **Learn address**, then move the control in TouchDesigner. Its address fills in.
- Choose the fixture (or all fixtures) and the parameter, set the input range (for example 0 to 1) and the output range (for example 0 to 255 for effect numbers), then **Add mapping**.
- The monitor line at the top shows what is arriving, which helps when a value does not seem to work.

**Testing without TouchDesigner**
```bash
.\.venv\Scripts\python tools\send_test_osc.py --address /td/fader1 --sweep 5
```

Note: the TouchDesigner side was not tested here, because TouchDesigner is not installed in this environment. The OSC path was tested with the sender script and the unit tests.

## OSC (TouchOSC)

Enable the listener in the Network tab. Default port is 8000. `<n>` is the fixture number (1-based).

| Address | Type | Meaning |
|---|---|---|
| `/martin/blackout` | int | 0 or 1 |
| `/martin/<n>/intensity` | float | beam intensity, 0.0-1.0 |
| `/martin/<n>/beam/rgb` | 3 floats | 0.0-1.0 each |
| `/martin/<n>/beam/preset` | int | 0 (none) or 1-48 |
| `/martin/<n>/aura/intensity` | float | 0.0-1.0 |
| `/martin/<n>/aura/rgb` | 3 floats | 0.0-1.0 each |
| `/martin/<n>/fx` | int | effect number, 0-255 |
| `/martin/<n>/fx/speed` | float | 0.0-1.0 maps to DMX 0-255 (128 = stopped) |

## Layout

```
martin_controller/
  artnet.py      ArtDMX packet builder and UDP sender
  sacn.py        E1.31 (sACN) packet builder and UDP/multicast sender
  fixture.py     Basic-mode (27 channel) model, Fixture and FixtureState
  effects.py     FX names and colour presets from the user guide
  engine.py      Holds the state and sends frames at the refresh rate
  controls.py    Option tables and unit conversions (strobe, flash, settings, pixels)
  config.py      settings.json, and project file load and save
  mapping.py     OSC address to parameter mapping (parameter table, ranges, lookup)
  osc_server.py  OSC listener: built-in /martin addresses, mappings, and the input monitor
  scenes.py      Scenes, playlist, and playback (recall, next/prev, auto-advance)
  preview.py     Virtual fixture preview widget
  ui.py          PySide6 window
  __main__.py    Entry point
tests/           Unit tests (.venv\Scripts\python -m unittest discover -s tests -t .)
tools/           send_test_osc.py, sends test OSC values without TouchDesigner
```

## Source

Channel numbers, value ranges and the FX table come from the Martin VDO Atomic Bold user guide
(DMX mode Basic, pages 43-46; FX table, pages 56-61).

## Not yet done

- RDM, to set the fixture's address and universe from the app.
- Art-Net discovery (ArtPoll).
- Preview of built-in effects and colour presets (text only for now).
- Pixel grid uses numeric order (1-72), not the physical layout in the manual diagram.
- Multi-fixture sync beyond what the fixture's FX sync settings provide.
