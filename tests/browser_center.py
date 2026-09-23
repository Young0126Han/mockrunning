"""Map centering regression with mocked status; no physical phone writes."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8765')
    page.wait_for_function('initialized')
    page.evaluate('''() => {
      const data = structuredClone(status);
      data.connected = false; data.current = null; renderStatus(structuredClone(data));
      map.setView([0, 0], 4);
      data.connected = true; data.udid = 'test';
      data.current = {lat: 39.9, lng: 116.4}; renderStatus(structuredClone(data));
      if (map.distance(map.getCenter(), [39.9, 116.4]) > 2) throw Error('not centered: ' + JSON.stringify(map.getCenter()));
      if (map.getZoom() < 17) throw Error('not zoomed');
      map.setView([0, 0], 4, {animate:false}); renderStatus(structuredClone(data));
      if (map.distance(map.getCenter(), [0, 0]) > 1) throw Error('poll stole viewport');
      document.getElementById('locate-phone').click();
      if (map.distance(map.getCenter(), [39.9, 116.4]) > 1) throw Error('button failed');
      data.connected = false; data.current = null; renderStatus(structuredClone(data));
      map.setView([0, 0], 4, {animate:false});
      data.connected = true; renderStatus(structuredClone(data));
      if (map.distance(map.getCenter(), [0, 0]) > 1) throw Error('invented GPS');
      document.getElementById('locate-phone').click();
      if (!document.getElementById('message').textContent.includes('GPS')) throw Error('missing limitation');
    }''')
    browser.close()
    print('PASS: connection centers, polling preserves pan, locate button, no-coordinate fallback')
