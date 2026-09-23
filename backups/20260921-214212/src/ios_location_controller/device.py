from __future__ import annotations

import logging
from collections.abc import Sequence
import asyncio
import math
import random
import time
from collections.abc import Awaitable, Callable

from .gpx import Point, bearing_radians, distance_meters, interpolate, offset_point

log = logging.getLogger(__name__)


class LocationDevice:
    """Adapter around pymobiledevice3's DVT location service."""

    def __init__(self, udid: str | None = None, rsd_host: str | None = None, rsd_port: int | None = None) -> None:
        self.udid = udid
        self.rsd_host = rsd_host
        self.rsd_port = rsd_port
        self._simulation = None
        self._provider = None
        self._transport = None
        self._tunnel = None

    async def connect(self) -> None:
        if (self.rsd_host is None) != (self.rsd_port is None):
            raise ValueError("RSD host and port must be provided together")
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        if self.rsd_host is not None:
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider

            self._transport = RemoteServiceDiscoveryService((self.rsd_host, self.rsd_port))
            await self._transport.connect()
            provider = DvtProvider(self._transport)
        else:
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel

            # iOS 17.4+ exposes DVT through CoreDeviceProxy, not the old USB lockdown service.
            # PreferredRsdTunnel creates the Windows userspace tunnel without admin privileges.
            self._tunnel = PreferredRsdTunnel(serial=self.udid)
            rsd = await self._tunnel.aopen()
            self._transport = rsd
            provider = DvtProvider(rsd)

        self._provider = provider
        try:
            await provider.connect()
            self._simulation = LocationSimulation(provider)
            await self._simulation.__aenter__()
        except Exception:
            await self.close()
            raise
        mode = f"RSD {self.rsd_host}:{self.rsd_port}" if self.rsd_host else "USB lockdown"
        log.info("Connected to iPhone (%s)", mode)

    async def set_point(self, point: Point) -> None:
        if self._simulation is None:
            raise RuntimeError("Device is not connected")
        await self._simulation.set(point.latitude, point.longitude)

    async def play(
        self,
        points: Sequence[Point],
        interval: float,
        loop: bool = False,
        speed_kmh: float | None = None,
        speed_variation_pct: float = 0.0,
        lateral_variation_m: float = 0.0,
        random_seed: int | None = None,
        on_point: Callable[[Point], Awaitable[None]] | None = None,
        pause_event: asyncio.Event | None = None,
    ) -> None:
        if not points or interval <= 0:
            raise ValueError("Route must contain points and interval must be positive")
        if speed_kmh is not None and speed_kmh <= 0:
            raise ValueError("Speed must be positive")
        if not 0 <= speed_variation_pct <= 100:
            raise ValueError("Speed variation must be between 0 and 100 percent")
        if lateral_variation_m < 0:
            raise ValueError("Lateral variation must not be negative")
        rng = random.Random(random_seed)
        while True:
            if pause_event is not None:
                await pause_event.wait()
            await self.set_point(points[0])
            if on_point is not None:
                await on_point(points[0])
            for start, end in zip(points, points[1:]):
                if speed_kmh is None:
                    if pause_event is not None:
                        await pause_event.wait()
                    await self.set_point(end)
                    if on_point is not None:
                        await on_point(end)
                    await asyncio.sleep(interval)
                    continue
                segment_distance = distance_meters(start, end)
                variation = speed_variation_pct / 100
                segment_speed = speed_kmh * rng.uniform(max(0.01, 1 - variation), 1 + variation)
                duration = segment_distance / (segment_speed / 3.6)
                steps = max(1, math.ceil(duration / interval))
                started = time.monotonic()
                bearing = bearing_radians(start, end)
                lateral = rng.uniform(-lateral_variation_m, lateral_variation_m)
                for step in range(1, steps + 1):
                    if pause_event is not None:
                        await pause_event.wait()
                    fraction = step / steps
                    point = interpolate(start, end, fraction)
                    sway = lateral * math.sin(math.pi * fraction)
                    point = offset_point(point, -math.sin(bearing) * sway, math.cos(bearing) * sway)
                    await self.set_point(point)
                    if on_point is not None:
                        await on_point(point)
                    target = started + duration * step / steps
                    await asyncio.sleep(max(0.0, target - time.monotonic()))
                log.debug("Segment %.1f m at %.2f km/h completed in %.2f s", segment_distance, segment_speed, duration)
            if not loop:
                return

    async def clear(self) -> None:
        if self._simulation is not None:
            await self._simulation.clear()

    async def close(self) -> None:
        if self._simulation is not None:
            try:
                try:
                    await self._simulation.clear()
                except Exception:
                    log.exception("Could not clear simulated location")
            finally:
                await self._simulation.__aexit__(None, None, None)
                self._simulation = None
        if self._provider is not None and self._provider is not self._transport:
            self._provider = None
        if self._transport is not None:
            if self._tunnel is None:
                await self._transport.close()
            self._transport = None
        if self._tunnel is not None:
            await self._tunnel.aclose()
            self._tunnel = None
