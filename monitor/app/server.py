import json
import os
import time
from typing import Dict

from flask import Flask, Response, jsonify, render_template, request

from .monitoring import InMemoryTimeSeriesStore, Sampler, load_targets_from_env


app = Flask(__name__, static_folder="../static", template_folder="../templates")

PERSIST_PATH = os.getenv("PERSIST_PATH", "/app_data/metrics.json")

_store = InMemoryTimeSeriesStore(max_points=7200, persistence_path=PERSIST_PATH, persist_interval_seconds=10.0)
_store.load_from_disk()

_mode = os.getenv("MONITOR_MODE", "winrm").lower()
_interval = float(os.getenv("SAMPLE_INTERVAL_SECONDS", "5"))
_targets = load_targets_from_env()
_sampler = Sampler(store=_store, interval_seconds=_interval, mode=_mode, targets=_targets)
_sampler.start()


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/snapshot")
def api_snapshot() -> Response:
    snap = _store.snapshot()
    return jsonify({"data": snap})


@app.route("/api/status")
def api_status() -> Response:
    return jsonify({"status": _sampler.status()})


@app.route("/events")
def sse_events() -> Response:
    def event_stream():
        last_sent = 0.0
        while True:
            time.sleep(1.0)
            snap: Dict[str, Dict[str, object]] = _store.snapshot()
            newest = 0.0
            for s in snap.values():
                pts = s.get("points", [])  # type: ignore
                if pts:
                    newest = max(newest, float(pts[-1]["t"]))
            if newest > last_sent:
                yield f"data: {json.dumps({'data': snap})}\n\n"
                last_sent = newest
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/winrm", methods=["POST"])
def api_set_winrm() -> Response:
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    host = (payload.get("host") or os.getenv("WINRM_HOST", "host.docker.internal")).strip()
    port = int(payload.get("port") or os.getenv("WINRM_PORT", "5985"))
    use_ssl = bool(payload.get("use_ssl") or (os.getenv("WINRM_USE_SSL", "false").lower() in {"1", "true", "yes"}))
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    try:
        _sampler.set_winrm_credentials(host, username, password, port=port, use_ssl=use_ssl)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
