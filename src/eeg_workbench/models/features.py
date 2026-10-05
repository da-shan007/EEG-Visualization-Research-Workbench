"""特征提取参数模型：频段分析、时频分析、连通性分析、非线性分析"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


class SpectralMethod(Enum):
    """功率谱估计方法"""
    WELCH = "welch"           # Welch 方法 (默认)
    MULTITAPER = "multitaper" # 多锥谱估计
    PERIODOGRAM = "periodogram" # 周期图
    FFT = "fft"               # 直接 FFT


class TimeFrequencyMethod(Enum):
    """时频分析方法"""
    STFT = "stft"             # 短时傅里叶变换
    MORLET = "morlet"         # Morlet 小波
    STOCKWELL = "stockwell"   # S 变换
    MULTITAPER = "multitaper" # 多锥时频


class ConnectivityMethod(Enum):
    """连通性分析方法"""
    COHERENCE = "coherence"           # 相干性
    IMAG_COHERENCE = "imag_coherence" # 虚部相干性
    PLV = "plv"                       # 相位锁定值
    PLI = "pli"                       # 相位滞后指数
    WPLI = "wpli"                     # 加权 PLI
    GCA = "gca"                       # 格兰杰因果
    DTF = "dtf"                       # 定向传递函数
    PDC = "pdc"                       # 偏定向传递函数


class NonlinearMeasure(Enum):
    """非线性指标"""
    SAMPLE_ENTROPY = "sample_entropy"     # 样本熵
    APPROX_ENTROPY = "approx_entropy"     # 近似熵
    PERMUTATION_ENTROPY = "perm_entropy"  # 排列熵
    HURST_EXPONENT = "hurst"              # Hurst 指数
    DETRENDED_FA = "dfa"                  # 去趋势波动分析
    LYAPUNOV = "lyapunov"                 # Lyapunov 指数
    CORRELATION_DIM = "corr_dim"          # 相关维数
    LZ_COMPLEXITY = "lz_complexity"       # Lempel-Ziv 复杂度


@dataclass
class BandPowerParams:
    """频段功率参数"""
    # 频段定义
    bands: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "Delta": (0.5, 4),
        "Theta": (4, 8),
        "Alpha": (8, 13),
        "Beta": (13, 30),
        "Gamma": (30, 45),
        "HighGamma": (60, 100),
    })
    
    # 谱估计参数
    method: SpectralMethod = SpectralMethod.WELCH
    n_fft: int = 256
    n_overlap: int = 128
    n_per_seg: int | None = None
    window: str = "hann"
    
    # 输出选项
    relative: bool = True      # 相对功率
    log_transform: bool = False # 对数变换
    normalize: bool = False     # 归一化
    
    # 通道选择
    picks: list[str] | str | None = None  # 'eeg', 'data', 或通道名列表
    
    # 多锥参数
    bandwidth: float = 4.0      # 多锥带宽
    adaptive: bool = True       # 自适应多锥
    
    def validate(self, sfreq: float) -> list[str]:
        errors = []
        for name, (low, high) in self.bands.items():
            if low >= high:
                errors.append(f"频段 {name}: 低频 ({low}) 必须小于高频 ({high})")
            if high > sfreq / 2:
                errors.append(f"频段 {name}: 高频 ({high}) 超过奈奎斯特频率 ({sfreq/2})")
        if self.n_fft <= 0:
            errors.append("n_fft 必须大于 0")
        if self.n_overlap >= self.n_fft:
            errors.append("n_overlap 必须小于 n_fft")
        return errors


@dataclass
class TimeFrequencyParams:
    """时频分析参数"""
    # 频率范围
    freqs: np.ndarray | None = None  # 目标频率数组
    fmin: float = 1.0
    fmax: float = 100.0
    n_freqs: int = 50                # 频率点数 (log 间隔)
    
    # 时间窗参数
    method: TimeFrequencyMethod = TimeFrequencyMethod.MORLET
    n_cycles: float | np.ndarray = 7.0  # Morlet 周期数
    time_bandwidth: float = 4.0         # 多锥时带宽积
    n_tapers: int | None = None         # 多锥数量
    
    # STFT 参数
    n_fft: int = 256
    n_overlap: int = 128
    window: str = "hann"
    
    # 输出选项
    output: Literal["power", "phase", "complex"] = "power"
    baseline: tuple[float, float] | None = None  # 基线校正 (tmin, tmax)
    baseline_mode: Literal["mean", "ratio", "logratio", "zscore"] = "logratio"
    decim: int = 1                        # 时间降采样
    
    # 通道选择
    picks: list[str] | str | None = None
    
    # 平均选项
    average: bool = False     # 试次平均
    average_method: str = "mean"
    
    def validate(self, sfreq: float, n_times: int) -> list[str]:
        errors = []
        if self.fmin >= self.fmax:
            errors.append("fmin 必须小于 fmax")
        if self.fmax > sfreq / 2:
            errors.append(f"fmax ({self.fmax}) 超过奈奎斯特频率 ({sfreq/2})")
        if self.method == TimeFrequencyMethod.MORLET:
            if isinstance(self.n_cycles, (int, float)) and self.n_cycles <= 0:
                errors.append("n_cycles 必须大于 0")
        if self.n_fft <= 0:
            errors.append("n_fft 必须大于 0")
        if self.decim <= 0:
            errors.append("decim 必须大于 0")
        return errors

    def __post_init__(self):
        if self.freqs is None:
            self.freqs = np.logspace(
                np.log10(self.fmin), np.log10(self.fmax), self.n_freqs
            )


@dataclass
class ConnectivityParams:
    """连通性分析参数"""
    method: ConnectivityMethod = ConnectivityMethod.COHERENCE
    
    # 频率范围
    fmin: float = 0.0
    fmax: float | None = None  # None = 奈奎斯特
    n_freqs: int = 20          # 频率点数
    
    # 时间窗
    tmin: float = 0.0
    tmax: float | None = None
    
    # 方法特定参数
    # GCA 参数
    gca_order: int = 10        # 模型阶数
    gca_n_fft: int = 256
    
    # PLV/PLI 参数
    n_cycles: float = 7.0
    
    # 通道选择
    picks: list[str] | str | None = None
    indices: tuple[np.ndarray, np.ndarray] | None = None  # (seed, target) 索引对
    
    # 统计检验
    n_permutations: int = 0    # 置换检验次数 (0=不做)
    tail: int = 0              # 0=双尾, 1=单尾
    alpha: float = 0.05
    
    # 输出选项
    average: bool = False      # 试次平均
    
    def validate(self, sfreq: float, n_channels: int) -> list[str]:
        errors = []
        if self.fmin < 0:
            errors.append("fmin 不能小于 0")
        if self.fmax is not None and self.fmax > sfreq / 2:
            errors.append(f"fmax 超过奈奎斯特频率 ({sfreq/2})")
        if self.method in (ConnectivityMethod.GCA, ConnectivityMethod.DTF, ConnectivityMethod.PDC):
            if self.gca_order <= 0:
                errors.append("gca_order 必须大于 0")
        if self.n_permutations < 0:
            errors.append("n_permutations 不能小于 0")
        return errors


@dataclass
class NonlinearParams:
    """非线性分析参数"""
    measures: list[NonlinearMeasure] = field(default_factory=lambda: [
        NonlinearMeasure.SAMPLE_ENTROPY,
        NonlinearMeasure.PERMUTATION_ENTROPY,
        NonlinearMeasure.HURST_EXPONENT,
    ])
    
    # 样本熵参数
    sample_entropy_m: int = 2
    sample_entropy_r: float = 0.2  # 容差倍数 (乘以 std)
    
    # 排列熵参数
    perm_entropy_order: int = 3
    perm_entropy_delay: int = 1
    
    # DFA 参数
    dfa_scales: np.ndarray | None = None
    
    # Lyapunov 参数
    lyap_min_sep: int = 10
    lyap_max_iter: int = 1000
    
    # 通用参数
    picks: list[str] | str | None = None
    n_jobs: int = -1
    
    def validate(self, n_samples: int) -> list[str]:
        errors = []
        if NonlinearMeasure.SAMPLE_ENTROPY in self.measures:
            if self.sample_entropy_m <= 0:
                errors.append("sample_entropy_m 必须大于 0")
            if n_samples < 10 ** (self.sample_entropy_m + 1):
                errors.append(f"样本数 ({n_samples}) 可能不足以计算样本熵 (建议 > {10**(self.sample_entropy_m+1)})")
        if NonlinearMeasure.PERMUTATION_ENTROPY in self.measures:
            if self.perm_entropy_order <= 1:
                errors.append("perm_entropy_order 必须大于 1")
        if NonlinearMeasure.DETRENDED_FA in self.measures:
            if self.dfa_scales is not None and len(self.dfa_scales) < 4:
                errors.append("dfa_scales 至少需要 4 个尺度")
        return errors


@dataclass
class FeatureExtractionResult:
    """特征提取结果容器"""
    # 频段功率
    band_power: dict[str, np.ndarray] | None = None      # (n_channels, n_bands) 或 (n_epochs, n_channels, n_bands)
    band_power_freqs: dict[str, tuple[float, float]] | None = None
    
    # 时频图
    time_frequency: np.ndarray | None = None             # (n_channels, n_freqs, n_times) 或 (n_epochs, ...)
    tf_freqs: np.ndarray | None = None
    tf_times: np.ndarray | None = None
    
    # 连通性矩阵
    connectivity: np.ndarray | None = None               # (n_channels, n_channels) 或 (n_freqs, n_channels, n_channels)
    conn_freqs: np.ndarray | None = None
    conn_method: str | None = None
    
    # 非线性指标
    nonlinear: dict[str, np.ndarray] | None = None       # {measure_name: (n_channels,) 或 (n_epochs, n_channels)}
    
    # 元信息
    params: Any = None
    processing_time_ms: float = 0.0
    ch_names: list[str] = field(default_factory=list)
    sfreq: float = 0.0


# ---- 常用频段预设 ----
STANDARD_BANDS: dict[str, tuple[float, float]] = {
    "Delta": (0.5, 4),
    "Theta": (4, 8),
    "Alpha": (8, 13),
    "Beta": (13, 30),
    "Gamma": (30, 45),
}

ERP_BANDS: dict[str, tuple[float, float]] = {
    "Delta": (1, 4),
    "Theta": (4, 7),
    "Alpha": (8, 12),
    "Beta": (13, 30),
    "Gamma": (30, 50),
}

MICRO_BANDS: dict[str, tuple[float, float]] = {
    "SlowDelta": (0.1, 1),
    "Delta": (1, 4),
    "Theta": (4, 8),
    "Alpha1": (8, 10),
    "Alpha2": (10, 12),
    "Beta1": (12, 20),
    "Beta2": (20, 30),
    "Gamma": (30, 45),
    "HighGamma": (60, 90),
}

CUSTOM_BAND_PRESETS: dict[str, dict[str, tuple[float, float]]] = {
    "standard": STANDARD_BANDS,
    "erp": ERP_BANDS,
    "micro": MICRO_BANDS,
}


def create_band_power_params(preset: str = "standard", **overrides) -> BandPowerParams:
    """从预设创建频段功率参数"""
    if preset not in CUSTOM_BAND_PRESETS:
        raise ValueError(f"未知预设: {preset}，可选: {list(CUSTOM_BAND_PRESETS.keys())}")
    bands = CUSTOM_BAND_PRESETS[preset].copy()
    bands.update(overrides.pop("bands", {}))
    return BandPowerParams(bands=bands, **overrides)