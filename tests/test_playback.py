import asyncio
import time
import pytest
from ios_location_controller.playback import PlaybackController

class FakeDevice:
    sent=[]
    def __init__(self, **kwargs): pass
    async def connect(self): pass
    async def close(self): pass
    async def clear(self): pass
    async def set_point(self,point): self.sent.append(point)

def test_lifecycle_and_persistence(tmp_path):
    c=PlaybackController(tmp_path/'session.json',FakeDevice)
    route={"name":"test","points":[{"lat":31.23,"lng":121.47},{"lat":31.24,"lng":121.48}]}
    try:
        with pytest.raises(ValueError): c.call('start')
        c.call('route',route)
        assert c.status()['current'] is None
        c.call('settings',{'interval':.1})
        c.call('connect')
        assert c.status()['current']==route['points'][0]
        c.call('position', {'lat': 35.0, 'lng': 139.0})
        assert c.status()['current']=={'lat': 35.0, 'lng': 139.0}
        c.call('start'); time.sleep(.35)
        c.call('pause')
        paused=c.status()
        time.sleep(.4)
        assert c.status()['current']==paused['current']
        assert c.status()['elapsed_s']==paused['elapsed_s']
        with pytest.raises(ValueError): c.call('route',route)
        c.call('start'); time.sleep(.2); c.call('pause')
        assert 0 < c.status()['elapsed_s']-paused['elapsed_s'] < .4
        c.call('stop'); assert c.status()['current'] is None
        c.call('disconnect'); assert not c.status()['connected']
    finally: c.close()
    restored=PlaybackController(tmp_path/'session.json',FakeDevice)
    try:
        assert restored.status()['route']==route
        assert restored.status()['settings']['interval']==.1
        assert restored.status()['state']=='idle'
        assert restored.status()['current'] is None
    finally: restored.close()
