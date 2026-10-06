"""特征提取主面板：整合频段功率、时频、连通性、非线性"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QMessageBox, QSplitter, QListWidget,
    QListWidgetItem
)

from eeg_workbench.utils.ui import wrap_scroll
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel, FeatureResultUI
from .band_power_widget import BandPowerWidget
from .connectivity_widget import ConnectivityWidget
from .nonlinear_widget import NonlinearWidget
from .time_frequency_widget import TimeFrequencyWidget
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.features import FeatureExtractionResult
from eeg_workbench.utils.ui import balance_form, relay_status


class FeaturesMainWidget(QWidget):
    """特征提取模块主面板"""

    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: FeaturesViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._dataset: Optional[EEGDataset] = None
        self._results_cache: dict[str, FeatureExtractionResult] = {}
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部信息栏 ----
        info_bar = QGroupBox("数据集状态")
        info_layout = QHBoxLayout(info_bar)

        self._lbl_dataset_name = QLabel("未加载数据")
        self._lbl_dataset_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        info_layout.addWidget(self._lbl_dataset_name)

        self._lbl_info = QLabel("通道: -- | 采样率: -- Hz | 时长: -- s")
        self._lbl_info.setStyleSheet("color: #666;")
        info_layout.addWidget(self._lbl_info, 1)

        self._btn_extract_epochs = QPushButton("提取 Epochs")
        self._btn_extract_epochs.setToolTip("根据事件定义提取 Epochs 用于特征分析")
        self._btn_extract_epochs.clicked.connect(self._extract_epochs_dialog)
        info_layout.addWidget(self._btn_extract_epochs)

        self._btn_run_all = QPushButton("一键全部分析")
        self._btn_run_all.setToolTip("运行频段功率、时频、连通性、非线性全部分析")
        self._btn_run_all.clicked.connect(self._run_all_features)
        info_layout.addWidget(self._btn_run_all)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        self._band_power_widget = BandPowerWidget(self._vm)
        self._tf_widget = TimeFrequencyWidget(self._vm)
        self._conn_widget = ConnectivityWidget(self._vm)
        self._nonlinear_widget = NonlinearWidget(self._vm)

        self._tabs.addTab(wrap_scroll(self._band_power_widget), "频段功率")
        self._tabs.addTab(wrap_scroll(self._tf_widget), "时频分析")
        self._tabs.addTab(wrap_scroll(self._conn_widget), "连通性分析")
        self._tabs.addTab(wrap_scroll(self._nonlinear_widget), "非线性分析")

        layout.addWidget(self._tabs, 1)

        # ---- 底部结果历史 ----
        history_group = QGroupBox("分析历史")
        history_layout = QVBoxLayout(history_group)

        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(120)
        history_layout.addWidget(self._history_list)

        history_btn_layout = QHBoxLayout()
        self._btn_export = QPushButton("导出结果")
        self._btn_export.clicked.connect(self._export_results)
        self._btn_clear = QPushButton("清空历史")
        self._btn_clear.clicked.connect(self._clear_history)
        history_btn_layout.addWidget(self._btn_export)
        history_btn_layout.addWidget(self._btn_clear)
        history_btn_layout.addStretch()
        history_layout.addLayout(history_btn_layout)

        layout.addWidget(history_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.band_power_result.connect(self._on_band_power_result)
        self._vm.tfr_result.connect(self._on_tfr_result)
        self._vm.connectivity_result.connect(self._on_connectivity_result)
        self._vm.nonlinear_result.connect(self._on_nonlinear_result)
        self._vm.processing_steps_changed.connect(self._update_history)
        self._vm.status_message.connect(self.status_message.emit)

        # 子面板信号
        relay_status(
            [self._band_power_widget, self._tf_widget, self._conn_widget, self._nonlinear_widget],
            self.status_message,
        )

    @Slot(object)
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        self._dataset = dataset
        enabled = dataset is not None
        self.setEnabled(enabled)

        if dataset:
            self._lbl_dataset_name.setText(dataset.name)
            self._lbl_info.setText(
                f"通道: {dataset.n_channels} | 采样率: {dataset.sfreq:.1f} Hz | 时长: {dataset.duration:.2f} s"
            )
        else:
            self._lbl_dataset_name.setText("未加载数据")
            self._lbl_info.setText("通道: -- | 采样率: -- Hz | 时长: -- s")

        self.dataset_changed.emit(dataset)

    @Slot(object)
    def _on_band_power_result(self, result: FeatureExtractionResult) -> None:
        self._results_cache["band_power"] = result
        self._update_history_from_vm()

    @Slot(object)
    def _on_tfr_result(self, result: FeatureExtractionResult) -> None:
        self._results_cache["time_frequency"] = result
        self._update_history_from_vm()

    @Slot(object)
    def _on_connectivity_result(self, result: FeatureExtractionResult) -> None:
        self._results_cache["connectivity"] = result
        self._update_history_from_vm()

    @Slot(object)
    def _on_nonlinear_result(self, result: FeatureExtractionResult) -> None:
        self._results_cache["nonlinear"] = result
        self._update_history_from_vm()

    def _update_history_from_vm(self) -> None:
        # 从 ViewModel 的 processing_steps 更新
        pass

    @Slot(list)
    def _update_history(self, steps: list[FeatureResultUI]) -> None:
        self._history_list.clear()
        for step in steps:
            status = "✓"
            item = QListWidgetItem(f"{status} {step.feature_type}: {step.description} ({step.shape})")
            item.setToolTip(f"耗时: {step.processing_time_ms:.1f}ms\n参数: {step.params}")
            self._history_list.addItem(item)

    @Slot()
    def _extract_epochs_dialog(self) -> None:
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return

        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QLineEdit, QDoubleSpinBox, QCheckBox

        dlg = QDialog(self)
        dlg.setWindowTitle("提取 Epochs")
        dlg.setModal(True)
        layout = QFormLayout(dlg)

        # 事件描述
        events_edit = QLineEdit()
        events_edit.setPlaceholderText("事件描述，逗号分隔 (如: Stimulus/Target,Stimulus/NonTarget)")
        layout.addRow("触发事件:", events_edit)

        # 时间窗
        tmin_spin = QDoubleSpinBox()
        tmin_spin.setRange(-10, 10)
        tmin_spin.setDecimals(3)
        tmin_spin.setValue(-0.2)
        tmin_spin.setSuffix(" s")
        layout.addRow("tmin:", tmin_spin)

        tmax_spin = QDoubleSpinBox()
        tmax_spin.setRange(-10, 10)
        tmax_spin.setDecimals(3)
        tmax_spin.setValue(0.8)
        tmax_spin.setSuffix(" s")
        layout.addRow("tmax:", tmax_spin)

        # 基线
        chk_baseline = QCheckBox("应用基线校正")
        chk_baseline.setChecked(True)
        layout.addRow("", chk_baseline)

        base_tmin = QDoubleSpinBox()
        base_tmin.setRange(-10, 0)
        base_tmin.setDecimals(3)
        base_tmin.setValue(-0.2)
        base_tmin.setSuffix(" s")
        layout.addRow("基线 tmin:", base_tmin)

        base_tmax = QDoubleSpinBox()
        base_tmax.setRange(-10, 0)
        base_tmax.setDecimals(3)
        base_tmax.setValue(0.0)
        base_tmax.setSuffix(" s")
        layout.addRow("基线 tmax:", base_tmax)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        balance_form(layout)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            event_descs = [e.strip() for e in events_edit.text().split(",") if e.strip()]
            tmin = tmin_spin.value()
            tmax = tmax_spin.value()
            baseline = (base_tmin.value(), base_tmax.value()) if chk_baseline.isChecked() else None

            epochs_data = self._vm.extract_epochs_for_analysis(event_descs, tmin, tmax, baseline)
            if epochs_data is not None:
                self.status_message.emit(f"已提取 {epochs_data.shape[0]} 个 Epochs: {epochs_data.shape}")
                # 可以将 epochs_data 传给后续分析

    @Slot()
    def _run_all_features(self) -> None:
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return

        reply = QMessageBox.question(
            self, "确认全部分析",
            "将依次运行：\n"
            "1. 频段功率分析\n"
            "2. 时频分析\n"
            "3. 连通性分析\n"
            "4. 非线性分析\n\n"
            "此操作可能需要较长时间，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._btn_run_all.setEnabled(False)
            self._btn_run_all.setText("运行中...")
            # 异步执行
            self._vm.run_all_features()
            self._btn_run_all.setEnabled(True)
            self._btn_run_all.setText("一键全部分析")

    @Slot()
    def _export_results(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出特征结果", "", "NPZ 文件 (*.npz);;CSV 文件 (*.csv)")
        if path:
            if self._vm.export_results(path):
                QMessageBox.information(self, "完成", f"结果已导出到: {path}")

    @Slot()
    def _clear_history(self) -> None:
        self._history_list.clear()
        self._results_cache.clear()