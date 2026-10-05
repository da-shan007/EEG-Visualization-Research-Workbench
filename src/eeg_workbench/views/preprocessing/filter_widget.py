"""滤波面板：带通、高通、低通、陷波、带阻"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QDoubleSpinBox, QPushButton, QCheckBox, QLabel,
    QRadioButton, QButtonGroup, QTabWidget, QScrollArea
)

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.models.preprocessing import FilterParams, FilterType, FilterMethod, FILTER_PRESETS
from eeg_workbench.utils.ui import balance_form


class FilterWidget(QWidget):
    """滤波参数设置与执行面板"""

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

        # ---- 预设选择 ----
        preset_group = QGroupBox("滤波预设")
        preset_layout = QHBoxLayout(preset_group)

        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(FILTER_PRESETS.keys()))
        self._cmb_preset.setCurrentText("standard")
        self._cmb_preset.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(QLabel("预设:"))
        preset_layout.addWidget(self._cmb_preset)

        self._btn_apply_preset = QPushButton("应用预设")
        self._btn_apply_preset.clicked.connect(self._apply_preset)
        preset_layout.addWidget(self._btn_apply_preset)
        preset_layout.addStretch()

        layout.addWidget(preset_group)

        # ---- 滤波类型标签页 ----
        self._tabs = QTabWidget()

        # 带通/高通/低通标签页
        self._tab_band = self._create_band_tab()
        self._tabs.addTab(self._tab_band, "带通/高通/低通")

        # 陷波/带阻标签页
        self._tab_notch = self._create_notch_tab()
        self._tabs.addTab(self._tab_notch, "陷波/带阻")

        layout.addWidget(self._tabs, 1)

        # ---- 进阶参数 ----
        adv_group = QGroupBox("进阶参数")
        adv_layout = QFormLayout(adv_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in FilterMethod])
        self._cmb_method.setCurrentText("fir")
        self._cmb_method.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("滤波方法:", self._cmb_method)

        self._cmb_phase = QComboBox()
        self._cmb_phase.addItems(["zero", "zero-double", "minimum"])
        self._cmb_phase.setCurrentText("zero")
        self._cmb_phase.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("相位:", self._cmb_phase)

        self._cmb_fir_window = QComboBox()
        self._cmb_fir_window.addItems(["hamming", "hann", "blackman", "kaiser"])
        self._cmb_fir_window.setCurrentText("hamming")
        self._cmb_fir_window.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("FIR 窗函数:", self._cmb_fir_window)

        self._cmb_fir_design = QComboBox()
        self._cmb_fir_design.addItems(["firwin", "firwin2"])
        self._cmb_fir_design.setCurrentText("firwin")
        self._cmb_fir_design.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("FIR 设计:", self._cmb_fir_design)

        self._spin_iir_order = QDoubleSpinBox()
        self._spin_iir_order.setRange(1, 20)
        self._spin_iir_order.setValue(4)
        self._spin_iir_order.setDecimals(0)
        self._spin_iir_order.valueChanged.connect(self._on_param_changed)
        adv_layout.addRow("IIR 阶数:", self._spin_iir_order)

        self._cmb_pad = QComboBox()
        self._cmb_pad.addItems(["reflect_limited", "reflect", "constant", "edge"])
        self._cmb_pad.setCurrentText("reflect_limited")
        self._cmb_pad.currentTextChanged.connect(self._on_param_changed)
        adv_layout.addRow("边缘填充:", self._cmb_pad)
        balance_form(adv_layout)

        layout.addWidget(adv_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("执行滤波")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_filter)
        exec_layout.addWidget(self._btn_run)

        self._btn_ica_prep = QPushButton("ICA 预处理 (1Hz 高通)")
        self._btn_ica_prep.clicked.connect(self._run_ica_prep)
        exec_layout.addWidget(self._btn_ica_prep)

        layout.addLayout(exec_layout)

        # 初始同步
        self._sync_from_vm()

    def _create_band_tab(self) -> QWidget:
        """创建带通/高通/低通参数页"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # 滤波类型单选
        type_group = QGroupBox("滤波类型")
        type_layout = QHBoxLayout(type_group)

        self._type_group = QButtonGroup(self)
        self._rb_bandpass = QRadioButton("带通")
        self._rb_highpass = QRadioButton("高通")
        self._rb_lowpass = QRadioButton("低通")
        self._rb_bandpass.setChecked(True)

        for rb in [self._rb_bandpass, self._rb_highpass, self._rb_lowpass]:
            self._type_group.addButton(rb)
            type_layout.addWidget(rb)
            rb.toggled.connect(self._on_filter_type_changed)

        layout.addRow(type_group)

        # 频率参数
        self._spin_l_freq = QDoubleSpinBox()
        self._spin_l_freq.setRange(0.01, 500)
        self._spin_l_freq.setDecimals(2)
        self._spin_l_freq.setSingleStep(0.1)
        self._spin_l_freq.setSuffix(" Hz")
        self._spin_l_freq.setValue(0.1)
        self._spin_l_freq.valueChanged.connect(self._on_param_changed)
        layout.addRow("高通截止 (l_freq):", self._spin_l_freq)

        self._spin_h_freq = QDoubleSpinBox()
        self._spin_h_freq.setRange(0.01, 500)
        self._spin_h_freq.setDecimals(2)
        self._spin_h_freq.setSingleStep(0.1)
        self._spin_h_freq.setSuffix(" Hz")
        self._spin_h_freq.setValue(40.0)
        self._spin_h_freq.valueChanged.connect(self._on_param_changed)
        layout.addRow("低通截止 (h_freq):", self._spin_h_freq)
        balance_form(layout)

        return tab

    def _create_notch_tab(self) -> QWidget:
        """创建陷波/带阻参数页"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # 陷波频率
        self._spin_notch_freq = QDoubleSpinBox()
        self._spin_notch_freq.setRange(1, 200)
        self._spin_notch_freq.setDecimals(1)
        self._spin_notch_freq.setSingleStep(1)
        self._spin_notch_freq.setSuffix(" Hz")
        self._spin_notch_freq.setValue(50.0)
        self._spin_notch_freq.valueChanged.connect(self._on_param_changed)
        layout.addRow("陷波频率:", self._spin_notch_freq)

        # 陷波带宽
        self._spin_notch_width = QDoubleSpinBox()
        self._spin_notch_width.setRange(0.1, 10)
        self._spin_notch_width.setDecimals(1)
        self._spin_notch_width.setSingleStep(0.5)
        self._spin_notch_width.setSuffix(" Hz")
        self._spin_notch_width.setValue(1.0)
        self._spin_notch_width.valueChanged.connect(self._on_param_changed)
        layout.addRow("陷波带宽:", self._spin_notch_width)

        # 多频率陷波 (工频及谐波)
        self._chk_harmonics = QCheckBox("同时陷除谐波 (2x, 3x...)")
        self._chk_harmonics.setChecked(False)
        layout.addRow("", self._chk_harmonics)

        self._spin_max_harmonic = QDoubleSpinBox()
        self._spin_max_harmonic.setRange(2, 10)
        self._spin_max_harmonic.setDecimals(0)
        self._spin_max_harmonic.setValue(5)
        self._spin_max_harmonic.setEnabled(False)
        self._chk_harmonics.toggled.connect(self._spin_max_harmonic.setEnabled)
        layout.addRow("最大谐波次数:", self._spin_max_harmonic)

        # 带阻频率范围
        layout.addRow(QLabel("<b>带阻滤波</b>"))

        self._spin_bandstop_low = QDoubleSpinBox()
        self._spin_bandstop_low.setRange(0.01, 500)
        self._spin_bandstop_low.setDecimals(2)
        self._spin_bandstop_low.setSuffix(" Hz")
        layout.addRow("带阻低频:", self._spin_bandstop_low)

        self._spin_bandstop_high = QDoubleSpinBox()
        self._spin_bandstop_high.setRange(0.01, 500)
        self._spin_bandstop_high.setDecimals(2)
        self._spin_bandstop_high.setSuffix(" Hz")
        layout.addRow("带阻高频:", self._spin_bandstop_high)
        balance_form(layout)

        return tab

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.filter_params_changed.connect(self._sync_from_vm)

    def _on_dataset_changed(self, dataset):
        # 数据集变化时启用/禁用控件
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _sync_from_vm(self):
        """从 ViewModel 同步参数到 UI"""
        params = self._vm.filter_params

        # 阻止信号递归
        self._block_signals(True)
        try:
            # 滤波类型
            if params.filter_type == FilterType.BANDPASS:
                self._rb_bandpass.setChecked(True)
            elif params.filter_type == FilterType.HIGHPASS:
                self._rb_highpass.setChecked(True)
            elif params.filter_type == FilterType.LOWPASS:
                self._rb_lowpass.setChecked(True)
            elif params.filter_type == FilterType.NOTCH:
                self._tabs.setCurrentIndex(1)

            # 频率
            if params.l_freq is not None:
                self._spin_l_freq.setValue(params.l_freq)
            if params.h_freq is not None:
                self._spin_h_freq.setValue(params.h_freq)
            if params.notch_freq is not None:
                self._spin_notch_freq.setValue(params.notch_freq)
            self._spin_notch_width.setValue(params.notch_width)

            # 进阶
            self._cmb_method.setCurrentText(params.method.value)
            self._cmb_phase.setCurrentText(params.phase)
            self._cmb_fir_window.setCurrentText(params.fir_window)
            self._cmb_fir_design.setCurrentText(params.fir_design)
            self._spin_iir_order.setValue(params.iir_order)
            self._cmb_pad.setCurrentText(params.pad)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._rb_bandpass, self._rb_highpass, self._rb_lowpass,
            self._spin_l_freq, self._spin_h_freq,
            self._spin_notch_freq, self._spin_notch_width,
            self._cmb_method, self._cmb_phase, self._cmb_fir_window,
            self._cmb_fir_design, self._spin_iir_order, self._cmb_pad,
            self._chk_harmonics, self._spin_max_harmonic,
            self._spin_bandstop_low, self._spin_bandstop_high,
        ]:
            w.blockSignals(block)

    @Slot(str)
    def _on_preset_changed(self, preset: str):
        # 预设改变时不自动应用，等用户点击按钮
        pass

    @Slot()
    def _apply_preset(self):
        preset = self._cmb_preset.currentText()
        self._vm.apply_filter_preset(preset)
        self._sync_from_vm()
        self.status_message.emit(f"已应用预设: {preset}")

    @Slot()
    def _on_filter_type_changed(self):
        self._on_param_changed()

    @Slot()
    def _on_param_changed(self):
        # 收集当前 UI 状态到 ViewModel
        params = FilterParams()

        # 确定滤波类型
        if self._tabs.currentIndex() == 0:  # 带通/高通/低通
            if self._rb_bandpass.isChecked():
                params.filter_type = FilterType.BANDPASS
                params.l_freq = self._spin_l_freq.value()
                params.h_freq = self._spin_h_freq.value()
            elif self._rb_highpass.isChecked():
                params.filter_type = FilterType.HIGHPASS
                params.l_freq = self._spin_l_freq.value()
                params.h_freq = None
            elif self._rb_lowpass.isChecked():
                params.filter_type = FilterType.LOWPASS
                params.l_freq = None
                params.h_freq = self._spin_h_freq.value()
        else:  # 陷波/带阻
            if self._chk_harmonics.isChecked():
                # 多频率陷波稍后处理
                pass
            params.filter_type = FilterType.NOTCH
            params.notch_freq = self._spin_notch_freq.value()
            params.notch_width = self._spin_notch_width.value()

        # 进阶参数
        params.method = FilterMethod(self._cmb_method.currentText())
        params.phase = self._cmb_phase.currentText()
        params.fir_window = self._cmb_fir_window.currentText()
        params.fir_design = self._cmb_fir_design.currentText()
        params.iir_order = int(self._spin_iir_order.value())
        params.pad = self._cmb_pad.currentText()

        self._vm.set_filter_params(**self._filter_params_to_dict(params))
        self.params_changed.emit()

    def _filter_params_to_dict(self, params: FilterParams) -> dict:
        return {
            "filter_type": params.filter_type,
            "l_freq": params.l_freq,
            "h_freq": params.h_freq,
            "notch_freq": params.notch_freq,
            "notch_width": params.notch_width,
            "method": params.method,
            "phase": params.phase,
            "fir_window": params.fir_window,
            "fir_design": params.fir_design,
            "iir_order": params.iir_order,
            "pad": params.pad,
        }

    @Slot()
    def _run_filter(self):
        self._vm.run_filter()

    @Slot()
    def _run_ica_prep(self):
        self._vm.apply_filter_preset("ica_prep")
        self._sync_from_vm()
        self.status_message.emit("已设置 ICA 预处理滤波 (1Hz 高通 + 50Hz 陷波)")