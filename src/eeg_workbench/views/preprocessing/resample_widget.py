"""重采样面板：降采样/升采样，目标采样率设置"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QDoubleSpinBox, QPushButton, QComboBox, QLabel, QCheckBox,
    QSpinBox
)

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.models.preprocessing import ResampleParams, ResampleMethod
from eeg_workbench.utils.ui import balance_form


class ResampleWidget(QWidget):
    """重采样参数设置与执行面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: PreprocessingViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 当前采样率显示 ----
        info_group = QGroupBox("当前数据信息")
        info_layout = QFormLayout(info_group)

        self._lbl_current_sfreq = QLabel("-- Hz")
        self._lbl_current_sfreq.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        info_layout.addRow("当前采样率:", self._lbl_current_sfreq)

        self._lbl_duration = QLabel("-- s")
        info_layout.addRow("数据时长:", self._lbl_duration)

        self._lbl_n_samples = QLabel("-- 样本点")
        info_layout.addRow("样本点数:", self._lbl_n_samples)
        balance_form(info_layout)

        layout.addWidget(info_group)

        # ---- 目标采样率设置 ----
        target_group = QGroupBox("目标采样率")
        target_layout = QFormLayout(target_group)

        self._spin_target_sfreq = QDoubleSpinBox()
        self._spin_target_sfreq.setRange(1, 10000)
        self._spin_target_sfreq.setDecimals(3)
        self._spin_target_sfreq.setSingleStep(1)
        self._spin_target_sfreq.setSuffix(" Hz")
        self._spin_target_sfreq.setValue(250.0)
        self._spin_target_sfreq.valueChanged.connect(self._on_param_changed)
        target_layout.addRow("目标采样率:", self._spin_target_sfreq)

        # 快速设置按钮
        quick_layout = QHBoxLayout()
        common_rates = [100, 128, 200, 250, 256, 500, 512, 1000, 1024, 2000]
        for rate in common_rates:
            btn = QPushButton(f"{rate} Hz")
            btn.setMaximumWidth(70)
            btn.clicked.connect(lambda checked, r=rate: self._spin_target_sfreq.setValue(r))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        target_layout.addRow("常用预设:", quick_layout)

        # 倍数显示
        self._lbl_ratio = QLabel("倍数: --")
        self._lbl_ratio.setStyleSheet("color: #666;")
        target_layout.addRow("", self._lbl_ratio)
        balance_form(target_layout)

        layout.addWidget(target_group)

        # ---- 进阶参数 ----
        adv_group = QGroupBox("进阶参数")
        adv_layout = QFormLayout(adv_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in ResampleMethod])
        self._cmb_method.setCurrentText("auto")
        self._cmb_method.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("重采样方法:", self._cmb_method)

        self._cmb_npad = QComboBox()
        self._cmb_npad.addItems(["auto", "0", "1", "2"])
        self._cmb_npad.setCurrentText("auto")
        self._cmb_npad.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("边缘填充:", self._cmb_npad)

        self._cmb_window = QComboBox()
        self._cmb_window.addItems(["kaiser", "hamming", "hann", "blackman"])
        self._cmb_window.setCurrentText("kaiser")
        self._cmb_window.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("窗函数:", self._cmb_window)
        balance_form(adv_layout)

        layout.addWidget(adv_group)

        # ---- 快速操作 ----
        quick_group = QGroupBox("快速操作")
        quick_layout = QVBoxLayout(quick_group)

        # 降采样按钮
        down_layout = QHBoxLayout()
        down_layout.addWidget(QLabel("整数倍降采样:"))
        self._spin_down_factor = QSpinBox()
        self._spin_down_factor.setRange(2, 20)
        self._spin_down_factor.setValue(2)
        down_layout.addWidget(self._spin_down_factor)
        self._btn_down = QPushButton("降采样")
        self._btn_down.clicked.connect(self._downsample)
        down_layout.addWidget(self._btn_down)
        down_layout.addStretch()
        quick_layout.addLayout(down_layout)

        # 升采样按钮
        up_layout = QHBoxLayout()
        up_layout.addWidget(QLabel("整数倍升采样:"))
        self._spin_up_factor = QSpinBox()
        self._spin_up_factor.setRange(2, 10)
        self._spin_up_factor.setValue(2)
        up_layout.addWidget(self._spin_up_factor)
        self._btn_up = QPushButton("升采样")
        self._btn_up.clicked.connect(self._upsample)
        up_layout.addWidget(self._btn_up)
        up_layout.addStretch()
        quick_layout.addLayout(up_layout)

        layout.addWidget(quick_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("执行重采样")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_resample)
        exec_layout.addWidget(self._btn_run)
        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._lbl_current_sfreq.setText(f"{dataset.sfreq:.3f} Hz")
            self._lbl_duration.setText(f"{dataset.duration:.3f} s")
            self._lbl_n_samples.setText(f"{dataset.n_samples}")
            self._spin_target_sfreq.setValue(dataset.sfreq)
            self._update_ratio(dataset.sfreq)

    def _update_ratio(self, current_sfreq: float):
        target = self._spin_target_sfreq.value()
        if current_sfreq > 0:
            ratio = target / current_sfreq
            if ratio > 1:
                self._lbl_ratio.setText(f"倍数: {ratio:.2f}x (上采样)")
                self._lbl_ratio.setStyleSheet("color: #e74c3c;")
            elif ratio < 1:
                self._lbl_ratio.setText(f"倍数: {ratio:.2f}x (下采样)")
                self._lbl_ratio.setStyleSheet("color: #3498db;")
            else:
                self._lbl_ratio.setText("倍数: 1.00x (无变化)")
                self._lbl_ratio.setStyleSheet("color: #27ae60;")

    def _sync_from_vm(self):
        params = self._vm.resample_params
        self._block_signals(True)
        try:
            self._spin_target_sfreq.setValue(params.sfreq)
            self._cmb_method.setCurrentText(params.method.value)
            self._cmb_npad.setCurrentText(str(params.npad) if params.npad != "auto" else "auto")
            self._cmb_window.setCurrentText(params.window)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [self._spin_target_sfreq, self._cmb_method, self._cmb_npad, self._cmb_window]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = ResampleParams(
            sfreq=self._spin_target_sfreq.value(),
            method=ResampleMethod(self._cmb_method.currentText()),
            npad=self._cmb_npad.currentText() if self._cmb_npad.currentText() != "auto" else "auto",
            window=self._cmb_window.currentText(),
        )
        self._vm.set_resample_params(**self._resample_params_to_dict(params))
        self._update_ratio(self._vm.dataset.sfreq if self._vm.dataset else 250)
        self.params_changed.emit()

    def _resample_params_to_dict(self, params: ResampleParams) -> dict:
        return {
            "sfreq": params.sfreq,
            "method": params.method,
            "npad": params.npad,
            "window": params.window,
        }

    @Slot()
    def _downsample(self):
        if not self._vm.dataset:
            return
        factor = self._spin_down_factor.value()
        target = self._vm.dataset.sfreq / factor
        if target != int(target):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "参数错误", f"降采样因子 {factor} 导致非整数采样率: {target}")
            return
        self._spin_target_sfreq.setValue(target)
        self._run_resample()

    @Slot()
    def _upsample(self):
        factor = self._spin_up_factor.value()
        target = (self._vm.dataset.sfreq if self._vm.dataset else 250) * factor
        self._spin_target_sfreq.setValue(target)
        self._run_resample()

    @Slot()
    def _run_resample(self):
        self._vm.run_resample()