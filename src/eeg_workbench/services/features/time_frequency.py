"""时频分析服务：STFT、Morlet 小波、多锥时频"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import (
    TimeFrequencyParams, TimeFrequencyMethod, FeatureExtractionResult
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class TFRResult:
    """时频分析结果"""
    dataset: EEGDataset | None = None
    feature_result: FeatureExtractionResult | None = None
    processing_time_ms: float = 0.0
    params_used: TimeFrequencyParams | None = None


class TimeFrequencyService:
    """时频分析服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        params: TimeFrequencyParams,
        *,
        epochs_data: np.ndarray | None = None,  # (n_epochs, n_ch, n_times)
        verbose: bool = False
    ) -> TFRResult:
        """计算时频图 (TFR)

        Args:
            dataset: 数据集
            params: 时频参数
            epochs_data: 可选的 Epochs 数据 (n_epochs, n_ch, n_times)
            verbose: 详细输出
        """
        start_time = time.perf_counter()

        # 获取数据
        if epochs_data is not None:
            data = epochs_data
            n_epochs, n_ch, n_times = data.shape
            is_epochs = True
        else:
            data = dataset.data[np.newaxis, ...]  # (1, n_ch, n_times)
            is_epochs = False

        sfreq = dataset.sfreq
        ch_names = dataset.ch_names

        # 处理 picks
        picks = TimeFrequencyService._resolve_picks(params.picks, ch_names, dataset)
        if picks is not None:
            data = data[:, picks, :]
            ch_names = [ch_names[i] for i in picks]

        # 根据方法计算 TFR
        if params.method == TimeFrequencyMethod.STFT:
            tfr, freqs, times = TimeFrequencyService._stft_tfr(data, sfreq, params)
        elif params.method == TimeFrequencyMethod.MORLET:
            tfr, freqs, times = TimeFrequencyService._morlet_tfr(data, sfreq, params)
        elif params.method == TimeFrequencyMethod.MULTITAPER:
            tfr, freqs, times = TimeFrequencyService._multitaper_tfr(data, sfreq, params)
        else:
            raise ValueError(f"不支持的时频方法: {params.method}")

        # 基线校正
        if params.baseline is not None:
            tfr = TimeFrequencyService._baseline_correction(
                tfr, times, params.baseline, params.baseline_mode
            )

        # 时间降采样
        if params.decim > 1:
            tfr = tfr[..., ::params.decim]
            times = times[::params.decim]

        # 试次平均
        if is_epochs and params.average:
            tfr = np.mean(tfr, axis=0, keepdims=True)
            n_epochs = 1

        # 非 epochs 输入：去掉虚拟 epoch 轴，输出 (n_ch, n_freqs, n_times)
        if not is_epochs:
            tfr = tfr[0]

        # 构建结果
        feature_result = FeatureExtractionResult(
            time_frequency=tfr,
            tf_freqs=freqs,
            tf_times=times,
            ch_names=ch_names,
            sfreq=sfreq,
            params=params,
            processing_time_ms=(time.perf_counter() - start_time) * 1000,
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="time_frequency",
                params={"method": params.method.value, "freq_range": [params.fmin, params.fmax]}
            ),
            source="TimeFrequencyService"
        )

        return TFRResult(
            dataset=dataset,
            feature_result=feature_result,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _resolve_picks(picks, ch_names: list[str], dataset: EEGDataset) -> list[int] | None:
        if picks is None:
            return None
        if isinstance(picks, str):
            if picks == "eeg":
                return [i for i, ch in enumerate(ch_names)
                        if dataset.channel_info.get(ch).type.value == "eeg"]
            elif picks == "data":
                return list(range(len(ch_names)))
        if isinstance(picks, list):
            return [ch_names.index(ch) for ch in picks if ch in ch_names]
        return None

    @staticmethod
    def _stft_tfr(data: np.ndarray, sfreq: float, params: TimeFrequencyParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """短时傅里叶变换 (STFT)"""
        from scipy.signal import stft

        n_epochs, n_ch, n_times = data.shape

        # 与 _welch_psd 一致：钳制 nperseg/noverlap 合法性
        nperseg = max(1, min(params.n_fft, n_times))
        noverlap = max(0, min(params.n_overlap, nperseg - 1))

        # 计算第一个通道确定维度
        f, t, Zxx = stft(
            data[0, 0], fs=sfreq, window=params.window,
            nperseg=nperseg, noverlap=noverlap,
            boundary="zeros", padded=True
        )

        # 批量计算
        tfr = np.zeros((n_epochs, n_ch, len(f), len(t)), dtype=np.complex128)
        for ep in range(n_epochs):
            for ch in range(n_ch):
                _, _, Zxx = stft(
                    data[ep, ch], fs=sfreq, window=params.window,
                    nperseg=nperseg, noverlap=noverlap,
                    boundary="zeros", padded=True
                )
                tfr[ep, ch] = Zxx

        # 转换输出格式
        if params.output == "power":
            tfr = np.abs(tfr) ** 2
        elif params.output == "phase":
            tfr = np.angle(tfr)
        # complex 保持不变

        return tfr, f, t

    @staticmethod
    def _morlet_tfr(data: np.ndarray, sfreq: float, params: TimeFrequencyParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Morlet 小波时频分析"""
        try:
            from mne.time_frequency import tfr_array_morlet
        except ImportError:
            raise RuntimeError("Morlet 小波需要 MNE: pip install mne")

        n_epochs, n_ch, n_times = data.shape

        # 确定频率
        freqs = params.freqs
        if freqs is None:
            freqs = np.logspace(
                np.log10(params.fmin), np.log10(params.fmax), params.n_freqs
            )

        # n_cycles 处理
        n_cycles = params.n_cycles
        if isinstance(n_cycles, (int, float)):
            n_cycles = freqs / params.fmin * n_cycles  # 频率相关的周期数

        # 限制小波长度不超过信号长度（mne 要求 wavelet <= n_times）。
        # mne 小波: sigma_t = n_cycles/(2πf)，长度 = 2*ceil(5*sigma_t*sfreq)-1。
        n_cycles = np.asarray(n_cycles, dtype=float)
        max_half = (n_times + 1) // 2 - 1  # 每侧最大样本数（留 1 样本余量）
        if max_half >= 1:
            max_sigma_t = max_half / (5.0 * sfreq)
            n_cycles = np.minimum(n_cycles, 2.0 * np.pi * freqs * max_sigma_t)

        # MNE 期望 (n_epochs, n_ch, n_times)
        tfr = tfr_array_morlet(
            data, sfreq=sfreq, freqs=freqs, n_cycles=n_cycles,
            output=params.output, verbose=False
        )  # (n_epochs, n_ch, n_freqs, n_times)

        # 时间轴
        times = np.arange(n_times) / sfreq

        return tfr, freqs, times

    @staticmethod
    def _multitaper_tfr(data: np.ndarray, sfreq: float, params: TimeFrequencyParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """多锥时频分析"""
        try:
            from mne.time_frequency import tfr_array_multitaper
        except ImportError:
            raise RuntimeError("多锥时频需要 MNE: pip install mne")

        n_epochs, n_ch, n_times = data.shape
        freqs = params.freqs
        if freqs is None:
            freqs = np.logspace(
                np.log10(params.fmin), np.log10(params.fmax), params.n_freqs
            )

        tfr = tfr_array_multitaper(
            data, sfreq=sfreq, freqs=freqs,
            n_cycles=params.n_cycles,
            time_bandwidth=params.time_bandwidth,
            output=params.output, verbose=False
        )

        times = np.arange(n_times) / sfreq
        return tfr, freqs, times

    @staticmethod
    def _baseline_correction(
        tfr: np.ndarray,
        times: np.ndarray,
        baseline: tuple[float, float],
        mode: str
    ) -> np.ndarray:
        """基线校正"""
        tmin, tmax = baseline
        # 找到基线时间范围内的索引
        baseline_mask = (times >= tmin) & (times <= tmax)
        if not np.any(baseline_mask):
            return tfr

        baseline_data = tfr[..., baseline_mask]

        if mode == "mean":
            baseline_mean = np.mean(baseline_data, axis=-1, keepdims=True)
            return tfr - baseline_mean
        elif mode == "ratio":
            baseline_mean = np.mean(baseline_data, axis=-1, keepdims=True)
            return tfr / (baseline_mean + 1e-12)
        elif mode == "logratio":
            baseline_mean = np.mean(baseline_data, axis=-1, keepdims=True)
            return np.log10(tfr / (baseline_mean + 1e-12))
        elif mode == "zscore":
            baseline_mean = np.mean(baseline_data, axis=-1, keepdims=True)
            baseline_std = np.std(baseline_data, axis=-1, keepdims=True)
            return (tfr - baseline_mean) / (baseline_std + 1e-12)
        return tfr

    # ---- 便捷方法 ----
    @classmethod
    def morlet(cls, dataset: EEGDataset, **kwargs) -> TFRResult:
        params = TimeFrequencyParams(method=TimeFrequencyMethod.MORLET, **kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def stft(cls, dataset: EEGDataset, **kwargs) -> TFRResult:
        params = TimeFrequencyParams(method=TimeFrequencyMethod.STFT, **kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def multitaper_tfr(cls, dataset: EEGDataset, **kwargs) -> TFRResult:
        params = TimeFrequencyParams(method=TimeFrequencyMethod.MULTITAPER, **kwargs)
        return cls.compute(dataset, params)


def compute_tfr(
    dataset: EEGDataset,
    params: TimeFrequencyParams,
    **kwargs
) -> TFRResult:
    return TimeFrequencyService.compute(dataset, params, **kwargs)