"""多重比较校正服务：FDR、Bonferroni、簇校正、TFCE"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests

from eeg_workbench.models.statistics import MultipleComparisonCorrection


@dataclass
class CorrectionResult:
    """校正结果"""
    rejected: np.ndarray              # 布尔数组：哪些假设被拒绝
    p_values_corrected: np.ndarray    # 校正后的 p 值
    alpha_corrected: float | None     # 校正后的显著性水平
    method: str                       # 校正方法
    details: dict                     # 详细信息


class MultipleComparisonService:
    """多重比较校正服务"""

    @staticmethod
    def correct_pvalues(
        p_values: np.ndarray,
        method: MultipleComparisonCorrection = MultipleComparisonCorrection.FDR_BH,
        alpha: float = 0.05,
        **kwargs
    ) -> CorrectionResult:
        """校正 p 值"""
        
        if method == MultipleComparisonCorrection.NONE:
            return CorrectionResult(
                rejected=p_values < alpha,
                p_values_corrected=p_values.copy(),
                alpha_corrected=alpha,
                method="none",
                details={}
            )

        elif method == MultipleComparisonCorrection.BONFERRONI:
            return MultipleComparisonService._bonferroni(p_values, alpha)

        elif method == MultipleComparisonCorrection.HOLM:
            return MultipleComparisonService._holm(p_values, alpha)

        elif method == MultipleComparisonCorrection.SIDAK:
            return MultipleComparisonService._sidak(p_values, alpha)

        elif method == MultipleComparisonCorrection.FDR_BH:
            return MultipleComparisonService._fdr_bh(p_values, alpha)

        elif method == MultipleComparisonCorrection.FDR_BY:
            return MultipleComparisonService._fdr_by(p_values, alpha)

        elif method == MultipleComparisonCorrection.MAX_STAT:
            return MultipleComparisonService._max_stat(p_values, alpha)

        else:
            raise ValueError(f"不支持的校正方法: {method}")

    @staticmethod
    def _bonferroni(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """Bonferroni 校正"""
        n = len(p_values)
        p_corrected = np.minimum(p_values * n, 1.0)
        rejected = p_corrected < alpha
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=alpha / n,
            method="bonferroni",
            details={"n_tests": n}
        )

    @staticmethod
    def _holm(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """Holm-Bonferroni 校正"""
        n = len(p_values)
        sorted_indices = np.argsort(p_values)
        sorted_p = p_values[sorted_indices]
        
        rejected = np.zeros(n, dtype=bool)
        p_corrected = np.zeros(n)
        
        for i, (idx, p) in enumerate(zip(sorted_indices, sorted_p)):
            corrected = p * (n - i)
            p_corrected[idx] = min(corrected, 1.0)
            if p_corrected[idx] < alpha:
                rejected[idx] = True
            else:
                break
        
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=alpha,
            method="holm",
            details={"n_tests": len(p_values)}
        )

    @staticmethod
    def _sidak(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """Sidak 校正"""
        n = len(p_values)
        alpha_sidak = 1 - (1 - alpha) ** (1 / n)
        p_corrected = 1 - (1 - p_values) ** n
        rejected = p_corrected < alpha
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=alpha_sidak,
            method="sidak",
            details={"n_tests": n}
        )

    @staticmethod
    def _fdr_bh(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """Benjamini-Hochberg FDR"""
        rejected, p_corrected, _, _ = multipletests(
            p_values, alpha=alpha, method='fdr_bh'
        )
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=alpha,
            method="fdr_bh",
            details={}
        )

    @staticmethod
    def _fdr_by(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """Benjamini-Yekutieli FDR"""
        rejected, p_corrected, _, _ = multipletests(
            p_values, alpha=alpha, method='fdr_by'
        )
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=alpha,
            method="fdr_by",
            details={}
        )

    @staticmethod
    def _max_stat(p_values: np.ndarray, alpha: float) -> CorrectionResult:
        """基于最大统计量的校正 (需要置换检验支持)"""
        # 这里简化实现，实际需要置换检验的零分布
        return MultipleComparisonService._bonferroni(p_values, alpha)

    @staticmethod
    def cluster_correction(
        p_values: np.ndarray,
        cluster_threshold: float,
        adjacency: np.ndarray | None = None,
        alpha: float = 0.05
    ) -> CorrectionResult:
        """簇级校正"""
        # 简化实现：基于阈值的簇形成
        n = len(p_values)
        rejected = p_values < cluster_threshold
        
        # 如果有邻接矩阵，形成簇
        if adjacency is not None:
            # 简化：只保留大小>=2的簇
            pass
        
        p_corrected = p_values.copy()
        p_corrected[~rejected] = 1.0
        
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_corrected,
            alpha_corrected=cluster_threshold,
            method="cluster",
            details={"cluster_threshold": cluster_threshold}
        )

    @staticmethod
    def tfce_correction(
        stat_map: np.ndarray,
        null_distribution: np.ndarray,
        alpha: float = 0.05,
        *,
        E: float = 0.5,
        H: float = 2.0,
        n_steps: int = 50,
    ) -> CorrectionResult:
        """TFCE (Threshold-Free Cluster Enhancement) 校正

        Smith & Nichols (2009) 无阈值簇增强：对统计量图（正负两部分分别）
        做 TFCE 变换，再用置换零分布的 TFCE 最大值做 family-wise 校正。

        stat_map: 观测统计量，可为任意维度（如 通道×时间）。
        null_distribution: 置换零分布，形状为 (n_perm, *stat_map.shape)。
        """
        from scipy import ndimage

        stat_map = np.asarray(stat_map, dtype=float)
        null_distribution = np.asarray(null_distribution, dtype=float)
        if null_distribution.ndim != stat_map.ndim + 1:
            raise ValueError(
                "null_distribution 形状须为 (n_perm, *stat_map.shape)，"
                f"实际得到 {null_distribution.shape} vs {stat_map.shape}"
            )
        if null_distribution.shape[0] < 2:
            raise ValueError("TFCE 校正需要至少 2 次置换的零分布")

        connectivity = ndimage.generate_binary_structure(stat_map.ndim, 1)

        def _tfce_positive(x: np.ndarray) -> np.ndarray:
            x = np.maximum(x, 0.0)
            h_max = float(x.max())
            if h_max <= 0:
                return np.zeros_like(x)
            dh = h_max / n_steps
            out = np.zeros_like(x)
            for i in range(1, n_steps + 1):
                h = i * dh
                mask = x >= h
                labeled, n_lab = ndimage.label(mask, structure=connectivity)
                if n_lab == 0:
                    continue
                sizes = ndimage.sum(np.ones_like(x), labeled, range(1, n_lab + 1))
                extent = np.zeros_like(x)
                for lab, sz in enumerate(np.atleast_1d(sizes), start=1):
                    extent[labeled == lab] = sz
                out += (extent ** E) * (h ** H) * dh
            return out

        def _tfce_signed(x: np.ndarray) -> np.ndarray:
            return _tfce_positive(x) - _tfce_positive(-x)

        tfce_obs = _tfce_signed(stat_map)
        n_perm = null_distribution.shape[0]
        tfce_max = np.empty(n_perm)
        for k in range(n_perm):
            tfce_max[k] = np.max(np.abs(_tfce_signed(null_distribution[k])))
        abs_obs = np.abs(tfce_obs)
        tfce_max_r = tfce_max.reshape((n_perm,) + (1,) * stat_map.ndim)
        p_values = (1.0 + np.sum(tfce_max_r >= abs_obs, axis=0)) / (n_perm + 1.0)
        rejected = p_values < alpha
        return CorrectionResult(
            rejected=rejected,
            p_values_corrected=p_values,
            alpha_corrected=alpha,
            method="tfce",
            details={"n_perm": n_perm, "E": E, "H": H, "n_steps": n_steps},
        )


def correct_pvalues(
    p_values: np.ndarray,
    method: MultipleComparisonCorrection = MultipleComparisonCorrection.FDR_BH,
    alpha: float = 0.05,
    **kwargs
) -> CorrectionResult:
    return MultipleComparisonService.correct_pvalues(p_values, method, alpha, **kwargs)


def cluster_correction(
    p_values: np.ndarray,
    cluster_threshold: float,
    adjacency: np.ndarray | None = None,
    alpha: float = 0.05
) -> CorrectionResult:
    return MultipleComparisonService.cluster_correction(p_values, cluster_threshold, adjacency, alpha)