"""逆向求解面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QMessageBox
)

from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.models.source import InverseParams, InverseMethod
from eeg_workbench.services.source import InverseService
from eeg_workbench.utils.ui import balance_form


class InverseSolutionWidget(QWidget):
    """逆向求解面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: SourceViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 方法选择 ----
        method_group = QGroupBox("逆向方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in InverseMethod])
        self._cmb_method.setCurrentText("mne")
        self._cmb_method.currentTextChanged.connect(self._on_method_changed)
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- MNE/dSPM/sLORETA/eLORETA 参数 ----
        self._mne_group = QGroupBox("分布式源模型参数 (MNE/dSPM/sLORETA/eLORETA)")
        mne_layout = QFormLayout(self._mne_group)

        self._spin_snr = QDoubleSpinBox()
        self._spin_snr.setRange(1, 20)
        self._spin_snr.setDecimals(1)
        self._spin_snr.setSingleStep(0.5)
        self._spin_snr.setValue(3.0)
        mne_layout.addRow("SNR:", self._spin_snr)

        self._spin_lambda2 = QDoubleSpinBox()
        self._spin_lambda2.setRange(0, 1)
        self._spin_lambda2.setDecimals(4)
        self._spin_lambda2.setSingleStep(0.001)
        self._spin_lambda2.setValue(1.0/9.0)
        mne_layout.addRow("Lambda2:", self._spin_lambda2)

        self._spin_depth = QDoubleSpinBox()
        self._spin_depth.setRange(0, 1)
        self._spin_depth.setDecimals(2)
        self._spin_depth.setSingleStep(0.05)
        self._spin_depth.setValue(0.8)
        mne_layout.addRow("深度加权:", self._spin_depth)

        self._spin_loose = QDoubleSpinBox()
        self._spin_loose.setRange(0, 1)
        self._spin_loose.setDecimals(2)
        self._spin_loose.setSingleStep(0.05)
        self._spin_loose.setValue(0.2)
        mne_layout.addRow("松散约束:", self._spin_loose)

        self._cmb_pick_ori = QComboBox()
        self._cmb_pick_ori.addItems(["normal", "max-power", "vector"])
        mne_layout.addRow("朝向选择:", self._cmb_pick_ori)
        balance_form(mne_layout)

        layout.addWidget(self._mne_group)

        # ---- 波束成形参数 (LCMV/DICS/SAM) ----
        self._beam_group = QGroupBox("波束成形参数 (LCMV/DICS/SAM)")
        self._beam_group.setVisible(False)
        beam_layout = QFormLayout(self._beam_group)

        self._spin_reg = QDoubleSpinBox()
        self._spin_reg.setRange(0, 1)
        self._spin_reg.setDecimals(3)
        self._spin_reg.setSingleStep(0.005)
        self._spin_reg.setValue(0.05)
        beam_layout.addRow("正则化:", self._spin_reg)

        self._cmb_beam_pick_ori = QComboBox()
        self._cmb_beam_pick_ori.addItems(["max-power", "normal", "none"])
        beam_layout.addRow("朝向选择:", self._cmb_beam_pick_ori)

        self._chk_weight_norm = QCheckBox("权重归一化")
        self._chk_weight_norm.setChecked(True)
        beam_layout.addRow("", self._chk_weight_norm)

        self._chk_reduce_rank = QCheckBox("降低秩")
        self._chk_reduce_rank.setChecked(True)
        beam_layout.addRow("", self._chk_reduce_rank)

        # DICS 频带
        self._spin_fmin = QDoubleSpinBox()
        self._spin_fmin.setRange(0.1, 200)
        self._spin_fmin.setDecimals(1)
        self._spin_fmin.setValue(8.0)
        self._spin_fmin.setSuffix(" Hz")
        beam_layout.addRow("频带下限:", self._spin_fmin)

        self._spin_fmax = QDoubleSpinBox()
        self._spin_fmax.setRange(0.1, 200)
        self._spin_fmax.setDecimals(1)
        self._spin_fmax.setValue(30.0)
        self._spin_fmax.setSuffix(" Hz")
        beam_layout.addRow("频带上限:", self._spin_fmax)
        balance_form(beam_layout)

        layout.addWidget(self._beam_group)

        # ---- 时间窗设置 ----
        time_group = QGroupBox("时间窗设置")
        time_layout = QFormLayout(time_group)

        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-10, 100)
        self._spin_tmin.setDecimals(3)
        self._spin_tmin.setSpecialValueText("无 (从头)")
        self._spin_tmin.setValue(0)
        time_layout.addRow("开始时间:", self._spin_tmin)

        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-10, 100)
        self._spin_tmax.setDecimals(3)
        self._spin_tmax.setSpecialValueText("无 (到尾)")
        self._spin_tmax.setValue(1)
        time_layout.addRow("结束时间:", self._spin_tmax)
        balance_form(time_layout)

        layout.addWidget(time_group)

        # ---- 正向模型信息（forward_model_ready 时填充） ----
        # 注：_on_forward_ready 会写这个标签，缺了它就是运行时 AttributeError
        self._lbl_fwd_info = QLabel("导场矩阵: 尚未计算")
        self._lbl_fwd_info.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self._lbl_fwd_info)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_compute = QPushButton("计算逆向解")
        self._btn_compute.setMinimumHeight(40)
        self._btn_compute.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_compute.clicked.connect(self._run_inverse)
        exec_layout.addWidget(self._btn_compute)

        self._btn_morph = QPushButton("形变到 fsaverage")
        self._btn_morph.clicked.connect(self._morph_to_fsaverage)
        exec_layout.addWidget(self._btn_morph)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.forward_model_ready.connect(self._on_forward_ready)
        self._vm.inverse_solution_ready.connect(self._on_inverse_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_forward_ready(self, result):
        info = result.leadfield_info
        self._lbl_fwd_info.setText(
            f"导场矩阵: {info['n_sources']} 源 × {info['n_channels']} 通道"
        )
        self._btn_compute.setEnabled(True)

    def _on_inverse_ready(self, result):
        self.status_message.emit(f"逆向解完成: {result.method}")

    def _on_method_changed(self, method: str):
        is_mne = method in ("mne", "dspm", "sloreta", "eloreta")
        is_beam = method in ("lcmv", "dics", "sam")
        is_sparse = method in ("mce", "gamma_map")

        self._mne_group.setVisible(is_mne)
        self._beam_group.setVisible(is_beam)

        # 更新预设
        self._vm.apply_inverse_preset(method)

    def _sync_from_vm(self):
        params = self._vm.inverse_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method.value)
            self._spin_snr.setValue(params.snr)
            self._spin_lambda2.setValue(params.lambda2)
            self._spin_depth.setValue(params.depth if params.depth else 0.8)
            self._spin_loose.setValue(params.loose)
            self._cmb_pick_ori.setCurrentText(params.pick_ori)
            self._spin_reg.setValue(params.reg)
            self._cmb_beam_pick_ori.setCurrentText(params.pick_ori)
            self._chk_weight_norm.setChecked(params.weight_norm)
            self._chk_reduce_rank.setChecked(params.reduce_rank)
            self._spin_fmin.setValue(params.fmin or 0)
            self._spin_fmax.setValue(params.fmax or 0)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_method, self._spin_snr, self._spin_lambda2,
            self._spin_depth, self._spin_loose, self._cmb_pick_ori,
            self._spin_reg, self._cmb_beam_pick_ori, self._chk_weight_norm,
            self._chk_reduce_rank, self._spin_fmin, self._spin_fmax,
            self._spin_tmin, self._spin_tmax
        ]:
            w.blockSignals(block)

    @Slot()
    def _run_inverse(self):
        if not self._vm._forward_result:
            QMessageBox.warning(self, "提示", "请先计算前向模型")
            return
        self._btn_compute.setEnabled(False)
        self._btn_compute.setText("计算中...")
        self._vm.run_inverse_solution()
        self._btn_compute.setEnabled(True)
        self._btn_compute.setText("计算逆向解")

    @Slot()
    def _morph_to_fsaverage(self):
        if not self._vm._inverse_result or not self._vm._inverse_result.stc:
            return
        self._vm._inverse_result.stc = InverseService.morph_to_fsaverage(
            self._vm._inverse_result.stc,
            subject_from=self._vm._inverse_result.stc.subject
        )
        self.status_message.emit("已形变到 fsaverage")

    def _on_param_changed(self):
        params = InverseParams(
            method=InverseMethod(self._cmb_method.currentText()),
            snr=self._spin_snr.value(),
            lambda2=self._spin_lambda2.value(),
            depth=self._spin_depth.value(),
            loose=self._spin_loose.value(),
            pick_ori=self._cmb_pick_ori.currentText(),
            reg=self._spin_reg.value(),
            weight_norm=self._chk_weight_norm.isChecked(),
            reduce_rank=self._chk_reduce_rank.isChecked(),
            fmin=self._spin_fmin.value() if self._spin_fmin.value() > 0 else None,
            fmax=self._spin_fmax.value() if self._spin_fmax.value() > 0 else None,
        )
        self._vm.set_inverse_params(**params.__dict__)
        self.params_changed.emit()