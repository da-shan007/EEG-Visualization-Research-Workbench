"""置换检验面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QLineEdit, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import PermutationParams


class PermutationWidget(QWidget):
    """置换检验面板"""

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

        # ---- 基本设置 ----
        basic_group = QGroupBox("基本设置")
        basic_layout = QFormLayout(basic_group)

        self._spin_perms = QSpinBox()
        self._spin_perms.setRange(100, 100000)
        self._spin_perms.setSingleStep(100)
        self._spin_perms.setValue(1000)
        basic_layout.addRow("置换次数:", self._spin_perms)

        self._cmb_statistic = QComboBox()
        self._cmb_statistic.addItems(["t", "f", "max_t", "max_f"])
        basic_layout.addRow("统计量:", self._cmb_statistic)

        self._cmb_tail = QComboBox()
        self._cmb_tail.addItems(["双尾 (0)", "单尾大于 (1)", "单尾小于 (-1)"])
        self._cmb_tail.setCurrentIndex(0)
        basic_layout.addRow("检验尾部:", self._cmb_tail)

        self._spin_seed = QSpinBox()
        self._spin_seed.setRange(0, 999999)
        self._spin_seed.setValue(42)
        self._spin_seed.setSpecialValueText("随机种子 (0=随机)")
        basic_layout.addRow("随机种子:", self._spin_seed)

        self._spin_n_jobs = QSpinBox()
        self._spin_n_jobs.setRange(-1, 64)
        self._spin_n_jobs.setValue(-1)
        self._spin_n_jobs.setSpecialValueText("自动 (所有核心)")
        basic_layout.addRow("并行作业数:", self._spin_n_jobs)

        layout.addWidget(basic_group)

        # ---- 簇置换设置 ----
        cluster_group = QGroupBox("簇置换设置 (时空数据)")
        cluster_layout = QFormLayout(cluster_group)

        self._spin_cluster_thresh = QDoubleSpinBox()
        self._spin_cluster_thresh.setRange(0.001, 10)
        self._spin_cluster_thresh.setDecimals(3)
        self._spin_cluster_thresh.setSpecialValueText("自动 (t分布95%)")
        self._spin_cluster_thresh.setValue(0.0)
        cluster_layout.addRow("簇形成阈值:", self._spin_cluster_thresh)

        self._cmb_cluster_method = QComboBox()
        self._cmb_cluster_method.addItems(["mass", "size", "max_sum"])
        cluster_layout.addRow("簇统计量:", self._cmb_cluster_method)

        self._spin_min_cluster = QSpinBox()
        self._spin_min_cluster.setRange(1, 100)
        self._spin_min_cluster.setValue(2)
        cluster_layout.addRow("最小簇大小:", self._spin_min_cluster)

        layout.addWidget(cluster_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_perm = QPushButton("运行置换检验")
        self._btn_perm.setMinimumHeight(40)
        self._btn_perm.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_perm.clicked.connect(self._run_permutation)
        exec_layout.addWidget(self._btn_perm)

        self._btn_cluster = QPushButton("运行簇置换检验")
        self._btn_cluster.clicked.connect(self._run_cluster)
        exec_layout.addWidget(self._btn_cluster)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _sync_from_vm(self):
        params = self._vm.perm_params
        self._block_signals(True)
        try:
            self._spin_perms.setValue(params.n_permutations)
            self._cmb_statistic.setCurrentText(params.test_statistic)
            self._cmb_tail.setCurrentIndex(params.tail + 1)
            self._spin_seed.setValue(params.seed if params.seed else 0)
            self._spin_n_jobs.setValue(params.n_jobs)
            self._spin_cluster_thresh.setValue(params.cluster_threshold if params.cluster_threshold else 0)
            self._cmb_cluster_method.setCurrentText(params.cluster_method)
            self._spin_min_cluster.setValue(params.min_cluster_size)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._spin_perms, self._cmb_statistic, self._cmb_tail,
            self._spin_seed, self._spin_n_jobs, self._spin_cluster_thresh,
            self._cmb_cluster_method, self._spin_min_cluster
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = PermutationParams(
            n_permutations=self._spin_perms.value(),
            test_statistic=self._cmb_statistic.currentText(),
            tail=[-1, 0, 1][self._cmb_tail.currentIndex()],
            seed=self._spin_seed.value() if self._spin_seed.value() > 0 else None,
            n_jobs=self._spin_n_jobs.value(),
            cluster_threshold=self._spin_cluster_thresh.value() if self._spin_cluster_thresh.value() > 0 else None,
            cluster_method=self._cmb_cluster_method.currentText(),
            min_cluster_size=self._spin_min_cluster.value(),
        )
        self._vm.set_perm_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_permutation(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "请先准备两组数据，然后调用 run_permutation_test 方法")

    @Slot()
    def _run_cluster(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "簇置换检验需要时空数据 (n_subjects, n_channels, n_times)，请先准备数据")