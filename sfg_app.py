"""SFG Processor — Flask backend with a refined web frontend.

Serves a single self-contained HTML page and exposes JSON endpoints:
  POST /api/browse   → native folder picker (tkinter on the backend), returns path
  POST /api/scan     → scan a folder, return detected samples + preview
                       (single-experiment or multi-folder mode)
  POST /api/process  → start background processing (cancel via /api/cancel)
  POST /api/cancel   → request cancellation of the running job
  GET  /api/status   → polling endpoint for progress / result
  POST /api/refit    → re-fit cached normalised data with new peak centres
  GET  /file?...     → serve a generated file (image / excel) for preview & download
  GET  /img?...      → serve a figure from the output folder(s) by filename
  POST /api/open     → open a folder in the system file explorer
"""

import glob
import os
import socket
import sys
import threading
import warnings
import webbrowser

from flask import Flask, jsonify, request, send_file, abort

from sfg_processor import (scan_folder, get_sample_names, process_experiment,
                           scan_experiment_folders, parse_filename, JobCancelled)


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
    "cancel_requested": False, "cancelled": False,
    "mode": "single", "folder": "", "ref": "",
    "folders": {}, "refs": {}, "norm_cache": {},
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


def _sample_preview(meta, default):
    """Per-sample preview rows (name, file count, wavenumbers, is-reference)."""
    preview = []
    for name in get_sample_names(meta):
        ms = [m for m in meta if m["sample"] == name and not m["is_background"]]
        waves = sorted({m["wave"] for m in ms})
        preview.append({
            "name": name,
            "count": len(ms),
            "waves": ", ".join(str(w) for w in waves),
            "ref": name == default,
        })
    return preview


@app.route("/api/scan", methods=["POST"])
def api_scan():
    folder = (request.get_json(silent=True) or {}).get("folder", "")
    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "Folder not found; check the path."}), 400

    # mode detection: parseable data .txt directly in the picked folder → one
    # experiment; data only in immediate subfolders → one experiment per
    # subfolder.  A stray notes/readme .txt must NOT flip the mode (it parses
    # to no sample and would silently merge independent experiments).
    def _is_data_txt(fname):
        if not fname.lower().endswith(".txt"):
            return False
        try:
            parse_filename(os.path.splitext(os.path.basename(fname))[0])
            return True
        except ValueError:
            return False

    has_direct_txt = any(
        _is_data_txt(f)
        for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
    )
    if not has_direct_txt:
        entries = scan_experiment_folders(folder)
        # multi mode needs at least one subfolder holding reference + test
        # sample; otherwise fall back to a single recursive experiment (e.g.
        # layouts with one sample per subfolder sharing one parent folder)
        if any(len(e["samples"]) >= 2 for e in entries):
            folders = []
            for e in entries:
                names = e["samples"]
                default = "quartz" if "quartz" in names else (names[0] if names else "")
                folders.append({
                    "name": e["name"], "path": e["path"], "samples": names,
                    "default": default, "ok": len(names) >= 2,
                })
            return jsonify({"mode": "multi", "folder": folder, "folders": folders})

    try:
        meta = scan_folder(folder)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    names = get_sample_names(meta)
    default = "quartz" if "quartz" in names else (names[0] if names else "")
    return jsonify({"mode": "single", "samples": names, "default": default,
                    "folder": folder, "preview": _sample_preview(meta, default)})


@app.route("/api/process", methods=["POST"])
def api_process():
    if STATE["busy"]:
        return jsonify({"error": "A job is already running; please wait"}), 409
    d = request.get_json(silent=True) or {}
    folder = d.get("folder", "")
    vis = float(d.get("vis", 1030))
    ranges = [(int(a), int(b)) for a, b in (d.get("ranges") or []) if a < b]
    cosmic = bool(d.get("cosmic", False))
    do_fit = bool(d.get("fit", False))
    try:
        peaks_hint = [float(p) for p in d.get("peaks", []) if p] or None
    except (TypeError, ValueError):
        peaks_hint = None

    multi = d.get("mode") == "multi"
    skipped_pre = []
    if multi:
        # one job per immediate subfolder; re-scan so skipped/renamed
        # folders are caught even if the UI preview is stale
        try:
            entries = {e["name"]: e for e in scan_experiment_folders(folder)}
        except Exception:
            entries = {}
        jobs = []
        for f in d.get("folders") or []:
            e = entries.get(f.get("name"))
            if not e or len(e["samples"]) < 2:
                skipped_pre.append(f.get("name", "?"))
                continue
            ref = f.get("ref")
            if ref not in e["samples"]:
                ref = ("quartz" if "quartz" in e["samples"] else e["samples"][0])
            jobs.append((e["name"], e["path"], ref))
        if not jobs:
            return jsonify({"error": "No subfolder holds a reference + test sample"}), 400
    else:
        if not folder:
            return jsonify({"error": "No data folder given"}), 400
        jobs = [("", folder, d.get("ref", ""))]

    def _cancelled():
        return bool(STATE.get("cancel_requested"))

    def run():
        n = len(jobs)
        STATE.update(busy=True, done=False, error=None, result=None,
                     cancelled=False, cancel_requested=False,
                     current=0, total=5 * n, message="Starting…")
        import pandas as pd
        images, skipped, notes, folders_map, refs_map, excels, norm_cache = \
            [], [], [], {}, {}, [], {}
        try:
            for i, (name, fpath, ref) in enumerate(jobs):
                if _cancelled():
                    raise JobCancelled("Cancelled by user")
                base = i * 5

                def prog(cur, tot, msg, base=base, i=i, name=name, n=n):
                    msg = f"[{i + 1}/{n}] {name} · {msg}" if name else msg
                    STATE.update(current=base + cur, total=5 * n, message=msg)

                try:
                    # surface pipeline warnings (e.g. dropped wavenumbers) in the UI
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        out = process_experiment(
                            fpath, ref, lambda_vis=vis, x_ranges=ranges,
                            cosmic=cosmic, peaks_hint=peaks_hint, do_fit=do_fit,
                            progress_callback=prog, cancel_check=_cancelled)
                    notes.extend((f"{name}: " if name else "") + str(w.message)
                                 for w in caught)
                except JobCancelled:
                    raise
                except Exception as e:
                    if not multi:  # single mode: surface the failure, don't
                        raise    # dress it up as "Done · 1 skipped"
                    # multi mode: one bad folder must not stop the rest
                    skipped.append(f"{name or os.path.basename(fpath)}: {e}")
                    continue

                # gallery: per-range fit figures, or scatter when fitting is off
                out_dir = os.path.join(fpath, "processed")
                pattern = ("*_[0-9]*_[0-9]*_fit.png" if do_fit
                           else "*_[0-9]*_[0-9]*_scatter.png")
                for p in sorted(glob.glob(os.path.join(out_dir, pattern))):
                    images.append({"folder": name, "file": os.path.basename(p)})
                folders_map[name] = fpath
                refs_map[name] = ref
                excels.append({"folder": name, "path": out})

                # cache normalised spectra so peak positions can be refined fast
                cache = {}
                try:
                    # context manager: an unclosed handle keeps the file (and
                    # its processed/ folder) locked on Windows until GC
                    with pd.ExcelFile(out) as xl:
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
                norm_cache[name] = cache
                # register incrementally so a cancelled run still exposes the
                # folders that already finished (gallery, /img, re-fit)
                STATE.update(folders=folders_map, refs=refs_map,
                             norm_cache=norm_cache)

            result = {
                "mode": "multi" if multi else "single",
                "folder": folder, "images": images, "excels": excels,
                "skipped": skipped_pre + skipped, "notes": notes,
                "excel": (excels[0]["path"] if len(excels) == 1 else None),
            }
            STATE.update(folders=folders_map, refs=refs_map, norm_cache=norm_cache,
                         folder=folder, ref=(jobs[0][2] if jobs else ""),
                         mode=("multi" if multi else "single"))
            msg = "Done" + (f" · {len(result['skipped'])} skipped"
                            if result["skipped"] else "")
            STATE.update(done=True, busy=False, result=result, message=msg)
        except JobCancelled:
            # keep whatever already finished: its outputs are on disk and stay
            # visible/usable (gallery, /img, re-fit) instead of vanishing
            result = {
                "mode": "multi" if multi else "single",
                "folder": folder, "images": images, "excels": excels,
                "skipped": skipped_pre + skipped, "notes": notes,
                "excel": (excels[0]["path"] if len(excels) == 1 else None),
            }
            STATE.update(folders=folders_map, refs=refs_map, norm_cache=norm_cache,
                         folder=folder, ref=(jobs[0][2] if jobs else ""),
                         mode=("multi" if multi else "single"), result=result,
                         done=True, busy=False, cancelled=True,
                         message=f"Cancelled · {len(excels)}/{len(jobs)} done")
        except Exception as e:  # pragma: no cover
            STATE.update(done=True, busy=False, error=str(e), message="Failed")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    """Cooperatively cancel the running job (checked between stages/samples)."""
    if not STATE.get("busy"):
        return jsonify({"ok": False, "error": "No job is running"}), 409
    STATE.update(cancel_requested=True, message="Cancelling…")
    return jsonify({"ok": True})


@app.route("/api/refit", methods=["POST"])
def api_refit():
    """Re-generate only the per-range figures (line/scatter/fit) with new peaks.

    No re-scan; all other outputs (denoised, sum curves, full-range, Excel) stay
    untouched. In multi-folder mode every subfolder's range figures are
    refreshed (norm_cache is keyed by subfolder name).
    """
    cache_all = STATE.get("norm_cache") or {}
    if not any(cache_all.values()):
        return jsonify({"error": "Run Process first"}), 400
    d = request.get_json(silent=True) or {}
    try:
        peaks_hint = [float(p) for p in d.get("peaks", []) if p] or None
    except (TypeError, ValueError):
        peaks_hint = None
    ranges = [(int(a), int(b)) for a, b in (d.get("ranges") or []) if a < b]
    folders_map = STATE.get("folders", {})
    refs_map = STATE.get("refs", {})
    images = []
    from sfg_processor import _set_nature_style, _plot_nature
    import pandas as pd
    try:
        _set_nature_style()
        for fname, cache in cache_all.items():
            fpath = folders_map.get(fname) or STATE.get("folder", "")
            ref = refs_map.get(fname) or d.get("ref") or STATE.get("ref", "ref")
            out_dir = os.path.join(fpath, "processed")
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
            pattern = "*_[0-9]*_[0-9]*_fit.png"
            for p in sorted(glob.glob(os.path.join(out_dir, pattern))):
                images.append({"folder": fname, "file": os.path.basename(p)})
        return jsonify({"images": images, "folder": STATE.get("folder", "")})
    except Exception as e:  # pragma: no cover
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def api_status():
    # norm_cache is bulky and only used server-side — keep it out of the poll
    return jsonify({k: v for k, v in STATE.items() if k != "norm_cache"})


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
    """Serve a figure from the cached output folder(s) by ASCII filename.

    Avoids putting the (possibly Chinese) folder path in the URL query string,
    which mangles non-ASCII characters. The folder is resolved server-side:
    ``folder`` names a processed subfolder (multi-folder mode); without it the
    single-experiment folder is used.
    """
    name = request.args.get("name", "")
    fname = request.args.get("folder", "")
    if not name or "/" in name or "\\" in name or "/" in fname or "\\" in fname:
        abort(404)
    if fname:
        base = STATE.get("folders", {}).get(fname)
    else:
        base = STATE.get("folder", "")
    if not base:
        abort(404)
    fp = os.path.join(base, "processed", name)
    if not os.path.isfile(fp):
        abort(404)
    return send_file(fp)


@app.route("/api/open", methods=["POST"])
def api_open():
    d = request.get_json(silent=True) or {}
    folder = d.get("folder", "")
    # single-experiment runs put every output in <folder>/processed — jump
    # straight to it; multi-folder runs open the parent folder (each
    # subfolder carries its own processed/). Mode comes from the request,
    # falling back to STATE so post-refit calls (which omit it) still work.
    if folder and (d.get("mode") or STATE.get("mode")) == "single":
        processed = os.path.join(folder, "processed")
        if os.path.isdir(processed):
            folder = processed
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
