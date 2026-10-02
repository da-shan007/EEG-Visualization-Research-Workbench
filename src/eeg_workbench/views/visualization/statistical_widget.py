"""统计图面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QMessageBox,
    QLineEdit
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import StatisticalPlotConfig


class StatisticalWidget(QWidget):
    """统计图面板"""

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

        # ---- 图表类型 ----
        type_group = QGroupBox("图表类型")
        type_layout = QFormLayout(type_group)

        self._cmb_plot_type = QComboBox()
        self._cmb_plot_type.addItems(["柱状图", "小提琴图", "箱线图", "雨云图", "森林图", "效应量图"])
        self._cmb_plot_type.setCurrentText("柱状图")
        type_layout.addRow("类型:", self._cmb_plot_type)

        layout.addWidget(type_group)

        # ---- 效应量参数 ----
        effect_group = QGroupBox("效应量设置")
        effect_layout = QFormLayout(effect_group)

        self._cmb_effect_size = QComboBox()
        self._cmb_effect_size.addItems(["cohen_d", "hedges_g", "eta_squared", "partial_eta_squared", "omega_squared", "r_squared", "cliff_delta"])
        self._cmb_effect_size.setCurrentText("cohen_d")
        effect_layout.addRow("效应量类型:", self._cmb_effect_size)

        self._chk_confidence = QCheckBox("显示置信区间")
        self._chk_confidence.setChecked(True)
        effect_layout.addRow("", self._chk_confidence)

        self._spin_conf_level = QDoubleSpinBox()
        self._spin_conf_level.setRange(0.8, 0.999)
        self._spin_conf_level.setDecimals(3)
        self._spin_conf_level.setSingleStep(0.01)
        self._spin_conf_level.setValue(0.95)
        effect_layout.addRow("置信水平:", self._spin_conf_level)

        layout.addWidget(effect_group)

        # ---- 显示选项 ----
        display_group = QGroupBox("显示选项")
        display_layout = QFormLayout(display_group)

        self._chk_individual = QCheckBox("显示个体数据点")
        self._chk_individual.setChecked(True)
        display_layout.addRow("", self._chk_individual)

        self._spin_point_alpha = QDoubleSpinBox()
        self._spin_point_alpha.setRange(0, 1)
        self._spin_point_alpha.setDecimals(2)
        self._spin_point_alpha.setSingleStep(0.05)
        self._spin_point_alpha.setValue(0.5)
        display_layout.addRow("点透明度:", self._spin_point_alpha)

        self._spin_jitter = QDoubleSpinBox()
        self._spin_jitter.setRange(0, 1)
        self._spin_jitter.setDecimals(2)
        self._spin_jitter.setSingleStep(0.05)
        self._spin_jitter.setValue(0.2)
        display_layout.addRow("抖动:", self._spin_jitter)

        self._chk_significance = QCheckBox("显示显著性标记")
        self._chk_significance.setChecked(True)
        display_layout.addRow("", self._chk_significance)

        self._chk_brackets = QCheckBox("显著性括号")
        self._chk_brackets.setChecked(True)
        display_layout.addRow("", self._chk_brackets)

        layout.addWidget(display_group)

        # ---- 分组顺序 ----
        group_group = QGroupBox("分组设置")
        group_layout = QFormLayout(group_group)

        self._edit_group_order = QLineEdit()
        self._edit_group_order.setPlaceholderText("组名，逗号分隔 (如: Control,Patient)")
        group_layout.addRow("组顺序:", self._edit_group_order)

        self._edit_hue_order = QLineEdit()
        self._edit_hue_order.setPlaceholderText("分组变量顺序")
        group_layout.addRow("分组变量顺序:", self._edit_hue_order)

        layout.addWidget(group_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_plot = QPushButton("绘制统计图")
        self._btn_plot.setMinimumHeight(40)
        self._btn_plot.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_plot.clicked.connect(self._plot_statistical)
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

    def _sync_from_vm(self):
        params = self._vm.stat_params
        self._block_signals(True)
        try:
            self._cmb_plot_type.setCurrentText(params.plot_type)
            self._cmb_effect_size.setCurrentText(params.effect_size_type)
            self._chk_confidence.setChecked(params.show_confidence)
            self._spin_conf_level.setValue(params.confidence_level)
            self._chk_individual.setChecked(params.show_individual_points)
            self._spin_point_alpha.setValue(params.point_alpha)
            self._spin_jitter.setValue(params.point_jitter)
            self._chk_significance.setChecked(params.show_significance)
            self._chk_brackets.setChecked(params.significance_brackets)
            self._edit_group_order.setText(params.group_order or "")
            self._edit_hue_order.setText(params.hue_order or "")
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_plot_type, self._cmb_effect_size, self._chk_confidence,
            self._spin_conf_level, self._chk_individual, self._spin_point_alpha,
            self._spin_jitter, self._chk_significance, self._chk_brackets,
            self._edit_group_order, self._edit_hue_order
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = StatisticalPlotConfig(
            plot_type=self._cmb_plot_type.currentText(),
            effect_size_type=self._cmb_effect_size.currentText(),
            show_confidence=self._chk_confidence.isChecked(),
            confidence_level=self._spin_conf_level.value(),
            show_individual_points=self._chk_individual.isChecked(),
            point_alpha=self._spin_point_alpha.value(),
            point_jitter=self._spin_jitter.value(),
            show_significance=self._chk_significance.isChecked(),
            significance_brackets=self._chk_brackets.isChecked(),
            group_order=self._edit_group_order.text().split(",") if self._edit_group_order.text() else None,
            hue_order=self._edit_hue_order.text().split(",") if self._edit_hue_order.text() else None,
        )
        self._vm.set_stat_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _plot_statistical(self):
        if not self._vm.dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        self._on_param_changed()
        self.status_message.emit("正在绘制统计图...")
        self._vm.plot_statistical()

    @Slot()
    def _export_figure(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出统计图", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self._vm.export_figure(path=path)