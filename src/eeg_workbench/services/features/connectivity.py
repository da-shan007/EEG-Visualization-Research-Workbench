"""连通性分析服务：相干性、PLV、PLI、格兰杰因果等"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import (
    ConnectivityParams, ConnectivityMethod, FeatureExtractionResult
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ConnectivityResult:
    """连通性分析结果"""
    dataset: EEGDataset | None = None
    feature_result: FeatureExtractionResult | None = None
    processing_time_ms: float = 0.0
    params_used: ConnectivityParams | None = None


class ConnectivityService:
    """连通性分析服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        params: ConnectivityParams,
        *,
        epochs_data: np.ndarray | None = None,  # (n_epochs, n_ch, n_times)
        verbose: bool = False
    ) -> ConnectivityResult:
        """计算连通性

        Args:
            dataset: 数据集
            params: 连通性参数
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
            data = dataset.data[np.newaxis, ...]
            is_epochs = False

        sfreq = dataset.sfreq
        ch_names = dataset.ch_names

        # 处理 picks
        picks = ConnectivityService._resolve_picks(params.picks, ch_names, dataset)
        if picks is not None:
            data = data[:, picks, :]
            ch_names = [ch_names[i] for i in picks]
            n_ch = len(ch_names)

        # 确定频率范围
        fmax = params.fmax or sfreq / 2
        freqs = np.linspace(params.fmin, fmax, params.n_freqs)

        # 根据方法计算连通性
        if params.method in (ConnectivityMethod.COHERENCE, ConnectivityMethod.IMAG_COHERENCE):
            conn = ConnectivityService._spectral_connectivity(
                data, sfreq, freqs, params, is_epochs=is_epochs)
        elif params.method in (ConnectivityMethod.PLV, ConnectivityMethod.PLI, ConnectivityMethod.WPLI):
            conn = ConnectivityService._phase_connectivity(data, sfreq, freqs, params)
        elif params.method in (ConnectivityMethod.GCA, ConnectivityMethod.DTF, ConnectivityMethod.PDC):
            conn = ConnectivityService._granger_connectivity(
                data, sfreq, freqs, params, is_epochs=is_epochs)
        else:
            raise ValueError(f"不支持的连通性方法: {params.method}")

        # 如果是单次分析，去掉 epoch 维度
        if not is_epochs and conn.ndim == 4:
            conn = conn[0]  # (n_freqs, n_ch, n_ch)

        # 置换检验
        p_values = None
        if params.n_permutations > 0:
            conn, p_values = ConnectivityService._permutation_test(
                data, sfreq, freqs, params, conn
            )

        # 构建结果
        feature_result = FeatureExtractionResult(
            connectivity=conn,
            conn_freqs=freqs,
            conn_method=params.method.value,
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
                step="connectivity",
                params={"method": params.method.value, "freq_range": [params.fmin, fmax]}
            ),
            source="ConnectivityService"
        )

        return ConnectivityResult(
            dataset=dataset,
            feature_result=feature_result,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _resolve_picks(picks: list[str] | str | None, ch_names: list[str], dataset: EEGDataset) -> list[int] | None:
        if picks is None:
            return None
        if isinstance(picks, str):
            if picks == "eeg":
                return [i for i, ch in enumerate(ch_names)
                        if (ch_info := dataset.channel_info.get(ch)) is not None and ch_info.type.value == "eeg"]
            elif picks == "data":
                return list(range(len(ch_names)))
        if isinstance(picks, list):
            return [ch_names.index(ch) for ch in picks if ch in ch_names]
        return None

    @staticmethod
    def _spectral_connectivity(
        data: np.ndarray, sfreq: float, freqs: np.ndarray, params: ConnectivityParams,
        is_epochs: bool = True,
    ) -> np.ndarray:
        """谱相干性连通性"""
        try:
            from mne.connectivity import spectral_connectivity_epochs
        except ImportError:
            # 简化实现
            return ConnectivityService._simple_coherence(data, sfreq, freqs)

        n_epochs, n_ch, n_times = data.shape
        fmax = float(freqs[-1])  # 由调用方 linspace 构造，等价于 params.fmax or sfreq/2

        # 准备索引
        if params.indices is not None:
            indices = params.indices
        else:
            # 全连接
            indices = (np.repeat(np.arange(n_ch), n_ch), np.tile(np.arange(n_ch), n_ch))

        # MNE 连通性计算
        con, freqs_used, times, n_epochs_used, n_tapers = spectral_connectivity_epochs(
            data, sfreq=sfreq,
            method=params.method.value,
            indices=indices,
            fmin=params.fmin, fmax=fmax,
            faverage=False,
            verbose=False
        )  # (n_connections, n_freqs)

        # 重塑为 (n_epochs, n_freqs, n_ch, n_ch) 或 (n_freqs, n_ch, n_ch)
        if is_epochs:
            conn = np.zeros((n_epochs, len(freqs), n_ch, n_ch))
            for ep in range(n_epochs):
                con_ep = spectral_connectivity_epochs(
                    data[ep:ep+1], sfreq=sfreq,
                    method=params.method.value,
                    indices=indices,
                    fmin=params.fmin, fmax=fmax,
                    faverage=False, verbose=False
                )[0]
                conn[ep] = con_ep.reshape(n_ch, n_ch, -1).transpose(2, 0, 1)
        else:
            conn = con.reshape(n_ch, n_ch, -1).transpose(2, 0, 1)  # (n_freqs, n_ch, n_ch)

        # 如果是虚部相干性，取虚部
        if params.method == ConnectivityMethod.IMAG_COHERENCE:
            conn = np.imag(conn)

        return conn

    @staticmethod
    def _simple_coherence(data: np.ndarray, sfreq: float, freqs: np.ndarray) -> np.ndarray:
        """简化的相干性计算 (无 MNE 时的回退)"""
        from scipy.signal import csd, welch

        n_epochs, n_ch, n_times = data.shape
        fmax = freqs[-1]

        # 计算 CSD 矩阵
        conn = np.zeros((n_epochs, len(freqs), n_ch, n_ch), dtype=complex)

        for ep in range(n_epochs):
            for i in range(n_ch):
                for j in range(n_ch):
                    if i == j:
                        continue
                    f, c = csd(data[ep, i], data[ep, j], fs=sfreq, nperseg=min(256, n_times//4))
                    # 插值到目标频率
                    from scipy.interpolate import interp1d
                    interp = interp1d(f, c, kind="linear", bounds_error=False, fill_value=0)
                    conn[ep, :, i, j] = interp(freqs)

        return np.abs(conn)  # 返回相干性模值

    @staticmethod
    def _phase_connectivity(
        data: np.ndarray, sfreq: float, freqs: np.ndarray, params: ConnectivityParams
    ) -> np.ndarray:
        """基于相位的连通性 (PLV, PLI, wPLI)"""
        from scipy.signal import hilbert

        n_epochs, n_ch, n_times = data.shape
        fmax = freqs[-1]

        # 带通滤波到目标频率范围
        # 这里简化：使用 Hilbert 变换计算解析信号
        # 实际应用中应该用 MNE 的 phase_slope_index 等

        # 简化实现：计算宽频带 PLV
        # 对每个 epoch 计算
        conn = np.zeros((n_epochs, len(freqs), n_ch, n_ch))

        # 这里只做演示，实际需要分频带计算
        # 使用 MNE 的 phase_connectivity 会更好
        try:
            from mne.connectivity import phase_connectivity
            fmin, fmax = params.fmin, params.fmax or sfreq/2
            con = phase_connectivity(
                data, sfreq=sfreq,
                method=params.method.value,
                fmin=fmin, fmax=fmax,
                verbose=False
            )
            return np.asarray(con)
        except ImportError:
            # 简化：计算全频带 PLV
            for ep in range(n_epochs):
                analytic = hilbert(data[ep], axis=-1)
                phase = np.angle(analytic)
                for i in range(n_ch):
                    for j in range(i+1, n_ch):
                        phase_diff = phase[i] - phase[j]
                        plv = np.abs(np.mean(np.exp(1j * phase_diff)))
                        conn[ep, :, i, j] = plv
                        conn[ep, :, j, i] = plv
            return conn

    @staticmethod
    def _granger_connectivity(
        data: np.ndarray, sfreq: float, freqs: np.ndarray, params: ConnectivityParams,
        is_epochs: bool = True,
    ) -> np.ndarray:
        """格兰杰因果 / DTF / PDC"""
        try:
            from mne.connectivity import spectral_connectivity_epochs
        except ImportError:
            raise RuntimeError("格兰杰因果需要 MNE: pip install mne")

        n_epochs, n_ch, n_times = data.shape
        fmax = float(freqs[-1])

        if params.indices is not None:
            indices = params.indices
        else:
            indices = (np.repeat(np.arange(n_ch), n_ch), np.tile(np.arange(n_ch), n_ch))

        method_map = {
            ConnectivityMethod.GCA: "gc",
            ConnectivityMethod.DTF: "dtf",
            ConnectivityMethod.PDC: "pdc",
        }

        con, freqs_used, times, n_epochs_used, n_tapers = spectral_connectivity_epochs(
            data, sfreq=sfreq,
            method=method_map[params.method],
            indices=indices,
            fmin=params.fmin, fmax=fmax,
            gca_n_lags=params.gca_order,
            verbose=False
        )

        # 重塑
        # MNE 无论输入是单段还是多个 epoch 都返回 (n_connections, n_freqs) 并已跨 epoch 平均。
        # 统一转成 (n_freqs, n_ch, n_ch)，与 _spectral_connectivity 的单段分支一致。
        conn = con.reshape(n_ch, n_ch, -1).transpose(2, 0, 1)
        if is_epochs:
            conn = conn[np.newaxis]  # 保留 epoch 维 -> (1, n_freqs, n_ch, n_ch)

        return np.asarray(conn)

    @staticmethod
    def _permutation_test(
        data: np.ndarray, sfreq: float, freqs: np.ndarray,
        params: ConnectivityParams, observed: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """置换检验"""
        # 简化实现
        # 实际应用中需要打乱试次标签重新计算
        p_values = np.ones_like(observed) * 0.5
        return observed, p_values

    # ---- 便捷方法 ----
    @classmethod
    def coherence(cls, dataset: EEGDataset, **kwargs: Any) -> ConnectivityResult:
        params = ConnectivityParams(method=ConnectivityMethod.COHERENCE, **kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def plv(cls, dataset: EEGDataset, **kwargs: Any) -> ConnectivityResult:
        params = ConnectivityParams(method=ConnectivityMethod.PLV, **kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def pli(cls, dataset: EEGDataset, **kwargs: Any) -> ConnectivityResult:
        params = ConnectivityParams(method=ConnectivityMethod.PLI, **kwargs)
        return cls.compute(dataset, params)

    @classmethod
    def granger(cls, dataset: EEGDataset, **kwargs: Any) -> ConnectivityResult:
        params = ConnectivityParams(method=ConnectivityMethod.GCA, **kwargs)
        return cls.compute(dataset, params)


def compute_connectivity(
    dataset: EEGDataset,
    params: ConnectivityParams,
    **kwargs: Any
) -> ConnectivityResult:
    return ConnectivityService.compute(dataset, params, **kwargs)