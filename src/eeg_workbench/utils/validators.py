"""数据校验器：文件格式、参数范围、业务规则"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np


# ---- 文件格式校验 ----
def validate_eeg_file(file_path: str) -> tuple[bool, str]:
    """快速校验文件是否为有效 EEG 格式（不完全加载）"""
    path = Path(file_path)
    if not path.exists():
        return False, "文件不存在"

    ext = path.suffix.lower()
    valid_exts = {".edf", ".bdf", ".vhdr", ".vmrk", ".eeg", ".set", ".fdt", ".csv", ".tsv", ".txt", ".xlsx", ".xls"}

    if ext not in valid_exts:
        return False, f"不支持的扩展名: {ext}"

    # 简单魔数/头部检查
    try:
        with open(file_path, "rb") as f:
            header = f.read(256)

        if ext in (".edf", ".bdf"):
            if not header.startswith(b"0       "):  # EDF/BDF 版本号
                return False, "不是有效的 EDF/BDF 文件"
        elif ext == ".set":
            # MATLAB .mat 文件魔数
            if not (header[:4] == b"MATLAB" or header[:4] == b"\x00\x00\x00\x00"):
                return False, "不是有效的 EEGLAB .set 文件"
        elif ext == ".vhdr":
            text = header.decode("utf-8", errors="ignore")
            if "BrainVision Data Exchange Header File" not in text:
                return False, "不是有效的 BrainVision .vhdr 文件"
        elif ext in (".csv", ".tsv", ".txt"):
            # 至少要有内容
            if len(header.strip()) == 0:
                return False, "文件为空"
    except Exception as e:
        return False, f"读取文件头失败: {e}"

    return True, "OK"


# ---- 参数范围校验 ----
class ParameterValidator:
    """预处理/分析参数校验器"""

    # 频率范围 (Hz)
    FREQ_RANGES = {
        "highpass": (0.01, 100),
        "lowpass": (0.1, 500),
        "bandpass": (0.01, 500),
        "notch": (1, 200),
    }

    # 采样率范围
    SFREQ_RANGE = (1, 10000)

    # 时间范围 (秒)
    TIME_RANGE = (-3600, 3600)  # ±1 小时

    @classmethod
    def validate_filter_params(cls, l_freq: float | None, h_freq: float | None,
                                notch_freq: float | None = None) -> list[str]:
        """校验滤波参数"""
        errors = []
        if l_freq is not None:
            lo, hi = cls.FREQ_RANGES["highpass"]
            if not (lo <= l_freq <= hi):
                errors.append(f"高通频率超出范围 [{lo}, {hi}]: {l_freq}")
        if h_freq is not None:
            lo, hi = cls.FREQ_RANGES["lowpass"]
            if not (lo <= h_freq <= hi):
                errors.append(f"低通频率超出范围 [{lo}, {hi}]: {h_freq}")
        if l_freq is not None and h_freq is not None:
            if l_freq >= h_freq:
                errors.append(f"高通频率 ({l_freq}) 必须小于低通频率 ({h_freq})")
        if notch_freq is not None:
            lo, hi = cls.FREQ_RANGES["notch"]
            if not (lo <= notch_freq <= hi):
                errors.append(f"陷波频率超出范围 [{lo}, {hi}]: {notch_freq}")
        return errors

    @classmethod
    def validate_resample_sfreq(cls, sfreq: float) -> list[str]:
        """校验重采样目标采样率"""
        errors = []
        lo, hi = cls.SFREQ_RANGE
        if not (lo <= sfreq <= hi):
            errors.append(f"采样率超出范围 [{lo}, {hi}]: {sfreq}")
        return errors

    @classmethod
    def validate_time_range(cls, tmin: float, tmax: float, max_duration: float) -> list[str]:
        """校验时间范围"""
        errors = []
        lo, hi = cls.TIME_RANGE
        if not (lo <= tmin <= hi):
            errors.append(f"tmin 超出范围 [{lo}, {hi}]: {tmin}")
        if not (lo <= tmax <= hi):
            errors.append(f"tmax 超出范围 [{lo}, {hi}]: {tmax}")
        if tmin >= tmax:
            errors.append(f"tmin ({tmin}) 必须小于 tmax ({tmax})")
        if tmax > max_duration:
            errors.append(f"tmax ({tmax}) 超出数据时长 ({max_duration})")
        return errors

    @classmethod
    def validate_epoch_params(cls, tmin: float, tmax: float,
                               baseline: tuple[float, float] | None = None) -> list[str]:
        """校验 Epoch 参数"""
        errors = cls.validate_time_range(tmin, tmax, 3600)
        if baseline is not None:
            b_tmin, b_tmax = baseline
            if b_tmin >= b_tmax:
                errors.append(f"基线 tmin ({b_tmin}) 必须小于 tmax ({b_tmax})")
            if b_tmin < tmin or b_tmax > tmax:
                errors.append(f"基线窗 [{b_tmin}, {b_tmax}] 必须在 epoch 窗 [{tmin}, {tmax}] 内")
        return errors


# ---- 业务规则校验 ----
def validate_reference_channels(dataset, ref_channels: list[str]) -> list[str]:
    """校验参考电极通道是否存在"""
    errors = []
    missing = [ch for ch in ref_channels if ch not in dataset.ch_names]
    if missing:
        errors.append(f"参考电极通道不存在: {missing}")
    return errors


def validate_bad_channels(dataset, bad_channels: list[str]) -> list[str]:
    """校验坏道标记"""
    errors = []
    missing = [ch for ch in bad_channels if ch not in dataset.ch_names]
    if missing:
        errors.append(f"标记的坏道不存在: {missing}")
    if len(bad_channels) >= dataset.n_channels:
        errors.append("坏道数量不能大于等于总通道数")
    return errors


def validate_event_consistency(dataset) -> list[str]:
    """校验事件一致性"""
    from eeg_workbench.models.dataset import Event
    warnings = []

    if not dataset.events:
        return warnings

    # 事件时间单调性
    onsets = [ev.onset for ev in dataset.events]
    if onsets != sorted(onsets):
        warnings.append("事件未按时间排序")

    # 重复事件检测
    seen = set()
    for i, ev in enumerate(dataset.events):
        key = (round(ev.onset, 6), ev.description, ev.value)
        if key in seen:
            warnings.append(f"疑似重复事件 index={i}: {ev.description} @ {ev.onset:.3f}s")
        seen.add(key)

    # 事件超出数据范围
    for ev in dataset.events:
        if ev.onset < 0 or ev.onset > dataset.duration:
            warnings.append(f"事件时间越界: {ev.description} @ {ev.onset:.3f}s (数据时长 {dataset.duration:.3f}s)")

    return warnings


# ---- 导出校验结果汇总 ----
class ValidationResult:
    """校验结果容器"""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_info(self, msg: str) -> None:
        self.info.append(msg)

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"错误({len(self.errors)}): " + "; ".join(self.errors[:3]))
        if self.warnings:
            parts.append(f"警告({len(self.warnings)}): " + "; ".join(self.warnings[:3]))
        if self.info:
            parts.append(f"信息({len(self.info)}): " + "; ".join(self.info[:3]))
        return " | ".join(parts) if parts else "校验通过"

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
        }


def validate_dataset_complete(dataset) -> ValidationResult:
    """完整数据集校验（加载后调用）"""
    from eeg_workbench.utils.montage import validate_dataset_integrity
    from eeg_workbench.utils.validators import validate_event_consistency

    result = ValidationResult()

    # 基础完整性
    for w in validate_dataset_integrity(dataset):
        result.add_warning(w)

    # 事件一致性
    for w in validate_event_consistency(dataset):
        result.add_warning(w)

    # 蒙版覆盖
    if dataset.montage:
        from eeg_workbench.utils.montage import validate_montage_coverage
        has_pos, missing = validate_montage_coverage(dataset.montage, dataset.ch_names)
        if missing:
            result.add_info(f"{len(missing)} 个通道缺少坐标 (共 {dataset.n_channels} 通道)")
        else:
            result.add_info("所有通道均有坐标")

    # 采样率合理性
    if dataset.sfreq < 50:
        result.add_warning(f"采样率较低 ({dataset.sfreq} Hz)，可能影响高频分析")
    elif dataset.sfreq > 2000:
        result.add_warning(f"采样率极高 ({dataset.sfreq} Hz)，注意存储/计算开销")

    # 数据时长
    if dataset.duration < 1:
        result.add_warning(f"数据时长极短 ({dataset.duration:.2f}s)")
    elif dataset.duration > 7200:
        result.add_info(f"长时程记录 ({dataset.duration/3600:.1f} 小时)")

    return result