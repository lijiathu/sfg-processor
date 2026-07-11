import pytest
import numpy as np
from sfg_processor import (
    parse_filename, wavelength_to_ir, scan_folder, read_sfg_data, get_sample_names
)


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


def _placeholder_end_of_file():
    pass
