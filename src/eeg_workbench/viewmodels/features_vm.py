"""特征提取模块 ViewModel：频段功率、时频分析、连通性、非线性"""
from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass
from copy import deepcopy

from PySide6.QtCore import Signal, Slot, QObject

from eeg_workbench.core.base import ViewModelBase, Command, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import (
    BandPowerParams, TimeFrequencyParams, ConnectivityParams, NonlinearParams,
    SpectralMethod, TimeFrequencyMethod, ConnectivityMethod, NonlinearMeasure,
    FeatureExtractionResult, STANDARD_BANDS
)
from eeg_workbench.services.features import (
    SpectralService, TimeFrequencyService, ConnectivityService, NonlinearService,
    BandPowerResult, TFRResult, ConnectivityResult, NonlinearResult,
    compute_band_power, compute_tfr, compute_connectivity, compute_nonlinear_features
)
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel


@dataclass
class FeatureResultUI:
    """UI 显示用的特征结果"""
    feature_type: str
    description: str
    shape: tuple
    processing_time_ms: float
    params: dict


class FeaturesViewModel(ViewModelBase):
    """特征提取模块 ViewModel"""

    # 信号
    dataset_changed = Signal(object)              # EEGDataset
    band_power_result = Signal(object)            # FeatureExtractionResult
    tfr_result = Signal(object)                   # FeatureExtractionResult
    connectivity_result = Signal(object)          # FeatureExtractionResult
    nonlinear_result = Signal(object)             # FeatureExtractionResult
    available_channels_changed = Signal(list)     # list[str]
    processing_steps_changed = Signal(list)       # list[FeatureResultUI]
    status_message = Signal(str)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        preproc_vm: PreprocessingViewModel,
        parent: QObject | None = None
    ):
        super().__init__(parent)
        self._data_vm = data_vm
        self._preproc_vm = preproc_vm
        self._dataset: Optional[EEGDataset] = None

        # 参数
        self._band_power_params = BandPowerParams()
        self._tf_params = TimeFrequencyParams()
        self._conn_params = ConnectivityParams()
        self._nonlinear_params = NonlinearParams()

        # 结果缓存
        self._band_power_result: Optional[FeatureExtractionResult] = None
        self._tfr_result: Optional[FeatureExtractionResult] = None
        self._conn_result: Optional[FeatureExtractionResult] = None
        self._nonlinear_result: Optional[FeatureExtractionResult] = None

        self._processing_steps: list[FeatureResultUI] = []

        # 订阅数据变化
        self._data_vm.dataset_changed.connect(self._on_dataset_changed)
        self._preproc_vm.dataset_changed.connect(self._on_preproc_dataset_changed)

    # ---- 只读属性 ----
    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def band_power_params(self) -> BandPowerParams:
        return self._band_power_params

    @property
    def tf_params(self) -> TimeFrequencyParams:
        return self._tf_params

    @property
    def conn_params(self) -> ConnectivityParams:
        return self._conn_params

    @property
    def nonlinear_params(self) -> NonlinearParams:
        return self._nonlinear_params

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

    # ---- 参数设置 ----
    def set_band_power_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._band_power_params, k):
                setattr(self._band_power_params, k, v)
        errors = self._band_power_params.validate(self._dataset.sfreq if self._dataset else 250)
        if errors:
            self.error_occurred.emit("; ".join(errors))

    def set_tf_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._tf_params, k):
                setattr(self._tf_params, k, v)
        errors = self._tf_params.validate(
            self._dataset.sfreq if self._dataset else 250,
            self._dataset.n_samples if self._dataset else 1000
        )
        if errors:
            self.error_occurred.emit("; ".join(errors))

    def set_conn_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._conn_params, k):
                setattr(self._conn_params, k, v)

    def set_nonlinear_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._nonlinear_params, k):
                setattr(self._nonlinear_params, k, v)
        errors = self._nonlinear_params.validate(
            self._dataset.n_samples if self._dataset else 1000
        )
        if errors:
            self.error_occurred.emit("; ".join(errors))

    def apply_band_preset(self, preset: str) -> None:
        """应用频段预设"""
        self._band_power_params = create_band_power_params(preset)
        # 触发 UI 更新

    # ---- 特征提取执行 ----
    @async_slot
    def run_band_power(self, epochs_data: np.ndarray | None = None) -> BandPowerResult | None:
        """计算频段功率"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._band_power_params.validate(self._dataset.sfreq)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status("正在计算频段功率...")
        result = SpectralService.compute(self._dataset, self._band_power_params, epochs_data=epochs_data)

        if result and result.feature_result:
            self._band_power_result = result.feature_result
            self._add_processing_step("频段功率", self._band_power_params, result.feature_result)
            self.band_power_result.emit(result.feature_result)
            self.show_status(f"频段功率计算完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_time_frequency(self, epochs_data: np.ndarray | None = None) -> TFRResult | None:
        """计算时频图"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._tf_params.validate(
            self._dataset.sfreq, self._dataset.n_samples
        )
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在计算时频图 ({self._tf_params.method.value})...")
        result = TimeFrequencyService.compute(self._dataset, self._tf_params, epochs_data=epochs_data)

        if result and result.feature_result:
            self._tfr_result = result.feature_result
            self._add_processing_step("时频分析", self._tf_params, result.feature_result)
            self.tfr_result.emit(result.feature_result)
            self.show_status(f"时频分析完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_connectivity(self, epochs_data: np.ndarray | None = None) -> ConnectivityResult | None:
        """计算连通性"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._conn_params.validate(self._dataset.sfreq, self._dataset.n_channels)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在计算连通性 ({self._conn_params.method.value})...")
        result = ConnectivityService.compute(self._dataset, self._conn_params, epochs_data=epochs_data)

        if result and result.feature_result:
            self._conn_result = result.feature_result
            self._add_processing_step("连通性分析", self._conn_params, result.feature_result)
            self.connectivity_result.emit(result.feature_result)
            self.show_status(f"连通性分析完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_nonlinear(self, epochs_data: np.ndarray | None = None) -> NonlinearResult | None:
        """计算非线性指标"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        errors = self._nonlinear_params.validate(self._dataset.n_samples)
        if errors:
            self.error_occurred.emit("; ".join(errors))
            return None

        self.show_status(f"正在计算非线性指标 ({len(self._nonlinear_params.measures)} 项)...")
        result = NonlinearService.compute(self._dataset, self._nonlinear_params, epochs_data=epochs_data)

        if result and result.feature_result:
            self._nonlinear_result = result.feature_result
            self._add_processing_step("非线性分析", self._nonlinear_params, result.feature_result)
            self.nonlinear_result.emit(result.feature_result)
            self.show_status(f"非线性分析完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_all_features(self, epochs_data: np.ndarray | None = None) -> dict | None:
        """一键运行所有特征提取"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        results = {}
        try:
            # 1. 频段功率
            bp = self.run_band_power(epochs_data)
            results["band_power"] = bp

            # 2. 时频
            tfr = self.run_time_frequency(epochs_data)
            results["time_frequency"] = tfr

            # 3. 连通性
            conn = self.run_connectivity(epochs_data)
            results["connectivity"] = conn

            # 4. 非线性
            nl = self.run_nonlinear(epochs_data)
            results["nonlinear"] = nl

            self.show_status("所有特征提取完成")
            return results

        except Exception as e:
            self.error_occurred.emit(f"特征提取失败: {e}")
            return None

    # ---- Epochs 相关 ----
    def extract_epochs_for_analysis(
        self,
        event_descriptions: list[str],
        tmin: float = -0.2,
        tmax: float = 0.8,
        baseline: tuple[float, float] | None = (-0.2, 0.0)
    ) -> np.ndarray | None:
        """从当前数据集提取 Epochs 用于特征分析
        返回: (n_epochs, n_ch, n_times)
        """
        if not self._dataset:
            return None

        from eeg_workbench.services.segmentation import extract_epochs_as_dataset
        epochs = extract_epochs_as_dataset(
            self._dataset, event_descriptions, tmin, tmax, baseline
        )

        if not epochs:
            self.error_occurred.emit("未找到匹配的事件")
            return None

        # 堆叠为 (n_epochs, n_ch, n_times)
        epochs_data = np.stack([ep.data for ep in epochs])
        return epochs_data

    # ---- 结果导出 ----
    def export_results(self, file_path: str, feature_type: str = "all") -> bool:
        """导出特征结果为 NPZ/CSV"""
        import numpy as np
        try:
            if feature_type == "all" or feature_type == "band_power":
                if self._band_power_result:
                    np.savez(f"{file_path}_band_power.npz",
                             **self._band_power_result.band_power)
            if feature_type == "all" or feature_type == "time_frequency":
                if self._tfr_result:
                    np.savez(f"{file_path}_tfr.npz",
                             tfr=self._tfr_result.time_frequency,
                             freqs=self._tfr_result.tf_freqs,
                             times=self._tfr_result.tf_times)
            if feature_type == "all" or feature_type == "connectivity":
                if self._conn_result:
                    np.savez(f"{file_path}_conn.npz",
                             conn=self._conn_result.connectivity,
                             freqs=self._conn_result.conn_freqs)
            if feature_type == "all" or feature_type == "nonlinear":
                if self._nonlinear_result:
                    np.savez(f"{file_path}_nonlinear.npz",
                             **self._nonlinear_result.nonlinear)

            self.show_status(f"结果已导出: {file_path}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出失败: {e}")
            return False

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        self._dataset = dataset
        self._notify_available_channels()
        # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm）
        self.dataset_changed.emit(dataset)

    def _on_preproc_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        # 预处理后的数据集更新
        if dataset:
            self._dataset = dataset
            self._notify_available_channels()
            self.dataset_changed.emit(dataset)

    def _notify_available_channels(self) -> None:
        self.available_channels_changed.emit(self.all_channels)

    def _add_processing_step(
        self,
        name: str,
        params: Any,
        result: FeatureExtractionResult
    ) -> None:
        step = FeatureResultUI(
            feature_type=name,
            description=self._params_to_description(name, params),
            shape=self._get_result_shape(name, result),
            processing_time_ms=result.processing_time_ms,
            params=self._params_to_dict(params)
        )
        self._processing_steps.append(step)
        self.processing_steps_changed.emit(self._processing_steps)

    def _params_to_description(self, name: str, params: Any) -> str:
        if name == "频段功率":
            return f"{len(params.bands)} 频段, {params.method.value}"
        elif name == "时频分析":
            return f"{params.method.value}, {params.fmin}-{params.fmax}Hz"
        elif name == "连通性分析":
            return f"{params.method.value}, {params.fmin}-{params.fmax or 'Nyq'}Hz"
        elif name == "非线性分析":
            return f"{len(params.measures)} 指标"
        return name

    def _get_result_shape(self, name: str, result: FeatureExtractionResult) -> tuple:
        if name == "频段功率" and result.band_power:
            first = next(iter(result.band_power.values()))
            return first.shape
        elif name == "时频分析" and result.time_frequency is not None:
            return result.time_frequency.shape
        elif name == "连通性分析" and result.connectivity is not None:
            return result.connectivity.shape
        elif name == "非线性分析" and result.nonlinear:
            first = next(iter(result.nonlinear.values()))
            return first.shape
        return ()

    def _params_to_dict(self, params: Any) -> dict:
        if hasattr(params, "__dataclass_fields__"):
            return {k: getattr(params, k) for k in params.__dataclass_fields__}
        return {}


# 需要导入 create_band_power_params
from eeg_workbench.models.features import create_band_power_params