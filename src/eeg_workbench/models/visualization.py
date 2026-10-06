"""可视化与报告参数模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


# 下拉框/配置共用的字面值别名：GUI 固定选项与这些值逐字对应，
# widget 侧用 cast() 标注 currentText()，运行时 round-trip 安全。
XScale = Literal["linear", "log"]
SpectralMethod = Literal["welch", "multitaper", "periodogram", "fft"]
TFRMethod = Literal["morlet", "multitaper", "stockwell"]
GraphLayout = Literal["circular", "spring", "kamada_kawai", "spectral", "random"]
StatPlotType = Literal["bar", "violin", "box", "raincloud", "forest", "effect_size"]
TimeUnit = Literal["s", "ms", "us"]
WaveformPicks = list[int] | list[str] | Literal["all", "eeg", "eog", "ecg"]


class PlotType(Enum):
    """绘图类型"""
    # 波形图
    RAW_WAVEFORM = "raw_waveform"           # 原始波形
    ERP_WAVEFORM = "erp_waveform"           # ERP波形
    EPOCH_WAVEFORM = "epoch_waveform"       # Epoch波形
    
    # 频谱图
    PSD = "psd"                             # 功率谱密度
    TOPOMAP = "topomap"                     # 地形图
    
    # 时频图
    TFR = "tfr"                             # 时频图
    TFR_TOPOMAP = "tfr_topomap"             # 时频地形图
    
    # 连通性
    CONNECTIVITY_MATRIX = "conn_matrix"     # 连通性矩阵
    CONNECTIVITY_GRAPH = "conn_graph"       # 连通性图
    CONNECTIVITY_3D = "conn_3d"             # 3D连通性
    
    # 统计图
    STAT_BAR = "stat_bar"                   # 柱状图
    STAT_VIOLIN = "stat_violin"             # 小提琴图
    STAT_BOX = "stat_box"                   # 箱线图
    STAT_RAINCLOUD = "stat_raincloud"       # 雨云图
    STAT_EFFECT_SIZE = "effect_size"        # 效应量图
    
    # 源定位
    SOURCE_ESTIMATE = "source_estimate"     # 源估计
    SOURCE_3D = "source_3d"                 # 3D源定位
    DIPOLE_3D = "dipole_3d"                 # 3D偶极子
    
    # 自定义
    CUSTOM = "custom"                       # 自定义


class ExportFormat(str, Enum):
    """导出格式（str 子类，便于与字符串直接比较/序列化）"""
    PNG = "png"
    PDF = "pdf"
    SVG = "svg"
    EPS = "eps"
    HTML = "html"          # 交互式 HTML
    JSON = "json"          # 数据导出
    NPZ = "npz"            # NumPy 数据
    CSV = "csv"            # 表格数据
    DOCX = "docx"          # Word 报告
    PPTX = "pptx"          # PPT 报告
    EXCEL = "xlsx"         # Excel 表格（ExportService._export_excel 使用）


class PlotBackend(Enum):
    """绘图后端"""
    MATPLOTLIB = "matplotlib"
    PYQTGRAPH = "pyqtgraph"
    PLOTLY = "plotly"
    MNE = "mne"
    BRAIN = "brain"        # MNE Brain (3D)


@dataclass
class PlotConfig:
    """绘图通用配置"""
    # 画布
    figsize: tuple[float, float] = (12, 8)
    dpi: int = 100
    facecolor: str = "white"
    
    # 字体
    font_family: str = "DejaVu Sans"
    font_size: int = 12
    title_size: int = 14
    label_size: int = 11
    tick_size: int = 10
    legend_size: int = 10
    
    # 颜色
    cmap: str = "RdBu_r"
    color_cycle: list[str] = field(default_factory=lambda: [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ])
    
    # 布局
    tight_layout: bool = True
    constrained_layout: bool = False
    subplot_adjust: dict[str, Any] = field(default_factory=dict)
    
    # 交互
    interactive: bool = False
    toolbar: bool = True
    
    # 后端
    backend: PlotBackend = PlotBackend.MATPLOTLIB


@dataclass
class WaveformPlotConfig(PlotConfig):
    """波形图配置"""
    # 时间轴
    tmin: float | None = None
    tmax: float | None = None
    time_unit: TimeUnit = "s"
    
    # 通道
    picks: WaveformPicks = "eeg"
    n_channels_per_plot: int = 20
    
    # 样式
    line_width: float = 0.8
    alpha: float = 0.8
    show_grid: bool = True
    grid_alpha: float = 0.3
    
    # 标记
    show_events: bool = True
    event_colors: dict[str, str] = field(default_factory=dict)
    event_markers: dict[str, str] = field(default_factory=dict)
    
    # 标度
    scalings: dict[str, float] = field(default_factory=lambda: {"eeg": 1e-6, "eog": 1e-6})
    unit: str = "µV"
    
    # 偏移
    offset_step: float = 1.0
    show_channel_names: bool = True


@dataclass
class SpectralPlotConfig(PlotConfig):
    """频谱图配置"""
    # 频率范围
    fmin: float = 0
    fmax: float = 100
    xscale: XScale = "linear"
    
    # 方法（与频谱组件下拉框四选项一致；multitaper 暂走 FFT 分支实现）
    method: SpectralMethod = "welch"
    n_fft: int = 256
    n_overlap: int = 128
    
    # 显示
    show_confidence: bool = True
    confidence_level: float = 0.95
    average: bool = True
    average_method: Literal["mean", "median"] = "mean"
    
    # 地形图插入
    show_topomap_inset: bool = False
    topomap_freqs: list[float] | None = None


@dataclass
class TFRPlotConfig(PlotConfig):
    """时频图配置"""
    # 频率/时间范围
    fmin: float = 1
    fmax: float = 100
    tmin: float | None = None
    tmax: float | None = None

    # 变换方法
    method: TFRMethod = "morlet"
    n_cycles: float = 7.0

    # 基线
    baseline: tuple[float, float] | None = (-0.5, -0.1)
    baseline_mode: Literal["mean", "ratio", "logratio", "zscore", "percent"] = "logratio"
    
    # 颜色
    vmin: float | None = None
    vmax: float | None = None
    cmap: str = "RdBu_r"
    
    # 地形图
    show_topomap: bool = False
    topomap_times: list[float] | None = None
    topomap_freqs: tuple[float, float] | None = None


@dataclass
class ConnectivityPlotConfig(PlotConfig):
    """连通性图配置"""
    # 矩阵
    show_matrix: bool = True
    matrix_cmap: str = "RdBu_r"
    matrix_vmin: float = -1
    matrix_vmax: float = 1
    
    # 图
    show_graph: bool = False
    graph_threshold: float = 0.5
    graph_layout: GraphLayout = "circular"
    node_size: float = 100
    edge_width_scale: float = 2.0
    
    # 3D
    show_3d: bool = False
    brain_surface: bool = True

    # 视图类型（矩阵 / 图 / 3D），由 UI 选择
    visualization_type: str = "连通性矩阵"
    show_brain_surface: bool = True


@dataclass
class TFRParams:
    """时频分析参数（UI ↔ ViewModel 交换用）"""
    method: str = "morlet"
    fmin: float = 1.0
    fmax: float = 50.0
    n_freqs: int = 40
    freqs: list[float] | None = None
    n_cycles: float = 7.0
    n_fft: int = 256
    n_overlap: int = 128
    window: str = "hann"
    baseline: tuple[float, float] | None = None
    baseline_mode: str = "logratio"
    cmap: str = "RdBu_r"
    vmin: float | None = None
    vmax: float | None = None


@dataclass
class StatisticalPlotConfig(PlotConfig):
    """统计图配置"""
    # 类型
    plot_type: StatPlotType = "bar"
    
    # 效应量
    effect_size_type: str = "cohen_d"
    show_confidence: bool = True
    confidence_level: float = 0.95
    
    # 显示
    show_individual_points: bool = True
    point_alpha: float = 0.5
    point_jitter: float = 0.2
    
    # 分组
    group_order: list[str] | None = None
    hue_order: list[str] | None = None
    
    # 显著性标记
    show_significance: bool = True
    significance_brackets: bool = True
    pvalue_format: str = "{:.3f}"


@dataclass
class SourcePlotConfig(PlotConfig):
    """源定位可视化配置"""
    # 表面
    surface: Literal["inflated", "pial", "white", "smooth", "flat"] = "inflated"
    hemi: Literal["lh", "rh", "both", "split"] = "both"
    
    # 视角
    views: list[str] = field(default_factory=lambda: ["lateral", "medial"])
    zoom: float = 1.0
    
    # 颜色
    colormap: str = "RdBu_r"
    clim: tuple[float, float] | Literal["auto"] = "auto"
    transparent: bool = False
    
    # 偶极子
    show_dipoles: bool = True
    dipole_scale: float = 10
    dipole_color: str = "red"
    
    # 连通性
    show_connectivity: bool = False
    connectivity_threshold: float = 0.5


@dataclass
class ReportConfig:
    """报告生成配置"""
    # 基本信息
    title: str = "EEG 分析报告"
    author: str = ""
    institution: str = ""
    date_format: str = "%Y-%m-%d"
    
    # 结构
    include_toc: bool = True
    include_methods: bool = True
    include_results: bool = True
    include_discussion: bool = False
    include_references: bool = False
    
    # 章节
    sections: list[str] = field(default_factory=lambda: [
        "overview", "methods", "preprocessing", "erp", "time_frequency",
        "connectivity", "source_localization", "statistics", "conclusion"
    ])
    
    # 图表
    figure_format: ExportFormat = ExportFormat.PNG
    figure_dpi: int = 300
    figure_width_cm: float = 16
    figure_height_cm: float = 12
    
    # 表格
    table_format: Literal["simple", "grid", "fancy_grid", "pipe", "orgtbl", "jira", "presto", "pretty", "psql", "rst"] = "grid"
    max_table_rows: int = 50
    
    # 输出
    output_format: ExportFormat = ExportFormat.PDF
    output_path: str = ""
    
    # 模板
    template_path: str | None = None
    custom_css: str = ""


# ---- 常用预设 ----
STANDARD_PLOT_CONFIG = PlotConfig()
WAVEFORM_PRESET = WaveformPlotConfig()
SPECTRAL_PRESET = SpectralPlotConfig()
TFR_PRESET = TFRPlotConfig()
CONNECTIVITY_PRESET = ConnectivityPlotConfig()
STATISTICAL_PRESET = StatisticalPlotConfig()
SOURCE_PRESET = SourcePlotConfig()
REPORT_PRESET = ReportConfig()


def create_plot_config(plot_type: PlotType, **overrides: Any) -> PlotConfig:
    """从预设创建绘图配置"""
    presets = {
        PlotType.RAW_WAVEFORM: WAVEFORM_PRESET,
        PlotType.ERP_WAVEFORM: WaveformPlotConfig(figsize=(14, 10), n_channels_per_plot=15),
        PlotType.PSD: SPECTRAL_PRESET,
        PlotType.TFR: TFR_PRESET,
        PlotType.CONNECTIVITY_MATRIX: CONNECTIVITY_PRESET,
        PlotType.STAT_BAR: StatisticalPlotConfig(figsize=(10, 6), plot_type="bar"),
        PlotType.STAT_VIOLIN: StatisticalPlotConfig(figsize=(10, 6), plot_type="violin"),
        PlotType.SOURCE_ESTIMATE: SourcePlotConfig(figsize=(12, 10)),
        PlotType.DIPOLE_3D: SourcePlotConfig(figsize=(10, 10), show_dipoles=True),
    }
    
    if plot_type not in presets:
        raise ValueError(f"未知绘图类型: {plot_type}")
    
    config = presets[plot_type]
    for k, v in overrides.items():
        if hasattr(config, k):
            setattr(config, k, v)
    return config