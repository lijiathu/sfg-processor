"""API-layer tests (Flask test client): scan mode detection, multi-folder
processing, cancel endpoint, /img folder resolution."""

import os
import time

import pytest

from sfg_app import app, STATE
from test_sfg_processor import _make_experiment, _write_spectrum


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_state():
    STATE.update(current=0, total=5, message="Ready", done=True, busy=False,
                 error=None, result=None, cancelled=False,
                 cancel_requested=False, mode="single", folders={},
                 norm_cache={})
    yield


def _wait_done(client, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get("/api/status").get_json()
        if s["done"]:
            return s
        time.sleep(0.2)
    raise TimeoutError("processing did not finish")


class TestScanModes:
    def test_single_mode_when_folder_has_direct_txt(self, client, tmp_path):
        _make_experiment(tmp_path)
        r = client.post("/api/scan", json={"folder": str(tmp_path)}).get_json()
        assert r["mode"] == "single"
        assert set(r["samples"]) == {"quartz", "water"}
        assert r["default"] == "quartz"

    def test_multi_mode_when_only_subfolders_have_txt(self, client, tmp_path):
        for name, samples in (("3200", ("quartz", "water")),
                              ("3400", ("quartz", "Au"))):
            sub = tmp_path / name
            sub.mkdir()
            _make_experiment(sub, samples=samples)
        (tmp_path / "onlyone").mkdir()
        _make_experiment(tmp_path / "onlyone", samples=("water",))
        r = client.post("/api/scan", json={"folder": str(tmp_path)}).get_json()
        assert r["mode"] == "multi"
        folders = {f["name"]: f for f in r["folders"]}
        assert set(folders) == {"3200", "3400", "onlyone"}
        assert folders["3200"]["default"] == "quartz"
        assert folders["3200"]["ok"] is True
        assert folders["onlyone"]["ok"] is False  # single sample → no reference

    def test_stray_txt_in_parent_keeps_multi_mode(self, client, tmp_path):
        """A notes/readme .txt in the parent must not flip detection to single
        (merged-experiment) mode — only parseable data files count."""
        sub = tmp_path / "3200"
        sub.mkdir()
        _make_experiment(sub, samples=("quartz", "water"))
        (tmp_path / "readme.txt").write_text("notes only, no data columns")
        r = client.post("/api/scan", json={"folder": str(tmp_path)}).get_json()
        assert r["mode"] == "multi"
        assert r["folders"][0]["name"] == "3200"

    def test_scan_error_on_missing_folder(self, client, tmp_path):
        r = client.post("/api/scan",
                        json={"folder": str(tmp_path / "nope")}).get_json()
        assert "error" in r


class TestMultiFolderProcess:
    def test_outputs_written_into_each_subfolder(self, client, tmp_path):
        for name, samples in (("3200", ("quartz", "water")),
                              ("3400", ("quartz", "Au"))):
            sub = tmp_path / name
            sub.mkdir()
            _make_experiment(sub, samples=samples)
        body = {
            "mode": "multi", "folder": str(tmp_path),
            "vis": 1030, "ranges": [[3100, 3700]],
            "cosmic": False, "peaks": [], "fit": False,
            "folders": [
                {"name": "3200", "ref": "quartz"},
                {"name": "3400", "ref": "quartz"},
            ],
        }
        assert client.post("/api/process", json=body).status_code == 200
        s = _wait_done(client)
        assert s["error"] is None
        for name in ("3200", "3400"):
            out = tmp_path / name / "processed"
            assert (out / "processed_SFG.xlsx").is_file()
            assert (out / "water_3100_3700_scatter.png").is_file() or \
                   (out / "Au_3100_3700_scatter.png").is_file()
        # gallery items carry their subfolder so the UI can group them
        result = s["result"]
        assert all("folder" in it and "file" in it for it in result["images"])
        assert {it["folder"] for it in result["images"]} == {"3200", "3400"}
        # /img resolves a figure by subfolder name
        it = result["images"][0]
        resp = client.get("/img", query_string={"name": it["file"],
                                                "folder": it["folder"]})
        assert resp.status_code == 200
        # no parent-level combined output
        assert not (tmp_path / "processed").exists()

    def test_folder_without_reference_is_skipped(self, client, tmp_path):
        good = tmp_path / "3200"; good.mkdir()
        _make_experiment(good, samples=("quartz", "water"))
        bad = tmp_path / "onlysample"; bad.mkdir()
        _make_experiment(bad, samples=("water",))
        body = {
            "mode": "multi", "folder": str(tmp_path),
            "vis": 1030, "ranges": [[3100, 3700]],
            "cosmic": False, "peaks": [], "fit": False,
            "folders": [{"name": "3200", "ref": "quartz"},
                        {"name": "onlysample", "ref": "water"}],
        }
        assert client.post("/api/process", json=body).status_code == 200
        s = _wait_done(client)
        assert s["error"] is None
        assert (tmp_path / "3200" / "processed" / "processed_SFG.xlsx").is_file()
        assert not (tmp_path / "onlysample" / "processed").exists()
        assert any("onlysample" in sk for sk in s["result"].get("skipped", []))

    def test_cancelled_multi_run_keeps_finished_folders(self, client, tmp_path):
        """Cancelling mid-run must keep the folders that already finished:
        partial gallery, /img resolution and re-fit state stay usable."""
        for name in ("A", "B"):
            sub = tmp_path / name
            sub.mkdir()
            _make_experiment(sub, samples=("quartz", "water"))
        body = {
            "mode": "multi", "folder": str(tmp_path),
            "vis": 1030, "ranges": [[3100, 3700]],
            "cosmic": False, "peaks": [], "fit": False,
            "folders": [{"name": "A", "ref": "quartz"},
                        {"name": "B", "ref": "quartz"}],
        }
        assert client.post("/api/process", json=body).status_code == 200
        # cancel as soon as the second folder starts
        deadline = time.time() + 30
        while time.time() < deadline:
            msg = client.get("/api/status").get_json()["message"]
            if msg.startswith("[2/2]"):
                client.post("/api/cancel")
                break
            time.sleep(0.05)
        s = _wait_done(client)
        assert s["cancelled"] is True
        assert s["result"] is not None
        assert {it["folder"] for it in s["result"]["images"]} == {"A"}
        assert (tmp_path / "A" / "processed" / "processed_SFG.xlsx").is_file()
        assert "A" in s["folders"]
        it = s["result"]["images"][0]
        assert client.get("/img", query_string={"name": it["file"],
                                                "folder": it["folder"]}).status_code == 200


class TestCancelEndpoint:
    def test_cancel_when_idle_returns_conflict(self, client):
        assert client.post("/api/cancel").status_code == 409

    def test_cancel_sets_flag_while_busy(self, client):
        STATE.update(busy=True, done=False)
        assert client.post("/api/cancel").status_code == 200
        assert STATE["cancel_requested"] is True


class TestSingleProcessGallery:
    def test_fit_off_gallery_uses_scatter_figures(self, client, tmp_path):
        _make_experiment(tmp_path)
        body = {"folder": str(tmp_path), "ref": "quartz", "vis": 1030,
                "ranges": [[3100, 3700]], "cosmic": False, "peaks": [],
                "fit": False}
        assert client.post("/api/process", json=body).status_code == 200
        s = _wait_done(client)
        assert s["error"] is None
        files = [it["file"] for it in s["result"]["images"]]
        assert any("scatter" in f for f in files)
        assert not any("fit" in f for f in files)

    def test_dropped_wavenumber_surfaced_in_notes(self, client, tmp_path):
        _make_experiment(tmp_path, samples=("quartz", "water"), waves=(3200, 3400))
        _write_spectrum(tmp_path / "water_3600_Purge.txt")
        _write_spectrum(tmp_path / "water_3600_Purge_NoVis.txt", scale=0.1)
        body = {"folder": str(tmp_path), "ref": "quartz", "vis": 1030,
                "ranges": [[3100, 3700]], "cosmic": False, "peaks": [],
                "fit": False}
        assert client.post("/api/process", json=body).status_code == 200
        s = _wait_done(client)
        assert s["error"] is None
        notes = s["result"].get("notes", [])
        assert any("3600" in n and "excluded" in n for n in notes)

    def test_single_mode_failure_surfaces_as_error(self, client, tmp_path):
        """Single-mode failures must set error/message=Failed, not masquerade
        as 'Done · 1 skipped'."""
        body = {"folder": str(tmp_path / "nope"), "ref": "quartz", "vis": 1030,
                "ranges": [[3100, 3700]], "cosmic": False, "peaks": [],
                "fit": False}
        assert client.post("/api/process", json=body).status_code == 200
        s = _wait_done(client)
        assert s["error"] is not None
        assert s["message"] == "Failed"
        assert s["result"] is None
