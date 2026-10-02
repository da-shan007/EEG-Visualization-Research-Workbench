"""重采样服务：降采样/升采样，支持多种算法"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.preprocessing import ResampleParams, ResampleMethod
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ResampleResult:
    dataset: EEGDataset
    params_used: ResampleParams
    processing_time_ms: float
    ratio: float = 1.0


class ResampleService:
    """重采样服务"""

    @staticmethod
    def apply(
        dataset: EEGDataset,
        params: ResampleParams,
        *,
        copy: bool = True,
        verbose: bool = False
    ) -> ResampleResult:
        """应用重采样"""
        start_time = time.perf_counter()

        raw = dataset.to_mne_raw(copy=copy)

        # 计算重采样比率
        ratio = params.sfreq / raw.info["sfreq"]
        
        # 执行重采样
        raw.resample(
            sfreq=params.sfreq,
            npad=params.npad,
            window=params.window,
            verbose=verbose
        )

        # 转回 EEGDataset
        new_dataset = EEGDataset.from_mne_raw(
            raw,
            name=f"{dataset.name}_resampled_{int(params.sfreq)}Hz",
            file_path=dataset.file_path
        )

        # 保留元数据和事件 (事件时间会自动同步)
        new_dataset = replace(
            new_dataset,
            id=dataset.id,
            metadata=dataset.metadata,
            events=dataset.events,
            annotations=dataset.annotations,
            montage=dataset.montage,
            processing_history=dataset.processing_history + [{
                "step": "resample",
                "params": ResampleService._params_to_dict(params),
                "duration_ms": (time.perf_counter() - start_time) * 1000,
                "input_shape": (dataset.n_channels, dataset.n_samples),
                "output_shape": (new_dataset.n_channels, new_dataset.n_samples),
                "ratio": ratio,
            }]
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=new_dataset.id,
                step="resample",
                params=ResampleService._params_to_dict(params)
            ),
            source="ResampleService"
        )

        return ResampleResult(
            dataset=new_dataset,
            params_used=params,
            processing_time_ms=elapsed,
            ratio=ratio
        )

    @staticmethod
    def _params_to_dict(params: ResampleParams) -> dict:
        return {
            "sfreq": params.sfreq,
            "method": params.method.value,
            "npad": params.npad,
            "window": params.window,
        }

    @classmethod
    def resample_to(cls, dataset: EEGDataset, sfreq: float, **kwargs) -> ResampleResult:
        """重采样到指定采样率"""
        params = ResampleParams(sfreq=sfreq, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def downsample(cls, dataset: EEGDataset, factor: int, **kwargs) -> ResampleResult:
        """整数倍降采样"""
        target_sfreq = dataset.sfreq / factor
        if target_sfreq != int(target_sfreq):
            raise ValueError(f"降采样因子 {factor} 导致非整数采样率: {target_sfreq}")
        return cls.resample_to(dataset, target_sfreq, **kwargs)

    @classmethod
    def upsample(cls, dataset: EEGDataset, factor: int, **kwargs) -> ResampleResult:
        """整数倍升采样"""
        target_sfreq = dataset.sfreq * factor
        return cls.resample_to(dataset, target_sfreq, **kwargs)


def apply_resample(
    dataset: EEGDataset,
    params: ResampleParams,
    **kwargs
) -> ResampleResult:
    return ResampleService.apply(dataset, params, **kwargs)