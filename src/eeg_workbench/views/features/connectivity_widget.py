"""连通性分析面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QCheckBox,
    QLabel, QLineEdit
)

from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.models.features import ConnectivityParams, ConnectivityMethod
from eeg_workbench.utils.ui import balance_form


class ConnectivityWidget(QWidget):
    """连通性分析参数设置与执行面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: FeaturesViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 方法选择 ----
        method_group = QGroupBox("连通性方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in ConnectivityMethod])
        self._cmb_method.setCurrentText("coherence")
        self._cmb_method.currentTextChanged.connect(self._on_method_changed)
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- 频率范围 ----
        freq_group = QGroupBox("频率范围")
        freq_layout = QFormLayout(freq_group)

        self._spin_fmin = QDoubleSpinBox()
        self._spin_fmin.setRange(0, 500)
        self._spin_fmin.setDecimals(1)
        self._spin_fmin.setValue(0.0)
        self._spin_fmin.setSuffix(" Hz")
        freq_layout.addRow("最低频率:", self._spin_fmin)

        self._spin_fmax = QDoubleSpinBox()
        self._spin_fmax.setRange(0, 500)
        self._spin_fmax.setDecimals(1)
        self._spin_fmax.setValue(100.0)
        self._spin_fmax.setSuffix(" Hz")
        self._spin_fmax.setSpecialValueText("奈奎斯特频率")
        freq_layout.addRow("最高频率:", self._spin_fmax)

        self._spin_n_freqs = QSpinBox()
        self._spin_n_freqs.setRange(5, 100)
        self._spin_n_freqs.setValue(20)
        freq_layout.addRow("频率点数:", self._spin_n_freqs)
        balance_form(freq_layout)

        layout.addWidget(freq_group)

        # ---- GCA 参数 ----
        self._gca_group = QGroupBox("格兰杰因果参数")
        self._gca_group.setVisible(False)
        gca_layout = QFormLayout(self._gca_group)

        self._spin_gca_order = QSpinBox()
        self._spin_gca_order.setRange(1, 50)
        self._spin_gca_order.setValue(10)
        gca_layout.addRow("模型阶数:", self._spin_gca_order)

        self._spin_gca_nfft = QSpinBox()
        self._spin_gca_nfft.setRange(64, 8192)
        self._spin_gca_nfft.setValue(256)
        self._spin_gca_nfft.setSingleStep(64)
        gca_layout.addRow("FFT 点数:", self._spin_gca_nfft)
        balance_form(gca_layout)

        layout.addWidget(self._gca_group)

        # ---- PLV/PLI 参数 ----
        self._phase_group = QGroupBox("相位连通性参数")
        self._phase_group.setVisible(False)
        phase_layout = QFormLayout(self._phase_group)

        self._spin_n_cycles = QDoubleSpinBox()
        self._spin_n_cycles.setRange(1, 30)
        self._spin_n_cycles.setDecimals(1)
        self._spin_n_cycles.setValue(7.0)
        phase_layout.addRow("Morlet 周期数:", self._spin_n_cycles)
        balance_form(phase_layout)

        layout.addWidget(self._phase_group)

        # ---- 统计检验 ----
        stat_group = QGroupBox("统计检验")
        stat_layout = QFormLayout(stat_group)

        self._spin_perms = QSpinBox()
        self._spin_perms.setRange(0, 10000)
        self._spin_perms.setValue(0)
        self._spin_perms.setSpecialValueText("不进行置换检验")
        stat_layout.addRow("置换检验次数:", self._spin_perms)

        self._cmb_tail = QComboBox()
        self._cmb_tail.addItems(["双尾 (0)", "单尾大于 (1)", "单尾小于 (-1)"])
        self._cmb_tail.setCurrentIndex(0)
        stat_layout.addRow("检验尾部:", self._cmb_tail)

        self._spin_alpha = QDoubleSpinBox()
        self._spin_alpha.setRange(0.001, 0.1)
        self._spin_alpha.setDecimals(3)
        self._spin_alpha.setSingleStep(0.01)
        self._spin_alpha.setValue(0.05)
        stat_layout.addRow("显著性水平:", self._spin_alpha)
        balance_form(stat_layout)

        layout.addWidget(stat_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("计算连通性")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_connectivity)
        exec_layout.addWidget(self._btn_run)

        self._btn_from_epochs = QPushButton("从 Epochs 计算")
        self._btn_from_epochs.clicked.connect(self._run_from_epochs)
        exec_layout.addWidget(self._btn_from_epochs)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.connectivity_result.connect(self._on_result_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_method_changed(self, method: str):
        # 显示/隐藏方法特定参数
        is_gca = method in ("gca", "dtf", "pdc")
        is_phase = method in ("plv", "pli", "wpli")
        self._gca_group.setVisible(is_gca)
        self._phase_group.setVisible(is_phase)

    def _sync_from_vm(self):
        params = self._vm.conn_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method.value)
            self._spin_fmin.setValue(params.fmin)
            self._spin_fmax.setValue(params.fmax if params.fmax else 0)
            self._spin_n_freqs.setValue(params.n_freqs)
            self._spin_gca_order.setValue(params.gca_order)
            self._spin_gca_nfft.setValue(params.gca_n_fft)
            self._spin_n_cycles.setValue(params.n_cycles)
            self._spin_perms.setValue(params.n_permutations)
            self._cmb_tail.setCurrentIndex(params.tail + 1 if params.tail in (-1, 0, 1) else 0)
            self._spin_alpha.setValue(params.alpha)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_method, self._spin_fmin, self._spin_fmax,
            self._spin_n_freqs, self._spin_gca_order, self._spin_gca_nfft,
            self._spin_n_cycles, self._spin_perms, self._cmb_tail, self._spin_alpha
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = ConnectivityParams(
            method=ConnectivityMethod(self._cmb_method.currentText()),
            fmin=self._spin_fmin.value(),
            fmax=self._spin_fmax.value() if self._spin_fmax.value() > 0 else None,
            n_freqs=self._spin_n_freqs.value(),
            gca_order=self._spin_gca_order.value(),
            gca_n_fft=self._spin_gca_nfft.value(),
            n_cycles=self._spin_n_cycles.value(),
            n_permutations=self._spin_perms.value(),
            tail=[-1, 0, 1][self._cmb_tail.currentIndex()],
            alpha=self._spin_alpha.value(),
        )
        self._vm.set_conn_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_connectivity(self):
        self._vm.run_connectivity()

    @Slot()
    def _run_from_epochs(self):
        self.status_message.emit("请先定义事件和 Epochs 参数")

    @Slot(object)
    def _on_result_ready(self, result):
        if result and result.connectivity is not None:
            shape = result.connectivity.shape
            self.status_message.emit(f"连通性计算完成: {shape}")