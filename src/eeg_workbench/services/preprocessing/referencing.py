"""重参考服务：平均参考、乳突参考、Cz、单电极、REST、自定义"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.preprocessing import ReferenceParams, ReferenceType
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ReferenceResult:
    dataset: EEGDataset
    params_used: ReferenceParams
    processing_time_ms: float
    # apply() 的每条分支都保证传入 dict；default_factory 只是让“裸构造”
    # 的测试/调用方也拿到 dict 而不是 None，VM 可直接 .get 无需判空
    ref_info: dict[str, Any] = field(default_factory=dict)


class ReferenceService:
    """重参考服务"""

    @staticmethod
    def apply(
        dataset: EEGDataset,
        params: ReferenceParams,
        *,
        copy: bool = True,
        verbose: bool = False
    ) -> ReferenceResult:
        """应用重参考"""
        start_time = time.perf_counter()

        raw = dataset.to_mne_raw(copy=copy)

        # 根据参考类型处理（显式标注：各分支的值类型不同，有 list 也有 str）
        ref_info: dict[str, Any]
        if params.ref_type == ReferenceType.AVERAGE:
            # 平均参考
            raw.set_eeg_reference(ref_channels="average", projection=params.projection, verbose=verbose)
            ref_info = {"type": "average", "channels": "all_eeg"}

        elif params.ref_type == ReferenceType.CZ:
            # Cz 参考
            if "Cz" not in raw.ch_names and "CZ" not in raw.ch_names:
                raise ValueError("数据集中未找到 Cz 通道")
            cz_name = "Cz" if "Cz" in raw.ch_names else "CZ"
            raw.set_eeg_reference(ref_channels=[cz_name], projection=params.projection, verbose=verbose)
            ref_info = {"type": "cz", "channel": cz_name}

        elif params.ref_type == ReferenceType.MAStoid:
            # 双侧乳突参考
            mastoid_chs = ReferenceService._find_mastoid_channels(raw.ch_names)
            if len(mastoid_chs) < 2:
                raise ValueError(f"未找到双侧乳突通道，可用通道: {raw.ch_names}")
            raw.set_eeg_reference(ref_channels=mastoid_chs[:2], projection=params.projection, verbose=verbose)
            ref_info = {"type": "mastoid", "channels": mastoid_chs[:2]}

        elif params.ref_type == ReferenceType.SINGLE:
            # 单电极参考
            if not params.ref_channels:
                raise ValueError("单电极参考需要指定 ref_channels")
            raw.set_eeg_reference(ref_channels=params.ref_channels, projection=params.projection, verbose=verbose)
            ref_info = {"type": "single", "channel": params.ref_channels[0]}

        elif params.ref_type == ReferenceType.CUSTOM:
            # 自定义通道组合参考
            if not params.ref_channels:
                raise ValueError("自定义参考需要指定 ref_channels")
            raw.set_eeg_reference(ref_channels=params.ref_channels, projection=params.projection, verbose=verbose)
            ref_info = {"type": "custom", "channels": params.ref_channels}

        elif params.ref_type == ReferenceType.REST:
            # REST 无限大参考 (需要 MNE-REST 插件或自行实现)
            try:
                # 尝试使用 mne.preprocessing.reference.REST
                from mne.preprocessing import reference
                raw = reference.rest_reference(raw, verbose=verbose)
                ref_info = {"type": "rest"}
            except ImportError:
                raise RuntimeError("REST 参考需要安装 mne-rest 插件: pip install mne-rest")

        elif params.ref_type == ReferenceType.NO_REF:
            # 不重参考，直接返回
            ref_info = {"type": "none"}
            new_dataset = dataset
            elapsed = (time.perf_counter() - start_time) * 1000
            return ReferenceResult(
                dataset=new_dataset,
                params_used=params,
                processing_time_ms=elapsed,
                ref_info=ref_info
            )

        else:
            raise ValueError(f"不支持的参考类型: {params.ref_type}")

        # 转回 EEGDataset
        new_dataset = EEGDataset.from_mne_raw(
            raw,
            name=f"{dataset.name}_reref",
            file_path=dataset.file_path
        )

        # 保留元数据和事件
        new_dataset = replace(
            new_dataset,
            id=dataset.id,
            metadata=dataset.metadata,
            events=dataset.events,
            annotations=dataset.annotations,
            montage=dataset.montage,
            processing_history=dataset.processing_history + [{
                "step": "reference",
                "params": ReferenceService._params_to_dict(params),
                "duration_ms": (time.perf_counter() - start_time) * 1000,
                "input_shape": (dataset.n_channels, dataset.n_samples),
                "output_shape": (new_dataset.n_channels, new_dataset.n_samples),
            }]
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=new_dataset.id,
                step="reference",
                params=ReferenceService._params_to_dict(params)
            ),
            source="ReferenceService"
        )

        return ReferenceResult(
            dataset=new_dataset,
            params_used=params,
            processing_time_ms=elapsed,
            ref_info=ref_info
        )

    @staticmethod
    def _find_mastoid_channels(ch_names: list[str]) -> list[str]:
        """查找乳突通道"""
        candidates = [
            ("A1", "A2"),    # 标准 10-20
            ("M1", "M2"),    # 替代标记
            ("TP9", "TP10"), # 10-10 系统
            ("FT9", "FT10"), # 10-10 系统
            ("P9", "P10"),   # 有时用作乳突
        ]
        for left, right in candidates:
            if left in ch_names and right in ch_names:
                return [left, right]
        # 尝试模糊匹配
        left_chs = [ch for ch in ch_names if any(x in ch.upper() for x in ["A1", "M1", "LEFT", "LPA"])]
        right_chs = [ch for ch in ch_names if any(x in ch.upper() for x in ["A2", "M2", "RIGHT", "RPA"])]
        if left_chs and right_chs:
            return [left_chs[0], right_chs[0]]
        return []

    @staticmethod
    def _params_to_dict(params: ReferenceParams) -> dict[str, Any]:
        return {
            "ref_type": params.ref_type.value,
            "ref_channels": params.ref_channels,
            "projection": params.projection,
        }

    # ---- 便捷方法 ----
    @classmethod
    def average(cls, dataset: EEGDataset, **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.AVERAGE, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def mastoid(cls, dataset: EEGDataset, **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.MAStoid, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def cz(cls, dataset: EEGDataset, **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.CZ, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def single(cls, dataset: EEGDataset, ref_channel: str, **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.SINGLE, ref_channels=[ref_channel], **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def custom(cls, dataset: EEGDataset, ref_channels: list[str], **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.CUSTOM, ref_channels=ref_channels, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def rest(cls, dataset: EEGDataset, **kwargs: Any) -> ReferenceResult:
        params = ReferenceParams(ref_type=ReferenceType.REST, **kwargs)
        return cls.apply(dataset, params)


def apply_reference(
    dataset: EEGDataset,
    params: ReferenceParams,
    **kwargs: Any
) -> ReferenceResult:
    return ReferenceService.apply(dataset, params, **kwargs)