"""统计与对比分析参数模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


class StatisticalTest(Enum):
    """统计检验类型"""
    # 参数检验
    TTEST_INDEP = "ttest_indep"           # 独立样本 t 检验
    TTEST_PAIRED = "ttest_paired"         # 配对 t 检验
    TTEST_ONE_SAMPLE = "ttest_1samp"      # 单样本 t 检验
    ANOVA_ONE_WAY = "anova_one_way"       # 单因素方差分析
    ANOVA_TWO_WAY = "anova_two_way"       # 双因素方差分析
    ANOVA_REPEATED = "anova_repeated"     # 重复测量方差分析
    MANOVA = "manova"                     # 多元方差分析
    
    # 非参数检验
    WILCOXON = "wilcoxon"                 # Wilcoxon 符号秩检验
    MANN_WHITNEY = "mann_whitney"         # Mann-Whitney U 检验
    KRUSKAL_WALLIS = "kruskal_wallis"     # Kruskal-Wallis 检验
    FRIEDMAN = "friedman"                 # Friedman 检验
    
    # 置换检验
    PERMUTATION_TTEST = "permutation_ttest"   # 置换 t 检验
    PERMUTATION_ANOVA = "permutation_anova"   # 置换方差分析
    CLUSTER_PERMUTATION = "cluster_permutation"  # 簇置换检验
    
    # 相关性
    PEARSON = "pearson"                   # Pearson 相关
    SPEARMAN = "spearman"                 # Spearman 秩相关
    KENDALL = "kendall"                   # Kendall tau
    PARTIAL = "partial"                   # 偏相关
    
    # 其他
    CHI_SQUARE = "chi_square"             # 卡方检验
    FISHER_EXACT = "fisher_exact"         # Fisher 精确检验


class MultipleComparisonCorrection(Enum):
    """多重比较校正方法"""
    NONE = "none"                         # 无校正
    BONFERRONI = "bonferroni"             # Bonferroni 校正
    HOLM = "holm"                         # Holm-Bonferroni
    SIDAK = "sidak"                       # Sidak 校正
    FDR_BH = "fdr_bh"                     # Benjamini-Hochberg FDR
    FDR_BY = "fdr_by"                     # Benjamini-Yekutieli FDR
    CLUSTER = "cluster"                   # 簇级校正
    TFCE = "tfce"                         # Threshold-Free Cluster Enhancement
    MAX_STAT = "max_stat"                 # 最大统计量校正
    RFT = "rft"                           # Random Field Theory


class EffectSize(Enum):
    """效应量类型"""
    COHEN_D = "cohen_d"                   # Cohen's d
    HEDGES_G = "hedges_g"                 # Hedges' g
    ETA_SQUARED = "eta_squared"           # η²
    PARTIAL_ETA_SQUARED = "partial_eta_squared"  # 偏 η²
    OMEGA_SQUARED = "omega_squared"       # ω²
    R_SQUARED = "r_squared"               # R²
    CLIFF_DELTA = "cliff_delta"           # Cliff's delta (非参数)


@dataclass
class TTestParams:
    """t 检验参数"""
    test_type: Literal["independent", "paired", "one_sample"] = "independent"
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"
    equal_var: bool = False               # Welch 校正
    confidence_level: float = 0.95
    correction: MultipleComparisonCorrection = MultipleComparisonCorrection.NONE
    effect_size: EffectSize = EffectSize.COHEN_D


@dataclass
class ANOVAParams:
    """方差分析参数"""
    design: Literal["one_way", "two_way", "repeated", "mixed"] = "one_way"
    factors: list[str] = field(default_factory=list)  # 因子名称
    subject_factor: str | None = None     # 受试者因子 (重复测量)
    corrections: list[MultipleComparisonCorrection] = field(default_factory=lambda: [MultipleComparisonCorrection.FDR_BH])
    post_hoc: bool = True                 # 事后检验
    post_hoc_method: Literal["tukey", "bonferroni", "scheffe", "games_howell"] = "tukey"
    effect_size: EffectSize = EffectSize.ETA_SQUARED
    sphericity_correction: Literal["none", "greenhouse_geisser", "huynh_feldt"] = "greenhouse_geisser"


@dataclass
class NonparametricParams:
    """非参数检验参数"""
    test: StatisticalTest = StatisticalTest.MANN_WHITNEY
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"
    correction: MultipleComparisonCorrection = MultipleComparisonCorrection.FDR_BH
    effect_size: EffectSize = EffectSize.CLIFF_DELTA


@dataclass
class PermutationParams:
    """置换检验参数"""
    n_permutations: int = 1000
    test_statistic: Literal["t", "f", "max_t", "max_f"] = "t"
    tail: int = 0                         # 0=双尾, 1=单尾大于, -1=单尾小于
    n_jobs: int = -1
    seed: int | None = 42
    
    # 簇置换特有
    cluster_threshold: float | None = None    # 簇形成阈值
    cluster_method: Literal["mass", "size", "max_sum"] = "mass"
    min_cluster_size: int = 2


@dataclass
class CorrelationParams:
    """相关性分析参数"""
    method: Literal["pearson", "spearman", "kendall", "partial"] = "pearson"
    alternative: Literal["two-sided", "less", "greater"] = "two-sided"
    confidence_level: float = 0.95
    correction: MultipleComparisonCorrection = MultipleComparisonCorrection.FDR_BH
    
    # 偏相关
    control_variables: list[str] = field(default_factory=list)


@dataclass
class StatisticsParams:
    """统计分析总参数"""
    # 基础设置
    alpha: float = 0.05
    confidence_level: float = 0.95
    
    # 数据结构
    within_subject: bool = False          # 组内设计
    subject_id_col: str = "subject"       # 受试者 ID 列
    condition_col: str = "condition"      # 条件列
    value_col: str = "value"              # 因变量列
    
    # 检验选择
    primary_test: StatisticalTest = StatisticalTest.TTEST_INDEP
    ttest_params: TTestParams = field(default_factory=TTestParams)
    anova_params: ANOVAParams = field(default_factory=ANOVAParams)
    nonparametric_params: NonparametricParams = field(default_factory=NonparametricParams)
    permutation_params: PermutationParams = field(default_factory=PermutationParams)
    correlation_params: CorrelationParams = field(default_factory=CorrelationParams)
    
    # 多重比较校正
    global_correction: MultipleComparisonCorrection = MultipleComparisonCorrection.FDR_BH
    
    # 可视化
    plot_effect_sizes: bool = True
    plot_confidence_intervals: bool = True
    violin_plots: bool = True


@dataclass
class ComparisonResult:
    """两组/多组对比结果"""
    test_name: str
    statistic: float
    p_value: float
    df: float | tuple[float, float] | None = None
    effect_size: float | None = None
    effect_size_type: EffectSize | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    corrected_p: float | None = None
    significant: bool = False
    details: dict = field(default_factory=dict)


@dataclass
class CorrelationResult:
    """相关性结果"""
    r: float
    p_value: float
    ci_low: float | None = None
    ci_high: float | None = None
    n: int = 0
    method: str = ""
    corrected_p: float | None = None
    significant: bool = False


@dataclass
class StatisticsResult:
    """统计分析完整结果"""
    # 组间对比
    comparisons: list[ComparisonResult] = field(default_factory=list)
    
    # 相关性
    correlations: list[CorrelationResult] = field(default_factory=list)
    
    # 相关性矩阵
    corr_matrix: np.ndarray | None = None
    corr_p_matrix: np.ndarray | None = None
    variables: list[str] = field(default_factory=list)
    
    # 统计摘要
    summary_table: Any | None = None      # pandas DataFrame
    anova_table: Any | None = None
    
    # 元信息
    params_used: StatisticsParams | None = None
    processing_time_ms: float = 0.0


# ---- 常用预设 ----
DEFAULT_TTEST_PARAMS = TTestParams()
DEFAULT_ANOVA_PARAMS = ANOVAParams()
DEFAULT_PERMUTATION_PARAMS = PermutationParams(n_permutations=5000)
DEFAULT_CORRELATION_PARAMS = CorrelationParams()


def create_statistics_params(
    design: Literal["two_group", "multi_group", "repeated", "correlation"] = "two_group",
    **overrides
) -> StatisticsParams:
    """从预设创建统计参数"""
    params = StatisticsParams()
    
    if design == "two_group":
        params.primary_test = StatisticalTest.TTEST_INDEP
    elif design == "multi_group":
        params.primary_test = StatisticalTest.ANOVA_ONE_WAY
    elif design == "repeated":
        params.primary_test = StatisticalTest.ANOVA_REPEATED
    elif design == "correlation":
        params.primary_test = StatisticalTest.PEARSON
    
    for k, v in overrides.items():
        if hasattr(params, k):
            setattr(params, k, v)
        elif hasattr(params.ttest_params, k):
            setattr(params.ttest_params, k, v)
        elif hasattr(params.anova_params, k):
            setattr(params.anova_params, k, v)
        elif hasattr(params.permutation_params, k):
            setattr(params.permutation_params, k, v)
        elif hasattr(params.correlation_params, k):
            setattr(params.correlation_params, k, v)
    
    return params