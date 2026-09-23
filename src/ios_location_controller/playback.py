from __future__ import annotations
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict
import json
import threading
from pathlib import Path
from .device import LocationDevice
from .gpx import Point
from .motion import Motion, Settings, route_points


class PlaybackController:
    """Serialize all device I/O and state transitions on one owned event loop."""

    def __init__(self, state_path: Path, device_factory=LocationDevice):
        self.path = state_path
        self.factory = device_factory
        self.points = []
        self.name = ""
        self.settings = Settings()
        self.device = None
        self.motion = None
        self.current = None
        self.state = "idle"
        self.error = None
        self.speed = 0
        self.pending_time = 0.0
        self.devices = []
        self.discovery_error = None
        self.udid = None
        self.real_current = None
        self.wda_error = None
        self._load()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.settings = Settings.parse(data["settings"])
            if data.get("points"):
                self.points = route_points(data["points"])
                self.name = str(data.get("name", "Route"))[:120]
        except Exception as exc:
            self.error = f"Saved session could not be loaded: {exc}"

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"name": self.name, "points": self._coordinates(),
                                    "settings": asdict(self.settings)}, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def _coordinates(self):
        return [{"lat": p.latitude, "lng": p.longitude} for p in self.points]

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.lock = asyncio.Lock()
        self.last_tick = self.loop.time()
        self.runner = self.loop.create_task(self._tick())
        self.discovery = self.loop.create_task(self._discover())
        self.loop.run_forever()

    def call(self, action, data=None):
        future = asyncio.run_coroutine_threadsafe(self._action(action, data or {}), self.loop)
        try:
            return future.result(timeout=40)
        except FutureTimeout:
            future.cancel()
            raise ValueError("Device operation timed out; reconnect the device") from None

    def status(self):
        return self.call("status")

    def _status(self):
        return {"state": self.state, "connected": self.device is not None, "udid": self.udid,
                "devices": self.devices, "discovery_error": self.discovery_error, "error": self.error,
                "route": {"name": self.name, "points": self._coordinates()},
                "real_current": self.real_current, "wda_error": self.wda_error,
                "settings": asdict(self.settings), "current": self.current, "speed_kmh": self.speed,
                "distance_m": self.motion.distance if self.motion else 0,
                "elapsed_s": self.motion.elapsed if self.motion else 0,
                "total_m": self.motion.total if self.motion else (Motion(self.points, self.settings).total if self.points else 0),
                "laps": self.motion.laps if self.motion else 0}

    async def _send(self, point):
        await asyncio.wait_for(self.device.set_point(point), 8)
        # Last successfully sent simulated coordinate, not a GPS readback.
        self.current = {"lat": point.latitude, "lng": point.longitude}

    async def _close_device(self):
        device, self.device = self.device, None
        self.udid = None
        self.current = None
        self.speed = 0
        if device:
            await asyncio.wait_for(device.close(), 10)

    async def _action(self, action, data):
        if action == "status":
            return self._status()
        async with self.lock:
            try:
                if action == "route":
                    if self.state in ("playing", "paused"):
                        raise ValueError("Stop playback before replacing the route")
                    points = route_points(data.get("points"))
                    self.points, self.name = points, str(data.get("name", "Route"))[:120]
                    self.motion = None
                    self._save()
                    if self.device:
                        await self._send(points[0])
                    self.state = "ready" if self.device else "idle"
                elif action == "settings":
                    if self.state == "playing":
                        raise ValueError("Pause before changing parameters")
                    self.settings = Settings.parse(data)
                    self.pending_time = 0.0
                    self.last_tick = self.loop.time()
                    self._save()
                elif action == "connect":
                    if self.state in ("playing", "paused"):
                        raise ValueError("Stop before changing the device")
                    if not self.device:
                        self.state = "connecting"
                        device = self.factory(udid=data.get("udid") or None)
                        try:
                            await asyncio.wait_for(device.connect(), 25)
                        except BaseException:
                            await asyncio.wait_for(device.close(), 8)
                            raise
                        self.device = device
                        self.udid = data.get("udid") or (self.devices[0]["udid"] if self.devices else None)
                        try:
                            self.real_current = await device.read_location()
                            self.wda_error = None
                        except Exception as exc:
                            self.real_current = None
                            self.wda_error = str(exc) or type(exc).__name__
                    if self.points:
                        await self._send(self.points[0])
                    self.state = "ready"
                elif action == "start":
                    if not self.device or not self.points:
                        raise ValueError("Connect an iPhone and import a route first")
                    if self.state != "playing":
                        if self.state != "paused":
                            self.motion = Motion(self.points, self.settings)
                            await self._send(self.points[0])
                        self.state = "playing"
                        self.pending_time = 0.0
                        self.last_tick = self.loop.time()
                elif action == "position":
                    if self.state == "playing":
                        raise ValueError("Pause or stop playback before switching location")
                    if not self.device:
                        raise ValueError("Connect an iPhone first")
                    lat, lng = float(data.get("lat")), float(data.get("lng"))
                    if not -85 <= lat <= 85 or not -180 <= lng <= 180:
                        raise ValueError("Invalid coordinates")
                    await self._send(Point(lat, lng))
                    self.state = "ready"
                elif action == "pause":
                    if self.state == "playing":
                        self.state = "paused"
                        self.speed = 0
                elif action == "stop":
                    self.state = "ready" if self.device else "idle"
                    self.motion = None
                    self.speed = 0
                    if self.device:
                        await asyncio.wait_for(self.device.clear(), 8)
                    self.current = None
                elif action == "disconnect":
                    self.state = "idle"
                    await self._close_device()
                    self.motion = None
                    self.real_current = None
                    self.wda_error = None
                else:
                    raise ValueError("Unknown action")
                self.error = None
            except BaseException as exc:
                self.error = str(exc) or type(exc).__name__
                if not isinstance(exc, ValueError):
                    self.state = "error"
                raise
            return self._status()

    async def _tick(self):
        while True:
            await asyncio.sleep(.02)
            async with self.lock:
                now = self.loop.time()
                delta, self.last_tick = now - self.last_tick, now
                if self.state != "playing":
                    self.pending_time = 0.0
                    continue
                self.pending_time += delta
                interval = self.settings.interval
                if self.pending_time + 1e-9 < interval:
                    continue
                # No burst catch-up after a slow device write or suspended computer.
                dt = min(self.pending_time, interval * 2)
                self.pending_time = 0.0
                try:
                    point, speed, done = self.motion.advance(dt, self.settings)
                    await self._send(point)
                    self.speed = 0 if done else speed
                    if done:
                        self.state = "completed"
                except Exception as exc:
                    self.state, self.error = "error", str(exc) or type(exc).__name__
                    try:
                        await self._close_device()
                    except Exception:
                        pass

    async def _discover(self):
        from pymobiledevice3.usbmux import list_devices
        while True:
            try:
                found = await asyncio.wait_for(list_devices(), 5)
                self.devices = [{"udid": str(d.serial), "type": str(d.connection_type)} for d in found]
                self.discovery_error = None
                if self.device and self.udid and self.udid not in {d["udid"] for d in self.devices}:
                    async with self.lock:
                        self.state, self.error = "error", "iPhone disconnected"
                        try:
                            await self._close_device()
                        except Exception:
                            pass
            except Exception as exc:
                self.discovery_error = str(exc) or type(exc).__name__
            await asyncio.sleep(3)

    def close(self):
        async def shutdown():
            self.runner.cancel()
            self.discovery.cancel()
            await asyncio.gather(self.runner, self.discovery, return_exceptions=True)
            await self._close_device()
        future = asyncio.run_coroutine_threadsafe(shutdown(), self.loop)
        try:
            future.result(timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
