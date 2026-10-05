"""效应量计算面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QCheckBox, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QDoubleSpinBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import EffectSize
from eeg_workbench.utils.ui import balance_form


class EffectSizeWidget(QWidget):
    """效应量计算面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: StatisticsViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 效应量类型 ----
        type_group = QGroupBox("效应量类型")
        type_layout = QHBoxLayout(type_group)

        self._effect_buttons = {}
        for es in EffectSize:
            btn = QPushButton(es.value)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, e=es: self._select_effect_size(e))
            self._effect_buttons[es] = btn
            type_layout.addWidget(btn)

        # 默认选中 Cohen's d
        self._effect_buttons[EffectSize.COHEN_D].setChecked(True)
        self._current_effect = EffectSize.COHEN_D

        layout.addWidget(type_group)

        # ---- 参数设置 ----
        param_group = QGroupBox("参数设置")
        param_layout = QFormLayout(param_group)

        self._chk_paired = QCheckBox("配对样本")
        param_layout.addRow("", self._chk_paired)

        self._chk_hedges = QCheckBox("Hedges' g 校正 (小样本修正)")
        self._chk_hedges.setChecked(True)
        param_layout.addRow("", self._chk_hedges)

        self._spin_confidence = QDoubleSpinBox()
        self._spin_confidence.setRange(0.8, 0.999)
        self._spin_confidence.setDecimals(3)
        self._spin_confidence.setSingleStep(0.01)
        self._spin_confidence.setValue(0.95)
        param_layout.addRow("置信水平:", self._spin_confidence)
        balance_form(param_layout)

        layout.addWidget(param_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_compute = QPushButton("计算效应量")
        self._btn_compute.setMinimumHeight(40)
        self._btn_compute.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_compute.clicked.connect(self._compute_effect_size)
        exec_layout.addWidget(self._btn_compute)

        self._btn_all = QPushButton("计算所有效应量")
        self._btn_all.clicked.connect(self._compute_all)
        exec_layout.addWidget(self._btn_all)

        layout.addLayout(exec_layout)

        # ---- 结果表格 ----
        result_group = QGroupBox("效应量结果")
        result_layout = QVBoxLayout(result_group)

        self._result_table = QTableWidget(0, 6)
        self._result_table.setHorizontalHeaderLabels([
            "效应量类型", "数值", "解释", "置信区间下限", "置信区间上限", "备注"
        ])
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self._result_table)

        # ---- 解释说明 ----
        info_group = QGroupBox("效应量解释标准")
        info_layout = QVBoxLayout(info_group)

        self._lbl_interpretation = QLabel("""
<b>Cohen's d / Hedges' g:</b>
- negligible: |d| < 0.2
- small: 0.2 ≤ |d| < 0.5
- medium: 0.5 ≤ |d| < 0.8
- large: |d| ≥ 0.8

<b>η² / η²_p / ω²:</b>
- negligible: < 0.01
- small: 0.01 - 0.06
- medium: 0.06 - 0.14
- large: ≥ 0.14

<b>Cliff's Delta:</b>
- negligible: |δ| < 0.147
- small: 0.147 - 0.33
- medium: 0.33 - 0.474
- large: ≥ 0.474
        """)
        self._lbl_interpretation.setWordWrap(True)
        self._lbl_interpretation.setStyleSheet("font-size: 11px; color: #555;")
        info_layout.addWidget(self._lbl_interpretation)

        layout.addWidget(info_group)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    @Slot()
    def _select_effect_size(self, effect: EffectSize):
        self._current_effect = effect
        for es, btn in self._effect_buttons.items():
            btn.setChecked(es == effect)

    @Slot()
    def _compute_effect_size(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "请准备两组数据，然后调用 compute_effect_size 方法")

    @Slot()
    def _compute_all(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "请准备两组数据，然后调用 compute_effect_size 方法")