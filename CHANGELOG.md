# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-05-22

### Added
- **Direct `.ngs` reading** — parses the native NGSNextGen v1 binary format
  (wavelength + intensity float32 arrays), so `.txt` export is no longer
  required. When both exist for a sample, `.txt` is preferred.
- **Batch auto-detection** — point the tool at one experiment folder; it
  recursively finds reference and test samples, matches background (`NoVis`)
  files, and normalises every test sample against one shared reference.
- **Publication-style figures** — scatter points + smooth Savitzky–Golay fit,
  Helvetica, thin axes, auto Y-scale driven by the fit. Always emits a
  full-range figure plus one zoomed figure per selected wavenumber window.
- **Refined web UI** (Flask + single-file frontend) with native folder
  picker, live progress, and a result gallery.
- Standalone Windows executable build via PyInstaller (`build.bat`).
- Unit-test suite (`test_sfg_processor.py`) and a bundled synthetic
  `example_data/` dataset.

### Changed
- Replaced the per-sample-folder manual workflow (copy reference, edit path,
  re-run) with one-click batch processing.
- Y-axis now auto-scales to the smoothed fit, so a single noise spike can no
  longer squash the figure.

### Fixed
- File-name parser now handles sample names containing underscores
  (e.g. `sample_water_3200_Purge`).

## [0.1.0] — 2025-11-23
- Original single-folder CLI script (`profess_sfg_Pro.py`): `.txt`-only,
  one sample per run, manual `folder_path` editing.
