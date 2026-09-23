from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Sequence

from .device import LocationDevice
from .gpx import Point


class PlaybackController:
    """Own the persistent device connection used by the local web console."""

    def __init__(self, rsd_host: str | None = None, rsd_port: int | None = None) -> None:
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._rsd_host = rsd_host or os.getenv("IOS_RSD_HOST")
        configured_port = rsd_port or os.getenv("IOS_RSD_PORT")
        self._rsd_port = int(configured_port) if configured_port else None
        self._device: LocationDevice | None = None
        self._task: asyncio.Task[None] | None = None
        self._pause_event: asyncio.Event | None = None
        self._points: list[Point] = []
        self._current: Point | None = None
        self._settings = {
            "interval": 1.0,
            "speed_kmh": 5.0,
            "speed_variation_pct": 15.0,
            "lateral_variation_m": 1.5,
            "loop": False,
        }
        self._state = "no-route"
        self._error: str | None = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout=30)

    def set_route(self, points: Sequence[Point]) -> None:
        with self._lock:
            self._points = list(points)
            self._current = None
            self._error = None
            self._state = "ready" if self._points else "no-route"

    def set_settings(self, settings: dict[str, object]) -> None:
        with self._lock:
            self._settings.update(settings)

    def prepare(self) -> None:
        self._submit(self._prepare())

    async def _prepare(self) -> None:
        with self._lock:
            points = list(self._points)
        if not points:
            raise ValueError("Route is empty")
        if self._device is None:
            device = LocationDevice(rsd_host=self._rsd_host, rsd_port=self._rsd_port)
            try:
                await device.connect()
            except Exception:
                await device.close()
                with self._lock:
                    self._state = "error"
                    self._error = "Unable to connect to iPhone"
                raise
            self._device = device
        try:
            await self._device.set_point(points[0])
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._error = str(exc)
            raise
        with self._lock:
            self._current = points[0]
            self._state = "ready"
            self._error = None

    def start(self) -> None:
        self._submit(self._start())

    async def _start(self) -> None:
        with self._lock:
            points = list(self._points)
            settings = dict(self._settings)
        if not points:
            raise ValueError("Route is empty")
        if self._device is None:
            await self._prepare()
        if self._task is None or self._task.done():
            self._pause_event = asyncio.Event()
            self._pause_event.set()
            self._task = asyncio.create_task(
                self._run_playback(points, settings, self._pause_event)
            )
        elif self._pause_event is not None:
            self._pause_event.set()
        with self._lock:
            self._state = "playing"
            self._error = None

    async def _run_playback(self, points, settings, pause_event) -> None:
        try:
            await self._device.play(
                points,
                float(settings["interval"]),
                bool(settings["loop"]),
                float(settings["speed_kmh"]),
                float(settings["speed_variation_pct"]),
                float(settings["lateral_variation_m"]),
                on_point=self._on_point,
                pause_event=pause_event,
            )
            with self._lock:
                self._state = "ready"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._error = str(exc)

    async def _on_point(self, point: Point) -> None:
        with self._lock:
            self._current = point

    def pause(self) -> None:
        def pause_now() -> None:
            if self._pause_event is not None:
                self._pause_event.clear()
            with self._lock:
                if self._state == "playing":
                    self._state = "paused"

        self._loop.call_soon_threadsafe(pause_now)

    def status(self) -> dict[str, object]:
        with self._lock:
            current = self._current
            return {
                "state": self._state,
                "error": self._error,
                "current": {"lat": current.latitude, "lng": current.longitude} if current else None,
                "has_route": bool(self._points),
            }
