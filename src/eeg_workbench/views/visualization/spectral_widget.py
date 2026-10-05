"""频谱图面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QMessageBox, QFileDialog,
    QLineEdit
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import SpectralPlotConfig
from eeg_workbench.utils.ui import balance_form


class SpectralWidget(QWidget):
    """频谱图面板"""

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
        method_group = QGroupBox("谱估计方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems(["welch", "multitaper", "periodogram", "fft"])
        self._cmb_method.setCurrentText("welch")
        method_layout.addRow("方法:", self._cmb_method)
        balance_form(method_layout)

        layout.addWidget(method_group)

        # ---- 参数设置 ----
        param_group = QGroupBox("参数设置")
        param_layout = QFormLayout(param_group)

        self._spin_fmin = QDoubleSpinBox()
        self._spin_fmin.setRange(0, 500)
        self._spin_fmin.setDecimals(1)
        self._spin_fmin.setValue(0)
        self._spin_fmin.setSuffix(" Hz")
        param_layout.addRow("最低频率:", self._spin_fmin)

        self._spin_fmax = QDoubleSpinBox()
        self._spin_fmax.setRange(0, 500)
        self._spin_fmax.setDecimals(1)
        self._spin_fmax.setValue(100)
        self._spin_fmax.setSuffix(" Hz")
        param_layout.addRow("最高频率:", self._spin_fmax)

        self._spin_n_fft = QSpinBox()
        self._spin_n_fft.setRange(16, 8192)
        self._spin_n_fft.setSingleStep(64)
        self._spin_n_fft.setValue(256)
        param_layout.addRow("FFT 点数:", self._spin_n_fft)

        self._spin_overlap = QSpinBox()
        self._spin_overlap.setRange(0, 4096)
        self._spin_overlap.setSingleStep(32)
        self._spin_overlap.setValue(128)
        param_layout.addRow("重叠点数:", self._spin_overlap)

        self._cmb_window = QComboBox()
        self._cmb_window.addItems(["hann", "hamming", "blackman", "bartlett"])
        self._cmb_window.setCurrentText("hann")
        param_layout.addRow("窗函数:", self._cmb_window)

        self._chk_confidence = QCheckBox("显示置信区间")
        self._chk_confidence.setChecked(True)
        param_layout.addRow("", self._chk_confidence)

        self._spin_conf_level = QDoubleSpinBox()
        self._spin_conf_level.setRange(0.5, 0.999)
        self._spin_conf_level.setDecimals(3)
        self._spin_conf_level.setSingleStep(0.01)
        self._spin_conf_level.setValue(0.95)
        param_layout.addRow("置信水平:", self._spin_conf_level)

        self._chk_average = QCheckBox("跨通道平均")
        self._chk_average.setChecked(True)
        param_layout.addRow("", self._chk_average)
        balance_form(param_layout)

        layout.addWidget(param_group)

        # ---- 显示选项 ----
        display_group = QGroupBox("显示选项")
        display_layout = QFormLayout(display_group)

        self._cmb_xscale = QComboBox()
        self._cmb_xscale.addItems(["linear", "log"])
        display_layout.addRow("X轴刻度:", self._cmb_xscale)

        self._chk_show_topomap = QCheckBox("显示地形图插图")
        display_layout.addRow("", self._chk_show_topomap)

        self._edit_topo_freqs = QLineEdit()
        self._edit_topo_freqs.setPlaceholderText("频率列表，逗号分隔 (如: 4,8,12,30)")
        display_layout.addRow("地形图频率:", self._edit_topo_freqs)
        balance_form(display_layout)

        layout.addWidget(display_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_plot = QPushButton("绘制频谱")
        self._btn_plot.setMinimumHeight(40)
        self._btn_plot.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_plot.clicked.connect(self._plot_spectral)
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

    def _collect_config(self) -> SpectralPlotConfig:
        """从界面控件收集频谱图配置"""
        # 地形图插入频率列表
        topo_raw = self._edit_topo_freqs.text().strip()
        topo_freqs = None
        if topo_raw:
            try:
                topo_freqs = [float(x) for x in topo_raw.replace("，", ",").split(",") if x.strip()]
            except ValueError:
                topo_freqs = None

        return SpectralPlotConfig(
            fmin=self._spin_fmin.value(),
            fmax=self._spin_fmax.value(),
            xscale=self._cmb_xscale.currentText(),
            method=self._cmb_method.currentText(),
            n_fft=self._spin_n_fft.value(),
            n_overlap=self._spin_overlap.value(),
            show_confidence=self._chk_confidence.isChecked(),
            confidence_level=self._spin_conf_level.value(),
            average=self._chk_average.isChecked(),
            show_topomap_inset=self._chk_show_topomap.isChecked(),
            topomap_freqs=topo_freqs,
        )

    @Slot()
    def _on_param_changed(self):
        cfg = self._collect_config()
        self._vm.set_spectral_config(**cfg.__dict__)
        self.params_changed.emit()

    @Slot()
    def _plot_spectral(self):
        if self._vm.dataset is None:
            self.status_message.emit("请先加载数据集")
            return
        try:
            self._on_param_changed()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "参数错误", str(e))
            return
        self.status_message.emit("正在计算频谱...")
        self._vm.plot_spectral()

    @Slot()
    def _export_figure(self):
        if self._vm.dataset is None:
            self.status_message.emit("请先加载数据集")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出频谱图", "",
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;EPS (*.eps);;HTML (*.html)"
        )
        if not path:
            return
        self._vm.export_figure(path=path)