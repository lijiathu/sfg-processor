import os
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_filename(fn_stem):
    """
    Parse SFG filename: {sample}_{wavenumber}_{flag1}_{flag2}_...

    The sample name itself may contain underscores (e.g. ``sample_water``),
    so we scan the tokens left-to-right and treat the FIRST token that is
    purely numeric as the wavenumber; everything before it is the sample
    name, everything after it is flags.

    Returns: (sample, wavenumber, flags_without_novis, is_background)
    """
    parts = fn_stem.split("_")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse filename: {fn_stem}")
    wave_idx = None
    for i, p in enumerate(parts):
        if p.isdigit():
            wave_idx = i
            break
    if wave_idx is None or wave_idx == 0:
        raise ValueError(f"Cannot parse wavenumber: {fn_stem}")
    sample = "_".join(parts[:wave_idx])
    wave = int(parts[wave_idx])
    flags = parts[wave_idx + 1:]
    is_background = any(f.lower() == "novis" for f in flags)
    other_flags = [f for f in flags if f.lower() != "novis"]
    return sample, wave, other_flags, is_background


def wavelength_to_ir(sfg_nm, lambda_vis_nm=1030.0):
    """Convert SFG wavelength (nm) to IR wavenumber (cm^-1)."""
    sfg = np.array(sfg_nm, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ir_cm1 = 1e7 * ((1.0 / sfg) - (1.0 / lambda_vis_nm))
    return ir_cm1


def scan_folder(folder_path):
    """Recursively scan folder for .txt files, return metadata list."""
    all_txt = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.endswith(".txt"):
                all_txt.append(os.path.join(root, f))
    if not all_txt:
        raise FileNotFoundError("No .txt files found; check the path.")
    meta_list = []
    for fpath in all_txt:
        stem = Path(fpath).stem
        try:
            sample, wave, flags, is_bg = parse_filename(stem)
        except ValueError as e:
            warnings.warn(f"Skipping unparseable file {stem}: {e}")
            continue
        meta_list.append({
            "stem": stem, "path": fpath, "sample": sample,
            "wave": wave, "flags": flags, "is_background": is_bg,
        })
    return meta_list


def get_sample_names(meta_list):
    """Extract unique sample names from metadata."""
    return sorted({m["sample"] for m in meta_list})


def read_sfg_data(fpath):
    """Read a single SFG .txt data file, return DataFrame (SFG_nm, Intensity).

    Two whitespace-separated columns (wavelength, intensity).
    """
    df = pd.read_csv(fpath, sep=r"\s+|\t", header=None, engine="python",
                     names=["SFG_nm", "Intensity"])
    df["SFG_nm"] = pd.to_numeric(df["SFG_nm"], errors="coerce")
    df["Intensity"] = pd.to_numeric(df["Intensity"], errors="coerce")
    return df


def _set_nature_style():
    """Publication (Nature/Science) figure style: Helvetica, thin borders, clean."""
    plt.style.use("default")
    plt.rcParams.update({
        "figure.dpi": 200,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 11,
        "axes.linewidth": 0.9,
        "axes.edgecolor": "#111111",
        "axes.labelcolor": "#111111",
        "axes.labelsize": 12,
        "axes.labelweight": "bold",
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.spines.top": True,
        "axes.spines.right": True,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.major.size": 4,
        "ytick.major.size": 4,
        "xtick.minor.size": 2.5,
        "ytick.minor.size": 2.5,
        "xtick.major.width": 0.9,
        "ytick.major.width": 0.9,
        "xtick.color": "#111111",
        "ytick.color": "#111111",
        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "mathtext.default": "regular",
        "mathtext.fontset": "dejavusans",
    })


def _smooth_fit(x, y):
    """Robust smoothed fit curve through noisy (x, y) data via Savitzky-Golay.

    Returns (x, y_raw, y_fit) sorted ascending, all the same length, on the
    finite (non-NaN) subset. Falls back to a moving average if Savitzky-Golay
    cannot be applied.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(x)
    x, y = x[order], y[order]
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]
    n = len(x)
    if n < 7:
        return x, y, y
    # odd window ~ 15% of points, clamped, must be odd and < n
    window = int(np.clip(round(n * 0.15) | 1, 7, 401))
    if window >= n:
        window = n - 1 if n % 2 == 0 else n - 2
    if window < 7:
        return x, y, y
    try:
        from scipy.signal import savgol_filter
        poly = 3 if window > 4 else 1
        yf = savgol_filter(y, window_length=window, polyorder=poly)
    except Exception:
        k = max(3, window)
        yf = np.convolve(y, np.ones(k) / k, mode="same")
    return x, y, yf


def _multi_peak_fit(x, y, max_peaks=6, peaks_hint=None):
    """Physically-correct SFG fit: I(ω) = |χ_NR·e^{iφ} + Σ A_q/(ω_q-ω-iΓ_q)|².

    Builds the complex χ⁽²⁾ (non-resonant with phase + resonant complex
    Lorentzians), takes the modulus squared — preserving interference (the
    physically correct target, vs. naively adding real Lorentzians to the
    intensity). Multi-start initial guesses; keeps the best-R² result.
    ``peaks_hint`` (list of wavenumbers) fixes the initial centres (manual).
    Returns dict {yfit, comps, table, r2, chi_nr, phi} or None on failure.
    """
    from scipy.signal import find_peaks, savgol_filter
    from scipy.optimize import curve_fit
    x = np.asarray(x, float); y = np.asarray(y, float)
    n = len(x)
    fin = np.isfinite(x) & np.isfinite(y)
    if fin.sum() < 12:
        return None
    x, y = x[fin], y[fin]
    order = np.argsort(x); x, y = x[order], y[order]
    xlo, xhi = float(x[0]), float(x[-1])
    span = xhi - xlo or 1.0
    dx = np.median(np.diff(x)) or (span / n)

    # --- initial peak centres (manual hint or auto-detect) ---
    win = int(np.clip(n // 6 | 1, 5, 101))
    if win >= n:
        win = n - 1 if n % 2 == 0 else n - 2
    try:
        ys = savgol_filter(y, win, 3) if win >= 5 else y
    except Exception:
        ys = y
    base = float(np.nanmedian(ys)); amp = float(np.nanmax(ys) - base) or 1.0
    if peaks_hint:
        idx = np.clip(np.searchsorted(x, np.array(peaks_hint, float)), 1, n - 2)
        centers = [float(x[i]) for i in sorted(set(idx))]
    else:
        pk, _ = find_peaks(ys - base, prominence=amp * 0.06,
                           distance=max(3, int(15 / dx)) if dx else 5)
        if len(pk) > max_peaks:
            pk = pk[np.argsort((ys[pk] - base))[-max_peaks:]]
            pk.sort()
        centers = [float(x[i]) for i in pk]
    if not centers:
        return None
    n_modes = len(centers)

    # --- model: I = |χ_NR·e^{iφ} + Σ A_q/(ω_q-ω-iΓ_q)|² ---
    def sfg_model(w, chi_nr, phi, *params):
        chi = np.full_like(w, chi_nr * np.exp(1j * phi), dtype=complex)
        for q in range(len(params) // 3):
            A, wq, gq = params[3 * q], params[3 * q + 1], params[3 * q + 2]
            chi = chi + A / (wq - w - 1j * gq)
        return np.abs(chi) ** 2

    def make_fit_func(m):
        return lambda w, *p: sfg_model(w, p[0], p[1], *p[2:])

    chi_nr0 = np.sqrt(max(base, 1e-6))
    lb = [0.0, -np.pi]; ub = [np.inf, np.pi]
    for _ in centers:
        lb += [-np.inf, xlo, 1e-3]; ub += [np.inf, xhi, 300.0]

    # --- multi-start guesses, keep best R² ---
    guess_sets = []
    for fac in (0.8, 1.2, 0.5):
        g = [chi_nr0, 0.0]
        for c in centers:
            g += [fac * chi_nr0, c, 50.0]
        guess_sets.append(g)
    for ph in (1.0, -1.5, 2.5):
        g = [chi_nr0, ph]
        for c in centers:
            g += [1.0 * chi_nr0, c, 45.0]
        guess_sets.append(g)

    f = make_fit_func(n_modes)
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) or 1.0
    best = None
    for g in guess_sets:
        try:
            popt, pcov = curve_fit(f, x, y, p0=g, bounds=(lb, ub), maxfev=200000)
        except Exception:
            continue
        yfit = f(x, *popt)
        r2 = 1.0 - float(np.sum((y - yfit) ** 2)) / ss_tot
        if best is None or r2 > best["r2"]:
            best = {"popt": popt, "pcov": pcov, "yfit": yfit, "r2": r2}
    if best is None:
        return None

    popt = best["popt"]; perr = np.sqrt(np.diag(best["pcov"]))
    chi_nr = float(popt[0]); phi = float(popt[1])
    comps = []; table = []
    for q in range(n_modes):
        A, wq, gq = popt[2 + 3 * q], popt[3 + 3 * q], abs(popt[4 + 3 * q])
        # clean per-mode Lorentzian intensity |A/(ωq-ω-iΓ)|² = A²/((ωq-ω)²+Γ²)
        comp = (A * A) / ((wq - x) ** 2 + gq * gq)
        comps.append((float(wq), comp))
        table.append({
            "center_cm-1": round(float(wq), 1),
            "FWHM_cm-1": round(2 * gq, 1),
            "A": round(float(A), 5),
            "gamma_cm-1": round(float(gq), 1),
            "area": round(float(abs(A) * np.pi * gq), 5),
            "err_center": round(float(perr[3 + 3 * q]), 1),
        })
    table.sort(key=lambda r: r["center_cm-1"])
    return {"yfit": best["yfit"], "comps": comps, "table": table,
            "r2": round(best["r2"], 4), "chi_nr": chi_nr, "phi": phi}


def remove_cosmics(y, win=7, thresh=6.0):
    """Detect and replace sharp cosmic-ray spikes.

    Uses a moving-median filter: points whose deviation from the local median
    exceeds ``thresh`` robust sigma (MAD-based) are treated as cosmic spikes and
    replaced by the median. NaNs are preserved (only finite points are cleaned).
    """
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(y)
    if finite.sum() < win * 2:
        return y
    try:
        from scipy.ndimage import median_filter
    except Exception:
        return y
    filled = np.where(finite, y, 0.0)
    med = median_filter(filled, size=win, mode="nearest")
    resid = np.where(finite, y - med, 0.0)
    rfin = resid[finite]
    mad = np.median(np.abs(rfin - np.median(rfin)))
    sigma = 1.4826 * mad if mad > 0 else float(np.std(rfin)) or 0.0
    if sigma <= 0:
        return y
    spike = finite & (np.abs(resid) > thresh * sigma)
    out = y.copy()
    out[spike] = med[spike]
    return out


def smooth_curve(y, frac=0.05):
    """Light Savitzky–Golay smoothing of a (possibly NaN-bearing) curve.

    Smooths only finite segments; NaNs left untouched so gaps are preserved.
    Window ≈ frac of finite-point count (odd, clamped). Reduces point-to-point
    noise without flattening real peaks.
    """
    from scipy.signal import savgol_filter
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(y)
    nfin = int(finite.sum())
    if nfin < 9:
        return y
    idx = np.where(finite)[0]
    yy = y[idx]
    win = int(np.clip(round(nfin * frac) | 1, 5, 101))
    if win >= nfin:
        win = nfin - 1 if nfin % 2 == 0 else nfin - 2
    if win < 5:
        return y
    poly = 3 if win > 4 else 1
    try:
        ys = savgol_filter(yy, win, poly)
    except Exception:
        return y
    out = y.copy()
    out[idx] = ys
    return out


def _plot_nature(norm_df, sample, ref_sample, save_path, xlim=None, mode="fit",
                 peaks_hint=None):
    """Nature-style spectrum.

    mode: 'line' (line only), 'scatter' (points only), 'fit' (points + fit).
    In 'fit' mode a multi-Lorentzian fit is attempted; peak centres are
    annotated and a peak table is returned for export (None otherwise).
    Returns the peak table (list of dicts) or None.
    """
    x = norm_df["IR_wavenumber_cm-1"].values
    y = norm_df["normalized_sum"].values
    if xlim is not None:
        sel = (x >= xlim[0]) & (x <= xlim[1])
    else:
        sel = np.isfinite(x) & np.isfinite(y)
    if sel.sum() < 7:
        return None
    x, y = x[sel], y[sel]
    o = np.argsort(x); x, y = x[o], y[o]

    xs, ys, yf = _smooth_fit(x, y)
    if len(xs) < 7:
        return None

    peak_table = None
    fit_res = _multi_peak_fit(x, y, peaks_hint=peaks_hint) if mode == "fit" else None

    # y-axis starts from 0; upper bound from the raw data so every point shows
    y_top = float(np.nanmax(ys))
    y_hi = y_top + (y_top * 0.06 if y_top > 0 else 1.0)
    y_lo = 0.0

    if xlim is None:
        xlim = (float(xs.min()), float(xs.max()))
        title_range = "full range"
    else:
        title_range = f"{xlim[0]}-{xlim[1]} cm$^{{-1}}$"

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    if mode == "line":
        ax.plot(x, y, color="#1b3a4b", linewidth=1.6, zorder=3)
    else:
        ax.scatter(x, y, s=11, c="#c9ced6", edgecolors="none", alpha=0.85,
                   zorder=2, label="data")
        if mode == "fit":
            if fit_res is not None:
                peak_table = fit_res["table"]
                ax.plot(x, fit_res["yfit"], color="#1b3a4b", linewidth=1.8,
                        zorder=4, label="fit")
                # label each peak centre on the fit curve (single line kept)
                for c, comp in fit_res["comps"]:
                    yc = float(np.nanmax(comp)) if np.nanmax(comp) > 0 else y_hi * 0.92
                    ax.annotate(f"{c:.0f}", (c, yc), ha="center", fontsize=8,
                                color="#1b3a4b")
            else:
                ax.plot(xs, yf, color="#1b3a4b", linewidth=1.7, zorder=3,
                        label="smooth")
    ax.set_xlim(xlim)
    ax.set_ylim(y_lo, y_hi)
    ax.set_xlabel(r"Wavenumber (cm$^{-1}$)")
    ax.set_ylabel("SFG signal (a.u.)")
    ax.set_title(f"{sample} / {ref_sample}   ({title_range})",
                 loc="left", pad=8)
    ax.minorticks_on()
    if mode == "fit":
        ax.legend(loc="upper right", handletextpad=0.4, borderaxespad=0.4)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)
    return peak_table


def _plot_denoised(df, sample, save_path):
    """Plot denoised spectrum (per-wavenumber components)."""
    plt.figure(figsize=(6, 4))
    for col in df.columns:
        if col not in ["IR_wavenumber_cm-1", "sum"]:
            plt.plot(df["IR_wavenumber_cm-1"], df[col], label=col)
    plt.xlabel(r"IR Wavenumber (cm$^{-1}$)")
    plt.ylabel("SFG Intensity")
    plt.title(f"SFG Spectrum (denoised): {sample}")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def _plot_denoised(df, sample, save_path):
    """Plot denoised spectrum."""
    plt.figure(figsize=(6, 4))
    for col in df.columns:
        if col not in ["IR_wavenumber_cm-1", "sum"]:
            plt.plot(df["IR_wavenumber_cm-1"], df[col], label=col)
    plt.xlabel(r"IR Wavenumber (cm$^{-1}$)")
    plt.ylabel("SFG Intensity")
    plt.title(f"SFG Spectrum (denoised): {sample}")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def process_experiment(folder_path, ref_sample_name, lambda_vis=1030.0,
                       x_ranges=None, progress_callback=None, mode="fit",
                       cosmic=True, peaks_hint=None):
    """
    Main processing: scan, denoise, normalize, output Excel and plots.

    Args:
        folder_path: experiment folder path
        ref_sample_name: reference sample name (e.g. "quartz")
        lambda_vis: visible light wavelength (nm)
        x_ranges: list of (min, max) for zoomed plots
        progress_callback: callback(current, total, message)

    Returns:
        output_excel path
    """
    if x_ranges is None:
        x_ranges = [(3000, 3800)]
    output_excel = os.path.join(folder_path, "processed_SFG.xlsx")

    # 1. Scan files
    if progress_callback:
        progress_callback(0, 5, "Scanning files...")
    meta_list = scan_folder(folder_path)

    # 2. Read and convert data
    if progress_callback:
        progress_callback(1, 5, "Reading data...")
    data_series = {}
    for meta in meta_list:
        df = read_sfg_data(meta["path"])
        ir = wavelength_to_ir(df["SFG_nm"].values, lambda_vis)
        series = pd.Series(df["Intensity"].values, index=ir, name=meta["stem"])
        data_series[meta["stem"]] = series

    all_ir = np.sort(np.unique(np.concatenate(
        [s.index.values for s in data_series.values()]
    )))

    # 3. Build denoised data per sample
    if progress_callback:
        progress_callback(2, 5, "Denoising...")
    samples = sorted({m["sample"] for m in meta_list})
    meta_lookup = {
        (m["sample"], m["wave"], tuple(sorted(f.lower() for f in m["flags"])), m["is_background"]): m
        for m in meta_list
    }
    sample_sheets = {}
    for sample in samples:
        metas = [m for m in meta_list if m["sample"] == sample and not m["is_background"]]
        if not metas:
            continue
        df_samp = pd.DataFrame({"IR_wavenumber_cm-1": all_ir})
        used_cols = []
        for m in sorted(metas, key=lambda x: (x["wave"], "_".join(x["flags"]))):
            colname = str(m["wave"])
            i = 1
            while colname in used_cols:
                colname = f"{colname}_{i}"
                i += 1
            used_cols.append(colname)
            sfg_series = data_series[m["stem"]].reindex(all_ir).values
            bg_key = (m["sample"], m["wave"],
                      tuple(sorted(f.lower() for f in m["flags"])), True)
            if bg_key in meta_lookup:
                bg_series = data_series[meta_lookup[bg_key]["stem"]].reindex(all_ir).values
                cleaned = sfg_series - bg_series
            else:
                cleaned = sfg_series
                warnings.warn(f"Sample {sample} wavenumber {m['wave']} flags {m['flags']} has no background file; keeping raw")
            df_samp[colname] = cleaned
        df_samp["sum"] = df_samp.iloc[:, 1:].sum(axis=1)
        sample_sheets[sample] = df_samp

    # 4. Normalize
    if progress_callback:
        progress_callback(3, 5, "Normalising...")
    test_samples = [s for s in samples if s != ref_sample_name]
    for sample in test_samples:
        if sample not in sample_sheets or ref_sample_name not in sample_sheets:
            warnings.warn(f"Sample {sample} or reference {ref_sample_name} missing data; skipping normalisation")
            continue
        df_w = sample_sheets[sample]
        df_ref = sample_sheets[ref_sample_name]
        norm_df = pd.DataFrame()
        norm_df["IR_wavenumber_cm-1"] = df_w["IR_wavenumber_cm-1"]
        with np.errstate(divide="ignore", invalid="ignore"):
            norm_df["normalized_sum"] = df_w["sum"] / df_ref["sum"]
        # optional cosmic-ray spike removal on the normalised spectrum
        if cosmic:
            norm_df["normalized_sum"] = remove_cosmics(norm_df["normalized_sum"].values)
        sample_sheets[sample + "_normalized"] = norm_df

    # 5. Write Excel
    with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
        all_df = pd.DataFrame({"IR_wavenumber_cm-1": all_ir})
        with np.errstate(divide="ignore", invalid="ignore"):
            sfg_from_ir = 1.0 / ((1.0 / lambda_vis) + all_ir * 1e-7)
        all_df.insert(0, "SFG_wavelength_nm", sfg_from_ir)
        for meta in sorted(meta_list, key=lambda m: (m["sample"].lower(), m["wave"])):
            all_df[meta["stem"]] = data_series[meta["stem"]].reindex(all_ir).values
        all_df.to_excel(writer, sheet_name="AllData", index=False)
        for sample, df in sample_sheets.items():
            df.to_excel(writer, sheet_name=sample[:31], index=False)

    # 6. Plot — Nature style (scatter + fit).
    #    Always emit a full-range figure; each selected range adds a zoomed one.
    if progress_callback:
        progress_callback(4, 5, "Plotting...")
    _set_nature_style()
    peak_sheets = {}  # sample -> DataFrame of peak parameters
    for sample in test_samples:
        norm_key = sample + "_normalized"
        if norm_key not in sample_sheets:
            continue
        norm_df = sample_sheets[norm_key]
        # full-range normalized figure (always)
        _plot_nature(norm_df, sample, ref_sample_name,
                     os.path.join(folder_path, f"{sample}_normalized_full.png"),
                     mode=mode, peaks_hint=peaks_hint)
        # one zoomed figure per selected range (capture peak table)
        for x_min, x_max in x_ranges:
            tbl = _plot_nature(norm_df, sample, ref_sample_name,
                               os.path.join(folder_path,
                                            f"{sample}_normalized_{x_min}_{x_max}.png"),
                               xlim=(x_min, x_max), mode=mode, peaks_hint=peaks_hint)
            if tbl and sample not in peak_sheets:
                rows = [{"range": f"{x_min}-{x_max}", **r} for r in tbl]
                peak_sheets[sample] = pd.DataFrame(rows)
    for sample in samples:
        if sample not in sample_sheets:
            continue
        _plot_denoised(sample_sheets[sample], sample,
                       os.path.join(folder_path, f"{sample}_denoised.png"))

    # 7. Append peak-fit tables to the workbook (if multi-peak fit ran)
    if peak_sheets:
        with pd.ExcelWriter(output_excel, engine="openpyxl",
                            mode="a", if_sheet_exists="replace") as writer:
            for sample, df in peak_sheets.items():
                df.to_excel(writer, sheet_name=(sample + "_peaks")[:31], index=False)

    if progress_callback:
        progress_callback(5, 5, "Done!")
    return output_excel
