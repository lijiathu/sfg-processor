<div align="center">

# SFG Processor

**A desktop tool for batch Sum-Frequency Generation (SFG) vibrational spectroscopy data processing.**

Read native `.ngs` instrument files or `.txt` exports · auto-detect reference & samples · background subtraction · reference normalisation · publication-style scatter-with-fit figures.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Status](https://img.shields.io/badge/status-v1.0.0-success.svg)

**English** · [简体中文](README.zh-CN.md)

</div>

---

<p align="center">
  <img src="docs/img/spectrum_example.png?v=3" width="560" alt="Example normalised SFG spectrum with scatter points and a smooth fit">
</p>

<p align="center"><em>Example output — normalised water O–H stretch SFG spectrum (3100–3800 cm⁻¹), experimental scatter points with a Savitzky–Golay fit, journal-ready style.</em></p>

---

## ✨ Features

- **Reads `.ngs` directly** — parses the native `NGSNextGen` binary format, so you no longer need to export `.txt` files. If both exist, `.txt` takes precedence.
- **One-click batch processing** — point it at a single experiment folder. It recursively finds every sample, matches each `NoVis` background, and normalises all test samples against **one shared reference** (e.g. quartz). No more copying reference files around.
- **Publication-grade figures** — scatter points + smooth fit curve, Helvetica typography, thin axes, no grid. Y-axis auto-scales to the fit, so a single noise spike can't squash the figure.
- **Always-on full-range figure** — every run emits a full-range normalised plot, plus one zoomed plot for each wavenumber window you select.
- **Refined interface** — a clean web UI with a native folder picker, live progress bar, and an inline result gallery.
- **Standalone executable** — package it as a single Windows `.exe`; recipients need no Python.

## 📦 Installation

### Option A — Standalone executable (no Python required)

1. Download `SFG_Processor.exe` from the [latest Release](../../releases).
2. Double-click to run. A browser window opens automatically.

### Option B — Run from source

```bash
git clone https://github.com/<your-user>/sfg-processor.git
cd sfg-processor
pip install -r requirements.txt
python sfg_app.py
```

Then open the URL printed in the console (default <http://127.0.0.1:5127>).

## 🚀 Usage

1. Click **选择目录** and pick your experiment folder.
2. The tool scans and previews every detected sample — the reference is auto-selected (`quartz` if present) and you can change it in the dropdown.
3. Adjust the visible-light wavelength and add/remove zoomed wavenumber windows as needed.
4. Click **处理并出图**. When the progress bar finishes, the gallery shows the figures and the Excel workbook is ready in the same folder.

### Output (written into your data folder)

| File | Content |
|------|---------|
| `processed_SFG.xlsx` | AllData · per-sample denoised · per-sample normalised sheets |
| `{sample}_normalized_full.png` | Full-range normalised figure (always produced) |
| `{sample}_normalized_{min}_{max}.png` | One zoomed figure per selected window |
| `{sample}_denoised.png` | Per-wavenumber denoised components |

## 🧪 Try it on the bundled example

A tiny synthetic dataset ships under [`example_data/`](example_data):

```bash
python -c "from sfg_processor import process_experiment; process_experiment('example_data','quartz',x_ranges=[(3000,3800)])"
```

…or just run the app and point it at the `example_data` folder.

## 🗂 File-naming convention

Files are parsed automatically as `{sample}_{wavenumber}_{flags}.txt` (or `.ngs`):

| File | Sample | Wavenumber | Note |
|------|--------|------------|------|
| `quartz_3200_Purge.txt` | quartz | 3200 | reference signal |
| `quartz_3200_Purge_NoVis.txt` | quartz | 3200 | reference background |
| `Al2O3Si-Water_3400_Purge.txt` | Al2O3Si-Water | 3400 | test signal |
| `sample_water_3400_Purge_NoVis.txt` | sample_water | 3400 | test background |

- The **first purely-numeric token** is the wavenumber; everything before it is the sample name (underscores and hyphens allowed).
- A filename containing `NoVis` is treated as the background for that sample/wavenumber.
- One reference sample can normalise many test samples in the same folder.

## 🏗 Build the executable yourself

```bash
build.bat
```

Produces `dist/SFG_Processor.exe` (PyInstaller, single-file, `--windowed`).

## 🧱 Project layout

```
sfg-processor/
├── sfg_processor.py     # core logic (pure, no GUI) — parsing, NGS reader, denoise, normalise, plotting
├── sfg_app.py           # Flask backend + native folder picker + job status
├── frontend/
│   └── index.html       # self-contained interface (HTML/CSS/JS)
├── test_sfg_processor.py# unit tests
├── example_data/        # tiny synthetic dataset to try the pipeline
├── build.bat            # PyInstaller build script
├── requirements.txt
└── docs/img/            # README screenshots
```

## 🔬 How it works

```
.ngs / .txt  →  recursive scan + filename parse
            →  SFG wavelength  →  IR wavenumber (ν = 1e7·(1/λ_SFG − 1/λ_vis))
            →  subtract matching NoVis background
            →  sum denoised components per sample
            →  normalise:  sample_sum / reference_sum
            →  Excel workbook + publication figures (scatter + Savitzky–Golay fit)
```

## ✅ Tests

```bash
python -m pytest -q
```

## 📜 License

[MIT](LICENSE) © Li Jia

## 📖 Citing

If this tool helps your research, please cite it — see [CITATION.cff](CITATION.cff).

## 🤝 Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
