from pathlib import Path
from ios_location_controller.gpx import load_points

def test_sample_route_loads() -> None:
    path = Path(__file__).parents[1] / "routes" / "sample.gpx"
    points = load_points(path)
    assert len(points) == 3
    assert points[0].latitude == 31.2304
