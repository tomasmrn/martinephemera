"""Send test OSC values to the controller, to check mappings without TouchDesigner.

Examples (run from the project folder with the venv's Python):

  python tools/send_test_osc.py --address /td/fader1 --sweep 5
  python tools/send_test_osc.py --address /td/fader1 --value 0.5
"""

import argparse
import math
import time

from pythonosc.udp_client import SimpleUDPClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1", help="controller address (default: this computer)")
    parser.add_argument("--port", type=int, default=8000, help="OSC listen port set in the Network tab")
    parser.add_argument("--address", default="/td/fader1", help="OSC address to send to")
    parser.add_argument("--value", type=float, help="send one value")
    parser.add_argument("--sweep", type=float, metavar="SECONDS",
                        help="sweep 0 to 1 and back for this many seconds, at 30 messages per second")
    args = parser.parse_args()

    client = SimpleUDPClient(args.host, args.port)
    if args.value is not None:
        client.send_message(args.address, args.value)
        print(f"sent {args.address} {args.value}")
    if args.sweep:
        steps = int(args.sweep * 30)
        for i in range(steps):
            value = 0.5 - 0.5 * math.cos(2 * math.pi * i / 60)  # 0 -> 1 -> 0 every 2 seconds
            client.send_message(args.address, value)
            time.sleep(1 / 30)
        print(f"swept {args.address} for {args.sweep} s")


if __name__ == "__main__":
    main()
