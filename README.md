# EEG Visualization Research Workbench

[![CI](https://github.com/da-shan007/EEG-Visualization-Research-Workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/da-shan007/EEG-Visualization-Research-Workbench/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](environment.yml)
[![MNE-Python 1.13](https://img.shields.io/badge/MNE--Python-1.13-orange.svg)](https://mne.tools)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://github.com/da-shan007/EEG-Visualization-Research-Workbench/releases) [![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://github.com/da-shan007/EEG-Visualization-Research-Workbench/releases)

科研级 EEG 分析桌面软件：从数据导入到源定位的完整分析流水线（PySide6 + MNE-Python）。

## 功能总览

| 模块 | 核心能力 | 状态 |
|------|---------|------|
| **数据管理** | 多格式读取 (EDF/BDF/BrainVision/EEGLAB/CSV/Excel)、元数据编辑、事件编辑器、裁剪拼接、标准蒙版 | ✅ 完整 |
| **预处理** | 滤波(高通/低通/带通/陷波)、重参考、ICA拟合/应用/自动标记、重采样、坏道插值、标准流水线 | ✅ 完整 |
| **特征提取** | 频段功率、时频分析(Morlet/Multitaper/Stockwell)、连通性(相干/虚部相干/PLV/PLI/wPLI/Granger/DTF/PDC)、非线性特征 | ✅ 完整 |
| **ERP/ERD/ERS** | 叠加平均、峰值检测、拓扑图、时频功率谱、单试次ERP | ✅ 完整 |
| **源定位** | 球形/BEM/FEM/多层球头模型、表面/体积/混合源空间、MNE/dSPM/sLORETA/eLORETA/LCMV/DICS逆解、偶极子拟合、3D可视化 | ✅ 完整 |
| **统计分析** | t检验/ANOVA(含重复测量)、非参数(KW/Friedman)、多重比较校正(FDR/Bonferroni/TFCE)、排列检验、效应量 | ✅ 完整 |
| **可视化与报告** | 原始波形、频谱、时频图、拓扑图、源空间3D、HTML/PDF/DOCX/PPTX报告导出 | ✅ 完整 |

## 架构设计

<details>
<summary>点击展开目录结构（MVVM 分层，约 120 个模块，mypy --strict 全绿）</summary>

```
src/eeg_workbench/
├── main.py                     # 程序入口 (MainWindow)
├── core/                       # 核心基础设施
│   ├── config.py               # 配置管理 (YAML, 单例)
│   ├── events.py               # 事件总线 (发布-订阅)
│   └── base.py                 # ObservableModel, ViewModelBase, Command
├── models/                     # 领域模型 (纯数据+业务规则)
│   ├── dataset.py              # EEGDataset, ChannelInfo, Event, Montage, EpochData
│   ├── metadata.py             # DatasetMetadata, SubjectInfo, ExperimentCondition
│   ├── preprocessing.py        # Filter/Reference/ICA/Resample/Interpolation 参数模型
│   ├── features.py             # BandPower/TFR/Connectivity/Nonlinear 结果模型
│   ├── erp.py                  # ERP/ERD/ERS 分析模型
│   ├── source.py               # 头模型/前向/逆向/偶极子 参数与结果模型
│   ├── statistics.py           # 统计参数/结果/校正方法枚举
│   └── visualization.py        # 绘图配置/导出格式枚举
├── services/                   # 业务逻辑服务 (无 UI 依赖)
│   ├── io/                     # 多格式读取 (ReaderFactory)
│   ├── events/                 # 事件编辑/导入导出
│   ├── preprocessing/          # 滤波/参考/ICA/重采样/插值
│   ├── features/               # 频段/时频/连通性/非线性
│   ├── erp/                    # ERP/ERD/ERS/拓扑图
│   ├── source/                 # 头模型/前向/逆向/偶极子/3D可视化
│   ├── statistics/             # 统计检验/多重比较/效应量/排列
│   ├── segmentation.py         # 裁剪/拼接
│   └── visualization/          # 绘图/报告导出
├── viewmodels/                 # MVVM 绑定层
│   ├── data_management_vm.py
│   ├── preprocessing_vm.py
│   ├── features_vm.py
│   ├── erp_vm.py
│   ├── source_vm.py
│   ├── statistics_vm.py
│   └── visualization_vm.py
├── views/                      # PySide6 UI 组件
│   ├── data_management/
│   ├── preprocessing/
│   ├── features/
│   ├── erp/
│   ├── source/
│   ├── statistics/
│   └── visualization/
└── utils/                      # 工具函数
    ├── montage.py              # ELP/CSD 蒙版、通道标准化、MNE版本兼容
    └── validators.py           # 文件/参数/业务规则校验
```

</details>

### 关键设计原则

1. **MVVM 分层**: Models(纯数据) → Services(无状态逻辑) → ViewModels(异步命令/状态) → Views(纯 Qt)
2. **事件总线解耦**: 跨模块通信通过 `get_event_bus().publish/subscribe`
3. **撤销/重做**: 事件编辑器支持撤销/重做 (`EditorAction` 栈)
4. **MNE 无缝互操作**: `dataset.to_mne_raw()` / `EEGDataset.from_mne_raw(raw)`
5. **跨版本兼容**: `utils.montage.make_standard_montage_compat` 自动处理 MNE 1.13+ `standard_1020`→`colin27_1020` 重命名

## 系统要求

| 项目 | 要求 |
|------|------|
| 一键版 | Windows 64 位：双击 `启动EEGWorkbench.exe`；Linux/macOS：执行 `./run.sh`（等价脚本，自动建 venv 装依赖） |
| 源码版 | Python 3.12+，见 `environment.yml` / `requirements-lock.txt`（版本已锁定防 MNE API 漂移） |
| Linux 额外要求 | pip 装不上 Qt 的 xcb 平台插件与中文字体，需系统级安装，见下方「Linux 系统依赖」 |

## 依赖环境 (实测可复现)

| 包 | 版本 | 说明 |
|----|------|------|
| Python | 3.14.0 | |
| PySide6 | 6.11.2 | Qt6 GUI 框架 |
| MNE-Python | 1.13.2 | 核心信号处理 |
| NumPy | 2.5.3 | 数值计算 |
| SciPy | 1.18.1 | 科学计算 |
| pandas | 3.0.5 | 表格数据 |
| nibabel | 5.4.2 | 神经影像 |
| pyedflib | 0.1.42 | EDF/BDF 读取 |
| pingouin | 0.7.0 | 统计检验 |
| statsmodels | 0.15.0 | 重复测量 ANOVA |
| mne-bids | 0.20.0 | BIDS 支持 |
| pyqtgraph | 0.14.0 | 高性能绘图 |

## 快速开始

**方式一：一键运行（无需敲命令）**

| 平台 | 操作 |
|------|------|
| Windows | 双击项目根目录下的 `启动EEGWorkbench.exe` |
| Linux / macOS | `./run.sh`（首次自动创建 `.venv` 并安装依赖，约 3-5 分钟；之后直接秒启） |

> 两者都要求同目录下有 `src/`；Windows 的 `.exe` 另外要求 `.venv/`（由启动器自身保证），`run.sh` 则会自己创建。

### Linux 系统依赖（先装这些，否则 Qt 起不来）

`PySide6` 的 pip wheel **不包含** xcb 平台插件和中文字体，必须系统级安装：

```bash
# Debian / Ubuntu
sudo apt install python3.12 python3.12-venv python3-pip
sudo apt install libegl1 libgl1 libglx-mesa0 libopengl0 libxkbcommon-x11-0 \
                 libdbus-1-3 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
                 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
                 libxcb-xinerama0 libxcb-xkb1 libfontconfig1
sudo apt install fonts-noto-cjk fonts-wqy-microhei    # 中文字体，缺了界面/图形全是方框

# Fedora
sudo dnf install python3.12 python3.12-pip
sudo dnf install mesa-libGL mesa-libEGL libxkbcommon-x11 dbus-libs fontconfig \
                 google-noto-sans-cjk-fonts wqy-microhei-fonts

# Arch
sudo pacman -S python python-pip noto-fonts-cjk wqy-microhei
```

装完先验证 Qt 本身能起来（这一步过了，pip 依赖装好后程序就能跑）：

```bash
python -c "from PySide6.QtWidgets import QApplication; print('Qt OK')"
```

### 命令行运行（推荐）

**Windows（PowerShell）**

```powershell
# 1. 下载源码
git clone https://github.com/da-shan007/EEG-Visualization-Research-Workbench.git
cd EEG-Visualization-Research-Workbench

# 2. 创建虚拟环境并安装依赖（约 3-5 分钟）
conda env create -f environment.yml
conda activate eeg-workbench

# 3. 启动（必须先 cd src）
cd src
python -m eeg_workbench
```

**macOS / Linux（bash）**

```bash
git clone https://github.com/da-shan007/EEG-Visualization-Research-Workbench.git
cd EEG-Visualization-Research-Workbench

# 路线 A：一键脚本（建 venv + 装依赖 + 启动）
./run.sh

# 路线 B：conda
conda env create -f environment.yml
conda activate eeg-workbench
PYTHONPATH=src python -m eeg_workbench

# 路线 C：venv + pip
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-lock.txt
PYTHONPATH=src python -m eeg_workbench
```

**已安装（pip）**

```bash
pip install -e .
eeg-workbench
```

常见问题：
- 找不到 `eeg-workbench` 命令 → 用 `PYTHONPATH=src python -m eeg_workbench`（Windows：`cd src` 后 `python -m eeg_workbench`）
- 依赖冲突 → 确认用 `conda activate eeg-workbench` 激活了正确环境
- Linux 报 `Could not load the Qt platform plugin "xcb"` → 缺系统库，见上方「Linux 系统依赖」
- Linux 界面/图形中文全是方框 → 没装中文字体，启动时 stderr 会打印安装提示
- Linux 无显示环境 → 设置 `QT_QPA_PLATFORM=offscreen` 或安装 xvfb（也可直接 `./run.sh --offscreen`）

## 测试与质量

```bash
# 完整测试套件 (208 测试通过)
pytest tests/ -q

# 类型检查 (120 文件，mypy --strict 零错误)
mypy src/eeg_workbench --strict

# 代码格式
ruff check src/eeg_workbench
black src/eeg_workbench
```

无显示器环境下加 `QT_QPA_PLATFORM=offscreen` 即可跑 GUI 测试（Windows / Linux 通用）：

```powershell
# Windows (PowerShell)
$env:QT_QPA_PLATFORM='offscreen'; pytest tests/ -q
```

```bash
# Linux / macOS
QT_QPA_PLATFORM=offscreen pytest tests/ -q
```

## 典型分析流程

```
EEG数据导入 → 数据验证 → 预处理(滤波/ICA/重参考)
    → ERP/时频/连通性分析
    → 统计检验 (含 TFCE 校正)
    → 头模型 → 前向模型 → 逆解 (MNE/dSPM/sLORETA/LCMV)
    → 3D 源估计可视化 → 报告导出 (HTML/PDF/DOCX/PPTX)
```

## 输出目录

```
outputs/
├── reports/    # HTML/PDF/DOCX/PPTX 报告
├── figures/    # 导出图片 (PNG/SVG)
└── logs/       # 测试/运行日志
```

## 科研可靠性说明

- **单位**: 数据内部统一 µV，MNE 转换自动处理
- **采样率**: 读取时显式指定，重采样保留事件时间戳
- **通道顺序**: 读取时保留文件顺序，Montage 仅用于空间定位
- **坐标系**: 传感器空间用 MNE Head 空间 (m)；源空间用 MRI (surface RAS, mm)
- **滤波**: FIR 零相位 (MNE 默认)，陷波频率可调 (默认 50 Hz)
- **ICA**: FastICA/Infomax/Picard 可选，EOG/ECG 相关自动标记伪迹成分
- **源定位**: 球形/BEM/FEM 头模型可选；球形模型仅作快速验证

## 故障排除

- **中文显示异常**: Qt 界面与 matplotlib 图形都会自动探测系统中文字体（Windows/macOS/Linux 各自的候选列表见 `src/eeg_workbench/utils/fonts.py`）。若启动时 stderr 打印了「未检测到中文字体」，按提示装 `fonts-noto-cjk` / `fonts-wqy-microhei` 即可；仍未生效请提 issue。
- **Linux Qt 起不来**: `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` 表示缺系统库，见「Linux 系统依赖」。
- **窄带滤波警告** (`filter_length`): 窄带 FIR 需要物理最小长度，极短数据段无法满足是正常现象，用更长的数据段即可，不是 bug。
- **MNE 版本**: 依赖已用 `requirements-lock.txt` 锁定为 MNE 1.13.2，自行升级可能遇到 `standard_1020` 等 API 更名问题（代码内已有兼容层）。

## 引用

本项目暂无专用论文。如用于科研，底层信号处理方法请引用 MNE-Python：

> Gramfort, A. et al. (2013). MEG and EEG data analysis with MNE-Python.
> Frontiers in Neuroscience, 7, 267. doi:10.3389/fninf.2013.00014

## 许可

[MIT License](LICENSE)