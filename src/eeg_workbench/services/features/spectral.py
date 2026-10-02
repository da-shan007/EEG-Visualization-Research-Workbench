"""频段功率分析服务：Welch、多锥、FFT 等方法"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import (
    BandPowerParams, SpectralMethod, FeatureExtractionResult,
    STANDARD_BANDS
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class BandPowerResult:
    """频段功率结果"""
    dataset: EEGDataset | None = None  # 原始数据集不变，结果在 feature_result 中
    feature_result: FeatureExtractionResult | None = None
    processing_time_ms: float = 0.0
    params_used: BandPowerParams | None = None


class SpectralService:
    """频段功率分析服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        params: BandPowerParams,
        *,
        epochs_data: np.ndarray | None = None,  # (n_epochs, n_ch, n_times)
        verbose: bool = False
    ) -> BandPowerResult:
        """计算频段功率

        Args:
            dataset: 数据集
            params: 频段功率参数
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
        picks = SpectralService._resolve_picks(params.picks, ch_names, dataset)
        if picks is not None:
            data = data[:, picks, :]
            ch_names = [ch_names[i] for i in picks]

        # 计算功率谱
        if params.method == SpectralMethod.WELCH:
            psd, freqs = SpectralService._welch_psd(data, sfreq, params)
        elif params.method == SpectralMethod.MULTITAPER:
            psd, freqs = SpectralService._multitaper_psd(data, sfreq, params)
        elif params.method == SpectralMethod.FFT:
            psd, freqs = SpectralService._fft_psd(data, sfreq, params)
        else:
            raise ValueError(f"不支持的谱估计方法: {params.method}")

        # 计算频段功率
        band_power, band_freqs = SpectralService._compute_band_power(
            psd, freqs, params.bands, params.relative, params.log_transform
        )

        # 构建结果
        feature_result = FeatureExtractionResult(
            band_power=band_power,
            band_power_freqs=band_freqs,
            ch_names=ch_names,
            sfreq=sfreq,
            params=params,
            processing_time_ms=(time.perf_counter() - start_time) * 1000,
        )

        # 如果是 epochs 数据，调整形状
        if is_epochs:
            # band_power: (n_epochs, n_ch, n_bands)
            pass
        else:
            # 去掉 epoch 维度
            for k, v in band_power.items():
                band_power[k] = v.squeeze(0)  # (n_ch, n_bands)
            feature_result.band_power = band_power

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="band_power",
                params={"method": params.method.value, "bands": list(params.bands.keys())}
            ),
            source="SpectralService"
        )

        return BandPowerResult(
            dataset=dataset,
            feature_result=feature_result,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _resolve_picks(picks, ch_names: list[str], dataset: EEGDataset) -> list[int] | None:
        """解析通道选择"""
        if picks is None:
            return None
        if isinstance(picks, str):
            if picks == "eeg":
                return [i for i, ch in enumerate(ch_names)
                        if dataset.channel_info.get(ch).type.value == "eeg"]
            elif picks == "data":
                return list(range(len(ch_names)))
            else:
                return None
        if isinstance(picks, list):
            return [ch_names.index(ch) for ch in picks if ch in ch_names]
        return None

    @staticmethod
    def _welch_psd(data: np.ndarray, sfreq: float, params: BandPowerParams) -> tuple[np.ndarray, np.ndarray]:
        """Welch 方法功率谱"""
        from scipy.signal import welch

        # data: (n_epochs, n_ch, n_times)
        n_epochs, n_ch, n_times = data.shape

        # 真实样本长度可能远短于默认 FFT/窗口参数，必须先裁剪到合法范围。
        n_fft = max(1, min(params.n_fft, n_times))
        desired_n_per_seg = params.n_per_seg or n_fft
        n_per_seg = max(1, min(int(desired_n_per_seg), n_times))
        noverlap = max(0, min(params.n_overlap, n_per_seg - 1 if n_per_seg > 1 else 0))

        # 计算第一个通道确定频率轴
        # 注意: scipy.signal.welch 返回 (freqs, psd)
        freqs, _psd_sample = welch(
            data[0, 0], fs=sfreq, window=params.window,
            nperseg=n_per_seg, noverlap=noverlap, nfft=n_fft
        )

        # 批量计算
        psd = np.zeros((n_epochs, n_ch, len(freqs)), dtype=np.float64)
        for ep in range(n_epochs):
            for ch in range(n_ch):
                _, psd[ep, ch] = welch(
                    data[ep, ch], fs=sfreq, window=params.window,
                    nperseg=n_per_seg, noverlap=noverlap, nfft=n_fft
                )

        return psd, freqs

    @staticmethod
    def _multitaper_psd(data: np.ndarray, sfreq: float, params: BandPowerParams) -> tuple[np.ndarray, np.ndarray]:
        """多锥谱估计"""
        try:
            from mne.time_frequency import psd_array_multitaper
        except ImportError:
            # 回退到 scipy
            return SpectralService._welch_psd(data, sfreq, params)

        n_epochs, n_ch, n_times = data.shape

        psd = np.zeros((n_epochs, n_ch, 0))
        freqs = None

        for ep in range(n_epochs):
            for ch in range(n_ch):
                psd_ch, freqs_ch = psd_array_multitaper(
                    data[ep, ch:ch+1], sfreq=sfreq,
                    bandwidth=params.bandwidth,
                    adaptive=params.adaptive,
                    normalization="full",
                    verbose=False
                )
                if freqs is None:
                    freqs = freqs_ch
                if psd.shape[2] == 0:
                    psd = np.zeros((n_epochs, n_ch, len(freqs)))
                psd[ep, ch] = psd_ch[0]

        return psd, freqs

    @staticmethod
    def _fft_psd(data: np.ndarray, sfreq: float, params: BandPowerParams) -> tuple[np.ndarray, np.ndarray]:
        """直接 FFT 功率谱"""
        n_epochs, n_ch, n_times = data.shape
        n_fft = params.n_fft

        # 零填充
        if n_times < n_fft:
            pad_width = ((0, 0), (0, 0), (0, n_fft - n_times))
            data = np.pad(data, pad_width, mode="constant")
        elif n_times > n_fft:
            data = data[..., :n_fft]

        # FFT
        fft_vals = np.fft.rfft(data, n=n_fft, axis=-1)
        psd = np.abs(fft_vals) ** 2 / (sfreq * n_fft)
        freqs = np.fft.rfftfreq(n_fft, 1/sfreq)

        # 单边谱功率补偿 (除去 DC 和奈奎斯特)
        psd[..., 1:-1] *= 2

        return psd, freqs

    @staticmethod
    def _compute_band_power(
        psd: np.ndarray,
        freqs: np.ndarray,
        bands: dict[str, tuple[float, float]],
        relative: bool,
        log_transform: bool
    ) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, float]]]:
        """计算各频段功率"""
        band_power = {}
        band_freqs = {}

        # 总功率 (用于相对功率)：跨通道求和为全局总功率，
        # 使所有频段相对功率之和 = 频段覆盖的功率占比（≈1）
        total_power = np.trapezoid(psd, freqs, axis=-1)  # (n_epochs, n_ch)
        grand_total = total_power.sum(axis=-1, keepdims=True)  # (n_epochs, 1)

        for band_name, (fmin, fmax) in bands.items():
            # 找到频段内的频率索引
            freq_mask = (freqs >= fmin) & (freqs <= fmax)
            if not np.any(freq_mask):
                band_power[band_name] = np.zeros(psd.shape[:-1])
                band_freqs[band_name] = (fmin, fmax)
                continue

            # 频段内功率积分
            band_psd = psd[..., freq_mask]
            band_freqs_sub = freqs[freq_mask]
            power = np.trapezoid(band_psd, band_freqs_sub, axis=-1)  # (n_epochs, n_ch)

            if relative:
                power = power / (grand_total + 1e-12)

            if log_transform:
                power = np.log10(power + 1e-12)

            band_power[band_name] = power
            band_freqs[band_name] = (fmin, fmax)

        return band_power, band_freqs

    # ---- 便捷方法 ----
    @classmethod
    def standard_bands(cls, dataset: EEGDataset, **kwargs) -> BandPowerResult:
        """标准频段功率"""
        params = BandPowerParams(**kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def alpha_power(cls, dataset: EEGDataset, **kwargs) -> BandPowerResult:
        """仅 Alpha 频段"""
        params = BandPowerParams(bands={"Alpha": (8, 13)}, **kwargs)
        return cls.compute(dataset, params)


def compute_band_power(
    dataset: EEGDataset,
    params: BandPowerParams,
    **kwargs
) -> BandPowerResult:
    return SpectralService.compute(dataset, params, **kwargs)