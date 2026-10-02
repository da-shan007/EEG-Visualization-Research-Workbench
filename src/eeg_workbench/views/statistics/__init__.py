"""统计分析模块 Views 导出"""
from .statistics_main_widget import StatisticsMainWidget
from .ttest_widget import TTestWidget
from .anova_widget import ANOVAWidget
from .nonparametric_widget import NonparametricWidget
from .permutation_widget import PermutationWidget
from .correlation_widget import CorrelationWidget
from .correction_widget import CorrectionWidget
from .effect_size_widget import EffectSizeWidget

__all__ = [
    "StatisticsMainWidget",
    "TTestWidget",
    "ANOVAWidget",
    "NonparametricWidget",
    "PermutationWidget",
    "CorrelationWidget",
    "CorrectionWidget",
    "EffectSizeWidget",
]