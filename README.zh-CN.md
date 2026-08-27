<div align="center">

# SFG Processor

**用于批量处理和频振动光谱（SFG）数据的桌面工具。**

读取 `.txt` 光谱导出 · 自动识别标准样品与测试样品 · 背景扣除 · 标准样品归一化 · 出版级散点拟合图。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Status](https://img.shields.io/badge/status-v1.5.0-success.svg)

[English](README.md) · **简体中文**

</div>

---

<p align="center">
  <img src="docs/img/spectrum_example.png?v=4" width="560" alt="归一化 SFG 光谱示例：散点 + 平滑拟合">
</p>

<p align="center"><em>示例输出 —— 归一化水 O–H 拉伸 SFG 光谱（3100–3800 cm⁻¹），实验散点叠加 Savitzky–Golay 拟合，期刊发表风格。</em></p>

---

## ✨ 特性

- **读取 `.txt` 光谱** —— 两列空白分隔导出（波长、强度）。
- **一键批量处理** —— 选定一个实验目录，程序递归找出所有样品、自动匹配每个 `NoVis` 背景，并用**同一个标准样品**（如 quartz）归一化所有测试样品。再也不用手动复制标准数据。
- **多文件夹批量** —— 上级目录里每个子文件夹各是一个实验，一次运行全部处理：各子文件夹的标准样品自动识别（优先 quartz，可改），`processed/` 输出直接生成在各自数据旁。
- **波数匹配归一化** —— 测试样品里标准样品缺失的波数自动剔除出归一化（原始数据不动）；最后追加一个 `Matched_norm` 表，每样品 4 列：波数 · 样品匹配 sum · 标准样品匹配 sum · 归一化值。
- **可选 χ² 拟合与宇宙射线去除** —— 均为开关（默认关闭）。拟合叠加多峰洛伦兹曲线、逐段拟合图与峰表；峰位可手填、可即时重拟合微调。
- **可随时取消** —— 运行中按钮变为 ✕ 取消；即使正在拟合也能很快停下，已生成的结果保留。
- **出版级图形** —— 散点 + 平滑拟合曲线，Helvetica 字体，细坐标轴，无网格。Y 轴按拟合曲线自适应缩放，单个噪声尖峰不会压垮整张图。
- **始终输出全范围图** —— 每次运行都会生成一张全范围归一化图，外加每个选定波数段各一张局部放大图。
- **精致界面** —— 简洁的桌面窗口界面，原生文件夹选择器、实时进度条、内嵌结果画廊，一键切换 EN / 中文。
- **独立可执行程序** —— 打包为单个 Windows `.exe`，接收者无需安装 Python。

## 📦 安装

### 方式 A —— 独立程序（无需 Python）

1. 从 [最新 Release](../../releases) 下载 `SFG_Processor.exe`。
2. 双击运行，浏览器窗口会自动打开。

### 方式 B —— 从源码运行

```bash
git clone https://github.com/<your-user>/sfg-processor.git
cd sfg-processor
pip install -r requirements.txt
python sfg_app.py
```

然后在控制台打印的地址打开（默认 <http://127.0.0.1:5127>）。

## 🚀 使用

1. 点击 **选择**，选中实验数据文件夹（选一个装着多个实验子文件夹的上级目录也行 —— 每个子文件夹单独处理，标准样品各自识别）。
2. 程序扫描并预览每个识别到的样品 —— 标准样品自动选中（如有 quartz 则默认选它），可在下拉框切换。
3. 按需调整可见光波长，增删要出图的波数段；需要 χ² 拟合 / 宇宙射线去除时打开对应开关。
4. 点击 **处理并出图**。进度条走完后，画廊显示图片，Excel 工作簿就绪在数据文件夹中。

### 输出（写入数据文件夹内的 `processed/`）

| 文件 | 内容 |
|------|------|
| `processed_SFG.xlsx` | AllData · 各样品去噪 / 归一化表 · 峰表（开 χ² 拟合时） · `Matched_norm`（波数 · 样品/标准样品匹配 sum · 归一化值） |
| `{样品}_denoised.png` | 各波数去噪分量 |
| `{样品}_full_{line,scatter}.png` | 全范围归一化图（始终生成） |
| `{样品}_{最小}_{最大}_{line,scatter,fit}.png` | 每个选定波数段一组（`fit` 仅在开启 χ² 拟合时生成） |

多文件夹模式下，每个子文件夹都会生成自己的 `processed/` 及上述全部输出。

## 🧪 用自带示例试跑

仓库自带一份小型合成数据 [`example_data/`](example_data)：

```bash
python -c "from sfg_processor import process_experiment; process_experiment('example_data','quartz',x_ranges=[(3000,3800)])"
```

……或直接运行程序，把目录指向 `example_data`。

## 🗂 文件命名约定

文件按 `{样品}_{波数}_{标志}.txt` 自动解析：

| 文件 | 样品 | 波数 | 说明 |
|------|------|------|------|
| `quartz_3200_Purge.txt` | quartz | 3200 | 标准样品信号 |
| `quartz_3200_Purge_NoVis.txt` | quartz | 3200 | 标准样品背景 |
| `Al2O3Si-Water_3400_Purge.txt` | Al2O3Si-Water | 3400 | 测试样品信号 |
| `sample_water_3400_Purge_NoVis.txt` | sample_water | 3400 | 测试样品背景 |

- **第一个纯数字 token** 是波数；它之前的所有部分是样品名（允许下划线、连字符）。
- 文件名含 `NoVis` 的，自动作为该样品/波数的背景。
- 一个标准样品可为同一目录下的多个测试样品归一化。

## 🏗 自行打包可执行程序

```bash
build.bat
```

生成 `dist/SFG_Processor.exe`（PyInstaller 单文件，`--windowed`）。

## 🧱 项目结构

```
sfg-processor/
├── sfg_processor.py     # 核心逻辑（纯函数，无 GUI 依赖）：解析、去噪、归一化、绘图、χ² 拟合
├── sfg_app.py           # Flask 后端 + 原生文件夹选择 + 任务状态
├── frontend/
│   └── index.html       # 自包含界面（HTML/CSS/JS）
├── test_sfg_processor.py# 单元测试
├── example_data/        # 小型合成数据，用于试跑
├── build.bat            # PyInstaller 打包脚本
├── requirements.txt
└── docs/img/            # README 截图
```

## 🔬 工作原理

```
.txt  →  递归扫描 + 文件名解析
            →  SFG 波长  →  IR 波数 (ν = 1e7·(1/λ_SFG − 1/λ_vis))
            →  扣除对应 NoVis 背景
            →  各样品去噪分量求和
            →  归一化：测试样品_sum / 标准样品_sum
            →  Excel 工作簿 + 出版级图形（散点 + Savitzky–Golay 拟合）
```

## ✅ 测试

```bash
python -m pytest -q
```

## 📜 许可证

[MIT](LICENSE) © Li Jia

## 📖 引用

如果本工具对你的研究有帮助，请按 [CITATION.cff](CITATION.cff) 引用。

## 🤝 贡献

欢迎贡献 —— 详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
