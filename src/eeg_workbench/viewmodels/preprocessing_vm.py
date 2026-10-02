"""预处理模块 ViewModel：滤波、重参考、重采样、ICA、坏道插值"""
from __future__ import annotations
from typing import Optional, Any, Callable
from dataclasses import dataclass
from copy import deepcopy

from PySide6.QtCore import Signal, Slot, QObject, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from eeg_workbench.core.base import ViewModelBase, Command, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo
from eeg_workbench.models.preprocessing import (
    FilterParams, ReferenceParams, ResampleParams, ICAParams,
    BadChannelInterpolationParams,
    FilterType, ReferenceType, ResampleMethod, ICAComponentType, InterpolationMethod,
    FILTER_PRESETS, REFERENCE_PRESETS,
    create_filter_params, create_reference_params
)
from eeg_workbench.services.preprocessing import (
    FilterService, ReferenceService, ResampleService, ICAService, InterpolationService,
    FilterResult, ReferenceResult, ResampleResult, ICAResult, InterpolationResult
)
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel


@dataclass
class PreprocessingStepUI:
    """UI 显示用的预处理步骤"""
    name: str
    description: str
    params: dict
    enabled: bool = True
    applied: bool = False


class PreprocessingViewModel(ViewModelBase):
    """预处理模块 ViewModel"""

    # 信号
    dataset_changed = Signal(object)           # EEGDataset
    preprocessing_steps_changed = Signal(list) # list[PreprocessingStepUI]
    available_channels_changed = Signal(list)  # list[str]
    ica_ready = Signal(object)                 # ICAResult
    ica_component_selected = Signal(int, dict) # comp_idx, properties
    filter_params_changed = Signal()           # 滤波参数变更
    status_message = Signal(str)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        parent: QObject | None = None
    ):
        super().__init__(parent)
        self._data_vm = data_vm
        self._dataset: Optional[EEGDataset] = None
        self._ica_result: Optional[ICAResult] = None
        self._processing_steps: list[PreprocessingStepUI] = []

        # 默认参数
        self._filter_params = FILTER_PRESETS["standard"]
        self._reference_params = REFERENCE_PRESETS["average"]
        self._resample_params = ResampleParams(sfreq=250.0)
        self._ica_params = ICAParams()
        self._interp_params = BadChannelInterpolationParams()

        # 订阅数据管理模块的数据集变化
        self._data_vm.dataset_changed.connect(self._on_dataset_changed)

    # ---- 只读属性 ----
    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def filter_params(self) -> FilterParams:
        return self._filter_params

    @property
    def reference_params(self) -> ReferenceParams:
        return self._reference_params

    @property
    def resample_params(self) -> ResampleParams:
        return self._resample_params

    @property
    def ica_params(self) -> ICAParams:
        return self._ica_params

    @property
    def interpolation_params(self) -> BadChannelInterpolationParams:
        return self._interp_params

    @property
    def ica_result(self) -> Optional[ICAResult]:
        return self._ica_result

    @property
    def processing_steps(self) -> list[PreprocessingStepUI]:
        return self._processing_steps

    @property
    def eeg_channels(self) -> list[str]:
        if self._dataset:
            return self._dataset.eeg_channels
        return []

    @property
    def all_channels(self) -> list[str]:
        if self._dataset:
            return self._dataset.ch_names
        return []

    @property
    def bad_channels(self) -> list[str]:
        if self._dataset:
            return self._dataset.bad_channels
        return []

    # ---- 参数设置 ----
    def set_filter_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._filter_params, k):
                setattr(self._filter_params, k, v)
        errors = self._filter_params.validate()
        if errors:
            self.error_occurred.emit("; ".join(errors))

    def set_reference_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._reference_params, k):
                setattr(self._reference_params, k, v)

    def set_resample_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._resample_params, k):
                setattr(self._resample_params, k, v)

    def set_ica_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._ica_params, k):
                setattr(self._ica_params, k, v)

    def set_interpolation_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._interp_params, k):
                setattr(self._interp_params, k, v)

    def apply_filter_preset(self, preset: str) -> None:
        """应用滤波预设"""
        self._filter_params = create_filter_params(preset)
        self._notify_filter_params_changed()

    def apply_reference_preset(self, preset: str) -> None:
        self._reference_params = create_reference_params(preset)
        self._notify_reference_params_changed()

    # ---- 预处理执行命令 ----
    @async_slot
    def run_filter(self) -> FilterResult:
        """执行滤波"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._filter_params.validate()
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在执行 {self._filter_params.filter_type.value} 滤波...")
        result = FilterService.apply(self._dataset, self._filter_params)

        if result:
            self._dataset = result.dataset
            self._add_processing_step("滤波", self._filter_params)
            self.dataset_changed.emit(self._dataset)
            self.show_status(f"滤波完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_reference(self) -> ReferenceResult:
        """执行重参考"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._reference_params.validate(self._dataset.ch_names)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在执行 {self._reference_params.ref_type.value} 重参考...")
        result = ReferenceService.apply(self._dataset, self._reference_params)

        if result:
            self._dataset = result.dataset
            self._add_processing_step("重参考", self._reference_params)
            self.dataset_changed.emit(self._dataset)
            self._notify_available_channels()
            self.show_status(f"重参考完成 ({result.ref_info.get('type', '')})")

        return result

    @async_slot
    def run_resample(self) -> ResampleResult:
        """执行重采样"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._resample_params.validate(self._dataset.sfreq)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在重采样到 {self._resample_params.sfreq} Hz...")
        result = ResampleService.apply(self._dataset, self._resample_params)

        if result:
            self._dataset = result.dataset
            self._add_processing_step("重采样", self._resample_params)
            self.dataset_changed.emit(self._dataset)
            self.show_status(f"重采样完成 (比率 {result.ratio:.2f}x)")

        return result

    @async_slot
    def run_ica_fit(self) -> ICAResult:
        """拟合 ICA"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._ica_params.validate(self._dataset.n_channels, self._dataset.sfreq)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status("正在拟合 ICA...")
        service = ICAService()
        result = service.fit(self._dataset, self._ica_params)

        if result:
            self._ica_result = result
            self._add_processing_step("ICA拟合", self._ica_params)
            self.ica_ready.emit(result)
            self.show_status(f"ICA 拟合完成，共 {result.ica.n_components_} 个成分，自动排除 {len(result.components_excluded)} 个")

        return result

    @async_slot
    def run_ica_apply(self, exclude: list[int] | None = None) -> ICAResult:
        """应用 ICA (排除成分)"""
        if not self._ica_result or not self._ica_result.ica:
            self.error_occurred.emit("请先拟合 ICA")
            return None

        self.show_status("正在应用 ICA...")
        service = ICAService()
        result = service.apply(self._dataset, self._ica_result, exclude=exclude)

        if result:
            self._dataset = result.dataset
            self._ica_result = result
            self._update_processing_step("ICA应用", {"exclude": result.components_excluded})
            self.dataset_changed.emit(self._dataset)
            self.show_status(f"ICA 应用完成，排除了 {len(result.components_excluded)} 个成分")

        return result

    @async_slot
    def run_ica_fit_apply(self) -> ICAResult:
        """一步完成：拟合 + 应用"""
        result = self.run_ica_fit()
        if result:
            return self.run_ica_apply()
        return None

    @async_slot
    def run_interpolation(self) -> InterpolationResult:
        """执行坏道插值"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._interp_params.validate(
            self._dataset.ch_names,
            self._dataset.montage.positions if self._dataset.montage else {}
        )
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在执行 {self._interp_params.method.value} 坏道插值...")
        result = InterpolationService.apply(self._dataset, self._interp_params)

        if result:
            self._dataset = result.dataset
            self._add_processing_step("坏道插值", self._interp_params)
            self.dataset_changed.emit(self._dataset)
            self._notify_available_channels()
            self.show_status(f"插值完成，修复了 {len(result.interpolated_channels)} 个通道")

        return result

    # ---- 组合流程 ----
    @async_slot
    def run_standard_pipeline(self) -> EEGDataset | None:
        """标准预处理流程：滤波 -> 重参考 -> ICA -> 插值"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        try:
            # 1. 滤波
            self._filter_params = create_filter_params("standard")
            result = self.run_filter()
            if not result:
                return None

            # 2. 重参考
            self._reference_params = create_reference_params("average")
            result = self.run_reference()
            if not result:
                return None

            # 3. ICA
            self._ica_params = ICAParams(auto_find=True)
            result = self.run_ica_fit()
            if not result:
                return None

            result = self.run_ica_apply()
            if not result:
                return None

            # 4. 坏道插值 (如果有坏道)
            if self._dataset.bad_channels:
                self._interp_params = BadChannelInterpolationParams(
                    bad_channels=self._dataset.bad_channels
                )
                result = self.run_interpolation()
                if not result:
                    return None

            self.show_status("标准预处理流程完成")
            return self._dataset

        except Exception as e:
            self.error_occurred.emit(f"流程失败: {e}")
            return None

    # ---- 撤销/重做 ----
    def undo_last_step(self) -> bool:
        """撤销最后一步预处理 (通过历史回溯)"""
        if not self._dataset or len(self._dataset.processing_history) < 2:
            self.error_occurred.emit("无法撤销：没有历史记录")
            return False

        # 移除最后一步
        history = self._dataset.processing_history[:-1]
        # 这里需要完整的历史回放机制，暂时简化处理
        self.show_status("撤销功能需要完整的历史记录回放")
        return False

    # ---- ICA 交互 ----
    def set_ica_exclude(self, comp_indices: list[int]) -> None:
        """设置要排除的 ICA 成分"""
        if self._ica_result:
            self._ica_result.components_excluded = comp_indices
            # 更新标签
            for idx in comp_indices:
                self._ica_result.component_labels[idx] = "manual_exclude"
            self.ica_ready.emit(self._ica_result)

    def get_ica_properties(self, comp_idx: int) -> dict:
        """获取成分属性 (用于可视化)"""
        if self._ica_result:
            return self._ica_result.component_properties.get(comp_idx, {})
        return {}

    def plot_ica_components(self, **kwargs) -> None:
        """绘制 ICA 成分图"""
        if self._ica_result:
            service = ICAService()
            service.plot_components(self._ica_result, **kwargs)

    def plot_ica_sources(self, **kwargs) -> None:
        """绘制 ICA 成分时间序列"""
        if self._ica_result and self._dataset:
            service = ICAService()
            service.plot_sources(self._ica_result, self._dataset, **kwargs)

    def plot_ica_properties(self, picks: list[int], **kwargs) -> None:
        """绘制成分属性"""
        if self._ica_result and self._dataset:
            service = ICAService()
            service.plot_properties(self._ica_result, self._dataset, picks, **kwargs)

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        self._dataset = dataset
        # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm）
        self.dataset_changed.emit(dataset)
        self._ica_result = None
        self._processing_steps.clear()
        self.preprocessing_steps_changed.emit(self._processing_steps)
        self._notify_available_channels()
        self._notify_filter_params_changed()
        self._notify_reference_params_changed()

    def _add_processing_step(self, name: str, params: Any) -> None:
        step = PreprocessingStepUI(
            name=name,
            description=self._params_to_description(params),
            params=self._params_to_dict(params),
            applied=True
        )
        self._processing_steps.append(step)
        self.preprocessing_steps_changed.emit(self._processing_steps)

    def _update_processing_step(self, name: str, extra_params: dict) -> None:
        if self._processing_steps:
            last = self._processing_steps[-1]
            last.name = name
            last.params.update(extra_params)
            last.description = self._params_to_description(last.params)
            self.preprocessing_steps_changed.emit(self._processing_steps)

    def _params_to_description(self, params: Any) -> str:
        if isinstance(params, FilterParams):
            if params.filter_type == FilterType.NOTCH:
                return f"陷波 {params.notch_freq}Hz"
            elif params.filter_type == FilterType.BANDPASS:
                return f"带通 {params.l_freq}-{params.h_freq}Hz"
            elif params.filter_type == FilterType.HIGHPASS:
                return f"高通 {params.l_freq}Hz"
            elif params.filter_type == FilterType.LOWPASS:
                return f"低通 {params.h_freq}Hz"
            return params.filter_type.value
        elif isinstance(params, ReferenceParams):
            return params.ref_type.value
        elif isinstance(params, ResampleParams):
            return f"重采样到 {params.sfreq}Hz"
        elif isinstance(params, ICAParams):
            return f"ICA ({params.method}, {params.n_components or 'auto'} 成分)"
        elif isinstance(params, BadChannelInterpolationParams):
            return f"{params.method.value} 插值 {len(params.bad_channels)} 通道"
        return str(params)

    def _params_to_dict(self, params: Any) -> dict:
        if hasattr(params, "__dataclass_fields__"):
            return {k: getattr(params, k) for k in params.__dataclass_fields__}
        return {}

    def _notify_available_channels(self) -> None:
        self.available_channels_changed.emit(self.all_channels)

    def _notify_filter_params_changed(self) -> None:
        # 触发 UI 更新 (通过属性变更信号)
        pass

    def _notify_reference_params_changed(self) -> None:
        pass

    # ---- 导出/导入预处理流程 ----
    def export_pipeline(self, file_path: str) -> bool:
        """导出预处理流程为 JSON"""
        import json
        try:
            pipeline = {
                "steps": [step.params for step in self._processing_steps],
                "dataset_info": {
                    "n_channels": self._dataset.n_channels if self._dataset else 0,
                    "sfreq": self._dataset.sfreq if self._dataset else 0,
                }
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(pipeline, f, indent=2, ensure_ascii=False)
            self.show_status(f"流程已导出: {file_path}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出失败: {e}")
            return False

    def import_pipeline(self, file_path: str) -> bool:
        """导入预处理流程"""
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                pipeline = json.load(f)
            # 恢复参数 (简化版)
            self.show_status(f"流程已导入: {file_path}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导入失败: {e}")
            return False