"""SFG Processor — Flask backend with a refined web frontend.

Serves a single self-contained HTML page and exposes JSON endpoints:
  POST /api/browse   → native folder picker (tkinter on the backend), returns path
  POST /api/scan     → scan a folder, return detected samples + preview
  POST /api/process  → start background processing
  GET  /api/status   → polling endpoint for progress / result
  GET  /file?...     → serve a generated file (image / excel) for preview & download
  POST /api/open     → open a folder in the system file explorer
"""

import glob
import os
import socket
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_file, abort

from sfg_processor import scan_folder, get_sample_names, process_experiment


# --------------------------------------------------------------------------- #
#  locate the frontend file (bundled or source layout)
# --------------------------------------------------------------------------- #
def _frontend_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "frontend"),
        os.path.join(sys._MEIPASS, "frontend") if hasattr(sys, "_MEIPASS") else "",
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    raise FileNotFoundError("frontend/ directory not found")


def _frontend_path():
    return os.path.join(_frontend_dir(), "index.html")


# --------------------------------------------------------------------------- #
#  tiny in-memory job state (single-user local tool)
# --------------------------------------------------------------------------- #
STATE = {
    "current": 0, "total": 5, "message": "Ready",
    "done": True, "busy": False, "error": None, "result": None,
}


def _progress(current, total, message):
    STATE.update(current=current, total=total, message=message)


app = Flask(__name__)


@app.route("/")
def index():
    return send_file(_frontend_path())


@app.route("/<path:fname>")
def frontend_asset(fname):
    """Serve a co-located frontend asset (e.g. sfg_schematic.png)."""
    fp = os.path.join(_frontend_dir(), fname)
    if os.path.isfile(fp):
        return send_file(fp)
    abort(404)


def _within(folder, path):
    """True if path is a file inside folder (realpath-safe)."""
    try:
        rp = os.path.realpath(path)
        rf = os.path.realpath(folder)
        return rp.startswith(rf + os.sep) and os.path.isfile(rp)
    except Exception:
        return False


@app.route("/api/browse", methods=["POST"])
def api_browse():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(parent=root, title="Select experiment data folder")
        root.destroy()
    except Exception as e:  # pragma: no cover
        return jsonify({"path": "", "error": str(e)}), 500
    return jsonify({"path": path})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    folder = (request.get_json(silent=True) or {}).get("folder", "")
    try:
        meta = scan_folder(folder)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    names = get_sample_names(meta)
    default = "quartz" if "quartz" in names else (names[0] if names else "")
    preview = []
    for name in names:
        ms = [m for m in meta if m["sample"] == name and not m["is_background"]]
        waves = sorted({m["wave"] for m in ms})
        preview.append({
            "name": name,
            "count": len(ms),
            "waves": ", ".join(str(w) for w in waves),
            "ref": name == default,
        })
    return jsonify({"samples": names, "default": default, "preview": preview})


@app.route("/api/process", methods=["POST"])
def api_process():
    if STATE["busy"]:
        return jsonify({"error": "A job is already running; please wait"}), 409
    d = request.get_json(silent=True) or {}
    folder = d.get("folder", "")
    ref = d.get("ref", "")
    vis = float(d.get("vis", 1030))
    ranges = d.get("ranges") or []
    ranges = [(int(a), int(b)) for a, b in ranges if a < b]

    def run():
        STATE.update(busy=True, done=False, error=None, result=None,
                     current=0, total=5, message="Starting…")
        try:
            out = process_experiment(folder, ref, lambda_vis=vis,
                                     x_ranges=ranges,
                                     progress_callback=_progress)
            imgs = sorted(glob.glob(os.path.join(folder, "*_normalized_*.png")))
            STATE.update(done=True, busy=False,
                         result={"excel": out, "images": imgs, "folder": folder},
                         message="Done")
        except Exception as e:  # pragma: no cover
            STATE.update(done=True, busy=False, error=str(e), message="Failed")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/status")
def api_status():
    return jsonify(dict(STATE))


@app.route("/file")
def api_file():
    folder = request.args.get("folder", "")
    path = request.args.get("path", "")
    dl = request.args.get("download", "")
    if not path or not _within(folder, path):
        abort(404)
    return send_file(path, as_attachment=bool(dl))


@app.route("/api/open", methods=["POST"])
def api_open():
    folder = (request.get_json(silent=True) or {}).get("folder", "")
    try:
        if os.path.isdir(folder):
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])  # noqa: S603
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])  # noqa: S603
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


def _free_port(preferred=5127):
    for port in (preferred, 5128, 5129, 5130, 5131):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"SFG Processor running at {url}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
