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
    cosmic = bool(d.get("cosmic", True))
    peaks_hint = [p for p in d.get("peaks", []) if p]
    try:
        peaks_hint = [float(p) for p in peaks_hint]
    except (TypeError, ValueError):
        peaks_hint = []

    def run():
        STATE.update(busy=True, done=False, error=None, result=None,
                     current=0, total=5, message="Starting…")
        try:
            out = process_experiment(folder, ref, lambda_vis=vis,
                                     x_ranges=ranges, cosmic=cosmic,
                                     peaks_hint=peaks_hint or None,
                                     progress_callback=_progress)
            # gallery shows only the per-range FIT figures
            out_dir = os.path.join(folder, "processed")
            imgs = sorted(glob.glob(os.path.join(out_dir, "*_[0-9]*_[0-9]*_fit.png")))
            # cache normalised spectra so peak positions can be refined fast
            import pandas as pd
            cache = {}
            try:
                xl = pd.ExcelFile(out)
                for s in xl.sheet_names:
                    if s.endswith("_normalized"):
                        df = xl.parse(s)
                        cache[s[:-len("_normalized")]] = {
                            "x": df["IR_wavenumber_cm-1"].tolist(),
                            "y": [None if v != v else float(v)
                                  for v in df["normalized_sum"].tolist()],
                        }
            except Exception:
                pass
            STATE.update(norm_cache=cache, folder=folder, ref=ref)
            STATE.update(done=True, busy=False,
                         result={"excel": out, "images": imgs, "folder": folder},
                         message="Done")
        except Exception as e:  # pragma: no cover
            STATE.update(done=True, busy=False, error=str(e), message="Failed")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/refit", methods=["POST"])
def api_refit():
    """Re-generate only the per-range figures (line/scatter/fit) with new peaks.

    No re-scan; all other outputs (denoised, sum curves, full-range, Excel) stay
    untouched. Only the given-wavenumber-range figures are refreshed.
    """
    cache = STATE.get("norm_cache")
    if not cache:
        return jsonify({"error": "Run Process first"}), 400
    d = request.get_json(silent=True) or {}
    try:
        peaks_hint = [float(p) for p in d.get("peaks", []) if p] or None
    except (TypeError, ValueError):
        peaks_hint = None
    ranges = [(int(a), int(b)) for a, b in (d.get("ranges") or []) if a < b]
    ref = d.get("ref", STATE.get("ref", "ref"))
    folder = STATE.get("folder", "")
    out_dir = os.path.join(folder, "processed")
    from sfg_processor import _set_nature_style, _plot_nature
    import pandas as pd
    try:
        _set_nature_style()
        for sample, xy in cache.items():
            norm_df = pd.DataFrame({"IR_wavenumber_cm-1": xy["x"],
                                    "normalized_sum": xy["y"]})
            for x_min, x_max in ranges:
                for mode in ("line", "scatter", "fit"):
                    _plot_nature(norm_df, sample, ref,
                                 os.path.join(out_dir,
                                              f"{sample}_{x_min}_{x_max}_{mode}.png"),
                                 mode=mode, xlim=(x_min, x_max),
                                 peaks_hint=peaks_hint)
        imgs = sorted(glob.glob(os.path.join(out_dir, "*_[0-9]*_[0-9]*_fit.png")))
        return jsonify({"images": imgs, "folder": folder})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def api_status():
    return jsonify(dict(STATE))


@app.route("/api/openurl", methods=["POST"])
def api_openurl():
    """Open an external URL in the system browser (footer GitHub links)."""
    d = request.get_json(silent=True) or {}
    url = d.get("url", "")
    # whitelist the project's own GitHub pages
    if not url.startswith("https://github.com/lijiathu/sfg-processor"):
        return jsonify({"error": "URL not allowed"}), 400
    try:
        webbrowser.open(url)
    except Exception as e:  # pragma: no cover
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/file")
def api_file():
    folder = request.args.get("folder", "")
    path = request.args.get("path", "")
    dl = request.args.get("download", "")
    if not path or not _within(folder, path):
        abort(404)
    return send_file(path, as_attachment=bool(dl))


@app.route("/img")
def api_img():
    """Serve a figure from the cached output folder by ASCII filename.

    Avoids putting the (possibly Chinese) folder path in the URL query string,
    which mangles non-ASCII characters. The folder is resolved server-side.
    """
    name = request.args.get("name", "")
    folder = STATE.get("folder", "")
    if not name or not folder or "/" in name or "\\" in name:
        abort(404)
    fp = os.path.join(folder, "processed", name)
    if not os.path.isfile(fp):
        abort(404)
    return send_file(fp)


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


def _wait_for_server(url, attempts=80):
    import time
    import urllib.request
    for _ in range(attempts):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    # run Flask in a background daemon thread (stopped when the app exits)
    server = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port,
                               debug=False, use_reloader=False),
        daemon=True,
    )
    server.start()
    if not _wait_for_server(url):
        print("Server failed to start.")
        return

    # open a native desktop window (no browser/address bar); fall back to browser
    # window size adapts to the screen so it fits on small laptops too
    try:
        import tkinter as tk
        _r = tk.Tk(); _r.withdraw()
        sw, sh = _r.winfo_screenwidth(), _r.winfo_screenheight()
        _r.destroy()
    except Exception:
        sw, sh = 1440, 900
    win_w = min(1440, max(1100, sw - 80))
    win_h = min(900, max(680, sh - 80))
    try:
        import webview
        webview.create_window("SFG Processor", url, width=win_w, height=win_h,
                              min_size=(1000, 600))
        webview.start()
    except Exception:
        webbrowser.open(url)
        server.join()


if __name__ == "__main__":
    main()
