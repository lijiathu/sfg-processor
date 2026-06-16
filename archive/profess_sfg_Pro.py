# -*-coding:utf-8-*-
# Author：Li Jia
# Data: 2025/11/23


"""
process_sfg_Pro.py
"""

import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
import warnings

# ================ 修改参数 ================
# 数据文件夹路径
folder_path = r"D:\1 PhD\1 Research Project\01 Experiments\20260520_Al2O3Si-Water"
# 测试样品名称
sample1 = "Al2O3Si-Water"
# 归一化样品名称
sample2 = "quartz"
# 指定横坐标范围 (最小值, 最大值)
x_ranges = [
    (3000, 3800),
    (3000, 3750),
]
# ================ 固定参数 ================
output_excel = os.path.join(folder_path, "processed_SFG.xlsx")
lambda_vis = 1030.0                 # 可见光波长 nm

# ================ 工具函数 ================
def parse_filename(fn_stem):
    """
    解析文件名，例如:
      quartz_3000, quartz_3600_Purge_NoVis
    返回:
      sample, wave (int), flags (list), is_background (bool)
    """
    parts = fn_stem.split('_')
    if len(parts) < 2:
        raise ValueError(f"无法解析文件名: {fn_stem}")
    sample = parts[0]
    wave_match = re.match(r'(\d+)', parts[1])
    if not wave_match:
        raise ValueError(f"无法解析波数: {fn_stem}")
    wave = int(wave_match.group(1))
    flags = parts[2:] if len(parts) > 2 else []
    is_background = any(f.lower() == 'novis' for f in flags)
    other_flags = [f for f in flags if f.lower() != 'novis']
    return sample, wave, other_flags, is_background

def wavelength_to_ir(sfg_nm, lambda_vis_nm=lambda_vis):
    """
    λ_IR = 1e7 * (1/λ_SFG - 1/λ_vis), 单位 cm^-1
    """
    sfg = np.array(sfg_nm, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        ir_cm1 = 1e7 * ((1.0 / sfg) - (1.0 / lambda_vis_nm))
    return ir_cm1

def set_origin_style():
    plt.style.use('default')
    plt.rcParams['figure.dpi'] = 200
    plt.rcParams['font.family'] = 'Times New Roman'
    plt.rcParams['axes.linewidth'] = 1.2
    plt.rcParams['axes.edgecolor'] = 'black'
    plt.rcParams['xtick.direction'] = 'in'
    plt.rcParams['ytick.direction'] = 'in'
    plt.rcParams['xtick.major.width'] = 1.1
    plt.rcParams['ytick.major.width'] = 1.1
    plt.rcParams['lines.linewidth'] = 2
    plt.rcParams['legend.frameon'] = False

# ================== 读取所有 txt 文件 ==================
all_txt_files = []
for root, dirs, files in os.walk(folder_path):
    for file in files:
        if file.endswith(".txt"):
            all_txt_files.append(os.path.join(root, file))

if not all_txt_files:
    raise FileNotFoundError("未找到任何 .txt 文件，请检查路径。")

data_series = {}   # key: filename stem, value: Series indexed by IR
meta_list = []

for fpath in all_txt_files:
    stem = Path(fpath).stem
    try:
        sample, wave, flags, is_bg = parse_filename(stem)
    except Exception as e:
        warnings.warn(f"跳过无法解析文件 {stem}: {e}")
        continue
    df = pd.read_csv(fpath, sep=r'\s+|\t', header=None, engine='python',
                     names=['SFG_nm','Intensity'])
    df['SFG_nm'] = pd.to_numeric(df['SFG_nm'], errors='coerce')
    df['Intensity'] = pd.to_numeric(df['Intensity'], errors='coerce')
    ir = wavelength_to_ir(df['SFG_nm'].values)
    series = pd.Series(df['Intensity'].values, index=ir, name=stem)
    data_series[stem] = series
    meta_list.append({
        'stem': stem,
        'sample': sample,
        'wave': wave,
        'flags': flags,
        'is_background': is_bg
    })

# ================== 构建 AllData ==================
meta_sorted = sorted(meta_list, key=lambda m: (m['sample'].lower(),
                                               m['wave'],
                                               m['is_background'],
                                               # "_".join(m['flags'])))
                                               ))
all_ir = np.unique(np.concatenate([s.index.values for s in data_series.values()]))
all_ir_sorted = np.sort(all_ir)
all_df = pd.DataFrame({'IR_wavenumber_cm-1': all_ir_sorted})

# 添加 SFG_wavelength_nm 列（从 IR 反算）
with np.errstate(divide='ignore', invalid='ignore'):
    sfg_from_ir = 1.0 / ((1.0 / lambda_vis) + all_ir_sorted * 1e-7)
all_df.insert(0, 'SFG_wavelength_nm', sfg_from_ir)

# 添加每个文件列
for meta in meta_sorted:
    s = data_series[meta['stem']].reindex(all_ir_sorted).values
    all_df[meta['stem']] = s

# ================== 构建每个样品去噪 sheet ==================
samples = sorted({m['sample'] for m in meta_list})
sample_sheets = {}

# 构建 meta lookup 方便查找背景
meta_lookup = {(m['sample'], m['wave'], tuple(sorted([f.lower() for f in m['flags']])), m['is_background']): m for m in meta_list}

for sample in samples:
    metas = [m for m in meta_list if m['sample']==sample and not m['is_background']]
    if not metas:
        warnings.warn(f"样品 {sample} 没有非背景文件，跳过")
        continue
    df_samp = pd.DataFrame({'IR_wavenumber_cm-1': all_ir_sorted})
    used_cols = []
    for m in sorted(metas, key=lambda x: (x['wave'], "_".join(x['flags']))):
        # colname = str(m['wave']) + ("_" + "_".join(m['flags']) if m['flags'] else "")
        colname = str(m['wave'])
        i = 1
        while colname in used_cols:
            colname = f"{colname}_{i}"; i += 1
        used_cols.append(colname)
        sfg_series = data_series[m['stem']].reindex(all_ir_sorted).values
        # 查找背景
        bg_key = (m['sample'], m['wave'], tuple(sorted([f.lower() for f in m['flags']])), True)
        if bg_key in meta_lookup:
            bg_series = data_series[meta_lookup[bg_key]['stem']].reindex(all_ir_sorted).values
            cleaned = sfg_series - bg_series
        else:
            cleaned = sfg_series
            warnings.warn(f"样品 {sample} 波数 {m['wave']} flags {m['flags']} 无背景文件，保留原始 SFG")
        df_samp[colname] = cleaned
    # 添加 sum 列
    df_samp['sum'] = df_samp.iloc[:,1:].sum(axis=1)
    sample_sheets[sample] = df_samp

# ================== 仅对 sample1 sum 归一化 ==================
normalized_sheet = None
if sample1 in sample_sheets and sample2 in sample_sheets:
    df_w = sample_sheets[sample1]
    df_ref = sample_sheets[sample2]
    norm_df = pd.DataFrame()
    norm_df['IR_wavenumber_cm-1'] = df_w['IR_wavenumber_cm-1']
    with np.errstate(divide='ignore', invalid='ignore'):
        norm_df['normalized_sum'] = df_w['sum'] / df_ref['sum']
    sample_sheets[sample1+'_normalized'] = norm_df
    normalized_sheet = norm_df
else:
    if sample1 not in sample_sheets:
        print("⚠ 未找到匹配样品名：请检查测试样品 " + sample1 + " 输入。")
    elif sample2 not in sample_sheets:
        print("⚠ 未找到匹配样品名：请检查标准样品 " + sample2 + " 输入。")

# ================== 写入 Excel ==================
with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
    all_df.to_excel(writer, sheet_name='AllData', index=False)
    for sample, df in sample_sheets.items():
        df.to_excel(writer, sheet_name=sample, index=False)
print(f"✅ 处理完成，Excel 已保存到 {output_excel}")

# ================== 绘图 ==================
set_origin_style()

# 1. 绘制归一化谱图
if normalized_sheet is not None:
    # -------------------------------
    # 第一部分：绘制全范围的归一化谱图
    # -------------------------------
    plt.figure(figsize=(6, 4))
    plt.plot(normalized_sheet['IR_wavenumber_cm-1'],
             normalized_sheet['normalized_sum'],
             label=f"Normalized {sample1}/{sample2}")
    plt.xlabel("IR Wavenumber (cm$^{-1}$)")
    plt.ylabel("Normalized SFG Intensity")
    plt.title(f"Normalized SFG Spectrum ({sample1}/{sample2})")
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(os.path.join(folder_path, "normalized_spectrum.png"), dpi=300)
    plt.close()

    # -------------------------------
    # 第二部分：循环绘制各个指定横坐标范围的归一化放大图
    # -------------------------------
    # 注意：确保这段代码运行前，x_ranges 列表已经被定义
    for x_min, x_max in x_ranges:
        plt.figure(figsize=(6, 4))
        plt.plot(normalized_sheet['IR_wavenumber_cm-1'],
                 normalized_sheet['normalized_sum'],
                 label=f"Normalized {sample1}/{sample2}")
        plt.xlabel("IR Wavenumber (cm$^{-1}$)")
        plt.ylabel("Normalized SFG Intensity")
        # 标题里加上当前范围，方便区分
        plt.title(f"Normalized SFG Spectrum ({sample1}/{sample2}) ({x_min}-{x_max} cm$^{{-1}}$)")

        # 核心修改：限制横坐标范围为当前循环的范围
        plt.xlim(x_min, x_max)

        plt.legend(loc='upper right')
        plt.tight_layout()

        # 修改保存的文件名，加上范围后缀，例如 "normalized_spectrum_zoomed_2800_3000.png"
        zoomed_filename = f"normalized_spectrum_zoomed_{x_min}_{x_max}.png"
        plt.savefig(os.path.join(folder_path, zoomed_filename), dpi=300)
        plt.close()

# 1. 绘制归一化谱图
# if normalized_sheet is not None:
#     plt.figure(figsize=(6,4))
#     plt.plot(normalized_sheet['IR_wavenumber_cm-1'],
#              normalized_sheet['normalized_sum'],
#              label=f"Normalized {sample1}/{sample2}")
#     plt.xlabel("IR Wavenumber (cm$^{-1}$)")
#     plt.ylabel("Normalized SFG Intensity")
#     plt.title(f"Normalized SFG Spectrum ({sample1}/{sample2})")
#     plt.legend(loc='upper right')
#     plt.tight_layout()
#     plt.savefig(os.path.join(folder_path, "normalized_spectrum.png"), dpi=300)
#     plt.close()



# 2. 绘制每个样品去噪谱图
for sample, df in sample_sheets.items():
    if sample.endswith("_normalized"):
        continue
    plt.figure(figsize=(6,4))
    for col in df.columns:
        if col not in ['IR_wavenumber_cm-1', 'sum']:
            plt.plot(df['IR_wavenumber_cm-1'], df[col], label=col)
    plt.xlabel("IR Wavenumber (cm$^{-1}$)")
    plt.ylabel("SFG Intensity")
    plt.title(f"SFG Spectrum (denoised): {sample}")
    plt.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(os.path.join(folder_path,f"{sample}_denoised.png"), dpi=300)
    plt.close()

print("✅ 绘图完成，图片已保存。")

'''
# ================== 优化去除宇宙射线 ==================
import xlsxwriter
from scipy.ndimage import median_filter

def remove_cosmic_rays_advanced(df, window=5, threshold=8):
    """
    高级去除宇宙射线：
    - 对每列（除 IR 列）进行一阶差分
    - 计算局部中位数滤波
    - 如果某点差分大于 threshold*局部中位数 std，则视为宇宙射线，用邻域中位数替换
    """
    df_clean = df.copy()
    cols = [c for c in df.columns if c != 'IR_wavenumber_cm-1']
    for col in cols:
        data = df[col].values
        # 局部中位数滤波
        local_med = median_filter(data, size=window)
        diff = data - local_med
        std_local = np.std(diff)
        mask = np.abs(diff) > threshold * std_local
        data_clean = data.copy()
        data_clean[mask] = local_med[mask]
        df_clean[col] = data_clean
    return df_clean

# ================== 对样品去除宇宙射线 ==================
cosmic_sheets_adv = {}
for sample, df in sample_sheets.items():
    if sample.endswith("_normalized"):
        continue
    # 高级去除宇宙射线
    cleaned_df = remove_cosmic_rays_advanced(df)
    # 重新计算 sum（忽略 IR_wavenumber_cm-1 列）
    value_cols = [c for c in cleaned_df.columns if c != 'IR_wavenumber_cm-1']
    cleaned_df['sum'] = cleaned_df[value_cols].sum(axis=1)
    cosmic_sheets_adv[sample] = cleaned_df


# ================== 平滑参考样品用于归一化 ==================
from scipy.ndimage import uniform_filter1d

def smooth_reference(df, window=5):
    """
    对参考样品每一列进行滑动平均平滑
    """
    df_smooth = df.copy()
    cols = [c for c in df.columns if c != 'IR_wavenumber_cm-1']
    for col in cols:
        df_smooth[col] = uniform_filter1d(df[col].values, size=window)
    return df_smooth

if sample2 in sample_sheets:
    ref_smooth_df = smooth_reference(sample_sheets[sample2])
else:
    ref_smooth_df = sample_sheets[sample2]

# ================== 去除宇宙射线后水样归一化（只对 sum） ==================
if sample1 in cosmic_sheets_adv:
    df_w = cosmic_sheets_adv[sample1]
    norm_df_cosmic = pd.DataFrame()
    norm_df_cosmic['IR_wavenumber_cm-1'] = df_w['IR_wavenumber_cm-1']
    # 用平滑后的参考样品 sum 列归一化
    with np.errstate(divide='ignore', invalid='ignore'):
        norm_df_cosmic['normalized_sum'] = df_w['sum'] / ref_smooth_df['sum']
    cosmic_sheets_adv[sample1 + '_normalized'] = norm_df_cosmic

# ================== 写入 Excel（追加 sheet） ==================
with pd.ExcelWriter(output_excel, engine='openpyxl', mode='a') as writer:
    for sample, df in cosmic_sheets_adv.items():
        df.to_excel(writer, sheet_name=sample+'_cosmic_removed', index=False)
print("✅ 去除宇宙射线（高级）+ 平滑参考样品后的数据已保存到新的 sheet 中。")

# ================== Science 风格绘图 ==================
def set_science_style():
    plt.style.use('seaborn-whitegrid')
    plt.rcParams['figure.dpi'] = 300
    plt.rcParams['font.family'] = 'Arial'
    plt.rcParams['axes.linewidth'] = 1.5
    plt.rcParams['axes.edgecolor'] = 'black'
    plt.rcParams['xtick.direction'] = 'out'
    plt.rcParams['ytick.direction'] = 'out'
    plt.rcParams['xtick.major.width'] = 1.2
    plt.rcParams['ytick.major.width'] = 1.2
    plt.rcParams['lines.linewidth'] = 2
    plt.rcParams['legend.frameon'] = False

# 绘制去除宇宙射线 + 平滑归一化谱图
if sample1 + '_normalized' in cosmic_sheets_adv:
    df_plot = cosmic_sheets_adv[sample1 + '_normalized']
    # 只保留 3100-3750 cm^-1
    mask = (df_plot['IR_wavenumber_cm-1'] >= 3100) & (df_plot['IR_wavenumber_cm-1'] <= 3750)
    df_plot = df_plot[mask]

    set_science_style()
    plt.figure(figsize=(6,4))
    plt.plot(df_plot['IR_wavenumber_cm-1'], df_plot['normalized_sum'], color='black')
    plt.xlabel("IR Wavenumber (cm$^{-1}$)")
    plt.ylabel("Normalized SFG Intensity")
    plt.title(f"{sample1} (cosmic rays removed, smoothed ref, normalized)")
    plt.xlim(3100, 3750)
    plt.ylim(0, np.max(df_plot['normalized_sum'])*1.1)
    plt.tight_layout()
    plt.savefig(os.path.join(folder_path, f"{sample1}_normalized_cosmic_removed_smoothed.png"), dpi=300)
    plt.close()
print("✅ 去除宇宙射线 + 平滑参考样品后的归一化谱图已绘制。")
'''