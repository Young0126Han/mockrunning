from __future__ import annotations
import argparse
import asyncio
import logging
from pathlib import Path
from .connections import create_device
from .android import discover as discover_android, pair
from .gpx import load_points


def positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def percentage(value: str) -> float:
    number = float(value)
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="iOS / Android location test controller")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--platform", choices=["ios", "android"], default="ios")
    pairing = sub.add_parser("pair", help="Pair Android wireless debugging (code prompted securely)")
    pairing.add_argument("address", help="Pairing IP:port, not the debugging port")
    validate = sub.add_parser("validate")
    validate.add_argument("route", type=Path)
    play = sub.add_parser("play")
    play.add_argument("route", type=Path)
    play.add_argument("--udid")
    play.add_argument("--interval", type=positive_float, default=1.0, help="GPS update interval in seconds")
    play.add_argument("--speed-kmh", type=positive_float, help="Travel speed along the route in km/h")
    play.add_argument("--speed-variation-pct", type=percentage, default=0.0, help="Random speed variation per segment")
    play.add_argument("--lateral-variation-m", type=nonnegative_float, default=0.0, help="Left/right sway amplitude in meters")
    play.add_argument("--random-seed", type=int, help="Optional seed for repeatable movement variation")
    play.add_argument("--loop", action="store_true")
    play.add_argument("--rsd-host", help="RSD host printed by pymobiledevice3 remote start-tunnel")
    play.add_argument("--rsd-port", type=int, help="RSD port printed by pymobiledevice3 remote start-tunnel")
    clear = sub.add_parser("clear")
    clear.add_argument("--udid")
    clear.add_argument("--rsd-host")
    clear.add_argument("--rsd-port", type=int)
    for command in (play, clear):
        command.add_argument("--platform", choices=["ios", "android"], default="ios")
        command.add_argument("--address", help="Android wireless debugging IP:port")
    web = sub.add_parser("map", help="Start the local OpenStreetMap route editor")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    return parser

async def run(args: argparse.Namespace) -> None:
    if args.command == "list":
        if args.platform == "android":
            for device in await discover_android():
                print(device)
            return
        from pymobiledevice3.usbmux import list_devices
        for device in await list_devices():
            print(device)
        return
    if args.command == "pair":
        from getpass import getpass
        await pair(args.address, getpass("Android pairing code: "))
        print("Paired successfully")
        return
    if args.command == "validate":
        print(f"valid: {len(load_points(args.route))} points")
        return
    if args.command == "map":
        from .web import serve
        serve(args.host, args.port)
        return
    rsd_host = getattr(args, "rsd_host", None)
    rsd_port = getattr(args, "rsd_port", None)
    if (rsd_host is None) != (rsd_port is None):
        raise ValueError("--rsd-host and --rsd-port must be used together")
    device = create_device(args.platform, getattr(args, "udid", None), rsd_host, rsd_port, args.address)
    try:
        await device.connect()
        if args.command == "clear":
            if args.platform == "android":
                await device.clear(existing=True)
            else:
                await device.clear()
        else:
            await device.play(
                load_points(args.route),
                args.interval,
                args.loop,
                args.speed_kmh,
                args.speed_variation_pct,
                args.lateral_variation_m,
                args.random_seed,
            )
    finally:
        await device.close()

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("\nStopped; cleanup was attempted.")

if __name__ == "__main__":
    main()
