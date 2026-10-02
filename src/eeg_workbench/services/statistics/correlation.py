"""相关性分析服务：Pearson/Spearman/Kendall/偏相关、相关性矩阵"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np
from scipy import stats
import pingouin as pg

from eeg_workbench.models.statistics import (
    CorrelationParams, MultipleComparisonCorrection,
    CorrelationResult, StatisticsParams
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class CorrelationResultWrap:
    """相关性分析结果"""
    results: list[CorrelationResult]
    corr_matrix: np.ndarray | None
    p_matrix: np.ndarray | None
    processing_time_ms: float


class CorrelationService:
    """相关性分析服务"""

    @staticmethod
    def compute_correlation(
        x: np.ndarray,
        y: np.ndarray,
        params: CorrelationParams,
        *,
        verbose: bool = False
    ) -> CorrelationResultWrap:
        """计算两变量相关性"""
        start_time = time.perf_counter()

        if params.method == "pearson":
            r, p = stats.pearsonr(x, y)
        elif params.method == "spearman":
            r, p = stats.spearmanr(x, y)
        elif params.method == "kendall":
            r, p = stats.kendalltau(x, y)
        else:
            raise ValueError(f"不支持的相关性方法: {params.method}")

        # 置信区间
        ci_low, ci_high = CorrelationService._confidence_interval(r, len(x), params.confidence_level)

        # 多重比较校正 (简化)
        corrected_p = p

        result = CorrelationResult(
            r=float(r),
            p_value=float(p),
            ci_low=ci_low,
            ci_high=ci_high,
            n=len(x),
            method=params.method,
            corrected_p=corrected_p,
            significant=p < 0.05
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        return CorrelationResultWrap(
            results=[result],
            corr_matrix=None,
            p_matrix=None,
            processing_time_ms=elapsed
        )

    @staticmethod
    def compute_correlation_matrix(
        data: np.ndarray,  # (n_samples, n_variables)
        params: CorrelationParams,
        *,
        variable_names: list[str] | None = None,
        verbose: bool = False
    ) -> CorrelationResultWrap:
        """计算相关性矩阵"""
        start_time = time.perf_counter()

        n_vars = data.shape[1]
        corr_matrix = np.zeros((n_vars, n_vars))
        p_matrix = np.zeros((n_vars, n_vars))

        results = []

        for i in range(n_vars):
            for j in range(i, n_vars):
                if i == j:
                    corr_matrix[i, j] = 1.0
                    p_matrix[i, j] = 0.0
                else:
                    if params.method == "pearson":
                        r, p = stats.pearsonr(data[:, i], data[:, j])
                    elif params.method == "spearman":
                        r, p = stats.spearmanr(data[:, i], data[:, j])
                    elif params.method == "kendall":
                        r, p = stats.kendalltau(data[:, i], data[:, j])
                    else:
                        raise ValueError(f"不支持的方法: {params.method}")

                    corr_matrix[i, j] = r
                    corr_matrix[j, i] = r
                    p_matrix[i, j] = p
                    p_matrix[j, i] = p

                    ci_low, ci_high = CorrelationService._confidence_interval(r, data.shape[0], 0.95)
                    
                    results.append(CorrelationResult(
                        r=float(r),
                        p_value=float(p),
                        ci_low=ci_low,
                        ci_high=ci_high,
                        n=data.shape[0],
                        method=params.method,
                        corrected_p=float(p),
                        significant=p < 0.05
                    ))

        elapsed = (time.perf_counter() - start_time) * 1000

        return CorrelationResultWrap(
            results=results,
            corr_matrix=corr_matrix,
            p_matrix=p_matrix,
            processing_time_ms=elapsed
        )

    @staticmethod
    def compute_partial_correlation(
        data: np.ndarray,  # (n_samples, n_variables)
        control_indices: list[int],
        target_indices: list[int] | None = None,
        params: CorrelationParams | None = None,
        verbose: bool = False
    ) -> CorrelationResultWrap:
        """计算偏相关"""
        start_time = time.perf_counter()

        try:
            import pingouin as pg
        except ImportError:
            raise RuntimeError("偏相关需要 pingouin: pip install pingouin")

        import pandas as pd
        
        n_vars = data.shape[1]
        if target_indices is None:
            target_indices = [i for i in range(n_vars) if i not in control_indices]

        # 构建 DataFrame
        var_names = [f"V{i}" for i in range(n_vars)]
        df = pd.DataFrame(data, columns=var_names)

        results = []
        n_targets = len(target_indices)
        corr_matrix = np.zeros((n_targets, n_targets))
        p_matrix = np.zeros((n_targets, n_targets))

        for i, ti in enumerate(target_indices):
            for j, tj in enumerate(target_indices):
                if i == j:
                    corr_matrix[i, j] = 1.0
                    p_matrix[i, j] = 0.0
                elif i < j:
                    # 计算偏相关
                    covars = [var_names[c] for c in control_indices]
                    try:
                        result = pg.partial_corr(
                            data=df, x=var_names[ti], y=var_names[tj],
                            covar=covars, method="pearson"
                        )
                        r = result['r'].values[0]
                        p = result['p-val'].values[0]
                    except Exception:
                        r, p = 0.0, 1.0

                    corr_matrix[i, j] = r
                    corr_matrix[j, i] = r
                    p_matrix[i, j] = p
                    p_matrix[j, i] = p

                    ci_low, ci_high = CorrelationService._confidence_interval(r, data.shape[0], 0.95)
                    
                    results.append(CorrelationResult(
                        r=float(r),
                        p_value=float(p),
                        ci_low=ci_low,
                        ci_high=ci_high,
                        n=data.shape[0],
                        method="partial_pearson",
                        corrected_p=float(p),
                        significant=p < 0.05
                    ))

        elapsed = (time.perf_counter() - start_time) * 1000

        return CorrelationResultWrap(
            results=results,
            corr_matrix=corr_matrix,
            p_matrix=p_matrix,
            processing_time_ms=elapsed
        )

    @staticmethod
    def _confidence_interval(r: float, n: int, confidence: float = 0.95) -> tuple[float, float]:
        """Fisher z 变换计算置信区间"""
        if n < 4:
            return -1.0, 1.0
        
        z = np.arctanh(np.clip(r, -0.999999, 0.999999))
        se = 1.0 / np.sqrt(n - 3)
        z_crit = stats.norm.ppf((1 + confidence) / 2)
        
        z_low = z - z_crit * se
        z_high = z + z_crit * se
        
        r_low = np.tanh(z_low)
        r_high = np.tanh(z_high)
        
        return float(r_low), float(r_high)

    @staticmethod
    def correlate_with_behavior(
        eeg_features: np.ndarray,  # (n_subjects, n_features)
        behavior: np.ndarray,      # (n_subjects,) 或 (n_subjects, n_behaviors)
        params: CorrelationParams,
        *,
        verbose: bool = False
    ) -> CorrelationResultWrap:
        """EEG 特征与行为数据相关性"""
        start_time = time.perf_counter()

        if behavior.ndim == 1:
            behavior = behavior.reshape(-1, 1)

        n_features = eeg_features.shape[1]
        n_behaviors = behavior.shape[1]

        results = []
        corr_matrix = np.zeros((n_features, n_behaviors))
        p_matrix = np.zeros((n_features, n_behaviors))

        for i in range(n_features):
            for j in range(n_behaviors):
                if params.method == "pearson":
                    r, p = stats.pearsonr(eeg_features[:, i], behavior[:, j])
                elif params.method == "spearman":
                    r, p = stats.spearmanr(eeg_features[:, i], behavior[:, j])
                elif params.method == "kendall":
                    r, p = stats.kendalltau(eeg_features[:, i], behavior[:, j])
                else:
                    raise ValueError(f"不支持的方法: {params.method}")

                corr_matrix[i, j] = r
                p_matrix[i, j] = p

                ci_low, ci_high = CorrelationService._confidence_interval(r, len(eeg_features), params.confidence_level)
                
                results.append(CorrelationResult(
                    r=float(r),
                    p_value=float(p),
                    ci_low=ci_low,
                    ci_high=ci_high,
                    n=len(eeg_features),
                    method=params.method,
                    corrected_p=float(p),
                    significant=p < 0.05
                ))

        elapsed = (time.perf_counter() - start_time) * 1000

        return CorrelationResultWrap(
            results=results,
            corr_matrix=corr_matrix,
            p_matrix=p_matrix,
            processing_time_ms=elapsed
        )


def compute_correlation(
    x: np.ndarray,
    y: np.ndarray,
    params: CorrelationParams,
    **kwargs
) -> CorrelationResultWrap:
    return CorrelationService.compute_correlation(x, y, params)


def compute_partial_correlation(
    data: np.ndarray,
    control_indices: list[int],
    target_indices: list[int] | None = None,
    params: CorrelationParams | None = None,
    **kwargs
) -> CorrelationResultWrap:
    return CorrelationService.compute_partial_correlation(data, control_indices, target_indices, params)