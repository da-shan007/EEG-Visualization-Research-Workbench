"""坏道插值服务：球面插值、最近邻平均、样条插值"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.preprocessing import (
    BadChannelInterpolationParams, InterpolationMethod
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class InterpolationResult:
    dataset: EEGDataset
    params_used: BadChannelInterpolationParams
    processing_time_ms: float
    interpolated_channels: list[str] = field(default_factory=list)


class InterpolationService:
    """坏道插值服务"""

    @staticmethod
    def apply(
        dataset: EEGDataset,
        params: BadChannelInterpolationParams,
        *,
        copy: bool = True,
        verbose: bool = False
    ) -> InterpolationResult:
        """应用坏道插值"""
        start_time = time.perf_counter()

        # 确定待插值通道
        bad_channels = params.bad_channels
        if not bad_channels:
            # 自动使用已标记的坏道
            bad_channels = dataset.bad_channels

        if not bad_channels:
            raise ValueError("没有坏道需要插值")

        # 验证通道存在
        missing = [ch for ch in bad_channels if ch not in dataset.ch_names]
        if missing:
            raise ValueError(f"坏道不存在: {missing}")

        raw = dataset.to_mne_raw(copy=copy)

        # 标记坏道
        raw.info["bads"] = bad_channels

        # 获取蒙版位置
        montage = raw.get_montage()
        if montage is None and params.method == InterpolationMethod.SPHERICAL:
            # 尝试使用标准蒙版
            try:
                from eeg_workbench.utils.montage import make_standard_montage_compat
                std_montage = make_standard_montage_compat("standard_1020")
                raw.set_montage(std_montage, on_missing="warn")
                montage = std_montage
            except Exception:
                pass

        # 执行插值
        if params.method == InterpolationMethod.SPHERICAL:
            raw.interpolate_bads(reset_bads=params.reset_bads, verbose=verbose)
            method_info = "spherical"
        elif params.method == InterpolationMethod.NEAREST:
            # 最近邻平均 (手动实现)
            raw = InterpolationService._nearest_neighbor_interpolation(raw, bad_channels, verbose)
            method_info = "nearest_neighbor"
        elif params.method == InterpolationMethod.SPLINE:
            # 样条插值 (需要位置信息)
            raw.interpolate_bads(reset_bads=params.reset_bads, method="spline", verbose=verbose)
            method_info = "spline"
        elif params.method == InterpolationMethod.GAUSSIAN:
            # 高斯过程插值
            raw.interpolate_bads(reset_bads=params.reset_bads, method="gaussian", verbose=verbose)
            method_info = "gaussian"
        else:
            raise ValueError(f"不支持的插值方法: {params.method}")

        # 转回 EEGDataset
        new_dataset = EEGDataset.from_mne_raw(
            raw,
            name=f"{dataset.name}_interpolated",
            file_path=dataset.file_path
        )

        new_dataset = replace(
            new_dataset,
            id=dataset.id,
            metadata=dataset.metadata,
            events=dataset.events,
            annotations=dataset.annotations,
            montage=dataset.montage,
            processing_history=dataset.processing_history + [{
                "step": "interpolate_bads",
                "params": InterpolationService._params_to_dict(params, bad_channels),
                "duration_ms": (time.perf_counter() - start_time) * 1000,
                "input_shape": (dataset.n_channels, dataset.n_samples),
                "output_shape": (new_dataset.n_channels, new_dataset.n_samples),
                "interpolated_channels": bad_channels,
            }]
        )

        # 如果重置坏道，更新 channel_info
        if params.reset_bads:
            new_info = new_dataset.channel_info.copy()
            for ch in bad_channels:
                if ch in new_info:
                    from eeg_workbench.models.dataset import ChannelInfo
                    old = new_info[ch]
                    new_info[ch] = ChannelInfo(
                        name=old.name, type=old.type, unit=old.unit,
                        location=old.location, montage_name=old.montage_name,
                        is_bad=False, custom_meta=old.custom_meta
                    )
            new_dataset = replace(new_dataset, channel_info=new_info)

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=new_dataset.id,
                step="interpolate_bads",
                params=InterpolationService._params_to_dict(params, bad_channels)
            ),
            source="InterpolationService"
        )

        return InterpolationResult(
            dataset=new_dataset,
            params_used=params,
            processing_time_ms=elapsed,
            interpolated_channels=bad_channels
        )

    @staticmethod
    def _nearest_neighbor_interpolation(raw, bad_channels: list[str], verbose: bool = False):
        """最近邻平均插值 (不依赖位置信息)"""
        from scipy.spatial.distance import cdist
        import mne

        data = raw.get_data()
        ch_names = raw.ch_names
        bad_idx = [ch_names.index(ch) for ch in bad_channels]
        good_idx = [i for i in range(len(ch_names)) if i not in bad_idx]

        if not good_idx:
            raise ValueError("没有良好通道可用于插值")

        # 获取通道位置 (如果有)
        montage = raw.get_montage()
        if montage and montage.ch_pos:
            positions = np.array([montage.ch_pos.get(ch, [0,0,0]) for ch in ch_names])
        else:
            # 使用标准 10-20 位置估计
            positions = np.zeros((len(ch_names), 3))
            # 简单的二维网格近似
            for i, ch in enumerate(ch_names):
                # 这里只是占位，实际应使用标准位置
                positions[i] = [i % 10, i // 10, 0]

        for b_idx in bad_idx:
            # 找最近的良好通道
            dists = cdist([positions[b_idx]], positions[good_idx])[0]
            nearest_good = good_idx[np.argmin(dists)]
            # 用最近邻替换
            data[b_idx] = data[nearest_good]
            if verbose:
                print(f"  插值 {ch_names[b_idx]} <- {ch_names[nearest_good]}")

        # 创建新 Raw
        new_raw = raw.copy()
        new_raw._data = data
        return new_raw

    @staticmethod
    def _params_to_dict(params: BadChannelInterpolationParams, bad_channels: list[str]) -> dict:
        return {
            "method": params.method.value,
            "bad_channels": bad_channels,
            "reset_bads": params.reset_bads,
        }

    @classmethod
    def spherical(cls, dataset: EEGDataset, bad_channels: list[str] = None, **kwargs) -> InterpolationResult:
        params = BadChannelInterpolationParams(
            method=InterpolationMethod.SPHERICAL,
            bad_channels=bad_channels or [],
            **kwargs
        )
        return cls.apply(dataset, params)

    @classmethod
    def nearest_neighbor(cls, dataset: EEGDataset, bad_channels: list[str] = None, **kwargs) -> InterpolationResult:
        params = BadChannelInterpolationParams(
            method=InterpolationMethod.NEAREST,
            bad_channels=bad_channels or [],
            **kwargs
        )
        return cls.apply(dataset, params)

    @classmethod
    def spline(cls, dataset: EEGDataset, bad_channels: list[str] = None, **kwargs) -> InterpolationResult:
        params = BadChannelInterpolationParams(
            method=InterpolationMethod.SPLINE,
            bad_channels=bad_channels or [],
            **kwargs
        )
        return cls.apply(dataset, params)


def interpolate_bads(
    dataset: EEGDataset,
    params: BadChannelInterpolationParams,
    **kwargs
) -> InterpolationResult:
    return InterpolationService.apply(dataset, params, **kwargs)


# 需要导入 field
from dataclasses import field