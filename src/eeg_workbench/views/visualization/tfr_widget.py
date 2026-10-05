"""时频图面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QLineEdit, QMessageBox
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import TFRPlotConfig, TFRParams
from eeg_workbench.utils.ui import balance_form


class TFRWidget(QWidget):
    """时频图面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 方法选择 ----
        method_group = QGroupBox("时频方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems(["morlet", "multitaper", "stft", "stockwell"])
        self._cmb_method.setCurrentText("morlet")
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- 频率范围 ----
        freq_group = QGroupBox("频率范围")
        freq_layout = QFormLayout(freq_group)

        self._spin_fmin = QDoubleSpinBox()
        self._spin_fmin.setRange(0.1, 500)
        self._spin_fmin.setDecimals(1)
        self._spin_fmin.setValue(1.0)
        self._spin_fmin.setSuffix(" Hz")
        freq_layout.addRow("最低频率:", self._spin_fmin)

        self._spin_fmax = QDoubleSpinBox()
        self._spin_fmax.setRange(0.1, 500)
        self._spin_fmax.setDecimals(1)
        self._spin_fmax.setValue(100.0)
        self._spin_fmax.setSuffix(" Hz")
        freq_layout.addRow("最高频率:", self._spin_fmax)

        self._spin_n_freqs = QSpinBox()
        self._spin_n_freqs.setRange(5, 200)
        self._spin_n_freqs.setValue(50)
        freq_layout.addRow("频率点数:", self._spin_n_freqs)

        # 自定义频率
        self._edit_custom_freqs = QLineEdit()
        self._edit_custom_freqs.setPlaceholderText("可选: 逗号分隔的频率值，如 4,8,12,30")
        freq_layout.addRow("自定义频率:", self._edit_custom_freqs)
        balance_form(freq_layout)

        layout.addWidget(freq_group)

        # ---- Morlet 参数 ----
        self._morlet_group = QGroupBox("Morlet 小波参数")
        morlet_layout = QFormLayout(self._morlet_group)

        self._spin_n_cycles = QDoubleSpinBox()
        self._spin_n_cycles.setRange(1, 30)
        self._spin_n_cycles.setDecimals(1)
        self._spin_n_cycles.setValue(7.0)
        morlet_layout.addRow("周期数:", self._spin_n_cycles)
        balance_form(morlet_layout)

        layout.addWidget(self._morlet_group)

        # ---- STFT 参数 ----
        self._stft_group = QGroupBox("STFT 参数")
        self._stft_group.setVisible(False)
        stft_layout = QFormLayout(self._stft_group)

        self._spin_n_fft = QSpinBox()
        self._spin_n_fft.setRange(16, 8192)
        self._spin_n_fft.setValue(256)
        self._spin_n_fft.setSingleStep(64)
        stft_layout.addRow("FFT 点数:", self._spin_n_fft)

        self._spin_overlap = QSpinBox()
        self._spin_overlap.setRange(0, 4096)
        self._spin_overlap.setValue(128)
        self._spin_overlap.setSingleStep(32)
        stft_layout.addRow("重叠点数:", self._spin_overlap)

        self._cmb_window = QComboBox()
        self._cmb_window.addItems(["hann", "hamming", "blackman"])
        stft_layout.addRow("窗函数:", self._cmb_window)
        balance_form(stft_layout)

        layout.addWidget(self._stft_group)

        # ---- 基线校正 ----
        baseline_group = QGroupBox("基线校正")
        baseline_layout = QFormLayout(baseline_group)

        self._chk_baseline = QCheckBox("启用基线校正")
        self._chk_baseline.setChecked(True)
        baseline_layout.addRow("", self._chk_baseline)

        base_row = QHBoxLayout()
        self._spin_base_tmin = QDoubleSpinBox()
        self._spin_base_tmin.setRange(-10, 0)
        self._spin_base_tmin.setDecimals(2)
        self._spin_base_tmin.setValue(-0.5)
        self._spin_base_tmin.setSuffix(" s")
        base_row.addWidget(self._spin_base_tmin)
        self._spin_base_tmax = QDoubleSpinBox()
        self._spin_base_tmax.setRange(-10, 0)
        self._spin_base_tmax.setDecimals(2)
        self._spin_base_tmax.setValue(-0.1)
        self._spin_base_tmax.setSuffix(" s")
        base_row.addWidget(self._spin_base_tmax)
        baseline_layout.addRow("基线窗口:", base_row)

        self._cmb_base_mode = QComboBox()
        self._cmb_base_mode.addItems(["mean", "ratio", "logratio", "zscore", "percent"])
        self._cmb_base_mode.setCurrentText("logratio")
        baseline_layout.addRow("校正模式:", self._cmb_base_mode)
        balance_form(baseline_layout)

        layout.addWidget(baseline_group)

        # ---- 颜色/显示 ----
        display_group = QGroupBox("显示选项")
        display_layout = QFormLayout(display_group)

        self._cmb_cmap = QComboBox()
        self._cmb_cmap.addItems(["RdBu_r", "hot", "coolwarm", "viridis", "plasma", "magma", "inferno"])
        self._cmb_cmap.setCurrentText("RdBu_r")
        display_layout.addRow("颜色映射:", self._cmb_cmap)

        self._spin_vmin = QDoubleSpinBox()
        self._spin_vmin.setRange(-100, 100)
        self._spin_vmin.setDecimals(2)
        self._spin_vmin.setSpecialValueText("自动")
        display_layout.addRow("最小值:", self._spin_vmin)

        self._spin_vmax = QDoubleSpinBox()
        self._spin_vmax.setRange(-100, 100)
        self._spin_vmax.setDecimals(2)
        self._spin_vmax.setSpecialValueText("自动")
        display_layout.addRow("最大值:", self._spin_vmax)
        balance_form(display_layout)

        layout.addWidget(display_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_plot = QPushButton("计算时频图")
        self._btn_plot.setMinimumHeight(40)
        self._btn_plot.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_plot.clicked.connect(self._run_tfr)
        exec_layout.addWidget(self._btn_plot)

        self._btn_export = QPushButton("导出图形")
        self._btn_export.clicked.connect(self._export_figure)
        exec_layout.addWidget(self._btn_export)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._spin_fmax.setMaximum(dataset.sfreq / 2)

    @Slot(str)
    def _on_method_changed(self, method: str):
        self._morlet_group.setVisible(method == "morlet")
        self._stft_group.setVisible(method == "stft")
        self._on_param_changed()

    def _sync_from_vm(self):
        params = self._vm.tf_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method)
            self._spin_fmin.setValue(params.fmin)
            self._spin_fmax.setValue(params.fmax)
            self._spin_n_freqs.setValue(params.n_freqs)
            if params.freqs is not None:
                self._edit_custom_freqs.setText(",".join(f"{f:.2f}" for f in params.freqs))
            self._spin_n_cycles.setValue(params.n_cycles if isinstance(params.n_cycles, float) else 7.0)
            self._spin_n_fft.setValue(params.n_fft)
            self._spin_overlap.setValue(params.n_overlap)
            self._cmb_window.setCurrentText(params.window)
            self._chk_baseline.setChecked(params.baseline is not None)
            if params.baseline:
                self._spin_base_tmin.setValue(params.baseline[0])
                self._spin_base_tmax.setValue(params.baseline[1])
            self._cmb_base_mode.setCurrentText(params.baseline_mode)
            self._cmb_cmap.setCurrentText(params.cmap)
            self._spin_vmin.setValue(params.vmin if params.vmin else 0)
            self._spin_vmax.setValue(params.vmax if params.vmax else 0)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_method, self._spin_fmin, self._spin_fmax, self._spin_n_freqs,
            self._edit_custom_freqs, self._spin_n_cycles, self._spin_n_fft,
            self._spin_overlap, self._cmb_window, self._chk_baseline,
            self._spin_base_tmin, self._spin_base_tmax, self._cmb_base_mode,
            self._cmb_cmap, self._spin_vmin, self._spin_vmax
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = TFRParams(
            method=self._cmb_method.currentText(),
            fmin=self._spin_fmin.value(),
            fmax=self._spin_fmax.value(),
            n_freqs=self._spin_n_freqs.value(),
            n_cycles=self._spin_n_cycles.value(),
            n_fft=self._spin_n_fft.value(),
            n_overlap=self._spin_overlap.value(),
            window=self._cmb_window.currentText(),
            baseline=(self._spin_base_tmin.value(), self._spin_base_tmax.value()) if self._chk_baseline.isChecked() else None,
            baseline_mode=self._cmb_base_mode.currentText(),
            cmap=self._cmb_cmap.currentText(),
            vmin=self._spin_vmin.value() if self._spin_vmin.value() != -100 else None,
            vmax=self._spin_vmax.value() if self._spin_vmax.value() != 100 else None,
        )
        # 处理自定义频率
        if self._edit_custom_freqs.text().strip():
            try:
                freqs = [float(x.strip()) for x in self._edit_custom_freqs.text().split(",") if x.strip()]
                if freqs:
                    params.freqs = freqs
                    params.n_freqs = len(freqs)
            except ValueError:
                pass

        self._vm.set_tf_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_tfr(self):
        if not self._vm.dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        self._on_param_changed()
        self.status_message.emit("正在计算时频图...")
        self._vm.plot_tfr()

    @Slot()
    def _export_figure(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出时频图", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self._vm.export_figure(path=path)