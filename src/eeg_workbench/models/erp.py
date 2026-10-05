"""ERP/ERD/ERS 分析参数模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


class BaselineMode(Enum):
    """基线校正模式"""
    NONE = "none"
    MEAN = "mean"
    RATIO = "ratio"
    LOGRATIO = "logratio"
    ZSCORE = "zscore"


class ERPComponent(Enum):
    """经典 ERP 成分"""
    P1 = "P1"
    N1 = "N1"
    P2 = "P2"
    N2 = "N2"
    P3 = "P3"
    N400 = "N400"
    P600 = "P600"
    CNV = "CNV"
    ERN = "ERN"
    PE = "Pe"
    CUSTOM = "custom"


@dataclass
class EpochParams:
    """Epochs 提取参数"""
    # 事件选择
    event_descriptions: list[str] = field(default_factory=list)  # 如 ["Stimulus/Target", "Stimulus/NonTarget"]
    event_codes: list[int] = field(default_factory=list)         # 如 [1, 2]
    
    # 时间窗
    tmin: float = -0.2
    tmax: float = 0.8
    
    # 基线校正
    baseline: tuple[float, float] | None = (-0.2, 0.0)
    baseline_mode: BaselineMode = BaselineMode.MEAN
    
    # 拒绝阈值
    reject: dict[str, float] | None = None  # {'eeg': 100e-6} 单位 V
    flat: dict[str, float] | None = None    # 扁平通道阈值
    
    # 去伪影
    apply_ica: bool = False
    ica_exclude: list[int] = field(default_factory=list)
    
    # 重采样
    resample_sfreq: float | None = None
    
    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self, sfreq: float) -> list[str]:
        errors = []
        if self.tmin >= self.tmax:
            errors.append("tmin 必须小于 tmax")
        if self.baseline is not None:
            b_tmin, b_tmax = self.baseline
            if b_tmin >= b_tmax:
                errors.append("基线 tmin 必须小于 tmax")
            if b_tmin < self.tmin or b_tmax > self.tmax:
                errors.append("基线窗必须在 epoch 窗内")
        if self.resample_sfreq is not None and self.resample_sfreq <= 0:
            errors.append("重采样频率必须大于 0")
        return errors


@dataclass
class ERPAnalysisParams:
    """ERP 分析参数"""
    # 条件对比
    conditions: dict[str, EpochParams] = field(default_factory=dict)  # 条件名 -> EpochParams
    
    # 平均选项
    average_method: Literal["mean", "median", "robust"] = "mean"
    
    # 差分波
    contrast_pairs: list[tuple[str, str]] = field(default_factory=list)  # [("Target", "NonTarget")]
    
    # 峰值检测
    peak_detection: bool = True
    peak_components: list[ERPComponent] = field(default_factory=lambda: [
        ERPComponent.P1, ERPComponent.N1, ERPComponent.P2, ERPComponent.N2, ERPComponent.P3
    ])
    peak_time_windows: dict[ERPComponent, tuple[float, float]] = field(default_factory=lambda: {
        ERPComponent.P1: (0.05, 0.15),
        ERPComponent.N1: (0.08, 0.18),
        ERPComponent.P2: (0.15, 0.25),
        ERPComponent.N2: (0.2, 0.35),
        ERPComponent.P3: (0.25, 0.5),
    })
    peak_polarity: dict[ERPComponent, Literal["pos", "neg", "both"]] = field(default_factory=lambda: {
        ERPComponent.P1: "pos", ERPComponent.N1: "neg",
        ERPComponent.P2: "pos", ERPComponent.N2: "neg", ERPComponent.P3: "pos",
    })
    
    # 统计检验
    stats_test: Literal["ttest", "wilcoxon", "permutation"] = "permutation"
    n_permutations: int = 1000
    alpha: float = 0.05
    correction: Literal["none", "fdr", "bonferroni", "cluster"] = "cluster"
    
    # 地形图
    topo_times: list[float] = field(default_factory=list)  # 自动使用峰值时刻


@dataclass
class ERDSParams:
    """ERD/ERS 分析参数"""
    # 频段
    bands: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "Alpha": (8, 13),
        "Beta": (13, 30),
        "Gamma": (30, 45),
    })
    
    # 时间窗
    tmin: float = -1.0
    tmax: float = 2.0
    baseline: tuple[float, float] = (-1.0, -0.5)
    
    # 时频参数
    tf_method: str = "morlet"  # morlet, multitaper, stft
    n_cycles: float = 7.0
    
    # 归一化模式
    baseline_mode: BaselineMode = BaselineMode.LOGRATIO
    
    # 条件对比
    conditions: dict[str, EpochParams] = field(default_factory=dict)
    
    # 统计
    stats_test: Literal["ttest", "permutation"] = "permutation"
    n_permutations: int = 1000
    alpha: float = 0.05
    correction: Literal["none", "fdr", "cluster"] = "cluster"


@dataclass
class ERPResult:
    """ERP 分析结果"""
    # 条件平均
    evokeds: dict[str, Any] = field(default_factory=dict)  # 条件名 -> mne.Evoked
    
    # 差分波
    contrasts: dict[str, Any] = field(default_factory=dict)  # 对比名 -> mne.Evoked
    
    # 峰值检测结果
    peaks: dict[str, dict[ERPComponent, dict]] = field(default_factory=dict)
    # {条件名: {成分: {"latency": float, "amplitude": float, "channel": str}}}
    
    # 统计结果
    stats: dict[str, Any] = field(default_factory=dict)
    
    # 地形图数据
    topomaps: dict[str, Any] = field(default_factory=dict)
    
    # 原始 Epochs 数据
    epochs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ERPAnalysisResult:
    """ERP 分析结果"""
    # 条件平均
    evokeds: dict[str, Any] = field(default_factory=dict)  # 条件名 -> mne.Evoked
    
    # 差分波
    contrasts: dict[str, Any] = field(default_factory=dict)  # 对比名 -> mne.Evoked
    
    # 峰值检测结果
    peaks: dict[str, dict[ERPComponent, dict]] = field(default_factory=dict)
    # {条件名: {成分: {"latency": float, "amplitude": float, "channel": str}}}
    
    # 统计结果
    stats: dict[str, Any] = field(default_factory=dict)
    
    # 地形图数据
    topomaps: dict[str, Any] = field(default_factory=dict)
    
    # 原始 Epochs 数据
    epochs: dict[str, Any] = field(default_factory=dict)


@dataclass
class PeakResult:
    """峰值检测结果"""
    component: ERPComponent
    latency: float          # 峰值潜伏期 (秒)
    amplitude: float        # 峰值幅度 (µV)
    channel: str            # 峰值通道
    polarity: str           # "positive" / "negative"
    time_window: tuple[float, float]
    all_candidates: list[dict] | None = None  # 所有候选峰值


@dataclass
class ERDSResult:
    """ERD/ERS 分析结果"""
    # 时频图
    tfrs: dict[str, Any] = field(default_factory=dict)  # 条件名 -> mne.time_frequency.EpochsTFR
    
    # 平均 TFR
    avg_tfrs: dict[str, Any] = field(default_factory=dict)
    
    # 差分 TFR
    contrast_tfrs: dict[str, Any] = field(default_factory=dict)
    
    # 统计结果
    stats: dict[str, Any] = field(default_factory=dict)
    
    # 频段平均 ERD/ERS
    band_erds: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    # {条件名: {频段名: (n_channels, n_times)}}


@dataclass
class ERDSAnalysisResult:
    """ERD/ERS 分析结果"""
    # 时频图
    tfrs: dict[str, Any] = field(default_factory=dict)  # 条件名 -> mne.time_frequency.EpochsTFR
    
    # 平均 TFR
    avg_tfrs: dict[str, Any] = field(default_factory=dict)
    
    # 差分 TFR
    contrast_tfrs: dict[str, Any] = field(default_factory=dict)
    
    # 统计结果
    stats: dict[str, Any] = field(default_factory=dict)
    
    # 频段平均 ERD/ERS
    band_erds: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    # {条件名: {频段名: (n_channels, n_times)}}


# ---- 常用预设 ----
DEFAULT_ERP_PEAK_WINDOWS = {
    ERPComponent.P1: (0.05, 0.15),
    ERPComponent.N1: (0.08, 0.18),
    ERPComponent.P2: (0.15, 0.25),
    ERPComponent.N2: (0.2, 0.35),
    ERPComponent.P3: (0.25, 0.5),
    ERPComponent.N400: (0.3, 0.5),
    ERPComponent.P600: (0.5, 0.8),
}

DEFAULT_ERP_POLARITY = {
    ERPComponent.P1: "pos", ERPComponent.N1: "neg",
    ERPComponent.P2: "pos", ERPComponent.N2: "neg",
    ERPComponent.P3: "pos", ERPComponent.N400: "neg",
    ERPComponent.P600: "pos",
}


def create_erp_params(
    event_descriptions: list[str],
    tmin: float = -0.2,
    tmax: float = 0.8,
    baseline: tuple[float, float] = (-0.2, 0.0),
    **kwargs
) -> ERPAnalysisParams:
    """快速创建 ERP 分析参数"""
    epoch_params = EpochParams(
        event_descriptions=event_descriptions,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        **kwargs
    )
    # 将所有事件归为同一条件
    cond_name = "Condition"
    return ERPAnalysisParams(conditions={cond_name: epoch_params})


def create_erds_params(
    event_descriptions: list[str],
    bands: dict[str, tuple[float, float]] | None = None,
    tmin: float = -1.0,
    tmax: float = 2.0,
    baseline: tuple[float, float] = (-1.0, -0.5),
    **kwargs
) -> ERDSParams:
    """快速创建 ERD/ERS 分析参数"""
    epoch_params = EpochParams(
        event_descriptions=event_descriptions,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        **kwargs
    )
    cond_name = "Condition"
    return ERDSParams(
        conditions={cond_name: epoch_params},
        bands=bands or {"Alpha": (8, 13), "Beta": (13, 30)},
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
    )