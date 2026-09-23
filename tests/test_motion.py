import math
import pytest
from ios_location_controller.motion import Settings, Motion, route_points
from ios_location_controller.gpx import distance_meters
from ios_location_controller.web import parse_gpx

ROUTE = [{"lat":31.2304,"lng":121.4737},{"lat":31.2308,"lng":121.4742}]

@pytest.mark.parametrize('data', [{"speed_kmh":0},{"interval":float('nan')},{"lateral_variation_m":-1},{"speed_variation_pct":81},{"loop":"false"},{"random_seed":1.2},{"extra":1}])
def test_invalid_settings(data):
    with pytest.raises(ValueError): Settings.parse(data)

@pytest.mark.parametrize('points', [[],ROUTE[:1],[ROUTE[0],ROUTE[0]],[{"lat":float('nan'),"lng":0},ROUTE[1]],[{"lat":91,"lng":0},ROUTE[1]]])
def test_invalid_routes(points):
    with pytest.raises(ValueError): route_points(points)

def test_motion_repeatability_and_bounds():
    settings=Settings()
    points=route_points(ROUTE)
    a,b=Motion(points,settings),Motion(points,settings)
    for _ in range(10):
        result=a.advance(.5,settings)
        assert result==b.advance(.5,settings)
        assert 4.5 <= result[1] <= 5.5
    assert a.elapsed==5

def test_end_and_loop():
    points=route_points(ROUTE)
    settings=Settings(speed_variation_pct=0,lateral_variation_m=0)
    m=Motion(points,settings)
    p,_,done=m.advance(1000,settings)
    assert done and distance_meters(p,points[-1])<.001
    m=Motion(points,settings)
    assert not m.advance(1000,Settings(loop=True))[2]
    assert m.laps>0

def test_gpx_validation():
    assert len(parse_gpx('<gpx><rte><rtept lat="1" lon="2"/><rtept lat="1.1" lon="2"/></rte></gpx>'))==2
    for text in ['<gpx/>','<!DOCTYPE x><gpx/>','<gpx><trkpt lat="nan" lon="0"/></gpx>']:
        with pytest.raises(ValueError): parse_gpx(text)
