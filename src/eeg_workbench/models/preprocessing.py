"""预处理参数模型：滤波、重参考、重采样、ICA、坏道插值配置"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


class FilterType(Enum):
    """滤波器类型"""
    BANDPASS = "bandpass"      # 带通
    HIGHPASS = "highpass"      # 高通
    LOWPASS = "lowpass"        # 低通
    NOTCH = "notch"            # 陷波
    BANDSTOP = "bandstop"      # 带阻


class FilterMethod(Enum):
    """滤波实现方法"""
    FIR = "fir"                # FIR 滤波器 (MNE 默认)
    IIR = "iir"                # IIR 滤波器
    FIRWIN = "firwin"          # scipy.signal.firwin
    BUTTERWORTH = "butterworth" # 巴特沃斯


class ReferenceType(Enum):
    """参考电极类型"""
    AVERAGE = "average"        # 平均参考
    MAStoid = "mastoid"        # 双侧乳突
    CZ = "cz"                  # Cz 单电极
    SINGLE = "single"          # 单电极
    REST = "rest"              # REST 无限大参考
    CUSTOM = "custom"          # 自定义通道组合
    NO_REF = "no_ref"          # 不重参考


class ResampleMethod(Enum):
    """重采样方法"""
    AUTO = "auto"              # 自动选择
    POLY = "poly"              # 多项式重采样 (scipy.signal.resample_poly)
    FFT = "fft"                # FFT 重采样 (scipy.signal.resample)
    KAISER = "kaiser"          # Kaiser 窗
    SINC = "sinc"              # Sinc 插值 (MNE 默认)


class ICAComponentType(Enum):
    """ICA 成分类型"""
    EYE_BLINK = "eye_blink"      # 眨眼
    EYE_MOVEMENT = "eye_movement" # 眼动
    HEARTBEAT = "heartbeat"       # 心跳
    MUSCLE = "muscle"             # 肌肉
    LINE_NOISE = "line_noise"     # 工频干扰
    CHANNEL_NOISE = "channel_noise" # 坏道噪声
    OTHER = "other"               # 其他
    UNKNOWN = "unknown"           # 未知


class InterpolationMethod(Enum):
    """坏道插值方法"""
    NEAREST = "nearest"          # 最近邻平均
    SPHERICAL = "spherical"      # 球面插值 (MNE 默认)
    SPLINE = "spline"            # 样条插值
    GAUSSIAN = "gaussian"        # 高斯过程插值


@dataclass
class FilterParams:
    """滤波参数"""
    # 基础参数
    filter_type: FilterType = FilterType.BANDPASS
    l_freq: Optional[float] = 0.1      # 高通截止频率 (Hz)
    # 默认 None：低通截止需显式指定，否则 BANDPASS/LOWPASS 校验会报错（与 validate 一致）
    h_freq: Optional[float] = None     # 低通截止频率 (Hz)
    
    # 陷波参数
    notch_freq: Optional[float] = 50.0  # 陷波频率 (Hz)
    notch_width: float = 1.0            # 陷波带宽 (Hz)
    
    # 进阶参数
    method: FilterMethod = FilterMethod.FIR
    phase: str = "zero"                 # 'zero', 'zero-double', 'minimum'
    fir_window: str = "hamming"         # FIR 窗函数
    fir_design: str = "firwin"          # FIR 设计方法
    iir_order: int = 4                  # IIR 阶数
    iir_btype: str = "bandpass"         # IIR 滤波器类型
    
    # 边缘处理
    pad: str = "reflect_limited"        # 填充方式
    verbose: bool = False

    def validate(self) -> list[str]:
        """参数校验，返回错误列表"""
        errors = []
        if self.filter_type in (FilterType.BANDPASS, FilterType.HIGHPASS) and self.l_freq is None:
            errors.append("高通/带通滤波需要指定 l_freq")
        if self.filter_type in (FilterType.BANDPASS, FilterType.LOWPASS) and self.h_freq is None:
            errors.append("低通/带通滤波需要指定 h_freq")
        if self.filter_type == FilterType.NOTCH and self.notch_freq is None:
            errors.append("陷波滤波需要指定 notch_freq")
        if self.l_freq is not None and self.h_freq is not None and self.l_freq >= self.h_freq:
            errors.append(f"l_freq ({self.l_freq}) 必须小于 h_freq ({self.h_freq})")
        if self.l_freq is not None and self.l_freq <= 0:
            errors.append("l_freq 必须大于 0")
        if self.h_freq is not None and self.h_freq <= 0:
            errors.append("h_freq 必须大于 0")
        return errors


@dataclass
class ReferenceParams:
    """重参考参数"""
    ref_type: ReferenceType = ReferenceType.AVERAGE
    ref_channels: list[str] = field(default_factory=list)  # 自定义参考通道
    copy: bool = True                # 是否复制数据
    projection: bool = False         # 是否使用投影算子 (不修改数据)
    verbose: bool = False

    def validate(self, available_channels: list[str]) -> list[str]:
        errors = []
        if self.ref_type == ReferenceType.SINGLE:
            if not self.ref_channels:
                errors.append("单电极参考需要指定 ref_channels")
            elif self.ref_channels[0] not in available_channels:
                errors.append(f"参考通道 {self.ref_channels[0]} 不存在")
        elif self.ref_type == ReferenceType.CUSTOM:
            if not self.ref_channels:
                errors.append("自定义参考需要指定 ref_channels")
            missing = [ch for ch in self.ref_channels if ch not in available_channels]
            if missing:
                errors.append(f"参考通道不存在: {missing}")
        elif self.ref_type == ReferenceType.MAStoid:
            # 检查是否有乳突通道
            mastoid_candidates = ["A1", "A2", "M1", "M2", "TP9", "TP10", "FT9", "FT10"]
            found = [ch for ch in available_channels if ch in mastoid_candidates]
            if len(found) < 2:
                errors.append(f"未找到双侧乳突通道 (需要 A1/A2 或 M1/M2 等)，可用: {available_channels}")
        return errors


@dataclass
class ResampleParams:
    """重采样参数"""
    sfreq: float                       # 目标采样率 (Hz)
    method: ResampleMethod = ResampleMethod.AUTO
    npad: str = "auto"                 # 边缘填充
    window: str = "hann"               # 窗函数（MNE 需要可直接解析的窗口名）
    verbose: bool = False

    def validate(self, current_sfreq: float) -> list[str]:
        errors = []
        if self.sfreq <= 0:
            errors.append("目标采样率必须大于 0")
        if self.sfreq > current_sfreq * 4:
            errors.append(f"上采样倍数过大 ({self.sfreq/current_sfreq:.1f}x)，建议分步进行")
        if self.sfreq < current_sfreq / 10:
            errors.append(f"下采样倍数过大 ({current_sfreq/self.sfreq:.1f}x)，注意混叠")
        return errors


@dataclass
class ICAParams:
    """ICA 参数"""
    n_components: Optional[float] = None  # 成分数 (None=自动, <1=方差比例, >=1=固定数)
    method: str = "fastica"               # 'fastica', 'infomax', 'extended-infomax', 'picard'
    random_state: int = 42                # 随机种子
    max_iter: int = 500                   # 最大迭代次数
    tol: float = 1e-4                     # 收敛容差
    
    # 自动识别设置
    auto_find: bool = True                # 是否自动识别伪影成分
    eog_channels: list[str] = field(default_factory=list)  # EOG 通道名
    ecg_channels: list[str] = field(default_factory=list)  # ECG 通道名
    eog_threshold: float = 0.3            # EOG 相关性阈值
    ecg_threshold: float = 0.3            # ECG 相关性阈值
    muscle_threshold: float = 0.5         # 肌肉成分阈值 (高频功率比)
    
    # 计算设置
    decim: int = 3                        # 降采样因子 (加速)
    reject: Optional[dict] = None         # 拒绝阈值 dict(ch_type: threshold)
    verbose: bool = False

    def validate(self, n_channels: int, sfreq: float) -> list[str]:
        errors = []
        if self.n_components is not None:
            if isinstance(self.n_components, float) and 0 < self.n_components < 1:
                pass  # 方差比例
            elif isinstance(self.n_components, int) and self.n_components > n_channels:
                errors.append(f"n_components ({self.n_components}) 不能大于通道数 ({n_channels})")
            elif self.n_components <= 0:
                errors.append("n_components 必须 > 0")
        if self.method not in ("fastica", "infomax", "extended-infomax", "picard"):
            errors.append(f"不支持的 ICA 方法: {self.method}")
        return errors


@dataclass
class BadChannelInterpolationParams:
    """坏道插值参数"""
    method: InterpolationMethod = InterpolationMethod.SPHERICAL
    bad_channels: list[str] = field(default_factory=list)  # 待插值通道
    reset_bads: bool = True             # 插值后重置坏道标记
    verbose: bool = False

    def validate(self, available_channels: list[str], montage_positions: dict) -> list[str]:
        errors = []
        if not self.bad_channels:
            errors.append("未指定待插值的坏道")
        missing = [ch for ch in self.bad_channels if ch not in available_channels]
        if missing:
            errors.append(f"坏道不存在: {missing}")
        if self.method == InterpolationMethod.SPHERICAL:
            # 球面插值需要位置信息
            no_pos = [ch for ch in self.bad_channels if ch not in montage_positions]
            if no_pos:
                errors.append(f"球面插值需要通道坐标，以下通道缺失位置: {no_pos}")
        return errors


@dataclass
class PreprocessingStep:
    """单步预处理记录（用于历史记录/可重现性）"""
    step_type: str                     # 'filter', 'reference', 'resample', 'ica', 'interpolate'
    params: dict                       # 参数字典
    timestamp: str                     # ISO 格式时间戳
    duration_ms: float                 # 耗时 (ms)
    input_shape: tuple[int, int]       # (n_ch, n_samples)
    output_shape: tuple[int, int]
    notes: str = ""                    # 备注


# ---- 便捷预设 ----
FILTER_PRESETS = {
    "standard": FilterParams(l_freq=0.1, h_freq=40.0, notch_freq=50.0),
    "erp": FilterParams(l_freq=0.1, h_freq=30.0, notch_freq=50.0),
    "high_gamma": FilterParams(l_freq=60.0, h_freq=150.0, notch_freq=50.0),
    "resting": FilterParams(l_freq=0.5, h_freq=45.0, notch_freq=50.0),
    # ICA 前只高通：必须显式 filter_type=HIGHPASS（数据类默认是 BANDPASS）
    "ica_prep": FilterParams(filter_type=FilterType.HIGHPASS, l_freq=1.0, h_freq=None, notch_freq=50.0),
}

REFERENCE_PRESETS = {
    "average": ReferenceParams(ref_type=ReferenceType.AVERAGE),
    "mastoid": ReferenceParams(ref_type=ReferenceType.MAStoid),
    "cz": ReferenceParams(ref_type=ReferenceType.CZ),
    "rest": ReferenceParams(ref_type=ReferenceType.REST),
}


def create_filter_params(preset: str, **overrides) -> FilterParams:
    """从预设创建滤波参数"""
    if preset not in FILTER_PRESETS:
        raise ValueError(f"未知预设: {preset}，可选: {list(FILTER_PRESETS.keys())}")
    params = FilterParams(**FILTER_PRESETS[preset].__dict__)
    for k, v in overrides.items():
        setattr(params, k, v)
    return params


def create_reference_params(preset: str, **overrides) -> ReferenceParams:
    """从预设创建参考参数"""
    if preset not in REFERENCE_PRESETS:
        raise ValueError(f"未知预设: {preset}，可选: {list(REFERENCE_PRESETS.keys())}")
    params = ReferenceParams(**REFERENCE_PRESETS[preset].__dict__)
    for k, v in overrides.items():
        setattr(params, k, v)
    return params