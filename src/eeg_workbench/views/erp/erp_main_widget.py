"""ERP/ERD/ERS 主面板：整合条件设置、峰值检测、ERD/ERS 分析"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QMessageBox, QSplitter, QListWidget,
    QListWidgetItem
)

from eeg_workbench.utils.ui import wrap_scroll
from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.views.erp.erp_condition_widget import ERPConditionWidget
from eeg_workbench.views.erp.erp_peak_widget import ERPPeakWidget
from eeg_workbench.views.erp.erds_widget import ERDSWidget
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.erp import ERPAnalysisResult, ERDSAnalysisResult


class ERPMainWidget(QWidget):
    """ERP/ERD/ERS 模块主面板"""

    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: ERPViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._dataset: Optional[EEGDataset] = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
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

        self._btn_run_erp = QPushButton("运行 ERP 分析")
        self._btn_run_erp.clicked.connect(self._run_erp_analysis)
        info_layout.addWidget(self._btn_run_erp)

        self._btn_run_erds = QPushButton("运行 ERD/ERS")
        self._btn_run_erds.clicked.connect(self._run_erds_analysis)
        info_layout.addWidget(self._btn_run_erds)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        self._cond_widget = ERPConditionWidget(self._vm)
        self._peak_widget = ERPPeakWidget(self._vm)
        self._erds_widget = ERDSWidget(self._vm)

        self._tabs.addTab(wrap_scroll(self._cond_widget), "条件设置")
        self._tabs.addTab(wrap_scroll(self._peak_widget), "峰值检测")
        self._tabs.addTab(wrap_scroll(self._erds_widget), "ERD/ERS")

        layout.addWidget(self._tabs, 1)

        # ---- 底部分析历史 ----
        history_group = QGroupBox("分析历史")
        history_layout = QVBoxLayout(history_group)

        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(100)
        history_layout.addWidget(self._history_list)

        history_btn = QHBoxLayout()
        self._btn_export_erp = QPushButton("导出 ERP 结果")
        self._btn_export_erp.clicked.connect(self._export_erp)
        self._btn_export_erds = QPushButton("导出 ERD/ERS")
        self._btn_export_erds.clicked.connect(self._export_erds)
        history_btn.addWidget(self._btn_export_erp)
        history_btn.addWidget(self._btn_export_erds)
        history_btn.addStretch()
        history_layout.addLayout(history_btn)

        layout.addWidget(history_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.erp_result.connect(self._on_erp_result)
        self._vm.erds_result.connect(self._on_erds_result)
        self._vm.status_message.connect(self.status_message.emit)

        # 子面板信号
        self._cond_widget.status_message.connect(self.status_message.emit)
        self._peak_widget.status_message.connect(self.status_message.emit)
        self._erds_widget.status_message.connect(self.status_message.emit)

    @Slot(object)
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]):
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
    def _on_erp_result(self, result: ERPAnalysisResult):
        self._add_history(f"ERP分析: {list(result.result.evokeds.keys())} ({len(result.result.peaks)} 条件有峰值)")
        self.status_message.emit(f"ERP 分析完成，耗时 {result.processing_time_ms:.1f}ms")

    @Slot(object)
    def _on_erds_result(self, result: ERDSAnalysisResult):
        self._add_history(f"ERD/ERS分析: {list(result.result.tfrs.keys())} x {len(result.result.band_erds.get(list(result.result.tfrs.keys())[0], {}))} 频段")
        self.status_message.emit(f"ERD/ERS 分析完成，耗时 {result.processing_time_ms:.1f}ms")

    def _add_history(self, desc: str):
        item = QListWidgetItem(f"✓ {desc}")
        self._history_list.addItem(item)

    @Slot()
    def _run_erp_analysis(self):
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        if not self._vm.erp_params.conditions:
            QMessageBox.warning(self, "提示", "请先在「条件设置」标签页添加至少一个 ERP 条件")
            self._tabs.setCurrentIndex(0)
            return
        self._btn_run_erp.setEnabled(False)
        self._btn_run_erp.setText("运行中...")
        # 异步执行，结果通过信号回调
        self._vm.run_erp_analysis()
        self._btn_run_erp.setEnabled(True)
        self._btn_run_erp.setText("运行 ERP 分析")

    @Slot()
    def _run_erds_analysis(self):
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        if not self._vm.erds_params.conditions:
            QMessageBox.warning(self, "提示", "请先在「ERD/ERS」标签页添加至少一个条件")
            self._tabs.setCurrentIndex(2)
            return
        self._btn_run_erds.setEnabled(False)
        self._btn_run_erds.setText("运行中...")
        self._vm.run_erds_analysis()
        self._btn_run_erds.setEnabled(True)
        self._btn_run_erds.setText("运行 ERD/ERS")

    @Slot()
    def _export_erp(self):
        if not self._vm._erp_result:
            QMessageBox.information(self, "提示", "没有 ERP 结果可导出")
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 ERP 结果", "", "NPZ 文件 (*.npz)")
        if path:
            self._vm.export_erp_results(path)

    @Slot()
    def _export_erds(self):
        if not self._vm._erds_result:
            QMessageBox.information(self, "提示", "没有 ERD/ERS 结果可导出")
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 ERD/ERS 结果", "", "NPZ 文件 (*.npz)")
        if path:
            self._vm.export_erds_results(path)