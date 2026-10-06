"""多重比较校正面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, Any

import numpy as np

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import MultipleComparisonCorrection
from eeg_workbench.utils.ui import balance_form


class CorrectionWidget(QWidget):
    """多重比较校正面板"""

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

        # ---- 校正方法 ----
        method_group = QGroupBox("校正方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in MultipleComparisonCorrection])
        self._cmb_method.setCurrentText("fdr_bh")
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- 参数设置 ----
        param_group = QGroupBox("参数设置")
        param_layout = QFormLayout(param_group)

        self._spin_alpha = QDoubleSpinBox()
        self._spin_alpha.setRange(0.001, 0.2)
        self._spin_alpha.setDecimals(3)
        self._spin_alpha.setSingleStep(0.01)
        self._spin_alpha.setValue(0.05)
        param_layout.addRow("显著性水平:", self._spin_alpha)

        self._chk_auto_correct = QCheckBox("自动应用全局校正")
        self._chk_auto_correct.setChecked(True)
        self._chk_auto_correct.setToolTip("运行统计检验时自动应用全局校正")
        param_layout.addRow("", self._chk_auto_correct)
        balance_form(param_layout)

        layout.addWidget(param_group)

        # ---- p值输入表格 ----
        input_group = QGroupBox("p值输入 (手动输入或从结果导入)")
        input_layout = QVBoxLayout(input_group)

        self._p_table = QTableWidget(0, 3)
        self._p_table.setHorizontalHeaderLabels(["检验名", "原始p值", "校正后p值"])
        self._p_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        input_layout.addWidget(self._p_table)

        p_btn_layout = QHBoxLayout()
        self._btn_add_p = QPushButton("添加p值")
        self._btn_add_p.clicked.connect(self._add_p_row)
        self._btn_remove_p = QPushButton("删除选中")
        self._btn_remove_p.clicked.connect(self._remove_p_row)
        self._btn_clear_p = QPushButton("清空")
        self._btn_clear_p.clicked.connect(self._clear_p_table)
        self._btn_import_results = QPushButton("从结果导入")
        self._btn_import_results.clicked.connect(self._import_from_results)
        p_btn_layout.addWidget(self._btn_add_p)
        p_btn_layout.addWidget(self._btn_remove_p)
        p_btn_layout.addWidget(self._btn_clear_p)
        p_btn_layout.addWidget(self._btn_import_results)
        p_btn_layout.addStretch()
        input_layout.addLayout(p_btn_layout)

        layout.addWidget(input_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_correct = QPushButton("执行校正")
        self._btn_correct.setMinimumHeight(40)
        self._btn_correct.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_correct.clicked.connect(self._run_correction)
        exec_layout.addWidget(self._btn_correct)

        self._btn_batch = QPushButton("批量校正所有结果")
        self._btn_batch.clicked.connect(self._batch_correct)
        exec_layout.addWidget(self._btn_batch)

        layout.addLayout(exec_layout)

        # ---- 结果表格 ----
        result_group = QGroupBox("校正结果")
        result_layout = QVBoxLayout(result_group)

        self._result_table = QTableWidget(0, 5)
        self._result_table.setHorizontalHeaderLabels([
            "检验名", "原始p值", "校正后p值", "alpha", "显著"
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

    def _sync_from_vm(self) -> None:
        pass

    def _add_p_row(self) -> None:
        row = self._p_table.rowCount()
        self._p_table.insertRow(row)
        self._p_table.setItem(row, 0, QTableWidgetItem(f"Test{row+1}"))
        self._p_table.setItem(row, 1, QTableWidgetItem("0.05"))
        self._p_table.setItem(row, 2, QTableWidgetItem(""))

    def _remove_p_row(self) -> None:
        rows = sorted(set(item.row() for item in self._p_table.selectedItems()), reverse=True)
        for row in rows:
            self._p_table.removeRow(row)

    def _clear_p_table(self) -> None:
        self._p_table.setRowCount(0)

    def _import_from_results(self) -> None:
        # 从之前的统计结果导入 p 值
        self.status_message.emit("从结果导入功能待实现")

    @Slot()
    def _run_correction(self) -> None:
        p_values = []
        names = []
        for row in range(self._p_table.rowCount()):
            name_item = self._p_table.item(row, 0)
            p_item = self._p_table.item(row, 1)
            if name_item and p_item:
                try:
                    p = float(p_item.text())
                    names.append(name_item.text())
                    p_values.append(p)
                except ValueError:
                    pass

        if not p_values:
            self.status_message.emit("没有有效的 p 值")
            return

        result = self._vm.run_multiple_comparison_correction(np.array(p_values))
        if result:
            self._display_result(names, p_values, result)
            self.status_message.emit(f"校正完成: {sum(result['rejected'])}/{len(p_values)} 显著")

    def _display_result(self, names: list[str], p_values: list[float], result: dict[str, Any]) -> None:
        self._result_table.setRowCount(len(names))
        for i, name in enumerate(names):
            self._result_table.setItem(i, 0, QTableWidgetItem(name))
            self._result_table.setItem(i, 1, QTableWidgetItem(f"{p_values[i]:.6f}"))
            self._result_table.setItem(i, 2, QTableWidgetItem(f"{result['p_values_corrected'][i]:.6f}"))
            self._result_table.setItem(i, 3, QTableWidgetItem(f"{result['alpha_corrected']:.4f}"))
            self._result_table.setItem(i, 4, QTableWidgetItem("是" if result['rejected'][i] else "否"))

    @Slot()
    def _batch_correct(self) -> None:
        # 批量校正所有之前的统计结果
        self.status_message.emit("批量校正功能待实现")