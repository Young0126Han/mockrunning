"""ADB transport for Android's system test providers (no root or APK)."""
import asyncio
import ipaddress
import math
import os
import re
import shutil
import subprocess

from .device import LocationDevice


def endpoint(value):
    if not isinstance(value, str):
        raise ValueError("Expected an IP address and port")
    host, sep, port = value.rpartition(":")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
        if not sep or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError()
        if address.is_unspecified or address.is_multicast:
            raise ValueError()
    except ValueError:
        raise ValueError("Expected IP:port (IPv6: [address]:port)") from None
    return f"[{address}]:{int(port)}" if address.version == 6 else f"{address}:{int(port)}"


async def adb(*args, input_text=None):
    executable = os.environ.get("ADB_PATH") or shutil.which("adb")
    if not executable:
        raise RuntimeError("Android requires Android SDK Platform-Tools: adb on PATH or ADB_PATH")
    process = await asyncio.create_subprocess_exec(
        executable, *args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out, err = await asyncio.wait_for(
            process.communicate(input_text.encode() if input_text else None), 15)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    text = (out + err).decode("utf-8", errors="replace").strip()
    # Android's default shell help handler returns -1 (usually 255 via adb)
    # even after successfully printing help. Only accept that result for this
    # read-only probe, with a recognizable help header and no stderr output.
    normal_location_help = (
        len(args) == 6
        and args[0] == "-s"
        and args[2:] == ("shell", "cmd", "location", "help")
        and process.returncode in (-1, 255)
        and not err.strip()
        and re.search(r"(?m)^Location service commands:[ \t]*\r?$",
                      out.decode("utf-8", errors="replace")) is not None
    )
    if (process.returncode and not normal_location_help) or any(s in text.lower() for s in
            ("error:", "exception", "failed", "cannot connect", "unknown command")):
        # Pairing codes must not be reflected into status or logs.
        raise RuntimeError("ADB pairing failed" if input_text else text[:500] or "ADB command failed")
    return text


async def discover():
    output = await adb("devices", "-l")
    return [{"udid": row[0], "platform": "android", "type": "ADB / " + row[1]}
            for line in output.splitlines()
            if len(row := line.split()) >= 2 and row[1] in ("device", "offline", "unauthorized")]


async def pair(address, code):
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise ValueError("Pairing code must contain six digits")
    await adb("pair", endpoint(address), input_text=code + "\n")


class AndroidDevice(LocationDevice):
    # Reuse the CLI route player; all actual device I/O is overridden here.
    def __init__(self, udid=None, address=None):
        self.udid = udid
        self.address = endpoint(address) if address else None
        self.providers = []
        self.original_mode = None

    async def shell(self, *args):
        if not self.udid:
            raise RuntimeError("No Android device selected")
        return await adb("-s", self.udid, "shell", *args)

    async def connect(self):
        if self.address:
            await adb("connect", self.address)
            self.udid = self.address
        if not self.udid:
            devices = [d for d in await discover() if d["type"] == "ADB / device"]
            if len(devices) != 1:
                raise ValueError("Select exactly one authorized Android device")
            self.udid = devices[0]["udid"]
        if await adb("-s", self.udid, "get-state") != "device":
            raise RuntimeError("Android device is offline or unauthorized")
        help_text = await self.shell("cmd", "location", "help")
        if "set-test-provider-location" not in help_text:
            raise RuntimeError("This Android ROM lacks ADB test-provider support (use Android 12+)")
        if await self.shell("cmd", "location", "is-location-enabled") != "true":
            raise RuntimeError("Android system location is disabled")
        mode = await self.shell("appops", "get", "com.android.shell", "android:mock_location")
        match = re.search(r"(?:MOCK_LOCATION|mock_location):\s*(allow|ignore|deny|default|foreground)", mode)
        if not match and "No operations" not in mode:
            raise RuntimeError("Cannot determine original mock-location permission")
        self.original_mode = match[1] if match else "default"
        await self.shell("appops", "set", "com.android.shell", "android:mock_location", "allow")

    async def set_point(self, point):
        lat, lon = point.latitude, point.longitude
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid coordinates")
        if self.original_mode is None:
            raise RuntimeError("Android is not connected")
        for provider in ("gps", "network"):
            if provider not in self.providers:
                await self.shell("cmd", "location", "providers", "add-test-provider", provider)
                self.providers.append(provider)
                await self.shell("cmd", "location", "providers", "set-test-provider-enabled", provider, "true")
            await self.shell("cmd", "location", "providers", "set-test-provider-location", provider,
                             "--location", f"{lat:.8f},{lon:.8f}", "--accuracy", "3")

    async def clear(self, existing=False):
        if existing:
            # Explicit CLI recovery also clears providers left by a previous run.
            self.providers = list(dict.fromkeys(self.providers + ["gps", "network"]))
        errors = []
        for provider in list(self.providers):
            try:
                await self.shell("cmd", "location", "providers", "remove-test-provider", provider)
                self.providers.remove(provider)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("Android cleanup failed; reconnect to restore location: " + "; ".join(errors))

    async def close(self):
        await self.clear()
        if self.original_mode is not None:
            await self.shell("appops", "set", "com.android.shell", "android:mock_location", self.original_mode)
            self.original_mode = None

    async def read_location(self):
        raise RuntimeError("Android displays sent coordinates only, not real GPS readback")
