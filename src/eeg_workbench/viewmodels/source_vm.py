"""源定位模块 ViewModel"""
from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass

from PySide6.QtCore import Signal, Slot, QObject

from eeg_workbench.core.base import ViewModelBase, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.source import (
    HeadModelParams, ForwardModelParams, InverseParams, DipoleFitParams,
    HeadModelType, SourceSpaceType, InverseMethod,
    HeadModelResult, ForwardModelResult, InverseSolutionResult,
    create_head_model_params, create_inverse_params, create_forward_params
)
from eeg_workbench.services.source import (
    HeadModelService, ForwardModelService, InverseService, DipoleFitService,
    SourceVisualization3D,
    build_head_model, compute_forward_solution, compute_inverse_solution, fit_dipoles
)
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.viewmodels.erp_vm import ERPViewModel


@dataclass
class SourceStepUI:
    name: str
    description: str
    completed: bool = False
    processing_time_ms: float = 0.0


class SourceViewModel(ViewModelBase):
    """源定位与脑区分析 ViewModel"""

    dataset_changed = Signal(object)
    head_model_ready = Signal(object)
    forward_model_ready = Signal(object)
    inverse_solution_ready = Signal(object)
    dipole_fit_ready = Signal(object)
    visualization_ready = Signal(object)
    processing_steps_changed = Signal(list)
    available_subjects_changed = Signal(list)
    status_message = Signal(str)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        preproc_vm: PreprocessingViewModel,
        features_vm: FeaturesViewModel,
        erp_vm: ERPViewModel,
        parent: QObject | None = None
    ):
        super().__init__(parent)
        self._data_vm = data_vm
        self._preproc_vm = preproc_vm
        self._features_vm = features_vm
        self._erp_vm = erp_vm
        self._dataset: Optional[EEGDataset] = None

        # 参数
        self._head_model_params = create_head_model_params("fsaverage_bem")
        self._forward_params = create_forward_params()
        self._inverse_params = create_inverse_params(InverseMethod.MNE)
        self._dipole_params = DipoleFitParams()

        # 结果缓存
        self._head_model_result: Optional[HeadModelResult] = None
        self._forward_result: Optional[ForwardModelResult] = None
        self._inverse_result: Optional[InverseSolutionResult] = None
        self._dipole_result: Optional[Any] = None
        self._viz = None  # 最近一次 3D 可视化对象（供场景导出复用）

        self._processing_steps: list[SourceStepUI] = []

        self._data_vm.dataset_changed.connect(self._on_dataset_changed)
        self._preproc_vm.dataset_changed.connect(self._on_preproc_dataset_changed)

    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def head_model_params(self) -> HeadModelParams:
        return self._head_model_params

    @property
    def forward_params(self) -> ForwardModelParams:
        return self._forward_params

    @property
    def inverse_params(self) -> InverseParams:
        return self._inverse_params

    @property
    def dipole_params(self) -> DipoleFitParams:
        return self._dipole_params

    @property
    def eeg_channels(self) -> list[str]:
        return self._dataset.eeg_channels if self._dataset else []

    # ---- 参数设置 ----
    def set_head_model_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._head_model_params, k):
                setattr(self._head_model_params, k, v)

    def set_forward_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._forward_params, k):
                setattr(self._forward_params, k, v)

    def set_inverse_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._inverse_params, k):
                setattr(self._inverse_params, k, v)

    def set_dipole_params(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._dipole_params, k):
                setattr(self._dipole_params, k, v)

    def apply_head_model_preset(self, preset: str):
        self._head_model_params = create_head_model_params(preset)

    def apply_inverse_preset(self, method: str, **kwargs):
        method_enum = InverseMethod(method)
        self._inverse_params = create_inverse_params(method_enum, **kwargs)

    # ---- 源定位流程 ----
    # 注：三步均拆为同步 core（_do_*）+ @async_slot 包装，供 run_full_pipeline
    # 真正按顺序执行；core 内 try/except 把异常转 error_occurred，避免 @async_slot
    # 吞异常导致的静默失败（验收 Step7 曾因此无任何报错地返回 None）。
    @async_slot
    def run_head_model(self) -> Any:
        return self._do_head_model()

    def _do_head_model(self) -> Any:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._head_model_params.validate()
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status("正在构建头模型...")
        try:
            result = HeadModelService.build(self._dataset, self._head_model_params)
        except Exception as e:
            self.error_occurred.emit(f"头模型构建失败: {e}")
            return None

        if result:
            self._head_model_result = result
            self._add_step("头模型", f"{result.model_type.value} ({result.subject})", result.processing_time_ms)
            self.head_model_ready.emit(result)
            self.show_status(f"头模型构建完成 ({result.model_type.value})")

        return result

    @async_slot
    def run_forward_model(self) -> Any:
        return self._do_forward()

    def _do_forward(self) -> Any:
        if not self._head_model_result:
            self.error_occurred.emit("请先构建头模型")
            return None

        self.show_status("正在计算导场矩阵...")
        try:
            result = ForwardModelService.compute(
                self._dataset, self._head_model_result, self._forward_params)
        except Exception as e:
            self.error_occurred.emit(f"前向模型计算失败: {e}")
            return None

        if result:
            self._forward_result = result
            info = result.leadfield_info
            self._add_step("前向模型", f"{info['n_sources']}源 x {info['n_channels']}通道", result.processing_time_ms)
            self.forward_model_ready.emit(result)
            self.show_status(f"导场矩阵计算完成")

        return result

    @async_slot
    def run_inverse_solution(self) -> Any:
        return self._do_inverse()

    def _do_inverse(self) -> Any:
        if not self._forward_result:
            self.error_occurred.emit("请先计算前向模型")
            return None

        self.show_status(f"正在计算逆向解 ({self._inverse_params.method.value})...")
        try:
            result = InverseService.compute(
                self._dataset, self._forward_result, self._inverse_params)
        except Exception as e:
            self.error_occurred.emit(f"逆向解计算失败: {e}")
            return None

        if result:
            self._inverse_result = result
            self._add_step("逆向解", f"{result.method}, SNR={self._inverse_params.snr}", result.processing_time_ms)
            self.inverse_solution_ready.emit(result)
            self.show_status(f"逆向解计算完成")

        return result

    @async_slot
    def run_dipole_fit(self) -> Any:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        self.show_status("正在拟合偶极子...")
        try:
            result = DipoleFitService.fit(self._dataset, self._dipole_params)
        except Exception as e:
            self.error_occurred.emit(f"偶极子拟合失败: {e}")
            return None

        if result:
            self._dipole_result = result
            self._add_step("偶极子拟合", f"{len(result.dipoles)} 个偶极子", result.processing_time_ms)
            self.dipole_fit_ready.emit(result)
            self.show_status(f"偶极子拟合完成: {len(result.dipoles)} 个")

        return result

    @async_slot
    def run_full_pipeline(self) -> bool:
        """一键运行完整源定位流程（同步顺序执行，前一步失败即停）"""
        # 必须调用同步 core：若直接调 run_*（@async_slot 包装）会拿到未完成的
        # Command，下一步因前置结果缺失立刻失败。
        try:
            if not self._do_head_model():
                return False
            if not self._do_forward():
                return False
            if not self._do_inverse():
                return False
            return True
        except Exception as e:
            self.error_occurred.emit(f"流程失败: {e}")
            return False

    # ---- 3D 可视化 ----
    def plot_source_estimate(self, **kwargs):
        if not self._inverse_result or not self._inverse_result.stc:
            self.error_occurred.emit("请先计算逆向解")
            return None

        viz = SourceVisualization3D()
        self._viz = viz
        return viz.plot_source_estimate(self._inverse_result.stc, **kwargs)

    def plot_brain_3d(self, **kwargs):
        if not self._inverse_result or not self._inverse_result.stc:
            self.error_occurred.emit("请先计算逆向解")
            return None

        viz = SourceVisualization3D()
        return viz.plot_source_estimate(self._inverse_result.stc, **kwargs)

    def plot_dipoles_3d(self, **kwargs):
        if not self._dipole_result:
            self.error_occurred.emit("请先进行偶极子拟合")
            return None

        viz = SourceVisualization3D()
        self._viz = viz
        return viz.plot_dipoles_3d(self._dipole_result.dipoles, **kwargs)

    def plot_connectivity_3d(self, connectivity_matrix, **kwargs):
        if not self._inverse_result:
            return None
        
        viz = SourceVisualization3D()
        return viz.plot_connectivity_3d(
            connectivity_matrix,
            self._inverse_result.src[0].vert,
            self._inverse_result.src[0].faces,
            **kwargs
        )

    def export_3d_scene(self, filepath: str, format: str = "html"):
        if self._viz is None:
            self.error_occurred.emit("请先绘制 3D 源估计或偶极子，再导出场景")
            return False
        try:
            self._viz.export_scene(filepath, format=format)
            return True
        except Exception as e:
            self.error_occurred.emit(f"3D 场景导出失败: {e}")
            return False

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset):
        self._dataset = dataset
        if dataset:
            self._notify_available_subjects()
        # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm）
        self.dataset_changed.emit(dataset)

    def _on_preproc_dataset_changed(self, dataset):
        if dataset:
            self._dataset = dataset
            self.dataset_changed.emit(dataset)

    def _notify_available_subjects(self):
        subjects = ["fsaverage", "fsaverage_sym", "sample", "subject01"]
        self.available_subjects_changed.emit(subjects)

    def _add_step(self, name: str, desc: str, time_ms: float):
        step = SourceStepUI(name=name, description=desc, completed=True, processing_time_ms=time_ms)
        self._processing_steps.append(step)
        self.processing_steps_changed.emit(self._processing_steps)

    def _notify_available_channels(self):
        pass