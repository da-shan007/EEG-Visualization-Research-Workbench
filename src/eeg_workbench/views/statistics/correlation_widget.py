"""相关性分析面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, cast

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QListWidget, QListWidgetItem, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import CorrelationParams, MultipleComparisonCorrection, CorrelationMethod, TestAlternative
from eeg_workbench.utils.ui import balance_form


class CorrelationWidget(QWidget):
    """相关性分析面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: StatisticsViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 方法选择 ----
        method_group = QGroupBox("相关性方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems(["pearson", "spearman", "kendall", "partial"])
        self._cmb_method.setCurrentText("pearson")
        self._cmb_method.currentTextChanged.connect(self._on_method_changed)
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- 基本参数 ----
        param_group = QGroupBox("参数设置")
        param_layout = QFormLayout(param_group)

        self._cmb_alternative = QComboBox()
        self._cmb_alternative.addItems(["two-sided", "less", "greater"])
        self._cmb_alternative.setCurrentText("two-sided")
        param_layout.addRow("备择假设:", self._cmb_alternative)

        self._spin_confidence = QDoubleSpinBox()
        self._spin_confidence.setRange(0.8, 0.999)
        self._spin_confidence.setDecimals(3)
        self._spin_confidence.setSingleStep(0.01)
        self._spin_confidence.setValue(0.95)
        param_layout.addRow("置信水平:", self._spin_confidence)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems([m.value for m in MultipleComparisonCorrection])
        self._cmb_correction.setCurrentText("fdr_bh")
        param_layout.addRow("多重校正:", self._cmb_correction)
        balance_form(param_layout)

        layout.addWidget(param_group)

        # ---- 偏相关设置 ----
        self._partial_group = QGroupBox("偏相关设置")
        self._partial_group.setVisible(False)
        partial_layout = QFormLayout(self._partial_group)

        self._lst_control = QListWidget()
        self._lst_control.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        control_vars_layout = QVBoxLayout()
        control_vars_layout.addWidget(QLabel("控制变量 (Ctrl+点击多选):"))
        control_vars_layout.addWidget(self._lst_control)
        partial_layout.addRow("控制变量:", control_vars_layout)

        self._lst_target = QListWidget()
        self._lst_target.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        target_vars_layout = QVBoxLayout()
        target_vars_layout.addWidget(QLabel("目标变量 (可选，不选则所有非控制变量):"))
        target_vars_layout.addWidget(self._lst_target)
        partial_layout.addRow("目标变量:", target_vars_layout)
        balance_form(partial_layout)

        layout.addWidget(self._partial_group)

        # ---- 变量列表 ----
        var_group = QGroupBox("变量列表")
        var_layout = QVBoxLayout(var_group)

        self._lst_variables = QListWidget()
        self._lst_variables.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        var_layout.addWidget(self._lst_variables)

        layout.addWidget(var_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("计算相关性")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_correlation)
        exec_layout.addWidget(self._btn_run)

        self._btn_partial = QPushButton("计算偏相关")
        self._btn_partial.clicked.connect(self._run_partial)
        exec_layout.addWidget(self._btn_partial)

        self._btn_eeg_behavior = QPushButton("EEG-行为相关性")
        self._btn_eeg_behavior.clicked.connect(self._run_eeg_behavior)
        exec_layout.addWidget(self._btn_eeg_behavior)

        layout.addLayout(exec_layout)

        # ---- 结果表格 ----
        result_group = QGroupBox("相关性矩阵")
        result_layout = QVBoxLayout(result_group)

        self._corr_table = QTableWidget()
        self._corr_table.setAlternatingRowColors(True)
        self._corr_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self._corr_table)

        layout.addWidget(result_group)

        layout.addStretch()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    @Slot(str)
    def _on_method_changed(self, method: str) -> None:
        is_partial = method == "partial"
        self._partial_group.setVisible(is_partial)
        self._on_param_changed()

    def _sync_from_vm(self) -> None:
        params = self._vm.corr_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method)
            self._cmb_alternative.setCurrentText(params.alternative)
            self._spin_confidence.setValue(params.confidence_level)
            self._cmb_correction.setCurrentText(params.correction.value)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [
            self._cmb_method, self._cmb_alternative, self._spin_confidence,
            self._cmb_correction
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self) -> None:
        params = CorrelationParams(
            method=cast(CorrelationMethod, self._cmb_method.currentText()),
            alternative=cast(TestAlternative, self._cmb_alternative.currentText()),
            confidence_level=self._spin_confidence.value(),
            correction=MultipleComparisonCorrection(self._cmb_correction.currentText()),
            control_variables=[],
        )
        self._vm.set_corr_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_correlation(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        # 这里需要选择变量并提取数据
        QMessageBox.information(self, "提示", "请先选择变量并提取数据，然后调用 run_correlation 方法")

    @Slot()
    def _run_partial(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "偏相关需要选择控制变量和目标变量")

    @Slot()
    def _run_eeg_behavior(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "EEG-行为相关性需要特征矩阵和行为数据")