# EEG Visualization Research Workbench - 模块一：数据管理模块

## 项目结构

```
src/eeg_workbench/
├── __init__.py                 # 包导出
├── main.py                     # 程序入口 (MainWindow)
├── core/                       # 核心基础设施
│   ├── __init__.py
│   ├── config.py               # 配置管理 (YAML, 单例)
│   ├── events.py               # 事件总线 (发布-订阅)
│   └── base.py                 # ObservableModel, ViewModelBase, Command
├── models/                     # 领域模型 (纯数据+业务规则)
│   ├── __init__.py
│   ├── dataset.py              # EEGDataset, ChannelInfo, Event, Montage, EpochData
│   └── metadata.py             # DatasetMetadata, SubjectInfo, ExperimentCondition
├── services/                   # 业务逻辑服务 (无 UI 依赖)
│   ├── __init__.py
│   ├── io/                     # 多格式读取
│   │   ├── __init__.py         # ReaderFactory, LoadResult, BaseReader
│   │   ├── edf.py              # EDF/BDF 读取
│   │   ├── brainvision.py      # BrainVision (.vhdr/.vmrk/.eeg) 读取
│   │   ├── eeglab.py           # EEGLAB (.set) 读取
│   │   └── csv_excel.py        # CSV/Excel/TXT 表格读取
│   ├── events/                 # 事件编辑与导入导出
│   │   ├── __init__.py
│   │   ├── editor.py           # EventEditor (增删改查、撤销/重做、自动检测)
│   │   └── importers.py        # VMRK/TSV 导入导出
│   └── segmentation.py         # 裁剪/拼接/分割
├── viewmodels/                 # MVVM 绑定层
│   ├── __init__.py
│   └── data_management_vm.py   # DataManagementViewModel
├── views/                      # PySide6 UI 组件
│   ├── __init__.py
│   └── data_management/
│       ├── __init__.py
│       ├── dataset_loader_widget.py    # 文件加载、最近文件
│       ├── metadata_editor.py          # 元数据编辑 (受试者、条件、采集参数)
│       ├── event_editor_widget.py      # 事件表格、导入导出、自动检测
│       └── segmentation_widget.py      # 裁剪、拼接、按事件分割
└── utils/                      # 工具函数
    ├── __init__.py
    ├── montage.py              # ELP/CSD 蒙版加载、通道标准化
    └── validators.py           # 文件/参数/业务规则校验
```

## 功能清单 (对应需求)

| 需求项 | 实现位置 | 状态 |
|--------|----------|------|
| **多格式支持** (EDF, BDF, BrainVision, EEGLAB, CSV, Excel, TXT) | `services/io/` | ✅ |
| **元数据编辑** (受试者信息、实验条件、通道坐标 .elp/.csd) | `models/metadata.py`, `views/data_management/metadata_editor.py`, `utils/montage.py` | ✅ |
| **事件编辑器** (可视化增删改、导入 .vmrk/.tsv、自动检测坏段) | `services/events/`, `views/data_management/event_editor_widget.py` | ✅ |
| **数据裁剪与拼接** (按时间裁剪、多 session 拼接) | `services/segmentation.py`, `views/data_management/segmentation_widget.py` | ✅ |

## 依赖安装

```bash
# 使用 conda (推荐)
conda env create -f environment.yml
conda activate eeg-workbench

# 或使用 pip
pip install -e .
```

**核心依赖**：
- Python 3.10+
- PySide6 6.6+ (Qt6)
- MNE-Python 1.6+
- NumPy 1.26+, SciPy 1.12+, Pandas 2.2+
- pyedflib 0.1.30+ (EDF/BDF)
- openpyxl, xlrd (Excel)

## 运行

```bash
# 开发模式
cd src
python -m eeg_workbench

# 或安装后
eeg-workbench
```

## 架构设计要点

### 1. MVC/MVVM 分层
- **Models**: 纯数据类 (`dataclass`)，含业务验证，无副作用
- **Services**: 无状态业务逻辑，可单测，发布领域事件
- **ViewModels**: 暴露命令/属性给 UI，管理异步任务、忙碌状态
- **Views**: 纯 Qt Widgets，通过信号/槽与 VM 通信

### 2. 事件总线解耦
```python
# 发布
get_event_bus().publish(EventType.DATASET_LOADED, payload, source="IO")

# 订阅
bus.subscribe(EventType.DATASET_LOADED, handler)
```

### 3. 不可变数据更新
```python
# 所有修改返回新实例，支持撤销/重做
new_ds = dataset.add_event(event)
new_ds = dataset.crop(tmin, tmax)
```

### 4. MNE 互操作
```python
# 无缝转换
raw = dataset.to_mne_raw()
dataset = EEGDataset.from_mne_raw(raw)
```

## 关键类速览

### EEGDataset (核心数据容器)
```python
ds = EEGDataset(
    data=np.ndarray,      # (n_ch, n_samples) µV
    sfreq=250.0,          # Hz
    ch_names=["Fp1", ...],
    channel_info={...},   # ChannelInfo 对象
    events=[Event(...)],
    montage=Montage(...),
    metadata=DatasetMetadata(...)
)
```

### EventEditor (事件编辑器)
```python
editor = EventEditor(dataset)
editor.add_event(Event(onset=1.2, description="Stimulus/Target"))
editor.auto_detect_bad_segments(threshold_uv=100)
editor.undo() / editor.redo()
```

### DataManagementViewModel (UI 绑定)
```python
vm = DataManagementViewModel()
vm.load_file("data.edf")          # 异步命令
vm.crop(0, 10)                    # 裁剪
vm.concatenate(["a.edf", "b.edf"]) # 拼接
vm.add_condition(ExperimentCondition(...))
```

## 测试

```bash
# 运行单测
pytest tests/ -v

# 类型检查
mypy src/eeg_workbench
```

## 后续模块预留

主窗口 `MainWindow` 已预留标签页接口：
- 预处理模块 (滤波、重参考、ICA、重采样)
- 特征提取 (频段、时频、连通性、非线性)
- ERP/ERD/ERS 分析
- 源定位
- 统计分析
- 可视化与报告
- 系统与性能 (批处理、插件、GPU、权限)