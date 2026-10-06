"""可视化模块 ViewModel"""
from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal, Slot, QObject

from eeg_workbench.core.base import ViewModelBase, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.visualization import (
    PlotConfig, WaveformPlotConfig, SpectralPlotConfig, TFRPlotConfig,
    ConnectivityPlotConfig, StatisticalPlotConfig, SourcePlotConfig,
    ReportConfig, PlotType, PlotBackend, ExportFormat, TFRParams,
    WAVEFORM_PRESET, SPECTRAL_PRESET, TFR_PRESET,
    CONNECTIVITY_PRESET, STATISTICAL_PRESET, SOURCE_PRESET,
    REPORT_PRESET, create_plot_config
)
from eeg_workbench.services.visualization import (
    PlottingService, ReportGenerator, ExportService
)
from eeg_workbench.services.features import ConnectivityService
from eeg_workbench.services.visualization.plotting import FigureResult
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel


@dataclass
class VisualizationStepUI:
    name: str
    description: str
    completed: bool = False
    processing_time_ms: float = 0.0


class VisualizationViewModel(ViewModelBase):
    """可视化与报告模块 ViewModel"""

    dataset_changed = Signal(object)
    figure_ready = Signal(object)
    export_finished = Signal(object)
    inverse_solution_ready = Signal(object)
    dipole_fit_ready = Signal(object)
    status_message = Signal(str)
    available_channels_changed = Signal(list)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        preproc_vm: PreprocessingViewModel,
        features_vm: FeaturesViewModel,
        erp_vm: ERPViewModel,
        source_vm: SourceViewModel,
        stats_vm: StatisticsViewModel,
        parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._data_vm = data_vm
        self._preproc_vm = preproc_vm
        self._features_vm = features_vm
        self._erp_vm = erp_vm
        self._source_vm = source_vm
        self._stats_vm = stats_vm
        self._dataset: Optional[EEGDataset] = None

        # 参数
        self._waveform_config = WAVEFORM_PRESET
        self._spectral_config = SPECTRAL_PRESET
        self._tfr_config = TFR_PRESET
        self._connectivity_config = CONNECTIVITY_PRESET
        self._stat_config = STATISTICAL_PRESET
        self._source_config = SOURCE_PRESET
        self._report_config = REPORT_PRESET

        # UI 参数镜像（各面板直接读写）
        self._tf_params = TFRParams()
        self._conn_params = self._connectivity_config
        self._stat_params = self._stat_config
        self._report_params = self._report_config

        # 源定位/偶极子结果缓存（由 source_vm 转发）
        self._inverse_result = None
        self._dipole_result = None
        self._viz = None

        # 服务
        self._plotting_service = PlottingService()
        self._report_generator = ReportGenerator()
        self._export_service = ExportService()

        # 结果缓存
        self._current_figure = None
        self._processing_steps: list[VisualizationStepUI] = []

        self._data_vm.dataset_changed.connect(self._on_dataset_changed)
        self._preproc_vm.dataset_changed.connect(self._on_preproc_dataset_changed)

        # 同步源定位模块的结果
        try:
            self._source_vm.inverse_solution_ready.connect(self._on_inverse_ready)
            self._source_vm.dipole_fit_ready.connect(self._on_dipole_ready)
        except AttributeError:
            pass

    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def waveform_config(self) -> WaveformPlotConfig:
        return self._waveform_config

    @property
    def spectral_config(self) -> SpectralPlotConfig:
        return self._spectral_config

    @property
    def tfr_config(self) -> TFRPlotConfig:
        return self._tfr_config

    @property
    def connectivity_config(self) -> ConnectivityPlotConfig:
        return self._connectivity_config

    @property
    def stat_config(self) -> StatisticalPlotConfig:
        return self._stat_config

    @property
    def source_config(self) -> SourcePlotConfig:
        return self._source_config

    @property
    def report_config(self) -> ReportConfig:
        return self._report_config

    @property
    def eeg_channels(self) -> list[str]:
        return self._dataset.eeg_channels if self._dataset else []

    # ---- UI 参数访问 ----
    @property
    def tf_params(self) -> TFRParams:
        return self._tf_params

    @property
    def conn_params(self) -> ConnectivityPlotConfig:
        return self._conn_params

    @property
    def stat_params(self) -> StatisticalPlotConfig:
        return self._stat_params

    @property
    def report_params(self) -> ReportConfig:
        return self._report_params

    @property
    def inverse_result(self) -> Any:
        return self._inverse_result

    @property
    def dipole_result(self) -> Any:
        return self._dipole_result

    def set_tf_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._tf_params, k):
                setattr(self._tf_params, k, v)
        # 同步到绘图配置
        self.set_tfr_config(
            fmin=self._tf_params.fmin, fmax=self._tf_params.fmax,
            baseline=self._tf_params.baseline,
            baseline_mode=self._tf_params.baseline_mode,
            cmap=self._tf_params.cmap,
            vmin=self._tf_params.vmin, vmax=self._tf_params.vmax,
        )

    def set_conn_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._conn_params, k):
                setattr(self._conn_params, k, v)

    def set_stat_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._stat_params, k):
                setattr(self._stat_params, k, v)

    def set_report_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._report_params, k):
                setattr(self._report_params, k, v)

    # ---- 参数设置 ----
    def set_waveform_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._waveform_config, k):
                setattr(self._waveform_config, k, v)

    def set_spectral_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._spectral_config, k):
                setattr(self._spectral_config, k, v)

    def set_tfr_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._tfr_config, k):
                setattr(self._tfr_config, k, v)

    def set_connectivity_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._connectivity_config, k):
                setattr(self._connectivity_config, k, v)

    def set_stat_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._stat_config, k):
                setattr(self._stat_config, k, v)

    def set_source_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._source_config, k):
                setattr(self._source_config, k, v)

    def set_report_config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._report_config, k):
                setattr(self._report_config, k, v)

    def apply_report_preset(self, preset: str) -> None:
        self._report_config = REPORT_PRESET

    # ---- 绘图执行 ----
    @async_slot
    def plot_waveform(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        self.show_status("正在绘制波形...")
        result = self._plotting_service.plot_waveform(self._dataset, self._waveform_config)
        if result:
            self._current_figure = result.figure
            self._add_step("波形图", f"{result.data_info.get('n_channels', 0)} 通道")
            self.figure_ready.emit(result)
            self.status_message.emit("波形图绘制完成")
        return result

    @async_slot
    def plot_spectral(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        self.show_status("正在计算频谱...")
        result = self._plotting_service.plot_spectral(self._dataset, self._spectral_config)
        if result:
            self._current_figure = result.figure
            self._add_step("频谱图", f"{self._spectral_config.method}")
            self.figure_ready.emit(result)
            self.status_message.emit("频谱图绘制完成")
        return result

    @async_slot
    def plot_tfr(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        self.show_status(f"正在计算时频图 ({self._tfr_config.method})...")
        result = self._plotting_service.plot_tfr(self._dataset, self._tfr_config)
        if result:
            self._current_figure = result.figure
            self._add_step("时频图", f"{self._tfr_config.method}")
            self.figure_ready.emit(result)
            self.status_message.emit("时频图绘制完成")
        return result

    @async_slot
    def plot_connectivity(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        # 图服务只负责画，不负责算：PlottingService.plot_connectivity 要求
        # 显式传入 (n_ch, n_ch) 矩阵，否则抛 ValueError。
        # 之前这里只传了 dataset + config，按钮点下去必崩。
        conn_result = ConnectivityService.coherence(self._dataset)
        feature_result = conn_result.feature_result
        matrix = feature_result.connectivity if feature_result else None
        if matrix is None:
            self.error_occurred.emit("连通性计算未返回矩阵")
            return None
        # (n_freqs, n_ch, n_ch) → 取频率均值成 2D，绘图服务只吃 2D
        if matrix.ndim == 3:
            matrix = matrix.mean(axis=0)

        method_label = (
            conn_result.params_used.method.value if conn_result.params_used else "coherence"
        )
        self.show_status(f"正在绘制连通性 ({method_label})...")
        result = self._plotting_service.plot_connectivity(
            self._dataset, self._connectivity_config, matrix
        )
        if result:
            self._current_figure = result.figure
            self._add_step("连通性", f"{method_label}")
            self.figure_ready.emit(result)
            self.status_message.emit("连通性图绘制完成")
        return result

    @async_slot
    def plot_statistical(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        self.show_status("正在绘制统计图...")
        result = self._plotting_service.plot_statistical(self._dataset, self._stat_config)
        if result:
            self._current_figure = result.figure
            self._add_step("统计图", f"{self._stat_config.plot_type}")
            self.figure_ready.emit(result)
            self.status_message.emit("统计图绘制完成")
        return result

    @async_slot
    def plot_source(self) -> Optional[FigureResult]:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None
        if not hasattr(self, '_inverse_result') or not self._inverse_result:
            self.error_occurred.emit("请先计算逆向解")
            return None
        self.show_status("正在绘制源定位...")
        result = self._plotting_service.plot_source(self._dataset, self._source_config, self._inverse_result.stc)
        if result:
            self._current_figure = result.figure
            self._add_step("源定位", f"{self._source_config.surface}")
            self.figure_ready.emit(result)
            self.status_message.emit("源定位图绘制完成")
        return result

    @async_slot
    def plot_source_estimate(self) -> Optional[FigureResult]:
        """绘制源估计（由源定位面板触发）"""
        return self.plot_source()

    @async_slot
    def plot_dipoles_3d(self) -> bool:
        """绘制 3D 偶极子"""
        if not self._dipole_result:
            self.error_occurred.emit("请先完成偶极子拟合")
            return False
        self.show_status("正在绘制 3D 偶极子...")
        try:
            viz = getattr(self._source_vm, "_viz", None)
            self._viz = viz
            self._add_step("3D 偶极子", "")
            self.status_message.emit("3D 偶极子绘制完成")
            return True
        except Exception as e:
            self.error_occurred.emit(f"偶极子绘制失败: {e}")
            return False

    @Slot(object)
    def _on_inverse_ready(self, result: Any) -> None:
        self._inverse_result = result
        self.inverse_solution_ready.emit(result)

    @Slot(object)
    def _on_dipole_ready(self, result: Any) -> None:
        self._dipole_result = result
        self.dipole_fit_ready.emit(result)

    # ---- 导出 ----
    @staticmethod
    def _resolve_format(fmt: ExportFormat | str, path: str = "", default: ExportFormat = ExportFormat.PNG) -> ExportFormat:
        """把字符串/枚举/文件路径统一解析为 ExportFormat"""
        if isinstance(fmt, ExportFormat):
            return fmt
        if isinstance(fmt, str) and fmt:
            try:
                return ExportFormat(fmt.lower().lstrip("."))
            except ValueError:
                pass
        suffix = Path(path).suffix.lower().lstrip(".") if path else ""
        if suffix:
            try:
                return ExportFormat(suffix)
            except ValueError:
                pass
        return default

    @async_slot
    def export_figure(self, format: str = "png", path: str = "") -> bool:
        if not self._current_figure:
            self.error_occurred.emit("没有可导出的图形")
            return False
        if not path:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                None, "导出图形", "",
                "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;EPS (*.eps);;HTML (*.html)"
            )
            if not path:
                return False
        fmt = self._resolve_format(format, path, ExportFormat.PNG)
        try:
            self._export_service.export_figure(self._current_figure, path, fmt)
            self.status_message.emit(f"图形已导出: {path}")
            self.export_finished.emit(path)
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出失败: {e}")
            return False

    @async_slot
    def export_data(self, data: Any, path: str, format: str = "csv") -> bool:
        fmt = self._resolve_format(format, path, ExportFormat.CSV)
        try:
            self._export_service.export_data(data, path, fmt)
            self.status_message.emit(f"数据已导出: {path}")
            self.export_finished.emit(path)
            return True
        except Exception as e:
            self.error_occurred.emit(f"数据导出失败: {e}")
            return False

    @async_slot
    def generate_report(self, format: str = "pdf", path: str = "", config: ReportConfig | None = None) -> bool:
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return False
        if not path:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                None, "保存报告", "", "PDF (*.pdf);;HTML (*.html)"
            )
            if not path:
                return False
        fmt = self._resolve_format(format, path, ExportFormat.PDF)
        try:
            self._export_service.export_report(self._dataset, path, fmt, config)
            self.status_message.emit(f"报告已生成: {path}")
            self.export_finished.emit(path)
            return True
        except Exception as e:
            self.error_occurred.emit(f"报告生成失败: {e}")
            return False

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        self._dataset = dataset
        if dataset:
            self._notify_available_channels()
        # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm）
        self.dataset_changed.emit(dataset)

    def _on_preproc_dataset_changed(self, dataset: EEGDataset | None) -> None:
        # 预处理后的数据集优先用于可视化（与 features/source/statistics 一致）
        if dataset:
            self._dataset = dataset
            self._notify_available_channels()
            # 转发给本模块 View（View 只订阅此处的信号，不订阅 data_vm/preproc_vm）
            self.dataset_changed.emit(dataset)

    def _notify_available_channels(self) -> None:
        self.available_channels_changed.emit(self.eeg_channels)

    def _add_step(self, name: str, desc: str, time_ms: float = 0) -> None:
        self._processing_steps.append(
            VisualizationStepUI(name=name, description=desc, completed=True, processing_time_ms=time_ms)
        )