from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, atan2, cos, radians, sin, sqrt
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float
    timestamp: datetime | None = None


EARTH_RADIUS_M = 6_371_000.0


def distance_meters(a: Point, b: Point) -> float:
    """Return the great-circle distance between two GPS points."""
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    dlat = lat2 - lat1
    dlon = radians(b.longitude - a.longitude)
    hav = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(hav)))


def interpolate(a: Point, b: Point, fraction: float) -> Point:
    fraction = max(0.0, min(1.0, fraction))
    return Point(
        a.latitude + (b.latitude - a.latitude) * fraction,
        a.longitude + (b.longitude - a.longitude) * fraction,
    )


def offset_point(point: Point, north_m: float, east_m: float) -> Point:
    """Move a GPS point by a local north/east offset in meters."""
    lat_delta = north_m / EARTH_RADIUS_M
    lon_scale = max(0.01, cos(radians(point.latitude)))
    lon_delta = east_m / (EARTH_RADIUS_M * lon_scale)
    return Point(
        point.latitude + lat_delta * 180 / 3.141592653589793,
        point.longitude + lon_delta * 180 / 3.141592653589793,
    )


def bearing_radians(a: Point, b: Point) -> float:
    """Return the initial bearing from a to b in radians."""
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    dlon = radians(b.longitude - a.longitude)
    return atan2(sin(dlon) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon))


def load_points(path: str | Path) -> list[Point]:
    root = ET.parse(path).getroot()
    points: list[Point] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "trkpt":
            continue
        lat, lon = float(node.attrib["lat"]), float(node.attrib["lon"])
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError(f"Invalid coordinate: {lat}, {lon}")
        stamp = next((child.text for child in node if child.tag.rsplit("}", 1)[-1] == "time"), None)
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
        points.append(Point(lat, lon, parsed))
    if not points:
        raise ValueError("GPX contains no track points")
    return points
