# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.4.0] — 2026-08-27

### Added
- **Multi-folder batch mode** — point the tool at a parent folder holding one
  experiment per subfolder. Each subfolder's reference is auto-detected
  (`quartz` preferred, changeable per folder), and every subfolder gets its own
  `processed/` output. Folders without a reference + test sample are skipped
  and reported. A stray notes/readme `.txt` in the parent no longer flips
  detection (only parseable data files count). Single-experiment folders keep
  working exactly as before.
- **Wavenumber-matched normalisation** — when a test sample was measured at
  wavenumbers the reference lacks, those wavenumbers are excluded from the
  normalisation (original data and all existing Excel sheets are untouched; a
  warning is surfaced in the UI). Duplicate sweeps of the same wavenumber are
  paired 1:1 between sample and reference so both sides cover the same sweeps;
  the unpaired excess is dropped with a warning. A final `Matched_norm` sheet
  collects the IR wavenumber axis plus each sample's matched sum and
  normalised values.
- **Cancel button** — the run button becomes ✕ Cancel while processing;
  cancellation is checked between stages, per sample, and between fit
  multi-starts, so even a slow fit stops within moments. Folders finished
  before the cancel keep their results visible (gallery, re-fit, output
  folder button).
- **Bilingual UI (EN / 中文)** — one-click language toggle; every label,
  toast, and the built-in help guide are translated.

### Changed
- **χ² fit and cosmic-ray removal both default OFF** — the two slower /
  optional steps are now explicit switches (fit adds the peak table + fit
  figures; cosmic cleans spike artefacts). The peak-centres input appears
  directly under the fit switch only when it is on.
- Gallery shows fit figures when χ² fit is on, scatter figures otherwise;
  in multi-folder mode thumbnails are grouped per subfolder.
- Headers unified: `Setup` / `Output` columns, same typography.

### Fixed
- Single-experiment failures are reported as errors again (not "Done · 1
  skipped"); in multi-folder mode a bad folder still doesn't stop the rest.
- Process-start errors (400/409) are shown instead of silently redisplaying
  the previous run's result; clicking Process right after editing the folder
  path now waits for the re-scan instead of submitting the previous folder's
  mode/reference.

## [1.3.0] — 2026-07-12

### Added
- **Physically-correct χ⁽²⁾ fit** — fits
  `I = |χ_NR·e^{iφ} + Σ A_q/(ω_q-ω-iΓ_q)|²` (complex χ summed then modulus
  squared, preserving non-resonant interference), multi-start, best-R².
  Peak table (centre / FWHM / amplitude / area / error) exported to Excel.
- **Iterative Re-fit** — re-fit cached data with new peak centres instantly
  (no re-scan); refine until it looks right. Manual peak-centre input.
- **Structured `processed/` output** — every run writes denoised + sum-curve +
  full-range (line & scatter) + per-range (line / scatter / fit) figures and
  the Excel workbook into a dedicated `processed/` subfolder.
- **Cosmic-ray removal** — moving-median spike cleaning on the normalised
  spectrum (on by default).
- **GitHub links in the footer** — open the repo / Releases in the system
  browser.
- **Adaptive window** — sizes to the screen; full-height layout keeps the
  footer always visible (columns scroll internally).

### Changed
- **Two-column UI** — controls left, results right; no page scrolling.
- Axis labels use Unicode `cm⁻¹` (DejaVu Sans) — natural superscript, no tofu.
- README showcase = clean water line chart (20260324 data).

### Removed
- `.ngs` support — reads `.txt` exports only (UI, docs, core).
- Plot-style dropdown — line / scatter / fit are all generated automatically.

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
