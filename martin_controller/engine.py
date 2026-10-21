"""Holds the fixture state and sends it to the network at a steady rate."""

import threading
import time

from .artnet import ARTNET_PORT, ArtNetSender
from .config import NetworkSettings
from .fixture import MAX_DMX_ADDRESS, Fixture, with_state
from .sacn import SACN_PORT, SacnSender

PROTOCOLS = ("artnet", "sacn")


def make_sender(network: NetworkSettings):
    """Create the sender for the protocol chosen in the settings."""
    if network.protocol == "sacn":
        return SacnSender(network.target_ip, network.artnet_port or SACN_PORT)
    if network.protocol == "artnet":
        return ArtNetSender(network.target_ip or "255.255.255.255",
                            network.artnet_port or ARTNET_PORT)
    raise ValueError(f"unknown protocol {network.protocol!r}")


class DmxEngine:
    def __init__(self, network: NetworkSettings, fixtures: list[Fixture], master: float = 1.0):
        self._lock = threading.Lock()
        self._fixtures = list(fixtures)
        self._network = network
        self._blackout = False
        self._master = max(0.0, min(1.0, master))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    # --- state access (called from UI / OSC threads) ---------------------------

    @property
    def fixtures(self) -> list[Fixture]:
        with self._lock:
            return list(self._fixtures)

    @property
    def network(self) -> NetworkSettings:
        return self._network

    def set_fixtures(self, fixtures: list[Fixture]) -> None:
        with self._lock:
            self._fixtures = list(fixtures)

    def update_fixture(self, index: int, **state_changes) -> None:
        """Change one or more FixtureState fields on fixture `index`."""
        with self._lock:
            self._fixtures[index] = with_state(self._fixtures[index], **state_changes)

    def modify_fixture(self, index: int, make_changes) -> None:
        """Read-modify-write one fixture under the lock. `make_changes(state)` returns the field changes."""
        with self._lock:
            if not 0 <= index < len(self._fixtures):
                return
            fixture = self._fixtures[index]
            self._fixtures[index] = with_state(fixture, **make_changes(fixture.state))

    def replace_fixture(self, index: int, fixture: Fixture) -> None:
        with self._lock:
            self._fixtures[index] = fixture

    @property
    def master(self) -> float:
        return self._master

    @master.setter
    def master(self, value: float) -> None:
        """Master dimmer, 0.0-1.0. Scales every fixture's beam and aura intensity."""
        self._master = max(0.0, min(1.0, float(value)))

    @property
    def blackout(self) -> bool:
        return self._blackout

    @blackout.setter
    def blackout(self, value: bool) -> None:
        self._blackout = bool(value)

    # --- sending ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="dmx-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def reconfigure(self, network: NetworkSettings) -> None:
        """Apply new network settings; restarts the sender."""
        was_running = self._thread is not None
        self.stop()
        self._network = network
        if was_running:
            self.start()

    def build_frames(self) -> dict[int, bytes]:
        """Return one DMX frame per universe, from the current fixture state."""
        frames: dict[int, bytearray] = {}
        for fixture in self.fixtures:
            frame = frames.setdefault(fixture.universe, bytearray(MAX_DMX_ADDRESS))
            data = fixture.to_dmx(blackout=self._blackout, master=self._master)
            start = fixture.address - 1
            frame[start:start + len(data)] = data
        return {universe: bytes(frame) for universe, frame in frames.items()}

    def _run(self) -> None:
        try:
            sender = make_sender(self._network)
        except (OSError, ValueError) as exc:
            self.last_error = f"Could not open the {self._network.protocol} sender: {exc}"
            return

        period = 1.0 / max(1.0, self._network.refresh_hz)
        next_frame = time.perf_counter()
        try:
            while not self._stop.is_set():
                errors = []
                for universe, frame in self.build_frames().items():
                    try:
                        sender.send(universe, frame)
                    except ValueError as exc:
                        errors.append(f"universe {universe}: {exc}")
                    except OSError as exc:
                        errors.append(f"universe {universe} send failed: {exc}")
                self.last_error = "; ".join(errors) or None

                next_frame += period
                delay = next_frame - time.perf_counter()
                if delay > 0:
                    self._stop.wait(delay)
                else:
                    next_frame = time.perf_counter()
        finally:
            sender.close()
