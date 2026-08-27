import inspect
import os
import glob

import pytest
import numpy as np
from sfg_processor import (
    parse_filename, wavelength_to_ir, scan_folder, read_sfg_data, get_sample_names,
    process_experiment, scan_experiment_folders, JobCancelled, _multi_peak_fit
)


def _write_spectrum(fpath, vis=1030.0, lo=3000, hi=3800, n=120, scale=1.0):
    """Write a synthetic two-column .txt (SFG nm, intensity) covering [lo, hi] cm⁻¹."""
    ir = np.linspace(lo, hi, n)
    sfg_nm = 1.0 / ((1.0 / vis) + ir * 1e-7)
    y = scale * (1.0 + 0.8 * np.exp(-((ir - 3400.0) ** 2) / (2 * 80.0 ** 2)))
    fpath.write_text("\n".join(f"{a:.4f} {b:.4f}" for a, b in zip(sfg_nm, y)))


def _make_experiment(folder, samples=("quartz", "water"), waves=(3200, 3400, 3600)):
    """Create a minimal experiment folder: sample+background per sample/wavenumber."""
    for s in samples:
        for w in waves:
            _write_spectrum(folder / f"{s}_{w}_Purge.txt", scale=2.0 if s == "quartz" else 1.0)
            _write_spectrum(folder / f"{s}_{w}_Purge_NoVis.txt", scale=0.1)


class TestParseFilename:
    def test_basic_signal(self):
        sample, wave, flags, is_bg = parse_filename("quartz_3200_Purge")
        assert sample == "quartz"
        assert wave == 3200
        assert flags == ["Purge"]
        assert is_bg is False

    def test_novis_background(self):
        sample, wave, flags, is_bg = parse_filename("quartz_3200_Purge_NoVis")
        assert sample == "quartz"
        assert wave == 3200
        assert flags == ["Purge"]
        assert is_bg is True

    def test_sample_with_dash(self):
        sample, wave, flags, is_bg = parse_filename("Al2O3Si-Water_3200_Purge")
        assert sample == "Al2O3Si-Water"
        assert wave == 3200
        assert is_bg is False

    def test_no_flags(self):
        sample, wave, flags, is_bg = parse_filename("quartz_3000")
        assert sample == "quartz"
        assert wave == 3000
        assert flags == []
        assert is_bg is False

    def test_complex_flags(self):
        sample, wave, flags, is_bg = parse_filename("Al2O3Si-Water_3200_Purge_NoVis")
        assert sample == "Al2O3Si-Water"
        assert wave == 3200
        assert "Purge" in flags
        assert is_bg is True

    def test_sample_name_with_underscore(self):
        # sample names containing underscores must still parse (no digits in name)
        sample, wave, flags, is_bg = parse_filename("sample_water_3200_Purge")
        assert sample == "sample_water"
        assert wave == 3200
        assert flags == ["Purge"]
        assert is_bg is False

    def test_sample_name_with_underscore_and_novis(self):
        sample, wave, flags, is_bg = parse_filename("sample_water_3400_Purge_NoVis")
        assert sample == "sample_water"
        assert wave == 3400
        assert is_bg is True

    def test_invalid_filename_raises(self):
        with pytest.raises(ValueError):
            parse_filename("no_wave_here")

    def test_single_part_raises(self):
        with pytest.raises(ValueError):
            parse_filename("justoneword")


class TestWavelengthToIr:
    def test_conversion(self):
        result = wavelength_to_ir(np.array([800.0]), 1030.0)
        expected = 1e7 * (1.0 / 800.0 - 1.0 / 1030.0)
        assert np.isclose(result[0], expected, rtol=1e-5)

    def test_array_input(self):
        sfg = np.array([800.0, 780.0, 760.0])
        result = wavelength_to_ir(sfg, 1030.0)
        assert len(result) == 3
        assert result[2] > result[1] > result[0]

    def test_default_vis(self):
        result = wavelength_to_ir(np.array([800.0]))
        expected = 1e7 * (1.0 / 800.0 - 1.0 / 1030.0)
        assert np.isclose(result[0], expected, rtol=1e-5)


class TestScanFolder:
    def test_finds_txt_files(self, tmp_path):
        (tmp_path / "quartz_3200_Purge.txt").write_text("1.0 100\n2.0 200\n")
        (tmp_path / "quartz_3200_Purge_NoVis.txt").write_text("1.0 50\n2.0 100\n")
        result = scan_folder(str(tmp_path))
        stems = [r["stem"] for r in result]
        assert "quartz_3200_Purge" in stems
        assert "quartz_3200_Purge_NoVis" in stems
        assert len(result) == 2

    def test_recursive_scan(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "sample_3200_Purge.txt").write_text("1.0 100\n")
        result = scan_folder(str(tmp_path))
        assert len(result) == 1
        assert result[0]["sample"] == "sample"

    def test_detects_all_samples(self, tmp_path):
        (tmp_path / "quartz_3200_Purge.txt").write_text("1.0 100\n")
        (tmp_path / "water_3200_Purge.txt").write_text("1.0 100\n")
        (tmp_path / "Au_3200_PPP.txt").write_text("1.0 100\n")
        result = scan_folder(str(tmp_path))
        samples = {r["sample"] for r in result}
        assert samples == {"quartz", "water", "Au"}

    def test_empty_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scan_folder(str(tmp_path))

    def test_get_sample_names(self, tmp_path):
        (tmp_path / "quartz_3200.txt").write_text("1.0 100\n")
        (tmp_path / "quartz_3400.txt").write_text("1.0 100\n")
        (tmp_path / "water_3200.txt").write_text("1.0 100\n")
        result = scan_folder(str(tmp_path))
        names = get_sample_names(result)
        assert "quartz" in names
        assert "water" in names


class TestReadSfgData:
    def test_reads_two_columns(self, tmp_path):
        fpath = tmp_path / "test.txt"
        fpath.write_text("799.3 650\n799.0 645\n798.7 660\n")
        df = read_sfg_data(str(fpath))
        assert len(df) == 3
        assert "SFG_nm" in df.columns
        assert "Intensity" in df.columns
        assert df["SFG_nm"].iloc[0] == pytest.approx(799.3)

    def test_handles_whitespace(self, tmp_path):
        fpath = tmp_path / "test.txt"
        fpath.write_text("799.3   650\n799.0   645\n")
        df = read_sfg_data(str(fpath))
        assert len(df) == 2


class TestProcessExperiment:
    def _out(self, tmp_path):
        return tmp_path / "processed"

    def test_basic_run_produces_outputs(self, tmp_path):
        _make_experiment(tmp_path)
        excel = process_experiment(str(tmp_path), "quartz",
                                   x_ranges=[(3100, 3700)])
        assert os.path.isfile(excel)
        out = self._out(tmp_path)
        assert (out / "water_denoised.png").is_file()
        assert (out / "water_full_line.png").is_file()
        assert (out / "water_3100_3700_line.png").is_file()
        assert (out / "water_3100_3700_scatter.png").is_file()

    def test_do_fit_false_skips_fit_outputs(self, tmp_path):
        _make_experiment(tmp_path)
        excel = process_experiment(str(tmp_path), "quartz",
                                   x_ranges=[(3100, 3700)], do_fit=False)
        out = self._out(tmp_path)
        assert not glob.glob(str(out / "*_fit.png"))
        import pandas as pd
        xl = pd.ExcelFile(excel)
        assert not [s for s in xl.sheet_names if s.endswith("_peaks")]

    def test_do_fit_true_produces_fit_figure(self, tmp_path):
        _make_experiment(tmp_path)
        process_experiment(str(tmp_path), "quartz",
                           x_ranges=[(3100, 3700)], do_fit=True)
        assert (self._out(tmp_path) / "water_3100_3700_fit.png").is_file()

    def test_defaults_fit_and_cosmic_off(self):
        p = inspect.signature(process_experiment).parameters
        assert p["do_fit"].default is False
        assert p["cosmic"].default is False


class TestWavenumberMatching:
    def test_mismatched_wavenumber_excluded(self, tmp_path):
        """Sample has 3200/3400/3600, reference only 3200/3400 → 3600 is
        dropped from the normalisation; a final Matched_norm sheet carries
        the per-sample matched sum + normalised values."""
        import pandas as pd
        _make_experiment(tmp_path, samples=("quartz", "water"), waves=(3200, 3400))
        _write_spectrum(tmp_path / "water_3600_Purge.txt")
        _write_spectrum(tmp_path / "water_3600_Purge_NoVis.txt", scale=0.1)
        with pytest.warns(UserWarning, match="3600"):
            excel = process_experiment(str(tmp_path), "quartz",
                                       x_ranges=[(3100, 3700)])
        xl = pd.ExcelFile(excel)
        assert xl.sheet_names[-1] == "Matched_norm"
        m = xl.parse("Matched_norm")
        # 4-column layout: wave axis · sample sum · reference sum · normalised
        assert list(m.columns) == ["IR_wavenumber_cm-1", "water_sum_matched",
                                   "quartz_sum_matched", "water_normalized"]
        # matched sum == full sum minus the unmatched 3600 component
        w = xl.parse("water")
        expected = w["sum"] - w["3600"]
        assert np.allclose(m["water_sum_matched"].values, expected.values,
                           equal_nan=True)
        # reference matched all its own wavenumbers → its sum is unchanged
        assert np.allclose(m["quartz_sum_matched"].values,
                           xl.parse("quartz")["sum"].values, equal_nan=True)

    def test_full_match_keeps_sum_equal(self, tmp_path):
        import pandas as pd
        _make_experiment(tmp_path)  # quartz + water, same wavenumbers
        excel = process_experiment(str(tmp_path), "quartz",
                                   x_ranges=[(3100, 3700)])
        xl = pd.ExcelFile(excel)
        m = xl.parse("Matched_norm")
        w = xl.parse("water")
        assert np.allclose(m["water_sum_matched"].values, w["sum"].values,
                           equal_nan=True)
        assert np.allclose(m["water_normalized"].values,
                           xl.parse("water_normalized")["normalized_sum"].values,
                           equal_nan=True)

    def test_second_test_sample_gets_suffixed_reference_column(self, tmp_path):
        """Two test samples against one reference: the first keeps the plain
        reference column, the second gets a sample-suffixed one (its sweep
        pairing may differ) instead of a merge collision."""
        import pandas as pd
        _make_experiment(tmp_path, samples=("quartz", "water", "oil"))
        excel = process_experiment(str(tmp_path), "quartz",
                                   x_ranges=[(3100, 3700)])
        xl = pd.ExcelFile(excel)
        m = xl.parse("Matched_norm")
        assert "quartz_sum_matched" in m.columns  # first sample keeps the plain name
        suffixed = [c for c in m.columns if c.startswith("quartz_sum_matched_for_")]
        assert len(suffixed) == 1  # second sample gets its own, no collision
        assert "water_normalized" in m.columns and "oil_normalized" in m.columns
        # same sweep coverage here → both reference columns show the same values
        assert np.allclose(m[suffixed[0]].values,
                           m["quartz_sum_matched"].values, equal_nan=True)

    def test_no_overlap_skips_normalisation(self, tmp_path):
        import pandas as pd
        _make_experiment(tmp_path, samples=("quartz",), waves=(3200,))
        _write_spectrum(tmp_path / "water_3400_Purge.txt")
        _write_spectrum(tmp_path / "water_3400_Purge_NoVis.txt", scale=0.1)
        with pytest.warns(UserWarning, match="no wavenumber overlap"):
            excel = process_experiment(str(tmp_path), "quartz",
                                       x_ranges=[(3100, 3700)])
        xl = pd.ExcelFile(excel)
        assert "water_normalized" not in xl.sheet_names
        assert "Matched_norm" not in xl.sheet_names

    def test_duplicate_wave_sweeps_paired_not_pooled(self, tmp_path):
        """A second sweep at an already-covered wavenumber must not skew the
        normalisation: sweeps are paired 1:1, the unpaired excess is dropped
        with a warning (pooled sums would inflate the ratio ~1.5x here)."""
        import pandas as pd
        _make_experiment(tmp_path, samples=("quartz", "water"), waves=(3200, 3400))
        _write_spectrum(tmp_path / "water_3200_Purge_2.txt", scale=1.0)
        _write_spectrum(tmp_path / "water_3200_Purge_2_NoVis.txt", scale=0.1)
        with pytest.warns(UserWarning, match="same sweeps"):
            excel = process_experiment(str(tmp_path), "quartz",
                                       x_ranges=[(3100, 3700)])
        xl = pd.ExcelFile(excel)
        m = xl.parse("Matched_norm")
        w = xl.parse("water")
        # matched sum = full sum minus the unpaired second 3200 sweep
        expected = w["sum"] - w["3200_1"]
        assert np.allclose(m["water_sum_matched"].values, expected.values,
                           equal_nan=True)
        # ratio stays the per-sweep value (0.9k / 1.9k with k sweeps a side)
        assert np.nanmean(m["water_normalized"].values) == pytest.approx(
            1.8 / 3.8, rel=1e-4)

    def test_cancel_check_raises_job_cancelled(self, tmp_path):
        _make_experiment(tmp_path)
        with pytest.raises(JobCancelled):
            process_experiment(str(tmp_path), "quartz", cancel_check=lambda: True)


class TestMultiPeakFitCancel:
    def test_cancel_between_starts_raises(self):
        ir = np.linspace(3100, 3700, 80)
        y = 1.0 + 0.8 * np.exp(-((ir - 3400.0) ** 2) / (2 * 60.0 ** 2))
        calls = {"n": 0}

        def slow_cancel():
            calls["n"] += 1
            return calls["n"] > 1  # allow the first start, cancel before the second

        with pytest.raises(JobCancelled):
            _multi_peak_fit(ir, y, cancel_check=slow_cancel)


class TestScanExperimentFolders:
    def test_returns_subfolders_with_data(self, tmp_path):
        sub1 = tmp_path / "3200"; sub1.mkdir()
        sub2 = tmp_path / "3400"; sub2.mkdir()
        empty = tmp_path / "empty"; empty.mkdir()
        _make_experiment(sub1, samples=("quartz", "water"))
        _make_experiment(sub2, samples=("quartz", "Au"))
        entries = scan_experiment_folders(str(tmp_path))
        assert [e["name"] for e in entries] == ["3200", "3400"]
        by_name = {e["name"]: e for e in entries}
        assert set(by_name["3200"]["samples"]) == {"quartz", "water"}
        assert set(by_name["3400"]["samples"]) == {"quartz", "Au"}
        assert os.path.isdir(by_name["3200"]["path"])

    def test_no_subfolders_returns_empty(self, tmp_path):
        assert scan_experiment_folders(str(tmp_path)) == []


def _placeholder_end_of_file():
    pass
