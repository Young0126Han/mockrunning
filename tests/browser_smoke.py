"""Real Edge UI checks. Does not connect to or change a physical iPhone."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width':1440,'height':1000}, accept_downloads=True,
                                  record_video_dir=str(OUT/'video'))
    page = context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765',wait_until='domcontentloaded')
    expect(page.locator('#service')).to_have_text('本地服务已连接')
    page.locator('#map').click(position={'x':250,'y':250})
    page.locator('#map').click(position={'x':380,'y':280})
    page.locator('#map').click(position={'x':480,'y':390})
    expect(page.locator('#node-count')).to_have_text('3')
    expect(page.locator('.node-icon')).to_have_count(3)
    page.locator('#undo').click()
    expect(page.locator('#node-count')).to_have_text('2')
    page.locator('#map').click(position={'x':480,'y':390})
    marker=page.locator('.node-icon').first.bounding_box()
    page.mouse.move(marker['x']+14,marker['y']+14)
    page.mouse.down();page.mouse.move(marker['x']+55,marker['y']+35,steps=8);page.mouse.up()
    page.locator('#route-name').fill('browser-test-route')
    with page.expect_download() as download:
        page.locator('#export').click()
    path=OUT/'browser-test-route.gpx'
    download.value.save_as(path)
    assert path.read_text().count('<trkpt')==3
    page.locator('#clear').click()
    expect(page.locator('#node-count')).to_have_text('0')
    page.locator('#editor-file').set_input_files(path)
    expect(page.locator('#node-count')).to_have_text('3')
    page.locator('#fit').click()
    page.wait_for_function("document.querySelectorAll('.leaflet-tile-loaded').length > 0",timeout=30000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT/'route-editor.png'))
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('#node-count')).to_have_text('3')
    page.locator('#tab-player').click()
    page.locator('#player-file').set_input_files(path)
    expect(page.locator('#loaded-route')).to_contain_text('3 节点')
    page.locator('#pace').fill('6')
    expect(page.locator('#speed')).to_have_value('10')
    page.locator('[name=speed_variation_pct]').fill('20')
    page.locator('#apply').click()
    expect(page.locator('#message')).to_contain_text('参数已保存')
    assert page.request.get('http://127.0.0.1:8765/api/status').json()['settings']['speed_kmh']==10
    page.screenshot(path=str(OUT/'playback-panel.png'))
    page.locator('#tab-editor').click()
    page.locator('#use-route').click()
    expect(page.locator('#player-panel')).to_be_visible()
    expect(page.locator('#loaded-route')).to_contain_text('3 节点')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    context.close(); browser.close()
    print('PASS: real map clicks, numbered nodes, dragging, undo, clear, GPX roundtrip, reload persistence, playback import, speed/pace, parameter save, mobile layout; no JS errors')
