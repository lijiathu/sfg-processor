# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.0] — 2026-07-11

### Added
- **Plot style selector** — choose Line / Scatter / Scatter+Fit per run
  (replaces the single curve-fit toggle).
- **Cosmic-ray removal** — moving-median spike detection on the normalised
  spectrum (on by default); cleans sharp artefacts before plotting and export.

### Changed
- README showcase figure is now a clean (cosmic-ray-removed) water line chart.

## [1.2.0] — 2026-06-18

### Added
- **Optional curve fit** — new "Curve fit" switch in the UI (**off by
  default**); turn it on to overlay a smooth fit on the scatter points.

### Changed
- **Show-all-points Y-scaling** — Y-axis starts at 0 and is scaled from the
  raw data maximum so every point stays visible (no clipping).
- **Cleaner axis labels** — `Wavenumber (cm⁻¹)` via mathtext (no more tofu
  boxes from missing Unicode glyphs) and `SFG signal (a.u.)`.
- **Default wavenumber window** — one window (3000–3750) is pre-filled.
- **UI trim** — removed the redundant Curve-fit caption, the header meta
  block, the two-tone card accent bar, and dropped `.ngs` from the footer
  tagline; lede order is `.txt / .ngs`.

### Fixed
- Curve-fit toggle knob misalignment (real span instead of `::before`).

## [1.1.0] — 2026-06-17

### Added
- **Native desktop window** — the app now opens as a standalone window
  (via pywebview / Edge WebView2) instead of a system browser tab. No address
  bar, no browser; closing the window exits the app.

### Changed
- **English-only interface** — all UI labels, toasts, and backend messages
  are now in English (bilingual README still ships both languages).
- **Wavenumber windows start empty** — no preset ranges; the user adds only
  the windows they want via "+ Add window". An empty selection still produces
  the full-range figure.
- **Water example dataset** — `example_data/` regenerated as a realistic
  water O–H stretch spectrum; README screenshot updated (3100–3800 cm⁻¹).

### Fixed
- File-name parser now handles sample names containing underscores
  (e.g. `water_3200_Purge`); covered by new unit tests.

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
