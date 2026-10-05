"""ERP/ERD/ERS 模块 ViewModel"""
from __future__ import annotations
from typing import Optional, Any
from dataclasses import dataclass

import numpy as np

from PySide6.QtCore import Signal, Slot, QObject

from eeg_workbench.core.base import ViewModelBase, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.erp import (
    ERPAnalysisParams, ERDSParams, EpochParams,
    ERPComponent, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY,
    create_erp_params, create_erds_params
)
from eeg_workbench.services.erp import (
    ERPService, ERDSService, PeakDetector, TopomapService,
    ERPAnalysisResult, ERDSAnalysisResult, PeakResult
)
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel


@dataclass
class ERPResultUI:
    """UI 显示用的 ERP 结果"""
    condition: str
    n_epochs: int
    peaks: dict  # {component: {latency, amplitude, channel}}
    has_contrast: bool = False


class ERPViewModel(ViewModelBase):
    """ERP/ERD/ERS 分析 ViewModel"""

    # 信号
    dataset_changed = Signal(object)              # EEGDataset
    erp_result = Signal(object)                   # ERPAnalysisResult
    erds_result = Signal(object)                  # ERDSAnalysisResult
    peaks_detected = Signal(dict)                 # {condition: {component: PeakResult}}
    topomap_ready = Signal(object)                # TopomapData
    available_channels_changed = Signal(list)     # list[str]
    processing_steps_changed = Signal(list)       # list[str]
    status_message = Signal(str)

    def __init__(
        self,
        data_vm: DataManagementViewModel,
        preproc_vm: PreprocessingViewModel,
        features_vm: FeaturesViewModel,
        parent: QObject | None = None
    ):
        super().__init__(parent)
        self._data_vm = data_vm
        self._preproc_vm = preproc_vm
        self._features_vm = features_vm
        self._dataset: Optional[EEGDataset] = None

        # 参数
        self._erp_params = ERPAnalysisParams()
        self._erds_params = ERDSParams()

        # 峰值检测器
        self._peak_detector = PeakDetector()

        # 结果缓存
        self._erp_result: Optional[ERPAnalysisResult] = None
        self._erds_result: Optional[ERDSAnalysisResult] = None

        self._processing_steps: list[str] = []

        # 订阅数据变化
        self._preproc_vm.dataset_changed.connect(self._on_dataset_changed)

    # ---- 只读属性 ----
    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def erp_params(self) -> ERPAnalysisParams:
        return self._erp_params

    @property
    def erds_params(self) -> ERDSParams:
        return self._erds_params

    @property
    def eeg_channels(self) -> list[str]:
        if self._dataset:
            return self._dataset.eeg_channels
        return []

    @property
    def events_list(self) -> list[str]:
        """获取当前数据集中的事件描述列表"""
        if self._dataset:
            descs = set()
            for ev in self._dataset.events:
                descs.add(ev.description)
            return sorted(descs)
        return []

    # ---- 参数设置 ----
    def set_erp_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._erp_params, k):
                setattr(self._erp_params, k, v)

    def set_erds_params(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._erds_params, k):
                setattr(self._erds_params, k, v)

    def set_epoch_params(self, condition: str, **kwargs) -> None:
        """设置特定条件的 Epoch 参数"""
        if condition not in self._erp_params.conditions:
            self._erp_params.conditions[condition] = EpochParams()
        ep = self._erp_params.conditions[condition]
        for k, v in kwargs.items():
            if hasattr(ep, k):
                setattr(ep, k, v)

    def set_erds_epoch_params(self, condition: str, **kwargs) -> None:
        if condition not in self._erds_params.conditions:
            self._erds_params.conditions[condition] = EpochParams()
        ep = self._erds_params.conditions[condition]
        for k, v in kwargs.items():
            if hasattr(ep, k):
                setattr(ep, k, v)

    def add_erp_condition(
        self,
        name: str,
        event_descriptions: list[str],
        tmin: float = -0.2,
        tmax: float = 0.8,
        baseline: tuple[float, float] = (-0.2, 0.0)
    ) -> None:
        """添加 ERP 条件"""
        self._erp_params.conditions[name] = EpochParams(
            event_descriptions=event_descriptions,
            tmin=tmin, tmax=tmax, baseline=baseline
        )
        self._notify_conditions_changed()

    def add_erds_condition(
        self,
        name: str,
        event_descriptions: list[str],
        tmin: float = -1.0,
        tmax: float = 2.0,
        baseline: tuple[float, float] = (-1.0, -0.5)
    ) -> None:
        """添加 ERD/ERS 条件"""
        self._erds_params.conditions[name] = EpochParams(
            event_descriptions=event_descriptions,
            tmin=tmin, tmax=tmax, baseline=baseline
        )
        self._notify_conditions_changed()

    def remove_condition(self, name: str, analysis_type: str = "erp") -> None:
        """移除条件"""
        if analysis_type == "erp":
            self._erp_params.conditions.pop(name, None)
        else:
            self._erds_params.conditions.pop(name, None)
        self._notify_conditions_changed()

    def add_contrast(self, cond_a: str, cond_b: str) -> None:
        """添加差分对比"""
        pair = (cond_a, cond_b)
        if pair not in self._erp_params.contrast_pairs:
            self._erp_params.contrast_pairs.append(pair)
            self._notify_conditions_changed()

    def set_peak_detection_params(
        self,
        components: list[ERPComponent] | None = None,
        time_windows: dict[ERPComponent, tuple[float, float]] | None = None,
        polarities: dict[ERPComponent, str] | None = None
    ) -> None:
        """设置峰值检测参数"""
        if components:
            self._erp_params.peak_components = components
        if time_windows:
            self._erp_params.peak_time_windows.update(time_windows)
        if polarities:
            self._erp_params.peak_polarity.update(polarities)
        # 更新检测器
        self._peak_detector = PeakDetector(
            peak_windows=self._erp_params.peak_time_windows,
            polarities=self._erp_params.peak_polarity
        )

    # ---- ERP 分析执行 ----
    @async_slot
    def run_erp_analysis(self) -> ERPAnalysisResult | None:
        """运行 ERP 分析"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        if not self._erp_params.conditions:
            self.error_occurred.emit("请先添加至少一个 ERP 条件")
            return None

        # 验证参数
        for cond_name, ep in self._erp_params.conditions.items():
            errors = ep.validate(self._dataset.sfreq)
            if errors:
                self.error_occurred.emit(f"条件 {cond_name} 参数错误: {'; '.join(errors)}")
                return None

        self.show_status("正在进行 ERP 分析...")
        result = ERPService.analyze(self._dataset, self._erp_params)

        if result:
            self._erp_result = result
            self._add_step(f"ERP分析: {list(result.result.evokeds.keys())}")
            self.erp_result.emit(result)
            self._emit_peaks(result.result.peaks)
            self.show_status(f"ERP 分析完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_erds_analysis(self) -> ERDSAnalysisResult | None:
        """运行 ERD/ERS 分析"""
        if not self._dataset:
            self.error_occurred.emit("请先加载数据集")
            return None

        if not self._erds_params.conditions:
            self.error_occurred.emit("请先添加至少一个 ERD/ERS 条件")
            return None

        for cond_name, ep in self._erds_params.conditions.items():
            errors = ep.validate(self._dataset.sfreq)
            if errors:
                self.error_occurred.emit(f"条件 {cond_name} 参数错误: {'; '.join(errors)}")
                return None

        self.show_status("正在进行 ERD/ERS 分析...")
        result = ERDSService.analyze(self._dataset, self._erds_params)

        if result:
            self._erds_result = result
            self._add_step(f"ERD/ERS分析: {list(result.result.tfrs.keys())}")
            self.erds_result.emit(result)
            self.show_status(f"ERD/ERS 分析完成，耗时 {result.processing_time_ms:.1f}ms")

        return result

    @async_slot
    def run_peak_detection(self, condition: str | None = None) -> dict | None:
        """手动运行峰值检测"""
        if not self._erp_result:
            self.error_occurred.emit("请先运行 ERP 分析")
            return None

        evokeds = self._erp_result.result.evokeds
        if condition:
            evokeds = {condition: evokeds[condition]}

        peaks = self._peak_detector.batch_detect(evokeds, self._erp_params.peak_components)
        self._emit_peaks(peaks)
        return peaks

    @async_slot
    def run_custom_peak_detection(
        self,
        condition: str,
        time_window: tuple[float, float],
        polarity: str = "both"
    ) -> PeakResult | None:
        """自定义峰值检测"""
        if not self._erp_result or condition not in self._erp_result.result.evokeds:
            return None

        evoked = self._erp_result.result.evokeds[condition]
        result = self._peak_detector.detect_custom(evoked, time_window, polarity)
        return result

    # ---- 地形图 ----
    def generate_topomap(
        self,
        condition: str,
        time_point: float
    ) -> Any:
        """生成指定条件、时间点的地形图"""
        if not self._erp_result or condition not in self._erp_result.result.evokeds:
            return None

        evoked = self._erp_result.result.evokeds[condition]
        topomap_data = TopomapService.compute_topomap_data(evoked, time_point)
        self.topomap_ready.emit(topomap_data)
        return topomap_data

    def plot_topomaps(
        self,
        times: list[float] | None = None,
        condition: str | None = None
    ) -> None:
        """绘制地形图"""
        if not self._erp_result:
            return

        if condition and condition in self._erp_result.result.evokeds:
            evoked = self._erp_result.result.evokeds[condition]
        else:
            # 使用第一个条件
            evoked = next(iter(self._erp_result.result.evokeds.values()))

        if times is None:
            # 使用峰值时间
            times = []
            for peaks in self._erp_result.result.peaks.values():
                for peak_info in peaks.values():
                    if "latency" in peak_info:
                        times.append(peak_info["latency"])
            times = list(set(times))

        TopomapService.plot_topomap_times(evoked, times)

    def plot_joint(self, condition: str | None = None) -> None:
        """绘制联合图"""
        if not self._erp_result:
            return

        if condition and condition in self._erp_result.result.evokeds:
            evoked = self._erp_result.result.evokeds[condition]
        else:
            evoked = next(iter(self._erp_result.result.evokeds.values()))

        TopomapService.plot_joint(evoked)

    # ---- ERDS 地形图 ----
    def plot_erds_topomaps(
        self,
        condition: str,
        band: str,
        times: list[float] | None = None
    ) -> None:
        """绘制 ERD/ERS 地形图"""
        if not self._erds_result or condition not in self._erds_result.result.avg_tfrs:
            return

        tfr = self._erds_result.result.avg_tfrs[condition]
        
        if times is None:
            times = np.linspace(tfr.times[0], tfr.times[-1], 6)

        # 选择频段
        if band in self._erds_params.bands:
            fmin, fmax = self._erds_params.bands[band]
            tfr = tfr.copy().crop(fmin=fmin, fmax=fmax)

        tfr.plot_topomap(times=times, ch_type='eeg')

    # ---- 结果导出 ----
    def export_erp_results(self, file_path: str) -> bool:
        """导出 ERP 结果"""
        if not self._erp_result:
            return False
        try:
            import numpy as np
            np.savez(
                file_path,
                conditions=list(self._erp_result.result.evokeds.keys()),
                peaks=self._serialize_peaks(self._erp_result.result.peaks),
            )
            self.show_status(f"ERP 结果已导出: {file_path}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出失败: {e}")
            return False

    def export_erds_results(self, file_path: str) -> bool:
        """导出 ERD/ERS 结果"""
        if not self._erds_result:
            return False
        try:
            import numpy as np
            np.savez(
                file_path,
                conditions=list(self._erds_result.result.tfrs.keys()),
                bands=list(self._erds_params.bands.keys()),
            )
            self.show_status(f"ERD/ERS 结果已导出: {file_path}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出失败: {e}")
            return False

    # ---- 内部方法 ----
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        self._dataset = dataset
        # 转发给本模块 View（View 只订阅此处的信号）
        self.dataset_changed.emit(dataset)
        self._notify_available_channels()

    def _notify_available_channels(self) -> None:
        self.available_channels_changed.emit(self.eeg_channels)

    def _notify_conditions_changed(self) -> None:
        # 通知 UI 条件列表变化
        pass

    def _add_step(self, desc: str) -> None:
        self._processing_steps.append(desc)
        self.processing_steps_changed.emit(self._processing_steps)

    def _emit_peaks(self, peaks: dict) -> None:
        """发射峰值信号，转换为可序列化格式

        ERPService._detect_peaks 返回 {ERPComponent: {"latency": ..., ...} | None}
        （纯 dict，非 PeakResult 对象），需按键访问。
        """
        serializable = {}
        for cond, cond_peaks in peaks.items():
            serializable[cond] = {}
            for comp, peak in cond_peaks.items():
                if peak:
                    serializable[cond][comp.value] = {
                        "latency": peak["latency"],
                        "amplitude": peak["amplitude"],
                        "channel": peak["channel"],
                        "polarity": peak["polarity"],
                    }
        self.peaks_detected.emit(serializable)

    def _serialize_peaks(self, peaks: dict) -> dict:
        result = {}
        for cond, cond_peaks in peaks.items():
            result[cond] = {}
            for comp, peak in cond_peaks.items():
                if peak:
                    result[cond][comp.value] = {
                        "latency": peak["latency"],
                        "amplitude": peak["amplitude"],
                        "channel": peak["channel"],
                        "polarity": peak["polarity"],
                    }
        return result


# 需要导入
from eeg_workbench.models.erp import ERPComponent