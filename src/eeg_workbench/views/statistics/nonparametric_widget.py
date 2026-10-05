"""非参数检验面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QLabel, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import NonparametricParams, StatisticalTest, MultipleComparisonCorrection, EffectSize
from eeg_workbench.utils.ui import balance_form


class NonparametricWidget(QWidget):
    """非参数检验面板"""

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

        # ---- 检验选择 ----
        test_group = QGroupBox("检验选择")
        test_layout = QFormLayout(test_group)

        self._cmb_test = QComboBox()
        tests = [
            (StatisticalTest.MANN_WHITNEY, "Mann-Whitney U (两独立样本)"),
            (StatisticalTest.WILCOXON, "Wilcoxon 符号秩检验 (两配对样本)"),
            (StatisticalTest.KRUSKAL_WALLIS, "Kruskal-Wallis (多独立样本)"),
            (StatisticalTest.FRIEDMAN, "Friedman (多配对样本)"),
        ]
        for enum_val, desc in tests:
            self._cmb_test.addItem(desc, enum_val)
        self._cmb_test.currentIndexChanged.connect(self._on_test_changed)
        test_layout.addRow("检验方法:", self._cmb_test)
        balance_form(test_layout)

        layout.addWidget(test_group)

        # ---- 参数设置 ----
        param_group = QGroupBox("参数设置")
        param_layout = QFormLayout(param_group)

        self._cmb_alternative = QComboBox()
        self._cmb_alternative.addItems(["two-sided", "less", "greater"])
        self._cmb_alternative.setCurrentText("two-sided")
        param_layout.addRow("备择假设:", self._cmb_alternative)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems([m.value for m in MultipleComparisonCorrection])
        self._cmb_correction.setCurrentText("fdr_bh")
        self._cmb_correction.setToolTip("多重比较校正方法")
        param_layout.addRow("多重校正:", self._cmb_correction)
        balance_form(param_layout)

        layout.addWidget(param_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("运行非参数检验")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_test)
        exec_layout.addWidget(self._btn_run)

        self._btn_effect_size = QPushButton("计算效应量 (Cliff's Delta)")
        self._btn_effect_size.clicked.connect(self._run_effect_size)
        exec_layout.addWidget(self._btn_effect_size)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    @Slot(int)
    def _on_test_changed(self, index: int):
        """检验方法切换"""
        test = self._cmb_test.currentData()
        # Friedman 需要配对数据，给出提示
        if test == StatisticalTest.FRIEDMAN:
            self.status_message.emit("Friedman 检验需要配对/重复测量数据")
        elif test == StatisticalTest.WILCOXON:
            self.status_message.emit("Wilcoxon 检验需要配对样本")

    @Slot()
    def _run_test(self):
        """运行非参数检验"""
        if not self._vm.dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        test = self._cmb_test.currentData()
        try:
            params = NonparametricParams(
                test=test,
                alternative=self._cmb_alternative.currentText(),
            )
            self.status_message.emit(f"正在运行 {self._cmb_test.currentText()} ...")
            result = self._vm.run_nonparametric(params)
            if result:
                self.status_message.emit("非参数检验完成")
            else:
                self.status_message.emit("非参数检验未返回结果")
        except AttributeError:
            QMessageBox.information(
                self, "提示",
                "统计服务尚未接入数据分组。\n请在「统计分析 → 数据准备」中配置分组后再运行。"
            )
        except Exception as e:
            QMessageBox.critical(self, "运行错误", f"非参数检验失败:\n{e}")

    @Slot()
    def _run_effect_size(self):
        """计算效应量 (Cliff's Delta)"""
        if not self._vm.dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        try:
            self.status_message.emit("正在计算 Cliff's Delta 效应量 ...")
            result = self._vm.run_effect_size()
            if result:
                self.status_message.emit("效应量计算完成")
            else:
                QMessageBox.information(self, "提示", "需要先运行一次检验以获得两组数据")
        except AttributeError:
            QMessageBox.information(self, "提示", "统计服务尚未接入数据分组。")
        except Exception as e:
            QMessageBox.critical(self, "运行错误", f"效应量计算失败:\n{e}")