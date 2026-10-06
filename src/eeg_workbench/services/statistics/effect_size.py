"""效应量计算服务：Cohen's d、Hedges' g、η²、ω²、Cliff's delta 等"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import numpy as np
from scipy import stats

from eeg_workbench.models.statistics import EffectSize


@dataclass
class EffectSizeResult:
    """效应量结果"""
    value: float
    effect_size_type: EffectSize
    interpretation: str  # "small", "medium", "large"
    ci_low: float | None = None
    ci_high: float | None = None
    details: dict[str, Any] | None = None


class EffectSizeService:
    """效应量计算服务"""

    # 解释标准 (Cohen's d)
    D_INTERPRETATION = {
        "small": 0.2,
        "medium": 0.5,
        "large": 0.8
    }

    @staticmethod
    def interpret_d(d: float) -> str:
        """解释 Cohen's d"""
        abs_d = abs(d)
        if abs_d < 0.2:
            return "negligible"
        elif abs_d < 0.5:
            return "small"
        elif abs_d < 0.8:
            return "medium"
        else:
            return "large"

    @staticmethod
    def interpret_eta_squared(eta2: float) -> str:
        """解释 η²"""
        if eta2 < 0.01:
            return "negligible"
        elif eta2 < 0.06:
            return "small"
        elif eta2 < 0.14:
            return "medium"
        else:
            return "large"

    @staticmethod
    def interpret_cliff_delta(delta: float) -> str:
        """解释 Cliff's delta"""
        abs_d = abs(delta)
        if abs_d < 0.147:
            return "negligible"
        elif abs_d < 0.33:
            return "small"
        elif abs_d < 0.474:
            return "medium"
        else:
            return "large"

    # ---- Cohen's d 系列 ----
    @staticmethod
    def cohen_d(
        group1: np.ndarray,
        group2: np.ndarray,
        paired: bool = False,
        correction: bool = False  # True 时返回 Hedges' g 校正值
    ) -> EffectSizeResult:
        """计算 Cohen's d 或 Hedges' g"""
        n1, n2 = len(group1), len(group2)
        
        if paired:
            diff = group1 - group2
            d = np.mean(diff) / np.std(diff, ddof=1)
            df = n1 - 1
        else:
            var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
            pooled_std = np.sqrt(((n1 - 1) * np.var(group1, ddof=1) + (n2 - 1) * np.var(group2, ddof=1)) / (n1 + n2 - 2))
            d = (np.mean(group1) - np.mean(group2)) / pooled_std
            df = n1 + n2 - 2

        # Hedges' g 校正
        if correction and df > 0:
            j = 1 - 3 / (4 * df - 1)
            g = d * j
            effect_type = EffectSize.HEDGES_G
            value = abs(g)
        else:
            effect_type = EffectSize.COHEN_D
            value = abs(d)

        # 置信区间 (非中心 t 分布近似)
        se = np.sqrt((n1 + n2) / (n1 * n2) + value**2 / (2 * (n1 + n2)))
        z = 1.96
        ci_low = value - z * se
        ci_high = value + z * se

        return EffectSizeResult(
            value=value,
            effect_size_type=effect_type,
            interpretation=EffectSizeService.interpret_d(value),
            ci_low=ci_low,
            ci_high=ci_high,
            details={"df": df, "paired": paired}
        )

    @staticmethod
    def glass_delta(
        group1: np.ndarray,
        group2: np.ndarray,
        control_group: int = 2  # 1 或 2
    ) -> EffectSizeResult:
        """Glass's Δ (使用对照组标准差)"""
        if control_group == 1:
            sd_control = np.std(group1, ddof=1)
        else:
            sd_control = np.std(group2, ddof=1)
        
        delta = (np.mean(group1) - np.mean(group2)) / sd_control
        
        return EffectSizeResult(
            value=delta,
            effect_size_type=EffectSize.COHEN_D,
            interpretation=EffectSizeService.interpret_d(delta),
            details={"control_group": control_group}
        )

    # ---- 方差分析效应量 ----
    @staticmethod
    def eta_squared(ss_effect: float, ss_total: float) -> EffectSizeResult:
        """η² (Eta squared)"""
        if ss_total == 0:
            return EffectSizeResult(0, EffectSize.ETA_SQUARED, "negligible")
        
        eta2 = ss_effect / ss_total
        return EffectSizeResult(
            value=eta2,
            effect_size_type=EffectSize.ETA_SQUARED,
            interpretation=EffectSizeService.interpret_eta_squared(eta2),
            details={"ss_effect": ss_effect, "ss_total": ss_total}
        )

    @staticmethod
    def partial_eta_squared(ss_effect: float, ss_error: float) -> EffectSizeResult:
        """偏 η²"""
        if ss_effect + ss_error == 0:
            return EffectSizeResult(0, EffectSize.PARTIAL_ETA_SQUARED, "negligible")
        
        peta2 = ss_effect / (ss_effect + ss_error)
        return EffectSizeResult(
            value=peta2,
            effect_size_type=EffectSize.PARTIAL_ETA_SQUARED,
            interpretation=EffectSizeService.interpret_eta_squared(peta2),
            details={"ss_effect": ss_effect, "ss_error": ss_error}
        )

    @staticmethod
    def omega_squared(ss_effect: float, ss_error: float, df_effect: int, df_error: int, ms_error: float) -> EffectSizeResult:
        """ω² (Omega squared)"""
        numerator = ss_effect - df_effect * ms_error
        denominator = ss_error + ms_error
        if denominator == 0:
            return EffectSizeResult(0, EffectSize.OMEGA_SQUARED, "negligible")
        
        omega2 = max(0, numerator / denominator)
        return EffectSizeResult(
            value=omega2,
            effect_size_type=EffectSize.OMEGA_SQUARED,
            interpretation=EffectSizeService.interpret_eta_squared(omega2),
            details={"df_effect": df_effect, "df_error": df_error, "ms_error": ms_error}
        )

    @staticmethod
    def epsilon_squared(ss_effect: float, ss_total: float) -> EffectSizeResult:
        """ε² (Epsilon squared) - 类似 ω² 但无偏"""
        if ss_total == 0:
            return EffectSizeResult(0, EffectSize.ETA_SQUARED, "negligible")
        eps2 = (ss_effect - 1) / (ss_total - 1)  # 简化
        return EffectSizeResult(
            value=max(0, eps2),
            effect_size_type=EffectSize.ETA_SQUARED,
            interpretation=EffectSizeService.interpret_eta_squared(max(0, eps2))
        )

    # ---- 相关系数效应量 ----
    @staticmethod
    def correlation_effect_size(r: float) -> EffectSizeResult:
        """相关系数作为效应量"""
        return EffectSizeResult(
            value=r,
            effect_size_type=EffectSize.R_SQUARED,
            interpretation="large" if abs(r) > 0.5 else ("medium" if abs(r) > 0.3 else "small"),
            details={"r_squared": r**2}
        )

    # ---- 非参数效应量 ----
    @staticmethod
    def cliff_delta(group1: np.ndarray, group2: np.ndarray) -> EffectSizeResult:
        """Cliff's Delta (非参数效应量)"""
        n1, n2 = len(group1), len(group2)
        
        # 计算优势对数
        greater = 0
        less = 0
        for x in group1:
            for y in group2:
                if x > y:
                    greater += 1
                elif x < y:
                    less += 1
        
        delta = (greater - less) / (n1 * n2)
        
        return EffectSizeResult(
            value=delta,
            effect_size_type=EffectSize.CLIFF_DELTA,
            interpretation=EffectSizeService.interpret_cliff_delta(delta),
            details={"greater": greater, "less": less, "n1": n1, "n2": n2}
        )

    @staticmethod
    def rank_biserial_correlation(group1: np.ndarray, group2: np.ndarray) -> EffectSizeResult:
        """秩二列相关系数 (Mann-Whitney U 对应的效应量)"""
        from scipy.stats import mannwhitneyu
        u, _ = mannwhitneyu(group1, group2, alternative='two-sided')
        n1, n2 = len(group1), len(group2)
        rbc = 1 - (2 * u) / (n1 * n2)
        
        return EffectSizeResult(
            value=rbc,
            effect_size_type=EffectSize.CLIFF_DELTA,
            interpretation=EffectSizeService.interpret_cliff_delta(rbc),
            details={"u_statistic": u}
        )

    # ---- 方差分析效应量计算 (从 ANOVA 表) ----
    @staticmethod
    def from_anova_table(
        anova_table: dict[str, Any],  # pingouin 返回的字典
        effect_name: str
    ) -> dict[str, EffectSizeResult]:
        """从 ANOVA 表提取多种效应量"""
        row = anova_table[anova_table['Source'] == effect_name].iloc[0]
        
        ss_effect = row['SS']
        ss_error = anova_table[anova_table['Source'] == 'Residual']['SS'].values[0]
        ss_total = anova_table['SS'].sum()
        df_effect = row['DF']
        df_error = anova_table[anova_table['Source'] == 'Residual']['DF'].values[0]
        ms_error = row['MS'] if 'MS' in row else ss_error / df_error
        
        results = {
            "eta_squared": EffectSizeService.eta_squared(ss_effect, ss_total),
            "partial_eta_squared": EffectSizeService.partial_eta_squared(ss_effect, ss_error),
            "omega_squared": EffectSizeService.omega_squared(ss_effect, ss_error, df_effect, df_error, ms_error),
            "epsilon_squared": EffectSizeService.epsilon_squared(ss_effect, ss_total),
        }
        return results

    # ---- 综合计算 ----
    @staticmethod
    def compute_all(
        group1: np.ndarray,
        group2: np.ndarray,
        paired: bool = False
    ) -> dict[str, EffectSizeResult]:
        """计算所有适用的效应量"""
        return {
            "cohen_d": EffectSizeService.cohen_d(group1, group2, paired),
            "hedges_g": EffectSizeService.cohen_d(group1, group2, paired, correction=True),
            "glass_delta": EffectSizeService.glass_delta(group1, group2),
            "cliff_delta": EffectSizeService.cliff_delta(group1, group2),
            "rrb": EffectSizeService.rank_biserial_correlation(group1, group2),
        }


def compute_effect_size(
    group1: np.ndarray,
    group2: np.ndarray,
    effect_type: EffectSize = EffectSize.COHEN_D,
    **kwargs: Any
) -> EffectSizeResult:
    """统一接口"""
    if effect_type == EffectSize.COHEN_D:
        return EffectSizeService.cohen_d(group1, group2, **kwargs)
    elif effect_type == EffectSize.HEDGES_G:
        return EffectSizeService.cohen_d(group1, group2, correction=True, **kwargs)
    elif effect_type == EffectSize.CLIFF_DELTA:
        return EffectSizeService.cliff_delta(group1, group2)
    else:
        raise ValueError(f"不支持的效应量类型: {effect_type}")