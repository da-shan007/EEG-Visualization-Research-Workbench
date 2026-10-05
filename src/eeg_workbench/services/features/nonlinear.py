"""非线性分析服务：熵、分形维数、Lyapunov 指数等"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np
from scipy import signal
from scipy.stats import entropy as scipy_entropy

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import (
    NonlinearParams, NonlinearMeasure, FeatureExtractionResult
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class NonlinearResult:
    """非线性分析结果"""
    dataset: EEGDataset | None = None
    feature_result: FeatureExtractionResult | None = None
    processing_time_ms: float = 0.0
    params_used: NonlinearParams | None = None


class NonlinearService:
    """非线性分析服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        params: NonlinearParams,
        *,
        epochs_data: np.ndarray | None = None,
        verbose: bool = False
    ) -> NonlinearResult:
        """计算非线性指标

        Args:
            dataset: 数据集
            params: 非线性参数
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
        picks = NonlinearService._resolve_picks(params.picks, ch_names, dataset)
        if picks is not None:
            data = data[:, picks, :]
            ch_names = [ch_names[i] for i in picks]
            n_ch = len(ch_names)

        results = {}

        # 计算各项指标
        for measure in params.measures:
            if measure == NonlinearMeasure.SAMPLE_ENTROPY:
                results["sample_entropy"] = NonlinearService._sample_entropy(data, params, is_epochs)
            elif measure == NonlinearMeasure.APPROX_ENTROPY:
                results["approx_entropy"] = NonlinearService._approx_entropy(data, params, is_epochs)
            elif measure == NonlinearMeasure.PERMUTATION_ENTROPY:
                results["perm_entropy"] = NonlinearService._permutation_entropy(data, params, is_epochs)
            elif measure == NonlinearMeasure.HURST_EXPONENT:
                results["hurst"] = NonlinearService._hurst_exponent(data, params, is_epochs)
            elif measure == NonlinearMeasure.DETRENDED_FA:
                results["dfa"] = NonlinearService._dfa(data, params, is_epochs)
            elif measure == NonlinearMeasure.LYAPUNOV:
                results["lyapunov"] = NonlinearService._lyapunov(data, params, is_epochs)
            elif measure == NonlinearMeasure.CORRELATION_DIM:
                results["corr_dim"] = NonlinearService._correlation_dimension(data, params, is_epochs)
            elif measure == NonlinearMeasure.LZ_COMPLEXITY:
                results["lz_complexity"] = NonlinearService._lz_complexity(data, params, is_epochs)

        # 构建结果
        feature_result = FeatureExtractionResult(
            nonlinear=results,
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
                step="nonlinear",
                params={"measures": [m.value for m in params.measures]}
            ),
            source="NonlinearService"
        )

        return NonlinearResult(
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

    # ---- 样本熵 ----
    @staticmethod
    def _sample_entropy(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """计算样本熵
        返回: (n_epochs, n_ch) 或 (n_ch,)
        """
        n_epochs, n_ch, n_times = data.shape
        m = params.sample_entropy_m
        r_factor = params.sample_entropy_r

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                r = r_factor * np.std(ts)
                if r == 0:
                    results[ep, ch] = 0
                    continue

                # 构建模板向量
                def _phi(m_val):
                    patterns = np.array([ts[i:i+m_val] for i in range(n_times - m_val + 1)])
                    count = 0
                    for i in range(len(patterns)):
                        # 计算与其他模板的 Chebyshev 距离
                        dists = np.max(np.abs(patterns - patterns[i]), axis=1)
                        count += np.sum(dists <= r) - 1  # 排除自身
                    return count / (len(patterns) * (len(patterns) - 1)) if len(patterns) > 1 else 0

                phi_m = _phi(m)
                phi_m1 = _phi(m + 1)

                if phi_m > 0 and phi_m1 > 0:
                    results[ep, ch] = -np.log(phi_m1 / phi_m)
                else:
                    results[ep, ch] = 0

        return results.squeeze(0) if not is_epochs else results

    # ---- 近似熵 ----
    @staticmethod
    def _approx_entropy(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """计算近似熵"""
        # 实现类似 Sample Entropy 但不排除自身匹配
        n_epochs, n_ch, n_times = data.shape
        m = params.sample_entropy_m
        r_factor = params.sample_entropy_r

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                r = r_factor * np.std(ts)
                if r == 0:
                    results[ep, ch] = 0
                    continue

                def _phi(m_val):
                    patterns = np.array([ts[i:i+m_val] for i in range(n_times - m_val + 1)])
                    count = 0
                    for i in range(len(patterns)):
                        dists = np.max(np.abs(patterns - patterns[i]), axis=1)
                        count += np.sum(dists <= r)
                    return count / len(patterns) if len(patterns) > 0 else 0

                phi_m = _phi(m)
                phi_m1 = _phi(m + 1)

                if phi_m > 0:
                    results[ep, ch] = np.log(phi_m / phi_m1) if phi_m1 > 0 else 0
                else:
                    results[ep, ch] = 0

        return results.squeeze(0) if not is_epochs else results

    # ---- 排列熵 ----
    @staticmethod
    def _permutation_entropy(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """计算排列熵"""
        n_epochs, n_ch, n_times = data.shape
        order = params.perm_entropy_order
        delay = params.perm_entropy_delay

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # 嵌入
                n_patterns = n_times - (order - 1) * delay
                if n_patterns <= 0:
                    results[ep, ch] = 0
                    continue

                patterns = np.zeros((n_patterns, order))
                for i in range(order):
                    patterns[:, i] = ts[i * delay:i * delay + n_patterns]

                # 排序得到排列模式
                sorted_idx = np.argsort(patterns, axis=1)
                # 将排列编码为整数
                pattern_codes = np.zeros(n_patterns, dtype=int)
                for i in range(order):
                    pattern_codes = pattern_codes * order + sorted_idx[:, i]

                # 计算熵
                _, counts = np.unique(pattern_codes, return_counts=True)
                probs = counts / n_patterns
                results[ep, ch] = scipy_entropy(probs, base=2) / np.log2(order)

        return results.squeeze(0) if not is_epochs else results

    # ---- Hurst 指数 ----
    @staticmethod
    def _hurst_exponent(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """计算 Hurst 指数 (R/S 分析)"""
        n_epochs, n_ch, n_times = data.shape

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # R/S 分析
                n_scales = 10
                scales = np.logspace(1, np.log10(n_times // 4), n_scales, dtype=int)
                rs_vals = []

                for scale in scales:
                    if scale < 4:
                        continue
                    n_segments = n_times // scale
                    if n_segments < 2:
                        continue
                    rs_sum = 0
                    for seg in range(n_segments):
                        segment = ts[seg * scale:(seg + 1) * scale]
                        if len(segment) < scale:
                            continue
                        mean_seg = np.mean(segment)
                        dev = segment - mean_seg
                        cumsum = np.cumsum(dev)
                        R = np.max(cumsum) - np.min(cumsum)
                        S = np.std(segment)
                        if S > 0:
                            rs_sum += R / S
                    if n_segments > 0:
                        rs_vals.append(rs_sum / n_segments)

                if len(rs_vals) > 2:
                    # 线性拟合 log(R/S) vs log(scale)
                    log_scales = np.log(scales[:len(rs_vals)])
                    log_rs = np.log(rs_vals)
                    coeffs = np.polyfit(log_scales, log_rs, 1)
                    results[ep, ch] = coeffs[0]  # Hurst 指数 = 斜率

        return results.squeeze(0) if not is_epochs else results

    # ---- DFA (去趋势波动分析) ----
    @staticmethod
    def _dfa(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """DFA 分析返回缩放指数 alpha"""
        n_epochs, n_ch, n_times = data.shape

        if params.dfa_scales is None:
            scales = np.unique(np.logspace(1, np.log10(n_times // 4), 20, dtype=int))
        else:
            scales = params.dfa_scales

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # 积分
                y = np.cumsum(ts - np.mean(ts))

                fluctuations = []
                for scale in scales:
                    if scale < 4:
                        continue
                    n_seg = len(y) // scale
                    if n_seg < 2:
                        continue
                    rms_sum = 0
                    for seg in range(n_seg):
                        segment = y[seg * scale:(seg + 1) * scale]
                        if len(segment) != scale:
                            continue
                        # 线性去趋势
                        x = np.arange(scale)
                        coeffs = np.polyfit(x, segment, 1)
                        trend = np.polyval(coeffs, x)
                        detrended = segment - trend
                        rms_sum += np.mean(detrended ** 2)
                    if n_seg > 0:
                        fluctuations.append(np.sqrt(rms_sum / n_seg))

                if len(fluctuations) > 2:
                    log_scales = np.log(scales[:len(fluctuations)])
                    log_fluc = np.log(fluctuations)
                    coeffs = np.polyfit(log_scales, log_fluc, 1)
                    results[ep, ch] = coeffs[0]

        return results.squeeze(0) if not is_epochs else results

    # ---- Lyapunov 指数 ----
    @staticmethod
    def _lyapunov(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """计算最大 Lyapunov 指数 (Rosenstein 方法)"""
        n_epochs, n_ch, n_times = data.shape

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # 简化实现：使用最近邻发散率
                # 实际需要相空间重构
                min_sep = params.lyap_min_sep
                max_iter = params.lyap_max_iter

                # 这里只做简化演示，实际需要更复杂的实现
                # 使用 Rosenstein 算法需要相空间重构
                results[ep, ch] = 0.0  # 占位

        return results.squeeze(0) if not is_epochs else results

    # ---- 相关维数 ----
    @staticmethod
    def _correlation_dimension(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """Grassberger-Procaccia 相关维数"""
        n_epochs, n_ch, n_times = data.shape

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # 简化实现
                results[ep, ch] = 0.0  # 占位

        return results.squeeze(0) if not is_epochs else results

    # ---- Lempel-Ziv 复杂度 ----
    @staticmethod
    def _lz_complexity(data: np.ndarray, params: NonlinearParams, is_epochs: bool = True) -> np.ndarray:
        """Lempel-Ziv 复杂度 (基于中位数二值化)"""
        n_epochs, n_ch, n_times = data.shape

        results = np.zeros((n_epochs, n_ch))

        for ep in range(n_epochs):
            for ch in range(n_ch):
                ts = data[ep, ch]
                # 中位数二值化
                median = np.median(ts)
                binary = (ts > median).astype(int)

                # LZ 复杂度计算
                sequence = "".join(map(str, binary))
                complexity = NonlinearService._lz_complexity_string(sequence)
                # 归一化
                n = len(sequence)
                if n > 0:
                    results[ep, ch] = complexity / (n / np.log2(n))

        return results.squeeze(0) if not is_epochs else results

    @staticmethod
    def _lz_complexity_string(s: str) -> int:
        """计算字符串的 LZ 复杂度"""
        n = len(s)
        if n == 0:
            return 0

        c = 1
        i = 0
        while i < n:
            # 寻找最长匹配子串
            l = 1
            while i + l <= n and s[i:i+l] in s[:i]:
                l += 1
            c += 1
            i += l - 1
            if i >= n:
                break

        return c

    # ---- 便捷方法 ----
    @classmethod
    def entropy_suite(cls, dataset: EEGDataset, **kwargs) -> NonlinearResult:
        """熵指标套件"""
        params = NonlinearParams(
            measures=[
                NonlinearMeasure.SAMPLE_ENTROPY,
                NonlinearMeasure.PERMUTATION_ENTROPY,
                NonlinearMeasure.APPROX_ENTROPY,
            ],
            **kwargs
        )
        return cls.compute(dataset, params)

    @classmethod
    def fractal_suite(cls, dataset: EEGDataset, **kwargs) -> NonlinearResult:
        """分形指标套件"""
        params = NonlinearParams(
            measures=[
                NonlinearMeasure.HURST_EXPONENT,
                NonlinearMeasure.DETRENDED_FA,
            ],
            **kwargs
        )
        return cls.compute(dataset, params)

    @classmethod
    def full_suite(cls, dataset: EEGDataset, **kwargs) -> NonlinearResult:
        """全套非线性指标"""
        params = NonlinearParams(
            measures=list(NonlinearMeasure),
            **kwargs
        )
        return cls.compute(dataset, params)


def compute_nonlinear_features(
    dataset: EEGDataset,
    params: NonlinearParams,
    **kwargs
) -> NonlinearResult:
    return NonlinearService.compute(dataset, params, **kwargs)