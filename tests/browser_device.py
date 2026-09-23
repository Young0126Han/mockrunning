"""Opt-in real iPhone smoke test: short playback, then clear simulation."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1100},record_video_dir=str(OUT/'device-video'))
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765',wait_until='domcontentloaded')
    page.locator('#tab-player').click()
    page.locator('#player-file').set_input_files(ROOT/'routes/sample.gpx')
    expect(page.locator('#loaded-route')).to_contain_text('sample',timeout=10000)
    expect(page.locator('#connect')).to_be_enabled(timeout=15000)
    try:
        page.locator('#connect').click()
        expect(page.locator('#device-state')).to_have_text('定位服务已连接',timeout=40000)
        expect(page.locator('#position')).to_contain_text('31.230400',timeout=10000)
        page.locator('#speed').fill('5')
        page.locator('[name=interval]').fill('0.2')
        page.locator('#start').click()
        expect(page.locator('#play-state')).to_have_text('正在移动',timeout=15000)
        page.wait_for_timeout(1500)
        page.locator('#pause').click()
        expect(page.locator('#play-state')).to_have_text('已暂停')
        paused=page.request.get('http://127.0.0.1:8765/api/status').json()
        page.wait_for_timeout(1000)
        again=page.request.get('http://127.0.0.1:8765/api/status').json()
        assert paused['current']==again['current']
        assert paused['current']['lat']!=31.2304
        page.locator('#speed').fill('6')
        page.locator('#start').click()
        expect(page.locator('#play-state')).to_have_text('正在移动')
        page.wait_for_timeout(600)
        page.locator('#pause').click()
        expect(page.locator('#play-state')).to_have_text('已暂停')
        page.screenshot(path=str(OUT/'device-paused.png'))
        page.locator('#stop').click()
        expect(page.locator('#position')).to_have_text('尚未发送模拟坐标')
        page.locator('#disconnect').click()
        expect(page.locator('#device-state')).to_have_text('尚未连接定位服务')
        assert not errors,errors
        print('PASS: physical iPhone DVT connection, route start, start, pause freezes coordinates, parameter change, resume, stop/clear, disconnect')
    finally:
        page.request.post('http://127.0.0.1:8765/api/stop',data={})
        page.request.post('http://127.0.0.1:8765/api/disconnect',data={})
        print('TILES',page.locator('.leaflet-tile-loaded').count())
        print('MAP ERRORS',page.locator('#map-warning').text_content())
        context.close();browser.close()
