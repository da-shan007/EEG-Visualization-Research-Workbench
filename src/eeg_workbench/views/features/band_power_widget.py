"""频段功率面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QHeaderView,
    QLabel, QAbstractItemView
)

from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.models.features import BandPowerParams, SpectralMethod, STANDARD_BANDS


class BandPowerWidget(QWidget):
    """频段功率参数设置与执行面板"""

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

        # ---- 预设选择 ----
        preset_group = QGroupBox("频段预设")
        preset_layout = QHBoxLayout(preset_group)

        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(["standard", "erp", "micro"])
        self._cmb_preset.setCurrentText("standard")
        preset_layout.addWidget(QLabel("预设:"))
        preset_layout.addWidget(self._cmb_preset)

        self._btn_apply_preset = QPushButton("应用预设")
        self._btn_apply_preset.clicked.connect(self._apply_preset)
        preset_layout.addWidget(self._btn_apply_preset)
        preset_layout.addStretch()

        layout.addWidget(preset_group)

        # ---- 频段定义表格 ----
        bands_group = QGroupBox("频段定义")
        bands_layout = QVBoxLayout(bands_group)

        self._bands_table = QTableWidget(0, 3)
        self._bands_table.setHorizontalHeaderLabels(["频段名称", "低频 (Hz)", "高频 (Hz)"])
        self._bands_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._bands_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        bands_layout.addWidget(self._bands_table)

        btn_layout = QHBoxLayout()
        self._btn_add_band = QPushButton("添加频段")
        self._btn_add_band.clicked.connect(self._add_band)
        self._btn_remove_band = QPushButton("删除选中")
        self._btn_remove_band.clicked.connect(self._remove_band)
        btn_layout.addWidget(self._btn_add_band)
        btn_layout.addWidget(self._btn_remove_band)
        btn_layout.addStretch()
        bands_layout.addLayout(btn_layout)

        layout.addWidget(bands_group)

        # ---- 谱估计参数 ----
        method_group = QGroupBox("谱估计方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in SpectralMethod])
        self._cmb_method.setCurrentText("welch")
        self._cmb_method.currentTextChanged.connect(self._on_param_changed)
        method_layout.addRow("方法:", self._cmb_method)

        self._spin_n_fft = QSpinBox()
        self._spin_n_fft.setRange(16, 8192)
        self._spin_n_fft.setValue(256)
        self._spin_n_fft.setSingleStep(64)
        self._spin_n_fft.valueChanged.connect(self._on_param_changed)
        method_layout.addRow("FFT 点数:", self._spin_n_fft)

        self._spin_overlap = QSpinBox()
        self._spin_overlap.setRange(0, 4096)
        self._spin_overlap.setValue(128)
        self._spin_overlap.setSingleStep(32)
        self._spin_overlap.valueChanged.connect(self._on_param_changed)
        method_layout.addRow("重叠点数:", self._spin_overlap)

        self._cmb_window = QComboBox()
        self._cmb_window.addItems(["hann", "hamming", "blackman", "bartlett"])
        self._cmb_window.setCurrentText("hann")
        self._cmb_window.currentTextChanged.connect(self._on_param_changed)
        method_layout.addRow("窗函数:", self._cmb_window)

        # 多锥参数
        self._spin_bandwidth = QDoubleSpinBox()
        self._spin_bandwidth.setRange(1, 20)
        self._spin_bandwidth.setDecimals(1)
        self._spin_bandwidth.setValue(4.0)
        self._spin_bandwidth.setSuffix(" Hz")
        self._spin_bandwidth.valueChanged.connect(self._on_param_changed)
        method_layout.addRow("多锥带宽:", self._spin_bandwidth)

        self._chk_adaptive = QCheckBox("自适应多锥")
        self._chk_adaptive.setChecked(True)
        method_layout.addRow("", self._chk_adaptive)

        layout.addWidget(method_group)

        # ---- 输出选项 ----
        output_group = QGroupBox("输出选项")
        output_layout = QHBoxLayout(output_group)

        self._chk_relative = QCheckBox("相对功率")
        self._chk_relative.setChecked(True)
        self._chk_relative.toggled.connect(self._on_param_changed)
        output_layout.addWidget(self._chk_relative)

        self._chk_log = QCheckBox("对数变换 (log10)")
        self._chk_log.toggled.connect(self._on_param_changed)
        output_layout.addWidget(self._chk_log)

        self._chk_normalize = QCheckBox("归一化")
        self._chk_normalize.toggled.connect(self._on_param_changed)
        output_layout.addWidget(self._chk_normalize)

        output_layout.addStretch()
        layout.addWidget(output_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("计算频段功率")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_band_power)
        exec_layout.addWidget(self._btn_run)

        self._btn_from_epochs = QPushButton("从 Epochs 计算")
        self._btn_from_epochs.setToolTip("使用事件编辑器定义的事件提取 Epochs 后计算")
        self._btn_from_epochs.clicked.connect(self._run_from_epochs)
        exec_layout.addWidget(self._btn_from_epochs)

        layout.addLayout(exec_layout)

        layout.addStretch()

        # 初始填充标准频段
        self._populate_standard_bands()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.band_power_result.connect(self._on_result_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _populate_standard_bands(self):
        self._bands_table.setRowCount(0)
        for name, (low, high) in STANDARD_BANDS.items():
            self._add_band_row(name, low, high)

    def _add_band_row(self, name: str, low: float, high: float):
        row = self._bands_table.rowCount()
        self._bands_table.insertRow(row)
        self._bands_table.setItem(row, 0, QTableWidgetItem(name))
        self._bands_table.setItem(row, 1, QTableWidgetItem(str(low)))
        self._bands_table.setItem(row, 2, QTableWidgetItem(str(high)))

    @Slot()
    def _add_band(self):
        row = self._bands_table.rowCount()
        self._bands_table.insertRow(row)
        self._bands_table.setItem(row, 0, QTableWidgetItem(f"Band{row+1}"))
        self._bands_table.setItem(row, 1, QTableWidgetItem("8"))
        self._bands_table.setItem(row, 2, QTableWidgetItem("13"))

    @Slot()
    def _remove_band(self):
        rows = sorted(set(item.row() for item in self._bands_table.selectedItems()), reverse=True)
        for row in rows:
            self._bands_table.removeRow(row)

    @Slot()
    def _apply_preset(self):
        preset = self._cmb_preset.currentText()
        self._vm.apply_band_preset(preset)
        self._populate_standard_bands()
        self.status_message.emit(f"已应用预设: {preset}")

    def _sync_from_vm(self):
        params = self._vm.band_power_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method.value)
            self._spin_n_fft.setValue(params.n_fft)
            self._spin_overlap.setValue(params.n_overlap)
            self._cmb_window.setCurrentText(params.window)
            self._spin_bandwidth.setValue(params.bandwidth)
            self._chk_adaptive.setChecked(params.adaptive)
            self._chk_relative.setChecked(params.relative)
            self._chk_log.setChecked(params.log_transform)
            self._chk_normalize.setChecked(params.normalize)

            # 更新频段表格
            self._bands_table.setRowCount(0)
            for name, (low, high) in params.bands.items():
                self._add_band_row(name, low, high)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_method, self._spin_n_fft, self._spin_overlap,
            self._cmb_window, self._spin_bandwidth, self._chk_adaptive,
            self._chk_relative, self._chk_log, self._chk_normalize
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        # 收集频段
        bands = {}
        for row in range(self._bands_table.rowCount()):
            name = self._bands_table.item(row, 0).text()
            try:
                low = float(self._bands_table.item(row, 1).text())
                high = float(self._bands_table.item(row, 2).text())
                bands[name] = (low, high)
            except (ValueError, AttributeError):
                continue

        params = BandPowerParams(
            bands=bands,
            method=SpectralMethod(self._cmb_method.currentText()),
            n_fft=self._spin_n_fft.value(),
            n_overlap=self._spin_overlap.value(),
            window=self._cmb_window.currentText(),
            bandwidth=self._spin_bandwidth.value(),
            adaptive=self._chk_adaptive.isChecked(),
            relative=self._chk_relative.isChecked(),
            log_transform=self._chk_log.isChecked(),
            normalize=self._chk_normalize.isChecked(),
        )
        self._vm.set_band_power_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_band_power(self):
        self._vm.run_band_power()

    @Slot()
    def _run_from_epochs(self):
        # 这里需要打开 Epochs 定义对话框
        self.status_message.emit("请先在事件编辑器中定义事件，然后使用此功能")

    @Slot(object)
    def _on_result_ready(self, result):
        if result and result.band_power:
            bands_str = ", ".join(f"{k}: {v.shape}" for k, v in result.band_power.items())
            self.status_message.emit(f"频段功率计算完成: {bands_str}")