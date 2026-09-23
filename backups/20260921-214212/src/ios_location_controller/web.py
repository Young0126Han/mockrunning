from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .gpx import Point, load_points
from .playback import PlaybackController


PLAYBACK = PlaybackController()
ROUTES_DIR = Path(__file__).resolve().parents[2] / "routes"


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>iOS Location Controller</title>
  <link rel="stylesheet" href="/static/leaflet.css">
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #edf2f0; color: #152522; }
    header { padding: 18px 24px; background: #123b35; color: #f4f7ed; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 4px 0 0; color: #b8d4c4; font-size: 13px; }
    main { display: grid; grid-template-columns: 1fr 310px; height: calc(100vh - 83px); }
    #map { min-height: 420px; }
    aside { padding: 18px; background: #fffdf8; border-left: 1px solid #d9e1da; overflow: auto; }
    .device-status { padding: 12px; margin-bottom: 18px; background: #f4eee2; border-radius: 8px; }
    .device-status h2 { margin: 0 0 8px; font-size: 14px; }
    .status-line { display: flex; align-items: center; gap: 8px; font-size: 13px; }
    .status-dot { width: 9px; height: 9px; border-radius: 50%; background: #8b9891; }
    .status-dot.connected { background: #2e9d63; }
    .status-dot.error { background: #c54e3e; }
    #device-list { margin: 8px 0 0; padding-left: 18px; font: 12px ui-monospace, monospace; }
    #device-updated { display: block; margin-top: 8px; color: #58706a; font-size: 11px; }
    .controls { display: grid; gap: 8px; margin-bottom: 18px; }
    .controls h2 { margin: 0; font-size: 14px; }
    .control-row { display: grid; grid-template-columns: 1fr 92px; align-items: center; gap: 8px; font-size: 12px; }
    input[type="number"] { width: 100%; border: 1px solid #cbd7cf; border-radius: 6px; padding: 7px; background: white; }
    input[type="file"] { width: 100%; font-size: 11px; }
    select { width: 100%; border: 1px solid #cbd7cf; border-radius: 6px; padding: 7px; background: white; }
    .check-row { display: flex; align-items: center; gap: 7px; font-size: 12px; }
    .playback-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .current-location { color: #58706a; font: 11px ui-monospace, monospace; }
    .map-help { position: absolute; z-index: 500; margin: 12px; padding: 8px 10px; border-radius: 6px; background: rgba(255,253,248,.94); color: #173326; font-size: 12px; box-shadow: 0 2px 8px rgba(21,37,34,.16); }
    button { border: 0; border-radius: 8px; padding: 10px 12px; cursor: pointer; background: #d8e9c7; color: #173326; font-weight: 650; }
    button.primary { background: #e66b45; color: white; }
    button.ghost { background: #edf2f0; }
    .actions { display: grid; gap: 8px; margin: 12px 0 18px; }
    .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; }
    .stat { padding: 10px; background: #edf2f0; border-radius: 8px; }
    .stat strong { display: block; font-size: 18px; }
    .stat span { font-size: 12px; color: #58706a; }
    ol { padding-left: 26px; font: 12px ui-monospace, monospace; }
    li { padding: 3px 0; }
    .hint { color: #58706a; font-size: 12px; line-height: 1.5; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; height: auto; } #map { height: 65vh; } aside { border-left: 0; } }
  </style>
</head>
<body>
  <header><h1>iOS Location Controller</h1><p>OpenStreetMap route editor for owned/test devices</p></header>
  <main>
    <div id="map"><div class="map-help" id="map-help">Click the map to add route nodes</div></div>
    <aside>
      <section class="device-status" aria-live="polite">
        <h2>iPhone connection</h2>
        <div class="status-line"><span id="device-dot" class="status-dot"></span><strong id="device-state">Checking...</strong></div>
        <ul id="device-list"></ul>
        <span id="device-updated"></span>
      </section>
      <section class="controls">
        <h2>Playback settings</h2>
        <div class="control-row"><label for="speed-kmh">Base speed (km/h)</label><input id="speed-kmh" type="number" min="0.01" step="0.1" value="5"></div>
        <div class="control-row"><label for="speed-variation">Speed variation (%)</label><input id="speed-variation" type="number" min="0" max="100" step="1" value="15"></div>
        <div class="control-row"><label for="lateral-variation">Left/right sway (m)</label><input id="lateral-variation" type="number" min="0" step="0.1" value="1.5"></div>
        <div class="control-row"><label for="interval">Update interval (s)</label><input id="interval" type="number" min="0.1" step="0.1" value="1"></div>
        <label class="check-row"><input id="loop" type="checkbox"> Loop route</label>
        <select id="route-select"><option value="">Select a saved route</option></select>
        <button class="ghost" id="set-route">Set route</button>
        <input id="import-route" type="file" accept=".gpx,application/gpx+xml">
        <div class="playback-actions"><button class="primary" id="start-playback">Start</button><button class="ghost" id="pause-playback">Pause</button></div>
        <button class="ghost" id="copy-command">Copy playback command</button>
        <span id="current-location" class="current-location">Current: not started</span>
      </section>
      <div class="stats"><div class="stat"><strong id="count">0</strong><span>路线点</span></div><div class="stat"><strong id="distance">0 m</strong><span>估算距离</span></div></div>
      <div class="actions">
        <button class="primary" id="export">导出 GPX</button>
        <button class="ghost" id="undo">撤销最后一点</button>
        <button class="ghost" id="clear">清空路线</button>
        <button class="ghost" id="locate">定位到当前位置</button>
      </div>
      <p class="hint">点击地图添加路线点。GPX 文件可交给现有 CLI 回放。地图数据 © OpenStreetMap contributors。</p>
      <ol id="points"></ol>
    </aside>
  </main>
  <script>
    // Keep the connection indicator independent from the optional map CDN.
    (async function watchDeviceStatus() {
      const dot = document.getElementById('device-dot');
      const state = document.getElementById('device-state');
      const list = document.getElementById('device-list');
      const updated = document.getElementById('device-updated');
      const startButton = document.getElementById('start-playback');
      window.addEventListener('error', event => {
        state.textContent = `UI error: ${event.message}`;
        dot.className = 'status-dot error';
      });
      window.addEventListener('unhandledrejection', event => {
        state.textContent = `UI error: ${event.reason}`;
        dot.className = 'status-dot error';
      });
      const settings = () => ({
        interval: Number(document.getElementById('interval').value),
        speed_kmh: Number(document.getElementById('speed-kmh').value),
        speed_variation_pct: Number(document.getElementById('speed-variation').value),
        lateral_variation_m: Number(document.getElementById('lateral-variation').value),
        loop: document.getElementById('loop').checked
      });
      startButton.onclick = async () => {
        startButton.disabled = true;
        startButton.textContent = 'Starting...';
        try {
          const response = await fetch('/api/playback/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(settings())});
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Unable to start playback');
          startButton.textContent = 'Started';
          setTimeout(() => { startButton.textContent = 'Start'; }, 1200);
        } catch (error) {
          startButton.textContent = 'Start error';
          alert(error.message);
          setTimeout(() => { startButton.textContent = 'Start'; }, 1800);
        } finally {
          startButton.disabled = false;
        }
      };
      document.getElementById('pause-playback').onclick = async () => {
        await fetch('/api/playback/pause', {method: 'POST'});
      };
      async function update() {
        try {
          const response = await fetch('/api/status', {cache: 'no-store'});
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const status = await response.json();
          dot.className = `status-dot ${status.error ? 'error' : status.count ? 'connected' : ''}`;
          state.textContent = status.error || (status.count ? `Connected: ${status.count}` : 'No iPhone detected');
          list.innerHTML = (status.devices || []).map(device => `<li>${device.name}</li>`).join('');
          updated.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
        } catch (error) {
          dot.className = 'status-dot error';
          state.textContent = `Status error: ${error.message}`;
        }
      }
      await update();
      setInterval(update, 3000);
    })();
  </script>
  <script src="/static/leaflet.js"></script>
  <script>
    const map = L.map('map').setView([31.2304, 121.4737], 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    const points = [], markers = [], line = L.polyline([], {color: '#e66b45', weight: 5}).addTo(map);
    const count = document.getElementById('count'), distance = document.getElementById('distance'), list = document.getElementById('points');
    const deviceDot = document.getElementById('device-dot'), deviceState = document.getElementById('device-state');
    const deviceList = document.getElementById('device-list'), deviceUpdated = document.getElementById('device-updated');
    const speedInput = document.getElementById('speed-kmh'), speedVariationInput = document.getElementById('speed-variation');
    const lateralInput = document.getElementById('lateral-variation'), intervalInput = document.getElementById('interval');
    const loopInput = document.getElementById('loop');
    const routeSelect = document.getElementById('route-select');
    const currentLocation = document.getElementById('current-location');
    const currentMarker = L.circleMarker([31.2304, 121.4737], {radius: 7, color: '#123b35', fillColor: '#e66b45', fillOpacity: 1}).addTo(map);
    currentMarker.setOpacity(0);
    let prepareRequested = false;
    const format = n => Number(n).toFixed(6);
    function refresh() {
      line.setLatLngs(points);
      count.textContent = points.length;
      list.innerHTML = points.map((p, i) => `<li>#${i + 1} ${format(p.lat)}, ${format(p.lng)}</li>`).join('');
      let meters = 0;
      for (let i = 1; i < points.length; i++) meters += map.distance(points[i - 1], points[i]);
      distance.textContent = meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(2)} km`;
    }
    function addPoint(latlng) {
      points.push({lat: latlng.lat, lng: latlng.lng});
      const marker = L.marker(latlng, {title: `Point ${points.length}`}).addTo(map);
      marker.bindTooltip(`#${points.length}`, {permanent: true, direction: 'top', offset: [0, -10]});
      markers.push(marker);
      refresh();
      syncRoute();
    }
    function removeLast() { if (!points.length) return; points.pop(); map.removeLayer(markers.pop()); refresh(); syncRoute(); }
    function replaceRoute(routePoints) {
      while (points.length) {
        points.pop();
        map.removeLayer(markers.pop());
      }
      routePoints.forEach(point => addPoint(L.latLng(point.lat, point.lng)));
      if (routePoints.length) map.fitBounds(L.latLngBounds(routePoints.map(point => L.latLng(point.lat, point.lng))));
      syncRoute();
    }
    map.getContainer().style.cursor = 'crosshair';
    map.on('click', e => addPoint(e.latlng));
    document.getElementById('undo').onclick = removeLast;
    document.getElementById('clear').onclick = () => { while (points.length) removeLast(); syncRoute(); };
    document.getElementById('locate').onclick = () => map.locate({setView: true, maxZoom: 17});
    /* Replaced below with an encoding-safe export handler.
    document.getElementById('export').onclick = () => {
      if (!points.length) return alert('请先在地图上添加路线点');
      const body = points.map(p => `    <trkpt lat="${format(p.lat)}" lon="${format(p.lng)}" />`).join('\n');
      const gpx = `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="ios-location-controller" xmlns="http://www.topografix.com/GPX/1/1">\n  <trk><name>Map route</name><trkseg>\n${body}\n  </trkseg></trk>\n</gpx>\n`;
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([gpx], {type: 'application/gpx+xml'})); a.download = 'route.gpx'; a.click(); URL.revokeObjectURL(a.href);
    }; */
    document.getElementById('export').onclick = () => {
      if (!points.length) return alert('Add at least one route point');
      const body = points.map(p => `    <trkpt lat="${format(p.lat)}" lon="${format(p.lng)}" />`).join('\n');
      const gpx = `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="ios-location-controller" xmlns="http://www.topografix.com/GPX/1/1">\n  <trk><name>Map route</name><trkseg>\n${body}\n  </trkseg></trk>\n</gpx>\n`;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([gpx], {type: 'application/gpx+xml'}));
      a.download = 'route.gpx';
      a.click();
      URL.revokeObjectURL(a.href);
    };
    document.getElementById('import-route').onchange = event => {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const xml = new DOMParser().parseFromString(reader.result, 'application/xml');
        if (xml.querySelector('parsererror')) return alert('Invalid GPX file');
        const imported = Array.from(xml.getElementsByTagNameNS('*', 'trkpt')).map(node => ({
          lat: Number(node.getAttribute('lat')), lng: Number(node.getAttribute('lon'))
        })).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lng));
        if (!imported.length) return alert('GPX contains no track points');
        replaceRoute(imported);
      };
      reader.readAsText(file);
    };
    async function loadSavedRoutes() {
      const response = await fetch('/api/routes', {cache: 'no-store'});
      const routes = await response.json();
      routes.forEach(route => routeSelect.add(new Option(route, route)));
    }
    document.getElementById('set-route').onclick = async () => {
      if (!routeSelect.value) return alert('Select a saved route first');
      const response = await fetch('/api/route/load', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: routeSelect.value})});
      const result = await response.json();
      if (!response.ok) return alert(result.error || 'Unable to set route');
      replaceRoute(result.points);
    };
    loadSavedRoutes().catch(error => console.error('Could not load saved routes', error));
    async function syncRoute() {
      prepareRequested = false;
      await fetch('/api/route', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        points: points.map(point => ({lat: point.lat, lng: point.lng}))
      })});
    }
    function playbackSettings() {
      return {
        interval: Number(intervalInput.value), speed_kmh: Number(speedInput.value),
        speed_variation_pct: Number(speedVariationInput.value),
        lateral_variation_m: Number(lateralInput.value), loop: loopInput.checked
      };
    }
    document.getElementById('copy-command').onclick = async () => {
      if (!points.length) return alert('Import or draw a route first');
      const args = [
        '.\\.venv\\Scripts\\python.exe -m ios_location_controller play .\\route.gpx',
        `--speed-kmh ${Number(speedInput.value)}`,
        `--interval ${Number(intervalInput.value)}`,
        `--speed-variation-pct ${Number(speedVariationInput.value)}`,
        `--lateral-variation-m ${Number(lateralInput.value)}`
      ];
      if (loopInput.checked) args.push('--loop');
      await navigator.clipboard.writeText(args.join(' '));
      alert('Playback command copied. Export the route as route.gpx first.');
    };
    async function refreshDeviceStatus() {
      try {
        const response = await fetch('/api/status', {cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const status = await response.json();
        deviceDot.className = `status-dot ${status.error ? 'error' : status.count ? 'connected' : ''}`;
        deviceState.textContent = status.error || (status.count ? `Connected: ${status.count}` : 'No iPhone detected');
        deviceList.innerHTML = (status.devices || []).map(device => `<li>${device.name}</li>`).join('');
        deviceUpdated.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
        const playback = status.playback || {};
        if (playback.current) {
          const point = [playback.current.lat, playback.current.lng];
          currentMarker.setLatLng(point).setOpacity(1);
          currentLocation.textContent = `Current: ${playback.current.lat.toFixed(6)}, ${playback.current.lng.toFixed(6)} (${playback.state})`;
        }
        if (status.count && points.length && !prepareRequested && ['ready', 'no-route'].includes(playback.state)) {
          prepareRequested = true;
          const prepareResponse = await fetch('/api/playback/prepare', {method: 'POST'});
          if (!prepareResponse.ok) prepareRequested = false;
        }
      } catch (error) {
        deviceDot.className = 'status-dot error';
        deviceState.textContent = `Status error: ${error.message}`;
        deviceList.innerHTML = '';
        deviceUpdated.textContent = '';
      }
    }
    refreshDeviceStatus();
    setInterval(refreshDeviceStatus, 3000);
  </script>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        static_files = {
            "/static/leaflet.js": ("leaflet.js", "application/javascript; charset=utf-8"),
            "/static/leaflet.css": ("leaflet.css", "text/css; charset=utf-8"),
            "/static/images/marker-icon.png": ("images/marker-icon.png", "image/png"),
            "/static/images/marker-icon-2x.png": ("images/marker-icon-2x.png", "image/png"),
            "/static/images/marker-shadow.png": ("images/marker-shadow.png", "image/png"),
        }
        if path in static_files:
            filename, content_type = static_files[path]
            file_path = Path(__file__).resolve().parent / "static" / filename
            if not file_path.exists():
                self.send_error(404)
                return
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/routes":
            routes = sorted(route.name for route in ROUTES_DIR.glob("*.gpx")) if ROUTES_DIR.exists() else []
            self._send_json(routes)
            return
        if path == "/api/status":
            self._send_status()
            return
        if path != "/":
            self.send_error(404)
            return
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/route":
                data = self._read_json()
                points = []
                for item in data.get("points", []):
                    point = Point(float(item["lat"]), float(item["lng"]))
                    if not -90 <= point.latitude <= 90 or not -180 <= point.longitude <= 180:
                        raise ValueError("Invalid coordinate")
                    points.append(point)
                PLAYBACK.set_route(points)
                self._send_json({"ok": True, "count": len(points)})
                return
            if path == "/api/route/load":
                data = self._read_json()
                name = str(data.get("name", ""))
                route_path = ROUTES_DIR / name
                if not name or route_path.name != name or route_path.suffix.lower() != ".gpx":
                    raise ValueError("Invalid route name")
                points = load_points(route_path)
                PLAYBACK.set_route(points)
                self._send_json({
                    "ok": True,
                    "name": name,
                    "count": len(points),
                    "points": [{"lat": point.latitude, "lng": point.longitude} for point in points],
                })
                return
            if path == "/api/playback/prepare":
                PLAYBACK.prepare()
                self._send_json({"ok": True, "playback": PLAYBACK.status()})
                return
            if path == "/api/playback/start":
                data = self._read_json()
                PLAYBACK.set_settings({
                    "interval": float(data.get("interval", 1.0)),
                    "speed_kmh": float(data.get("speed_kmh", 5.0)),
                    "speed_variation_pct": float(data.get("speed_variation_pct", 0.0)),
                    "lateral_variation_m": float(data.get("lateral_variation_m", 0.0)),
                    "loop": bool(data.get("loop", False)),
                })
                PLAYBACK.start()
                self._send_json({"ok": True, "playback": PLAYBACK.status()})
                return
            if path == "/api/playback/pause":
                PLAYBACK.pause()
                self._send_json({"ok": True, "playback": PLAYBACK.status()})
                return
            self.send_error(404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_status(self) -> None:
        try:
            from pymobiledevice3.usbmux import list_devices

            devices = asyncio.run(list_devices())
            names = []
            for device in devices:
                udid = getattr(device, "serial", None) or getattr(device, "udid", None)
                product = getattr(device, "product_type", None) or getattr(device, "device_class", None)
                label = " / ".join(str(value) for value in (product, udid) if value)
                names.append(label or str(device))
            payload = {"count": len(names), "devices": [{"name": name} for name in names]}
        except Exception as exc:
            payload = {"count": 0, "devices": [], "error": str(exc)}
        payload["playback"] = PLAYBACK.status()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Map server: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
