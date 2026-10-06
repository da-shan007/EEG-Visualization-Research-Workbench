"""T 检验面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, cast

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QCheckBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import TTestParams, MultipleComparisonCorrection, TTestType, TestAlternative
from eeg_workbench.utils.ui import balance_form


class TTestWidget(QWidget):
    """T 检验面板"""

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

        # ---- 检验类型 ----
        type_group = QGroupBox("检验类型")
        type_layout = QFormLayout(type_group)

        self._cmb_test_type = QComboBox()
        self._cmb_test_type.addItems(["independent", "paired", "one_sample"])
        self._cmb_test_type.setCurrentText("independent")
        self._cmb_test_type.currentTextChanged.connect(self._on_type_changed)
        type_layout.addRow("类型:", self._cmb_test_type)
        balance_form(type_layout)

        layout.addWidget(type_group)

        # ---- 独立/配对样本设置 ----
        self._two_sample_group = QGroupBox("两样本设置")
        two_layout = QFormLayout(self._two_sample_group)

        self._cmb_alternative = QComboBox()
        self._cmb_alternative.addItems(["two-sided", "less", "greater"])
        self._cmb_alternative.setCurrentText("two-sided")
        two_layout.addRow("备择假设:", self._cmb_alternative)

        self._chk_equal_var = QCheckBox("假设方差相等 (Student's t)")
        self._chk_equal_var.setChecked(False)
        self._chk_equal_var.setToolTip("不勾选使用 Welch's t-test")
        two_layout.addRow("", self._chk_equal_var)

        self._spin_confidence = QDoubleSpinBox()
        self._spin_confidence.setRange(0.8, 0.999)
        self._spin_confidence.setDecimals(3)
        self._spin_confidence.setSingleStep(0.01)
        self._spin_confidence.setValue(0.95)
        two_layout.addRow("置信水平:", self._spin_confidence)
        balance_form(two_layout)

        layout.addWidget(self._two_sample_group)

        # ---- 单样本设置 ----
        self._one_sample_group = QGroupBox("单样本设置")
        self._one_sample_group.setVisible(False)
        one_layout = QFormLayout(self._one_sample_group)

        self._spin_popmean = QDoubleSpinBox()
        self._spin_popmean.setRange(-1e6, 1e6)
        self._spin_popmean.setDecimals(4)
        self._spin_popmean.setValue(0.0)
        one_layout.addRow("总体均值:", self._spin_popmean)
        balance_form(one_layout)

        layout.addWidget(self._one_sample_group)

        # ---- 多重比较校正 ----
        corr_group = QGroupBox("多重比较校正")
        corr_layout = QFormLayout(corr_group)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems([m.value for m in MultipleComparisonCorrection])
        self._cmb_correction.setCurrentText("fdr_bh")
        corr_layout.addRow("校正方法:", self._cmb_correction)
        balance_form(corr_layout)

        layout.addWidget(corr_group)

        # ---- 效应量 ----
        effect_group = QGroupBox("效应量")
        effect_layout = QFormLayout(effect_group)

        self._chk_effect_size = QCheckBox("计算效应量")
        self._chk_effect_size.setChecked(True)
        effect_layout.addRow("", self._chk_effect_size)
        balance_form(effect_layout)

        layout.addWidget(effect_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("运行 T 检验")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_ttest)
        exec_layout.addWidget(self._btn_run)

        self._btn_effect_size = QPushButton("仅计算效应量")
        self._btn_effect_size.clicked.connect(self._run_effect_size)
        exec_layout.addWidget(self._btn_effect_size)

        layout.addLayout(exec_layout)

        # ---- 结果表格 ----
        result_group = QGroupBox("检验结果")
        result_layout = QVBoxLayout(result_group)

        self._result_table = QTableWidget(0, 8)
        self._result_table.setHorizontalHeaderLabels([
            "组1", "组2", "t值", "自由度", "p值", "校正p", "效应量", "显著性"
        ])
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self._result_table)

        layout.addWidget(result_group)

        layout.addStretch()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_type_changed(self, test_type: str) -> None:
        is_two_sample = test_type in ("independent", "paired")
        self._two_sample_group.setVisible(is_two_sample)
        self._one_sample_group.setVisible(not is_two_sample)
        self._on_param_changed()

    def _sync_from_vm(self) -> None:
        params = self._vm.ttest_params
        self._block_signals(True)
        try:
            self._cmb_test_type.setCurrentText(params.test_type)
            self._cmb_alternative.setCurrentText(params.alternative)
            self._chk_equal_var.setChecked(params.equal_var)
            self._spin_confidence.setValue(params.confidence_level)
            self._cmb_correction.setCurrentText(params.correction.value)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [
            self._cmb_test_type, self._cmb_alternative, self._chk_equal_var,
            self._spin_confidence, self._cmb_correction, self._spin_popmean
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self) -> None:
        params = TTestParams(
            test_type=cast(TTestType, self._cmb_test_type.currentText()),
            alternative=cast(TestAlternative, self._cmb_alternative.currentText()),
            equal_var=self._chk_equal_var.isChecked(),
            confidence_level=self._spin_confidence.value(),
            correction=MultipleComparisonCorrection(self._cmb_correction.currentText()),
        )
        self._vm.set_ttest_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_ttest(self) -> None:
        # 这里需要数据输入对话框
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QComboBox
        dlg = QDialog(self)
        dlg.setWindowTitle("T 检验数据输入")
        layout = QFormLayout(dlg)

        # 简化：这里只是示例，实际需要选择变量/通道/条件
        layout.addRow(QLabel("请在特征提取/ERP模块中准备好分组数据"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        balance_form(layout)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.status_message.emit("请先准备分组数据，然后调用 run_ttest 方法")

    @Slot()
    def _run_effect_size(self) -> None:
        self.status_message.emit("效应量计算功能待集成")