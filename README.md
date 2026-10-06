# EEG Visualization Research Workbench

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

科研级 EEG 分析软件：从数据导入到源定位的完整分析流水线。

## 功能总览

| 模块 | 核心能力 | 状态 |
|------|---------|------|
| **数据管理** | 多格式读取 (EDF/BDF/BrainVision/EEGLAB/CSV/Excel)、元数据编辑、事件编辑器、裁剪拼接、标准蒙版 | ✅ 完整 |
| **预处理** | 滤波(高通/低通/带通/陷波)、重参考、ICA拟合/应用/自动标记、重采样、坏道插值、标准流水线 | ✅ 完整 |
| **特征提取** | 频段功率、时频分析(Morlet/Multitaper/Stockwell)、连通性(PLV/相干/虚部相干/PAC/Granger)、非线性特征 | ✅ 完整 |
| **ERP/ERD/ERS** | 叠加平均、峰值检测、拓扑图、时频功率谱、单试次ERP | ✅ 完整 |
| **源定位** | 球形/BEM/FEM/多层球头模型、表面/体积/混合源空间、MNE/dSPM/sLORETA/eLORETA/LCMV/DICS逆解、偶极子拟合、3D可视化 | ✅ 完整 |
| **统计分析** | t检验/ANOVA(含重复测量)、非参数(KW/Friedman)、多重比较校正(FDR/Bonferroni/TFCE)、排列检验、效应量 | ✅ 完整 |
| **可视化与报告** | 原始波形、频谱、时频图、拓扑图、源空间3D、HTML/PDF/DOCX/PPTX报告导出 | ✅ 完整 |

## 架构设计

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

### 关键设计原则

1. **MVVM 分层**: Models(纯数据) → Services(无状态逻辑) → ViewModels(异步命令/状态) → Views(纯 Qt)
2. **事件总线解耦**: 跨模块通信通过 `get_event_bus().publish/subscribe`
3. **不可变数据更新**: 修改返回新实例，支持撤销/重做
4. **MNE 无缝互操作**: `dataset.to_mne_raw()` / `EEGDataset.from_mne_raw(raw)`
5. **跨版本兼容**: `utils.montage.make_standard_montage_compat` 自动处理 MNE 1.13+ `standard_1020`→`colin27_1020` 重命名

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
| mne-bids | 0.18.0 | BIDS 支持 |
| pyqtgraph | 0.13.7 | 高性能绘图 |

### 安装

```bash
# 推荐：conda 环境 (含 MNE 二进制依赖)
conda env create -f environment.yml
conda activate eeg-workbench

# 或 pip (需预装系统级依赖)
pip install -e .
```

## 快速开始

```bash
# 开发模式
cd src
python -m eeg_workbench

# 安装后
eeg-workbench
```

## 测试与质量

```bash
# 完整测试套件 (203 测试通过)
pytest tests/ -q

# 类型检查
mypy src/eeg_workbench

# 代码格式
ruff check src/eeg_workbench
black src/eeg_workbench
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
- **滤波**: FIR 零相位 (MNE 默认)，陷波 50/60 Hz 可选
- **ICA**: FastICA/Infomax/Picard 可选，ICLabel 自动标记成分
- **源定位**: BEM 推荐 fsaverage 模板；球形模型仅作快速验证；FEM 需外部工具生成 .msh

## 许可

MIT License