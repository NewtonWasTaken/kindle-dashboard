"""
Kindle Dashboard Server

Flask application that serves a dashboard PNG image for Kindle e-readers.
Data is refreshed in a background thread; images are rendered on-demand
so the clock always shows the current time.
"""

import os
import io
import time
import logging
import threading
from datetime import datetime

from flask import Flask, send_file, render_template_string, jsonify, redirect, url_for
from data_sources import fetch_docker_status, fetch_weather, fetch_calendar_events, fetch_tasks
from render import render_dashboard

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_REFRESH_INTERVAL = int(os.environ.get('DATA_REFRESH_INTERVAL', 300))
SCREEN_WIDTH = int(os.environ.get('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.environ.get('SCREEN_HEIGHT', 600))
PORT = int(os.environ.get('PORT', 5000))

# ---------------------------------------------------------------------------
# Data cache (refreshed by background thread)
# ---------------------------------------------------------------------------

_data_cache = {
    'weather': None,
    'containers': None,
    'events': None,
    'tasks': None,
    'last_update': None,
    'error': None,
}
_lock = threading.Lock()
_refresh_in_progress = False


def refresh_data():
    """Fetch fresh data from all sources and update the cache."""
    global _refresh_in_progress
    with _lock:
        if _refresh_in_progress:
            return
        _refresh_in_progress = True

    t0 = time.time()
    try:
        weather = fetch_weather()
        containers = fetch_docker_status()
        events = fetch_calendar_events()
        tasks = fetch_tasks()

        with _lock:
            _data_cache['weather'] = weather
            _data_cache['containers'] = containers
            _data_cache['events'] = events
            _data_cache['tasks'] = tasks
            _data_cache['last_update'] = datetime.now()
            _data_cache['error'] = None

        logging.info("Data refreshed in %.2fs (containers=%d, events=%d, tasks=%d)",
                      time.time() - t0,
                      len(containers), len(events), len(tasks))
    except Exception as exc:
        logging.error("Data refresh failed: %s", exc)
        with _lock:
            _data_cache['error'] = str(exc)
            _data_cache['last_update'] = datetime.now()
    finally:
        with _lock:
            _refresh_in_progress = False


def background_refresh():
    """Daemon thread: refresh data periodically."""
    while True:
        try:
            refresh_data()
        except Exception as exc:
            logging.error("Background refresh thread error: %s", exc)
        time.sleep(DATA_REFRESH_INTERVAL)


# Start background thread on import
_bg_thread = threading.Thread(target=background_refresh, daemon=True, name="BgRefreshThread")
_bg_thread.start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/dashboard.png')
def dashboard_png():
    """Render and return the dashboard PNG (always fresh clock)."""
    with _lock:
        needs_initial_refresh = (_data_cache['last_update'] is None and not _refresh_in_progress)

    if needs_initial_refresh:
        refresh_data()

    with _lock:
        weather = _data_cache['weather'] or {}
        containers = _data_cache['containers'] or []
        events = _data_cache['events'] or []
        tasks = _data_cache['tasks'] or []

    img_bytes = render_dashboard(
        weather=weather,
        containers=containers,
        events=events,
        tasks=tasks,
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
    )

    resp = send_file(io.BytesIO(img_bytes), mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/')
def index():
    """Status page with live preview."""
    with _lock:
        last_update = (_data_cache['last_update'].strftime('%H:%M:%S')
                       if _data_cache['last_update'] else 'Načítám...')
        containers_count = len(_data_cache['containers'] or [])
        events_count = len(_data_cache['events'] or [])
        tasks_count = len(_data_cache['tasks'] or [])
        weather_temp = (_data_cache['weather'].get('current', {}).get('temperature')
                        if _data_cache['weather'] else None)
        error = _data_cache['error']
        ts = int(time.time())

    return render_template_string(STATUS_HTML,
        last_update=last_update,
        data_interval=DATA_REFRESH_INTERVAL,
        width=SCREEN_WIDTH, height=SCREEN_HEIGHT,
        containers_count=containers_count,
        events_count=events_count,
        tasks_count=tasks_count,
        weather_temp=weather_temp,
        error=error,
        ts=ts,
    )


@app.route('/refresh')
def refresh():
    """Force an immediate data refresh asynchronously."""
    t = threading.Thread(target=refresh_data, daemon=True)
    t.start()
    return redirect(url_for('index'))


@app.route('/api/status')
def api_status():
    with _lock:
        return jsonify({
            'last_update': (_data_cache['last_update'].isoformat()
                            if _data_cache['last_update'] else None),
            'data_refresh_interval': DATA_REFRESH_INTERVAL,
            'screen': {'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT},
            'data': {
                'containers': len(_data_cache['containers'] or []),
                'events': len(_data_cache['events'] or []),
                'tasks': len(_data_cache['tasks'] or []),
                'weather_temp': (_data_cache['weather'].get('current', {}).get('temperature')
                                 if _data_cache['weather'] else None),
            },
        })


# ---------------------------------------------------------------------------
# Status page HTML
# ---------------------------------------------------------------------------

STATUS_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Kindle Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{
      background:#0f0f1a;color:#ccc;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      display:flex;justify-content:center;padding:24px;
    }
    .wrap{max-width:860px;width:100%;text-align:center}
    h1{color:#fff;font-size:1.8rem;margin-bottom:20px;letter-spacing:.5px}
    .preview{
      max-width:560px;width:100%;border:2px solid #333;border-radius:10px;
      margin:0 auto 24px;box-shadow:0 6px 24px rgba(0,0,0,.5);
      background:#fff;
    }
    .cards{
      display:grid;grid-template-columns:1fr 1fr;gap:14px;
      margin-bottom:20px;text-align:left;
    }
    .card{
      background:#16213e;padding:14px 16px;border-radius:8px;
      border:1px solid #0f3460;
    }
    .card h3{color:#e94560;margin-bottom:8px;font-size:.95rem}
    .card p{margin:3px 0;font-size:.88rem;color:#aaa}
    .card span{color:#eee}
    .btn{
      display:inline-block;background:#e94560;color:#fff;
      border:none;padding:10px 28px;border-radius:6px;
      font-size:.95rem;cursor:pointer;text-decoration:none;
      transition:background .2s;
    }
    .btn:hover{background:#c73550}
    .err{color:#ff6b6b;margin-bottom:12px}
    .note{color:#555;font-size:.78rem;margin-top:16px}
  </style>
  <script>
    // auto-reload preview image every 30 s
    setInterval(()=>{
      const img=document.getElementById('preview');
      img.src='/dashboard.png?t='+Date.now();
    },30000);
  </script>
</head>
<body>
<div class="wrap">
  <h1>📱 Kindle Dashboard</h1>
  {% if error %}<p class="err">Chyba: {{ error }}</p>{% endif %}
  <a href="/dashboard.png" target="_blank">
    <img id="preview" src="/dashboard.png?t={{ ts }}" class="preview" alt="Dashboard">
  </a>
  <div class="cards">
    <div class="card">
      <h3>Systém</h3>
      <p>Data: <span>{{ last_update }}</span></p>
      <p>Refresh dat: <span>{{ data_interval }}s</span></p>
      <p>Rozlišení: <span>{{ width }}×{{ height }}</span></p>
    </div>
    <div class="card">
      <h3>Zdroje dat</h3>
      <p>Kontejnery: <span>{{ containers_count }}</span></p>
      <p>Události: <span>{{ events_count }}</span></p>
      <p>Úkoly: <span>{{ tasks_count }}</span></p>
      <p>Počasí: <span>{% if weather_temp %}{{ weather_temp }}°C{% else %}N/A{% endif %}</span></p>
    </div>
  </div>
  <a href="/refresh" class="btn">🔄 Obnovit data</a>
  <p class="note">Obrázek se automaticky obnovuje každých 30 s · data každých {{ data_interval }}s</p>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
