"""滤波服务：带通、高通、低通、陷波、带阻"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Optional, Any
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.preprocessing import FilterParams, FilterType, FilterMethod, FILTER_PRESETS, create_filter_params
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class FilterResult:
    """滤波结果"""
    dataset: EEGDataset
    params_used: FilterParams
    processing_time_ms: float
    filter_info: dict[str, Any] | None = None


class FilterService:
    """滤波服务：提供各类滤波操作，支持 MNE 和 scipy 双引擎"""

    @staticmethod
    def apply(
        dataset: EEGDataset,
        params: FilterParams,
        *,
        picks: list[int] | str | None = None,
        copy: bool = True,
        verbose: bool = False
    ) -> FilterResult:
        """应用滤波器

        Args:
            dataset: 输入数据集
            params: 滤波参数
            picks: 选择通道 (索引、名称列表、'eeg'、'data' 等)
            copy: 是否复制数据
            verbose: 详细输出
        """
        start_time = time.perf_counter()

        # 转换为 MNE Raw 进行滤波
        raw = dataset.to_mne_raw(copy=copy)
        
        # 解析 picks
        if picks is None:
            picks = "data"  # 所有数据通道
        
        # 构建 MNE 滤波参数
        mne_kwargs = FilterService._build_mne_kwargs(params)
        
        # 执行滤波
        if params.filter_type == FilterType.NOTCH:
            raw.notch_filter(**mne_kwargs, picks=picks, verbose=verbose)
        else:
            raw.filter(**mne_kwargs, picks=picks, verbose=verbose)

        # 转回 EEGDataset
        new_dataset = EEGDataset.from_mne_raw(
            raw, 
            name=f"{dataset.name}_filtered",
            file_path=dataset.file_path
        )
        
        # 保留原数据集的元数据和事件
        new_dataset = replace(
            new_dataset,
            id=dataset.id,
            metadata=dataset.metadata,
            events=dataset.events,
            annotations=dataset.annotations,
            montage=dataset.montage,
            processing_history=dataset.processing_history + [{
                "step": "filter",
                "params": FilterService._params_to_dict(params),
                "duration_ms": (time.perf_counter() - start_time) * 1000,
                "input_shape": (dataset.n_channels, dataset.n_samples),
                "output_shape": (new_dataset.n_channels, new_dataset.n_samples),
            }]
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        # 发布事件
        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=new_dataset.id,
                step="filter",
                params=FilterService._params_to_dict(params)
            ),
            source="FilterService"
        )

        return FilterResult(
            dataset=new_dataset,
            params_used=params,
            processing_time_ms=elapsed,
            filter_info=mne_kwargs
        )

    @staticmethod
    def _build_mne_kwargs(params: FilterParams) -> dict[str, Any]:
        """构建 MNE 滤波参数字典"""
        kwargs: dict[str, Any] = {}

        if params.filter_type != FilterType.NOTCH:
            kwargs["l_freq"] = params.l_freq
            kwargs["h_freq"] = params.h_freq
        else:
            kwargs["freqs"] = params.notch_freq
            kwargs["notch_widths"] = params.notch_width

        # 方法选择
        if params.method == FilterMethod.FIR:
            kwargs["method"] = "fir"
            kwargs["fir_window"] = params.fir_window
            kwargs["fir_design"] = params.fir_design
        elif params.method == FilterMethod.IIR:
            kwargs["method"] = "iir"
            kwargs["iir_params"] = dict(order=params.iir_order, btype=params.iir_btype)
        else:
            kwargs["method"] = params.method.value

        # 相位
        kwargs["phase"] = params.phase
        kwargs["pad"] = params.pad

        return kwargs

    @staticmethod
    def _params_to_dict(params: FilterParams) -> dict[str, Any]:
        return {
            "filter_type": params.filter_type.value,
            "l_freq": params.l_freq,
            "h_freq": params.h_freq,
            "notch_freq": params.notch_freq,
            "notch_width": params.notch_width,
            "method": params.method.value,
            "phase": params.phase,
            "fir_window": params.fir_window,
            "fir_design": params.fir_design,
            "iir_order": params.iir_order,
        }

    # ---- 便捷预设方法 ----
    @classmethod
    def bandpass(cls, dataset: EEGDataset, l_freq: float, h_freq: float, **kwargs: Any) -> FilterResult:
        """带通滤波"""
        params = create_filter_params("standard", l_freq=l_freq, h_freq=h_freq, filter_type=FilterType.BANDPASS, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def highpass(cls, dataset: EEGDataset, l_freq: float, **kwargs: Any) -> FilterResult:
        """高通滤波"""
        params = create_filter_params("standard", l_freq=l_freq, filter_type=FilterType.HIGHPASS, h_freq=None, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def lowpass(cls, dataset: EEGDataset, h_freq: float, **kwargs: Any) -> FilterResult:
        """低通滤波"""
        params = create_filter_params("standard", h_freq=h_freq, filter_type=FilterType.LOWPASS, l_freq=None, **kwargs)
        return cls.apply(dataset, params)

    @classmethod
    def notch(cls, dataset: EEGDataset, freqs: float | list[float] = 50.0, width: float = 1.0, **kwargs: Any) -> FilterResult:
        """陷波滤波"""
        params = FilterParams(
            filter_type=FilterType.NOTCH,
            notch_freq=freqs if isinstance(freqs, float) else freqs[0],
            notch_width=width,
            **kwargs
        )
        return cls.apply(dataset, params)

    @classmethod
    def bandstop(cls, dataset: EEGDataset, l_freq: float, h_freq: float, **kwargs: Any) -> FilterResult:
        """带阻滤波"""
        params = FilterParams(
            filter_type=FilterType.BANDSTOP,
            l_freq=l_freq,
            h_freq=h_freq,
            **kwargs
        )
        return cls.apply(dataset, params)

    @classmethod
    def standard_preprocessing(cls, dataset: EEGDataset, **overrides: Any) -> FilterResult:
        """标准预处理滤波：0.1-40Hz + 50Hz 陷波"""
        params = create_filter_params("standard", **overrides)
        return cls.apply(dataset, params)

    @classmethod
    def ica_preparation(cls, dataset: EEGDataset, **overrides: Any) -> FilterResult:
        """ICA 预处理滤波：1Hz 高通 + 陷波 (不低通)"""
        params = create_filter_params("ica_prep", **overrides)
        return cls.apply(dataset, params)


# ---- 函数式接口 ----
def apply_filter(
    dataset: EEGDataset,
    params: FilterParams,
    **kwargs: Any
) -> FilterResult:
    """函数式接口"""
    return FilterService.apply(dataset, params, **kwargs)