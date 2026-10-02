"""统计检验服务：t 检验、方差分析、非参数检验"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np
from scipy import stats
from scipy.stats import (
    ttest_ind, ttest_rel, ttest_1samp,
    f_oneway, kruskal, mannwhitneyu, wilcoxon,
    friedmanchisquare
)
import pingouin as pg

from eeg_workbench.models.statistics import (
    TTestParams, ANOVAParams, NonparametricParams,
    StatisticalTest, MultipleComparisonCorrection, EffectSize,
    ComparisonResult, StatisticsParams
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class TTestResult:
    """t 检验结果"""
    result: ComparisonResult
    group_stats: dict
    processing_time_ms: float


class StatisticalTestService:
    """统计检验服务"""

    @staticmethod
    def run_ttest(
        group1: np.ndarray,
        group2: np.ndarray | None,
        params: TTestParams,
        *,
        verbose: bool = False
    ) -> TTestResult:
        """运行 t 检验"""
        start_time = time.perf_counter()

        if params.test_type == "independent":
            # 独立样本 t 检验
            stat, p = ttest_ind(group1, group2, equal_var=params.equal_var, alternative=params.alternative)
            df = len(group1) + len(group2) - 2 if params.equal_var else None
            n1, n2 = len(group1), len(group2)
            
        elif params.test_type == "paired":
            # 配对 t 检验
            stat, p = ttest_rel(group1, group2, alternative=params.alternative)
            df = len(group1) - 1
            n1 = n2 = len(group1)
            
        elif params.test_type == "one_sample":
            # 单样本 t 检验 (group2 是假设均值)
            popmean = group2[0] if group2 is not None else 0
            stat, p = ttest_1samp(group1, popmean, alternative=params.alternative)
            df = len(group1) - 1
            n1 = len(group1)
            n2 = 1
        else:
            raise ValueError(f"未知的 t 检验类型: {params.test_type}")

        # 效应量
        if params.test_type in ["independent", "paired"]:
            effect_size = StatisticalTestService._compute_effect_size(group1, group2, params.test_type)
        else:
            effect_size = (np.mean(group1) - (group2[0] if group2 is not None else 0)) / np.std(group1, ddof=1)

        # 置信区间
        if params.test_type == "independent":
            se = np.sqrt(np.var(group1, ddof=1)/len(group1) + np.var(group2, ddof=1)/len(group2))
            mean_diff = np.mean(group1) - np.mean(group2)
        elif params.test_type == "paired":
            diff = group1 - group2
            se = np.std(diff, ddof=1) / np.sqrt(len(diff))
            mean_diff = np.mean(diff)
        else:
            se = np.std(group1, ddof=1) / np.sqrt(len(group1))
            mean_diff = np.mean(group1) - (group2[0] if group2 is not None else 0)

        from scipy.stats import t
        t_crit = t.ppf((1 + 0.95) / 2, df) if df else 1.96
        ci_low = mean_diff - t_crit * se
        ci_high = mean_diff + t_crit * se

        # 多重比较校正
        corrected_p = p  # 简化：实际需要所有比较的 p 值一起校正

        result = ComparisonResult(
            test_name="t-test",
            statistic=float(np.abs(stat)),
            p_value=float(p),
            df=df,
            effect_size=abs(effect_size) if effect_size else None,
            effect_size_type=EffectSize.COHEN_D,
            ci_low=ci_low,
            ci_high=ci_high,
            corrected_p=p,
            significant=p < 0.05
        )

        return TTestResult(
            result=ComparisonResult(
                test_name="t-test",
                statistic=float(np.abs(stat)),
                p_value=float(p),
                df=df,
                effect_size=abs(effect_size) if effect_size else None,
                effect_size_type=EffectSize.COHEN_D,
                ci_low=ci_low,
                ci_high=ci_high,
                corrected_p=p,
                significant=p < 0.05
            ),
            group_stats={
                "group1": {"mean": np.mean(group1), "std": np.std(group1, ddof=1), "n": len(group1)},
                "group2": {"mean": np.mean(group2), "std": np.std(group2, ddof=1), "n": len(group2)} if group2 is not None else None
            },
            processing_time_ms=0  # 会在外部设置
        )

    @staticmethod
    def _compute_effect_size(group1: np.ndarray, group2: np.ndarray, test_type: str) -> float:
        """计算 Cohen's d"""
        n1, n2 = len(group1), len(group2)
        var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
        
        if test_type == "paired":
            diff = group1 - group2
            return np.mean(group1 - group2) / np.std(group1 - group2, ddof=1)
        else:
            pooled_std = np.sqrt(((n1-1)*np.var(group1, ddof=1) + (n2-1)*np.var(group2, ddof=1)) / (n1 + n2 - 2))
            return (np.mean(group1) - np.mean(group2)) / pooled_std

    @staticmethod
    def run_anova(
        groups: list[np.ndarray],
        params: ANOVAParams,
        *,
        verbose: bool = False,
        subject_ids: np.ndarray | list | None = None,
    ) -> dict:
        """运行方差分析

        one_way: 组间单因素（pingouin.anova）。
        repeated: 重复测量（pingouin.rm_anova），需要被试内配对数据；
            可通过 subject_ids 显式传入被试 ID（长度须等于每组样本数），
            缺省时假设各组等长且按顺序一一对应同一批被试。
        """
        # 使用 pingouin 进行方差分析
        try:
            import pingouin as pg
        except ImportError:
            raise RuntimeError("方差分析需要 pingouin: pip install pingouin")

        # 构建数据框
        import pandas as pd
        data = []
        for i, g in enumerate(groups):
            for val in g:
                data.append({"group": f"G{i}", "value": val})
        df = pd.DataFrame(data)

        if params.design == "one_way":
            aov = pg.anova(data=df, dv="value", between="group", detailed=True)
        elif params.design == "repeated":
            # 构建被试内长表：subject × condition
            n = min(len(g) for g in groups)
            if n == 0:
                raise ValueError("重复测量 ANOVA 需要每组至少 1 个样本")
            if subject_ids is None:
                subjects = list(range(n))
            else:
                subjects = list(subject_ids)
                if len(subjects) < n:
                    raise ValueError(
                        f"subject_ids 长度 ({len(subjects)}) 少于每组样本数 ({n})"
                    )
                subjects = subjects[:n]
            rows = []
            for i, g in enumerate(groups):
                for s in range(n):
                    rows.append({"subject": subjects[s], "condition": f"G{i}", "value": float(g[s])})
            rm_df = pd.DataFrame(rows)
            aov = pg.rm_anova(
                data=rm_df, dv="value", within="condition", subject="subject",
                correction=params.sphericity_correction != "none", detailed=True,
            )
        else:
            raise ValueError(
                f"未支持的 ANOVA 设计: {params.design}（当前支持 one_way / repeated）"
            )

        return aov.to_dict()

    @staticmethod
    def run_nonparametric(
        group1: np.ndarray,
        group2: np.ndarray | None,
        params: NonparametricParams,
        *,
        verbose: bool = False,
        groups: list[np.ndarray] | None = None,
    ) -> dict:
        """运行非参数检验

        两组检验（Mann-Whitney / Wilcoxon）使用 group1/group2；
        多组检验（Kruskal-Wallis / Friedman）通过 groups=[g1, g2, ...] 传入，
        也可用 group1/group2 便捷传入两组数据。
        """
        if params.test == StatisticalTest.MANN_WHITNEY:
            stat, p = mannwhitneyu(group1, group2, alternative=params.alternative)
            test_name = "Mann-Whitney U"
        elif params.test == StatisticalTest.WILCOXON:
            stat, p = wilcoxon(group1, group2, alternative=params.alternative)
            test_name = "Wilcoxon"
        elif params.test == StatisticalTest.KRUSKAL_WALLIS:
            multi = groups if groups is not None else (
                [group1, group2] if group2 is not None else None
            )
            if multi is None or len(multi) < 2:
                raise ValueError(
                    "Kruskal-Wallis 需要多组数据：请通过 groups=[g1, g2, ...] 传入至少两组"
                )
            stat, p = kruskal(*multi)
            test_name = "Kruskal-Wallis"
        elif params.test == StatisticalTest.FRIEDMAN:
            multi = groups if groups is not None else (
                [group1, group2] if group2 is not None else None
            )
            if multi is None or len(multi) < 2:
                raise ValueError(
                    "Friedman 检验需要多组配对数据：请通过 groups=[g1, g2, ...] 传入至少两组"
                )
            stat, p = friedmanchisquare(*multi)
            test_name = "Friedman"
        else:
            raise ValueError(f"未知的非参数检验: {params.test}")

        return {"statistic": stat, "p_value": p, "test": test_name}


def run_ttest(
    group1: np.ndarray,
    group2: np.ndarray | None,
    params: TTestParams,
    **kwargs
) -> TTestResult:
    return StatisticalTestService.run_ttest(group1, group2, params, **kwargs)


def run_anova(
    groups: list[np.ndarray],
    params: ANOVAParams,
    **kwargs
) -> dict:
    return StatisticalTestService.run_anova(groups, params, **kwargs)


def run_nonparametric(
    group1: np.ndarray,
    group2: np.ndarray | None,
    params: NonparametricParams,
    **kwargs
) -> dict:
    return StatisticalTestService.run_nonparametric(group1, group2, params, **kwargs)