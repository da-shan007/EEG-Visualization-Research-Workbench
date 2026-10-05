"""统计分析模块 ViewModel"""
from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

import numpy as np

from PySide6.QtCore import Signal, Slot, QObject

from eeg_workbench.core.base import ViewModelBase, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.statistics import (
    StatisticsParams, TTestParams, ANOVAParams, NonparametricParams,
    PermutationParams, CorrelationParams,
    StatisticalTest, MultipleComparisonCorrection, EffectSize,
    ComparisonResult, CorrelationResult, StatisticsResult,
    create_statistics_params
)
from eeg_workbench.services.statistics import (
    StatisticalTestService, PermutationService, CorrelationService,
    MultipleComparisonService, EffectSizeService,
    TTestResult, PermutationResult, CorrelationResultWrap
)
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.viewmodels.source_vm import SourceViewModel


@dataclass
class StatisticsStepUI:
    name: str
    description: str
    completed: bool = False
    processing_time_ms: float = 0.0


class StatisticsViewModel(ViewModelBase):
    """统计分析模块 ViewModel"""

    # 信号
    dataset_changed = Signal(object)
    ttest_result = Signal(object)           # ComparisonResult
    anova_result = Signal(object)           # dict
    nonparametric_result = Signal(object)   # dict
    permutation_result = Signal(object)     # PermutationResult
    correlation_result = Signal(object)     # CorrelationResultWrap
    correction_result = Signal(object)      # CorrectionResult
    effect_size_result = Signal(object)     # EffectSizeResult
    processing_steps_changed = Signal(list)
    status_message = Signal(str)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        preproc_vm: PreprocessingViewModel,
        features_vm: FeaturesViewModel,
        erp_vm: ERPViewModel,
        source_vm: SourceViewModel,
        parent: QObject | None = None
    ):
        super().__init__(parent)
        self._data_vm = data_vm
        self._preproc_vm = preproc_vm
        self._features_vm = features_vm
        self._erp_vm = erp_vm
        self._source_vm = source_vm
        self._dataset: Optional[EEGDataset] = None

        # 参数
        self._stats_params = StatisticsParams()
        self._ttest_params = TTestParams()
        self._anova_params = ANOVAParams()
        self._nonparam_params = NonparametricParams()
        self._perm_params = PermutationParams()
        self._corr_params = CorrelationParams()

        # 结果缓存
        self._ttest_results: list = []
        self._anova_results: list = []
        self._correlation_results: list = []

        self._processing_steps: list[StatisticsStepUI] = []

        # 订阅数据变化
        self._data_vm.dataset_changed.connect(self._on_dataset_changed)
        self._preproc_vm.dataset_changed.connect(self._on_preproc_dataset_changed)
        self._features_vm.dataset_changed.connect(self._on_features_dataset_changed)

    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def stats_params(self) -> StatisticsParams:
        return self._stats_params

    @property
    def ttest_params(self) -> TTestParams:
        return self._ttest_params

    @property
    def anova_params(self) -> ANOVAParams:
        return self._anova_params

    @property
    def nonparam_params(self) -> NonparametricParams:
        return self._nonparam_params

    @property
    def perm_params(self) -> PermutationParams:
        return self._perm_params

    @property
    def corr_params(self) -> CorrelationParams:
        return self._corr_params

    @property
    def available_variables(self) -> list[str]:
        """可用于统计的变量列表"""
        vars = []
        if self._dataset:
            vars.extend(["channel", "time", "frequency"])
        if self._erp_vm._erp_result:
            vars.extend(["ERP_amplitude", "ERP_latency"])
        if self._features_vm._band_power_result:
            vars.extend(["band_power"])
        return vars

    # ---- 参数设置 ----
    def set_stats_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._stats_params, k):
                setattr(self._stats_params, k, v)

    def set_ttest_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._ttest_params, k):
                setattr(self._ttest_params, k, v)

    def set_anova_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._anova_params, k):
                setattr(self._anova_params, k, v)

    def set_nonparam_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._nonparam_params, k):
                setattr(self._nonparam_params, k, v)

    def set_perm_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._perm_params, k):
                setattr(self._perm_params, k, v)

    def set_corr_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._corr_params, k):
                setattr(self._corr_params, k, v)

    def apply_preset(self, design: str, **overrides):
        """应用预设设计"""
        self._stats_params = create_statistics_params(design, **overrides)
        self._sync_from_vm()

    # ---- 统计检验执行 ----
    @async_slot
    def run_ttest(
        self,
        group1_data: np.ndarray,
        group2_data: np.ndarray | None = None,
        group1_name: str = "Group1",
        group2_name: str = "Group2"
    ) -> Optional[ComparisonResult]:
        """运行 t 检验"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._ttest_params.validate() if hasattr(self._ttest_params, 'validate') else []
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在运行 {self._ttest_params.test_type} t 检验...")
        
        result_wrap = StatisticalTestService.run_ttest(group1_data, group2_data, self._ttest_params)
        
        if result_wrap:
            self._ttest_results.append({
                "groups": (group1_name, group2_name),
                "result": result_wrap.result
            })
            self._add_step(f"t检验 ({self._ttest_params.test_type})", f"{group1_name} vs {group2_name}")
            self.ttest_result.emit(result_wrap.result)
            self.show_status(f"t 检验完成: p={result_wrap.result.p_value:.4f}")

        return result_wrap.result

    @async_slot
    def run_anova(
        self,
        groups_data: list[np.ndarray],
        group_names: list[str],
        subject_ids: np.ndarray | list | None = None,
    ) -> Optional[dict]:
        """运行方差分析"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        self.show_status(f"正在运行 {self._anova_params.design} ANOVA...")
        
        result = StatisticalTestService.run_anova(
            groups_data, self._anova_params, subject_ids=subject_ids
        )
        
        if result:
            self._anova_results.append({
                "groups": group_names,
                "result": result
            })
            self._add_step(f"ANOVA ({self._anova_params.design})", f"{len(groups_data)} 组")
            self.anova_result.emit(result)
            self.show_status("ANOVA 完成")

        return result

    @async_slot
    def run_nonparametric(
        self,
        group1: np.ndarray,
        group2: np.ndarray | None,
        groups: list[np.ndarray] | None = None,
    ) -> Optional[dict]:
        """运行非参数检验"""
        if not self._dataset:
            return None

        self.show_status(f"正在运行 {self._nonparam_params.test.value}...")
        
        result = StatisticalTestService.run_nonparametric(
            group1, group2, self._nonparam_params, groups=groups
        )
        
        if result:
            self.nonparametric_result.emit(result)
            self.show_status(f"非参数检验完成: p={result['p_value']:.4f}")

        return result

    @async_slot
    def run_permutation_test(
        self,
        group1: np.ndarray,
        group2: np.ndarray
    ) -> Optional[PermutationResult]:
        """运行置换检验"""
        if not self._dataset:
            return None

        self.show_status("正在运行置换检验...")
        
        result = PermutationService.run_permutation_ttest(group1, group2, self._perm_params)
        
        if result:
            self.permutation_result.emit(result)
            self.show_status(f"置换检验完成: p={result.result.p_value:.4f}")

        return result

    @async_slot
    def run_cluster_permutation(
        self,
        data: np.ndarray,  # (n_subjects, n_channels, n_times) or (n_subjects, n_channels)
        channel_adjacency: np.ndarray | None = None
    ) -> Optional[dict]:
        """运行簇置换检验"""
        if not self._dataset:
            return None

        self.show_status("正在运行簇置换检验...")
        
        result = PermutationService.run_cluster_permutation(data, self._perm_params, channel_adjacency=channel_adjacency)
        
        if result:
            self.permutation_result.emit(PermutationResult(
                result=ComparisonResult(
                    test_name="cluster_permutation",
                    statistic=result.get("observed_max_stat", 0),
                    p_value=result.get("p_value", 1),
                    significant=result.get("significant", False)
                ),
                null_distribution=result.get("null_distribution", np.array([])),
                observed_statistic=result.get("observed_max_stat", 0),
                processing_time_ms=0
            ))
            self.show_status(f"簇置换检验完成: p={result.get('p_value', 1):.4f}")

        return result

    @async_slot
    def run_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray | None = None,
        data_matrix: np.ndarray | None = None,
        variable_names: list[str] | None = None
    ) -> Optional[CorrelationResultWrap]:
        """运行相关性分析"""
        if not self._dataset:
            return None

        self.show_status(f"正在计算 {self._corr_params.method} 相关性...")
        
        if data_matrix is not None:
            result = CorrelationService.compute_correlation_matrix(data_matrix, self._corr_params)
        elif y is not None:
            result = CorrelationService.compute_correlation(x, y, self._corr_params)
        else:
            self.error_occurred.emit("请提供数据")
            return None

        if result:
            self._correlation_results.append(result)
            self._add_step(f"相关性 ({self._corr_params.method})", f"{len(result.results)} 对变量")
            self.correlation_result.emit(result)
            self.show_status(f"相关性分析完成: {len(result.results)} 对")

        return result

    @async_slot
    def run_partial_correlation(
        self,
        data: np.ndarray,
        control_indices: list[int],
        target_indices: list[int] | None = None
    ) -> Optional[CorrelationResultWrap]:
        """运行偏相关"""
        if not self._dataset:
            return None

        self.show_status("正在计算偏相关...")
        
        result = CorrelationService.compute_partial_correlation(
            data, control_indices, target_indices, self._corr_params
        )
        
        if result:
            self.correlation_result.emit(result)
            self.show_status("偏相关计算完成")

        return result

    @async_slot
    def correlate_eeg_behavior(
        self,
        eeg_features: np.ndarray,
        behavior: np.ndarray
    ) -> Optional[CorrelationResultWrap]:
        """EEG 特征与行为数据相关性"""
        if not self._dataset:
            return None

        self.show_status("正在计算 EEG-行为相关性...")
        
        result = CorrelationService.correlate_with_behavior(eeg_features, behavior, self._corr_params)
        
        if result:
            self.correlation_result.emit(result)
            self.show_status("EEG-行为相关性完成")

        return result

    @async_slot
    def run_multiple_comparison_correction(
        self,
        p_values: np.ndarray,
        method: MultipleComparisonCorrection | None = None
    ) -> Optional[dict]:
        """多重比较校正"""
        if method is None:
            method = self._stats_params.global_correction

        result = MultipleComparisonService.correct_pvalues(p_values, method)
        self.correction_result.emit(result)
        self.show_status(f"校正完成: {sum(result.rejected)}/{len(p_values)} 显著")
        return result.__dict__

    @async_slot
    def compute_effect_size(
        self,
        group1: np.ndarray,
        group2: np.ndarray,
        effect_type: EffectSize = EffectSize.COHEN_D
    ) -> Optional[dict]:
        """计算效应量"""
        from eeg_workbench.services.statistics.effect_size import (
            compute_effect_size as _compute_effect_size,
        )
        result = _compute_effect_size(group1, group2, effect_type)
        self.effect_size_result.emit(result)
        return dict(result.__dict__) if result else None

    def run_effect_size(
        self,
        effect_type: EffectSize = EffectSize.COHEN_D,
    ) -> Optional[dict]:
        """基于当前数据集事件分组的效应量便捷计算

        按事件描述把采样点分成两组，比较两组的平均振幅，
        返回 None 表示数据不足以分组。
        """
        ds = self._dataset
        if ds is None or ds.data is None or ds.data.size == 0:
            return None
        events = list(getattr(ds, "events", []) or [])
        if len(events) < 2:
            return None

        sfreq = float(ds.sfreq or 100.0)
        n_times = ds.data.shape[1]

        groups: dict[str, list[np.ndarray]] = {}
        for ev in events:
            key = (ev.description or str(ev.value)).strip() or "unknown"
            idx = int(round(ev.onset * sfreq))
            if 0 <= idx < n_times:
                groups.setdefault(key, []).append(ds.data[:, idx])

        if len(groups) < 2:
            return None

        keys = sorted(groups)[:2]
        g1 = np.concatenate([v.reshape(-1) for v in groups[keys[0]]])
        g2 = np.concatenate([v.reshape(-1) for v in groups[keys[1]]])
        if g1.size < 2 or g2.size < 2:
            return None

        from eeg_workbench.services.statistics.effect_size import (
            compute_effect_size as _compute_effect_size,
        )
        result = _compute_effect_size(g1, g2, effect_type)
        self.effect_size_result.emit(result)
        self.show_status(
            f"效应量完成 ({keys[0]} vs {keys[1]}): {result.value:.3f}"
            if result else "效应量计算完成"
        )
        return dict(result.__dict__) if result else None

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset):
        self._dataset = dataset
        # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm）
        self.dataset_changed.emit(dataset)

    def _on_preproc_dataset_changed(self, dataset):
        if dataset:
            self._dataset = dataset
            self.dataset_changed.emit(dataset)

    def _on_features_dataset_changed(self, dataset):
        if dataset:
            self._dataset = dataset
            self.dataset_changed.emit(dataset)

    def _add_step(self, name: str, desc: str, time_ms: float = 0):
        step = StatisticsStepUI(name=name, description=desc, completed=True, processing_time_ms=time_ms)
        self._processing_steps.append(step)
        self.processing_steps_changed.emit(self._processing_steps)

    def _sync_from_vm(self):
        # 同步 UI 参数
        pass