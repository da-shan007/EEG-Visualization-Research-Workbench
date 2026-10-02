"""工具函数：蒙版加载、标准坐标、通道校验"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np

from eeg_workbench.models.dataset import Montage


# ---- 标准蒙版名称列表 ----
def standard_montage_names() -> list[str]:
    """返回 MNE 内置标准蒙版名称"""
    try:
        import mne
        return sorted(mne.channels.get_builtin_montages())
    except Exception:
        return [
            "standard_1020", "standard_1005", "standard_alphabetic",
            "standard_postfixed", "standard_prefixed", "standard_primed",
            "biosemi16", "biosemi32", "biosemi64", "biosemi128",
            "biosemi160", "biosemi256", "easycap-M1", "easycap-M10",
            "easycap-M42", "EGI_256", "GSN-HydroCel-128", "GSN-HydroCel-256",
        ]


# MNE >= 1.13 重命名（旧名 1.14 移除）：优先新名，旧 MNE 回退旧名
MONTAGE_COMPAT_NAMES = {"standard_1020": "colin27_1020"}


def make_standard_montage_compat(name: str, **kwargs):
    """跨 MNE 版本的标准蒙版构造，自动处理重命名"""
    import mne
    for cand in (MONTAGE_COMPAT_NAMES.get(name), name):
        if cand is None:
            continue
        try:
            return mne.channels.make_standard_montage(cand, **kwargs)
        except Exception:
            continue
    return mne.channels.make_standard_montage(name, **kwargs)


# ---- .elp 解析 (Neuroscan/ Curry 格式) ----
def load_elp(file_path: str) -> Montage | None:
    """加载 .elp 电极坐标文件 (ASCII 格式)

    格式示例：
    32
    Fp1  -30.5  80.2  -5.3
    Fp2   30.5  80.2  -5.3
    ...
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ELP 文件不存在: {file_path}")

    positions = {}
    nasion = None
    lpa = None
    rpa = None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # 首行通常是电极数
    idx = 0
    if lines and lines[0].strip().isdigit():
        idx = 1

    for line in lines[idx:]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            name = parts[0]
            try:
                x, y, z = map(float, parts[1:4])
                # 单位通常是 mm，MNE 需要 m，这里保持 mm 统一
                if name.upper() in ("NASION", "NZ", "Nz"):
                    nasion = (x, y, z)
                elif name.upper() in ("LPA", "A1", "LEFT_EAR"):
                    lpa = (x, y, z)
                elif name.upper() in ("RPA", "A2", "RIGHT_EAR"):
                    rpa = (x, y, z)
                else:
                    positions[name] = (x, y, z)
            except ValueError:
                continue

    if not positions:
        return None

    return Montage(
        name=path.stem,
        positions=positions,
        nasion=nasion,
        lpa=lpa,
        rpa=rpa,
        coord_frame="head",
        custom_meta={"source_file": str(path)}
    )


# ---- .csd 解析 (BrainVision/ASA 格式) ----
def load_csd(file_path: str) -> Montage | None:
    """加载 .csd 电极坐标文件 (BrainVision/ASA 格式)

    格式示例：
    [Channels]
    Ch1=Fp1, -30.5, 80.2, -5.3
    ...
    [Reference]
    Ref=FCz
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSD 文件不存在: {file_path}")

    positions = {}
    nasion = None
    lpa = None
    rpa = None
    in_channels = False

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("["):
                in_channels = line.lower() == "[channels]"
                continue
            if in_channels and "=" in line:
                # Ch1=Fp1, -30.5, 80.2, -5.3
                _, coords = line.split("=", 1)
                parts = [p.strip() for p in coords.split(",")]
                if len(parts) >= 4:
                    name = parts[0]
                    try:
                        x, y, z = map(float, parts[1:4])
                        if name.upper() in ("NASION", "NZ", "Nz"):
                            nasion = (x, y, z)
                        elif name.upper() in ("LPA", "A1"):
                            lpa = (x, y, z)
                        elif name.upper() in ("RPA", "A2"):
                            rpa = (x, y, z)
                        else:
                            positions[name] = (x, y, z)
                    except ValueError:
                        continue

    if not positions:
        return None

    return Montage(
        name=path.stem,
        positions=positions,
        nasion=nasion,
        lpa=lpa,
        rpa=rpa,
        coord_frame="head",
        custom_meta={"source_file": str(path)}
    )


# ---- 通道名称标准化 ----
_1020_ALIASES = {
    "FP1": "Fp1", "FP2": "Fp2", "FPZ": "Fpz",
    "F7": "F7", "F8": "F8", "F3": "F3", "F4": "F4", "FZ": "Fz",
    "T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8",
    "C3": "C3", "C4": "C4", "CZ": "Cz",
    "P3": "P3", "P4": "P4", "PZ": "Pz",
    "O1": "O1", "O2": "O2", "OZ": "Oz",
    "A1": "A1", "A2": "A2",
    "F9": "F9", "F10": "F10",
    "P9": "P9", "P10": "P10",
    "PO3": "PO3", "PO4": "PO4", "POZ": "POz",
    "FT7": "FT7", "FT8": "FT8", "TP7": "TP7", "TP8": "TP8",
}


def normalize_channel_name(name: str) -> str:
    """将通道名标准化为 10-20 标准命名"""
    upper = name.upper().strip()
    return _1020_ALIASES.get(upper, name)


def auto_rename_channels(ch_names: list[str]) -> dict[str, str]:
    """自动重命名通道到标准命名，返回 {old: new} 映射"""
    mapping = {}
    for ch in ch_names:
        new = normalize_channel_name(ch)
        if new != ch:
            mapping[ch] = new
    return mapping


# ---- 通道类型推断 ----
def infer_channel_types(ch_names: list[str]) -> dict[str, str]:
    """根据通道名推断类型 (eeg, eog, ecg, emg, stim, misc)"""
    types = {}
    for ch in ch_names:
        upper = ch.upper()
        if any(x in upper for x in ["EOG", "EOGL", "EOGR", "VEOG", "HEOG"]):
            types[ch] = "eog"
        elif "ECG" in upper or "EKG" in upper:
            types[ch] = "ecg"
        elif "EMG" in upper:
            types[ch] = "emg"
        elif any(x in upper for x in ["STIM", "TRIG", "STATUS", "MARKER", "SYNC"]):
            types[ch] = "stim"
        elif "RESP" in upper or "BREATH" in upper:
            types[ch] = "resp"
        elif "TEMP" in upper:
            types[ch] = "temp"
        elif "GSR" in upper or "EDA" in upper:
            types[ch] = "gsr"
        else:
            types[ch] = "eeg"
    return types


# ---- 数据校验 ----
def validate_dataset_integrity(dataset) -> list[str]:
    """校验数据集完整性，返回警告/错误列表"""
    from eeg_workbench.models.dataset import EEGDataset
    warnings = []

    if not isinstance(dataset, EEGDataset):
        return ["对象不是 EEGDataset"]

    if dataset.data.size == 0:
        warnings.append("数据为空")
        return warnings

    # 形状检查
    if dataset.data.ndim != 2:
        warnings.append(f"数据维度异常: {dataset.data.ndim}D, 期望 2D")

    if dataset.n_channels != dataset.data.shape[0]:
        warnings.append(f"通道数不匹配: ch_names={dataset.n_channels}, data.shape[0]={dataset.data.shape[0]}")

    if dataset.sfreq <= 0:
        warnings.append("采样率无效 (<= 0)")

    # NaN/Inf 检查
    if np.any(np.isnan(dataset.data)):
        warnings.append("数据包含 NaN")
    if np.any(np.isinf(dataset.data)):
        warnings.append("数据包含 Inf")

    # 通道名重复
    if len(set(dataset.ch_names)) != len(dataset.ch_names):
        warnings.append("存在重复通道名")

    # 事件时间越界
    for i, ev in enumerate(dataset.events):
        if ev.onset < 0 or ev.onset > dataset.duration:
            warnings.append(f"事件 {i} ({ev.description}) 时间越界: {ev.onset:.3f}s")

    # 蒙版缺失
    if dataset.montage is None:
        warnings.append("缺少电极蒙版 (无法绘制地形图)")

    return warnings


def validate_montage_coverage(montage: Montage, ch_names: list[str]) -> tuple[list[str], list[str]]:
    """检查蒙版覆盖情况，返回 (有坐标通道, 缺失坐标通道)"""
    has_pos = []
    missing = []
    for ch in ch_names:
        if montage.has_position(ch):
            has_pos.append(ch)
        else:
            missing.append(ch)
    return has_pos, missing