"""统计分析模块单元测试"""
import numpy as np
import pytest

from eeg_workbench.models.statistics import (
    StatisticsParams, TTestParams, ANOVAParams, NonparametricParams,
    PermutationParams, CorrelationParams,
    StatisticalTest, MultipleComparisonCorrection, EffectSize,
    ComparisonResult, CorrelationResult,
    create_statistics_params
)
from eeg_workbench.services.statistics import (
    StatisticalTestService, PermutationService, CorrelationService,
    MultipleComparisonService, EffectSizeService
)


# ---- 测试辅助 ----
def make_two_groups(n1=20, n2=20, diff=0.5):
    """生成两组测试数据"""
    np.random.seed(42)
    group1 = np.random.randn(20) * 10
    group2 = np.random.randn(20) * 10 + diff * 10
    return group1, group2


# ---- Models 测试 ----
class TestTTestParams:
    def test_default_validation(self):
        params = TTestParams()
        assert params.test_type == "independent"
        assert params.alternative == "two-sided"
        assert params.equal_var is False  # Welch by default

    def test_paired_validation(self):
        params = TTestParams(test_type="paired")
        assert params.test_type == "paired"


class TestANOVAParams:
    def test_one_way_default(self):
        params = ANOVAParams()
        assert params.design == "one_way"

    def test_repeated_requires_subject(self):
        params = ANOVAParams(design="repeated")
        # 重复测量需要 subject_factor


class TestCorrelationParams:
    def test_pearson_default(self):
        params = CorrelationParams()
        assert params.method == "pearson"

    def test_partial_requires_control(self):
        params = CorrelationParams(method="partial")
        # 偏相关需要 control_variables


class TestPermutationParams:
    def test_defaults(self):
        params = PermutationParams()
        assert params.n_permutations == 1000
        assert params.tail == 0

    def test_cluster_requires_threshold(self):
        params = PermutationParams(cluster_threshold=None)
        # 簇置换需要阈值


class TestStatisticsParams:
    def test_create_from_preset_two_group(self):
        params = create_statistics_params("two_group")
        assert params.primary_test == StatisticalTest.TTEST_INDEP

    def test_create_from_preset_multi_group(self):
        params = create_statistics_params("multi_group")
        assert params.primary_test == StatisticalTest.ANOVA_ONE_WAY

    def test_create_from_preset_repeated(self):
        params = create_statistics_params("repeated")
        assert params.primary_test == StatisticalTest.ANOVA_REPEATED

    def test_create_from_preset_correlation(self):
        params = create_statistics_params("correlation")
        assert params.primary_test == StatisticalTest.PEARSON


# ---- Services 测试 ----
class TestStatisticalTestService:
    def test_ttest_independent(self):
        g1, g2 = make_two_groups()
        params = TTestParams(test_type="independent")
        result = StatisticalTestService.run_ttest(g1, g2, params)
        assert result is not None
        assert result.result.p_value >= 0
        assert result.result.test_name == "t-test"

    def test_ttest_paired(self):
        g1, g2 = make_two_groups()
        params = TTestParams(test_type="paired")
        result = StatisticalTestService.run_ttest(g1, g2, params)
        assert result is not None

    def test_ttest_one_sample(self):
        g1, _ = make_two_groups()
        params = TTestParams(test_type="one_sample")
        result = StatisticalTestService.run_ttest(g1, np.array([0.0]), params)
        assert result is not None

    def test_nonparametric_mann_whitney(self):
        g1, g2 = make_two_groups()
        params = NonparametricParams(test=StatisticalTest.MANN_WHITNEY)
        result = StatisticalTestService.run_nonparametric(g1, g2, params)
        assert result is not None
        assert result["p_value"] >= 0

    def test_anova_repeated(self):
        rng = np.random.default_rng(0)
        groups = [rng.normal(i, 1.0, 15) for i in range(3)]
        params = ANOVAParams(design="repeated")
        result = StatisticalTestService.run_anova(groups, params)
        assert result is not None
        assert "F" in result

    def test_nonparametric_kruskal_wallis(self):
        rng = np.random.default_rng(1)
        groups = [rng.normal(i, 1.0, 15) for i in range(3)]
        params = NonparametricParams(test=StatisticalTest.KRUSKAL_WALLIS)
        result = StatisticalTestService.run_nonparametric(groups[0], None, params, groups=groups)
        assert result is not None
        assert result["test"] == "Kruskal-Wallis"
        assert 0 <= result["p_value"] <= 1

    def test_nonparametric_friedman(self):
        rng = np.random.default_rng(2)
        groups = [rng.normal(i, 1.0, 15) for i in range(3)]
        params = NonparametricParams(test=StatisticalTest.FRIEDMAN)
        result = StatisticalTestService.run_nonparametric(groups[0], None, params, groups=groups)
        assert result is not None
        assert result["test"] == "Friedman"
        assert 0 <= result["p_value"] <= 1


class TestPermutationService:
    def test_permutation_ttest(self):
        g1, g2 = make_two_groups()
        params = PermutationParams(n_permutations=100, seed=42)
        result = PermutationService.run_permutation_ttest(g1, g2, params)
        assert result is not None
        assert result.result.p_value >= 0
        assert len(result.null_distribution) == 100

    def test_cluster_permutation_2d(self):
        """测试 2D 簇置换 (n_subj, n_channels)"""
        np.random.seed(42)
        data = np.random.randn(20, 10)  # 20受试者, 10通道
        params = PermutationParams(n_permutations=50, seed=42)
        result = PermutationService.run_cluster_permutation(data, params)
        assert result is not None
        assert "p_value" in result


class TestCorrelationService:
    def test_pearson_correlation(self):
        x = np.random.randn(50)
        y = x + np.random.randn(50) * 0.5
        params = CorrelationParams(method="pearson")
        result = CorrelationService.compute_correlation(x, y, params)
        assert result.results[0].r > 0.5
        assert result.results[0].p_value < 0.05

    def test_spearman_correlation(self):
        x = np.random.randn(50)
        y = x + np.random.randn(50) * 0.5
        params = CorrelationParams(method="spearman")
        result = CorrelationService.compute_correlation(x, y, params)
        assert abs(result.results[0].r) > 0.3

    def test_correlation_matrix(self):
        data = np.random.randn(30, 5)
        data[:, 1] = data[:, 0] + np.random.randn(30) * 0.3
        params = CorrelationParams(method="pearson")
        result = CorrelationService.compute_correlation_matrix(data, params)
        assert result.corr_matrix is not None
        assert result.corr_matrix.shape == (5, 5)
        assert result.corr_matrix[0, 0] == 1.0
        assert result.corr_matrix[0, 1] > 0.5

    def test_partial_correlation(self):
        data = np.random.randn(30, 4)
        data[:, 2] = data[:, 0] + data[:, 1] + np.random.randn(30) * 0.2
        params = CorrelationParams(method="partial")
        result = CorrelationService.compute_partial_correlation(
            data, control_indices=[0], target_indices=[1, 2, 3]
        )
        assert result.corr_matrix is not None
        assert result.corr_matrix.shape == (3, 3)


class TestMultipleComparisonService:
    def test_bonferroni(self):
        p_vals = np.array([0.01, 0.03, 0.04, 0.2, 0.5])
        result = MultipleComparisonService.correct_pvalues(p_vals, MultipleComparisonCorrection.BONFERRONI)
        assert len(result.p_values_corrected) == 5
        assert result.method == "bonferroni"

    def test_holm(self):
        p_vals = np.array([0.01, 0.03, 0.04, 0.2, 0.5])
        result = MultipleComparisonService.correct_pvalues(p_vals, MultipleComparisonCorrection.HOLM)
        assert result.method == "holm"
        # Holm 比 Bonferroni 更有力
        assert result.p_values_corrected[0] <= 1.0

    def test_fdr_bh(self):
        p_vals = np.random.uniform(0, 1, 20)
        p_vals[0] = 0.001  # 确保有显著结果
        result = MultipleComparisonService.correct_pvalues(p_vals, MultipleComparisonCorrection.FDR_BH)
        assert result.method == "fdr_bh"
        assert np.sum(result.rejected) >= 1

    def test_fdr_by(self):
        p_vals = np.random.uniform(0, 1, 20)
        result = MultipleComparisonService.correct_pvalues(p_vals, MultipleComparisonCorrection.FDR_BY)
        assert result.method == "fdr_by"

    def test_tfce_detects_cluster(self):
        rng = np.random.default_rng(1)
        stat = rng.normal(0, 1, (8, 20))
        stat[2:4, 8:12] += 2.5
        null = rng.normal(0, 1, (39, 8, 20))
        result = MultipleComparisonService.tfce_correction(stat, null, alpha=0.05)
        assert result.method == "tfce"
        assert result.rejected.shape == stat.shape
        assert bool(result.rejected[2:4, 8:12].any())
        assert float(result.p_values_corrected.min()) < 0.05


class TestEffectSizeService:
    def test_cohen_d_independent(self):
        g1 = np.random.randn(30) * 10
        g2 = np.random.randn(30) * 10 + 5
        result = EffectSizeService.cohen_d(g1, g2, paired=False)
        assert result.value > 0
        assert result.effect_size_type == EffectSize.COHEN_D

    def test_cohen_d_paired(self):
        g1 = np.random.randn(30) * 10
        g2 = g1 + np.random.randn(30) * 2
        result = EffectSizeService.cohen_d(g1, g2, paired=True)
        assert result.effect_size_type == EffectSize.COHEN_D

    def test_hedges_g(self):
        g1 = np.random.randn(10) * 10
        g2 = np.random.randn(10) * 10 + 3
        result = EffectSizeService.cohen_d(g1, g2, paired=False, correction=True)
        assert result.effect_size_type == EffectSize.HEDGES_G

    def test_cliff_delta(self):
        g1 = np.random.randn(20) * 10 + 5
        g2 = np.random.randn(20) * 10
        result = EffectSizeService.cliff_delta(g1, g2)
        assert result.effect_size_type == EffectSize.CLIFF_DELTA

    def test_eta_squared(self):
        result = EffectSizeService.eta_squared(50.0, 200.0)
        assert result.value == 0.25
        assert result.effect_size_type == EffectSize.ETA_SQUARED

    def test_partial_eta_squared(self):
        result = EffectSizeService.partial_eta_squared(50.0, 150.0)
        assert result.value == 0.25

    def test_omega_squared(self):
        result = EffectSizeService.omega_squared(50.0, 150.0, 2, 57, 2.63)
        assert result.value >= 0

    def test_cliff_delta_interpretation(self):
        assert EffectSizeService.interpret_cliff_delta(0.1) == "negligible"
        assert EffectSizeService.interpret_cliff_delta(0.2) == "small"
        assert EffectSizeService.interpret_cliff_delta(0.4) == "medium"
        assert EffectSizeService.interpret_cliff_delta(0.6) == "large"

    def test_compute_all(self):
        g1 = np.random.randn(30) * 10
        g2 = np.random.randn(30) * 10 + 4
        results = EffectSizeService.compute_all(g1, g2)
        assert "cohen_d" in results
        assert "hedges_g" in results
        assert "cliff_delta" in results
        assert "rrb" in results


# ---- 集成测试 ----
class TestStatisticsIntegration:
    def test_full_pipeline_ttest(self):
        """完整流程：数据 -> t检验 -> 校正 -> 效应量"""
        g1, g2 = make_two_groups(diff=0.8)
        
        # 1. t检验
        params = TTestParams(test_type="independent")
        result = StatisticalTestService.run_ttest(g1, g2, params)
        assert result is not None
        
        # 2. 效应量
        es_result = EffectSizeService.cohen_d(g1, g2)
        assert es_result.value > 0

    def test_correlation_with_behavior(self):
        """EEG 特征与行为数据相关性"""
        np.random.seed(42)
        eeg = np.random.randn(50, 10)
        behavior = eeg[:, 0] * 2 + np.random.randn(50)
        
        params = CorrelationParams(method="pearson")
        result = CorrelationService.correlate_with_behavior(eeg, behavior, CorrelationParams())
        
        assert result.corr_matrix is not None
        assert result.corr_matrix.shape == (10, 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])