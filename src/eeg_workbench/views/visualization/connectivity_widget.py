"""连通性可视化面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QMessageBox
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import ConnectivityPlotConfig
from eeg_workbench.utils.ui import balance_form


class ConnectivityWidget(QWidget):
    """连通性可视化面板"""

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

        # ---- 可视化类型 ----
        type_group = QGroupBox("可视化类型")
        type_layout = QFormLayout(type_group)

        self._cmb_type = QComboBox()
        self._cmb_type.addItems(["连通性矩阵", "连通性图 (2D)", "3D 脑连通性"])
        type_layout.addRow("类型:", self._cmb_type)
        balance_form(type_layout)

        layout.addWidget(type_group)

        # ---- 矩阵显示参数 ----
        self._matrix_group = QGroupBox("矩阵显示")
        matrix_layout = QFormLayout(self._matrix_group)

        self._cmb_matrix_cmap = QComboBox()
        self._cmb_matrix_cmap.addItems(["RdBu_r", "hot", "coolwarm", "viridis", "plasma", "magma", "inferno", "RdYlBu"])
        self._cmb_matrix_cmap.setCurrentText("RdBu_r")
        matrix_layout.addRow("颜色映射:", self._cmb_matrix_cmap)

        self._spin_vmin = QDoubleSpinBox()
        self._spin_vmin.setRange(-1, 1)
        self._spin_vmin.setDecimals(2)
        self._spin_vmin.setSingleStep(0.1)
        self._spin_vmin.setValue(-1)
        matrix_layout.addRow("最小值:", self._spin_vmin)

        self._spin_vmax = QDoubleSpinBox()
        self._spin_vmax.setRange(-1, 1)
        self._spin_vmax.setDecimals(2)
        self._spin_vmax.setSingleStep(0.1)
        self._spin_vmax.setValue(1)
        matrix_layout.addRow("最大值:", self._spin_vmax)
        balance_form(matrix_layout)

        layout.addWidget(self._matrix_group)

        # ---- 图显示参数 ----
        self._graph_group = QGroupBox("连通性图")
        self._graph_group.setVisible(False)
        graph_layout = QFormLayout(self._graph_group)

        self._spin_threshold = QDoubleSpinBox()
        self._spin_threshold.setRange(0, 1)
        self._spin_threshold.setDecimals(2)
        self._spin_threshold.setSingleStep(0.05)
        self._spin_threshold.setValue(0.5)
        graph_layout.addRow("阈值:", self._spin_threshold)

        self._cmb_layout = QComboBox()
        self._cmb_layout.addItems(["circular", "spring", "kamada_kawai", "spectral", "random"])
        self._cmb_layout.setCurrentText("circular")
        graph_layout.addRow("布局算法:", self._cmb_layout)

        self._spin_node_size = QSpinBox()
        self._spin_node_size.setRange(10, 500)
        self._spin_node_size.setValue(100)
        graph_layout.addRow("节点大小:", self._spin_node_size)

        self._spin_edge_scale = QDoubleSpinBox()
        self._spin_edge_scale.setRange(0.1, 10)
        self._spin_edge_scale.setDecimals(1)
        self._spin_edge_scale.setSingleStep(0.1)
        self._spin_edge_scale.setValue(2.0)
        graph_layout.addRow("边宽缩放:", self._spin_edge_scale)
        balance_form(graph_layout)

        layout.addWidget(self._graph_group)

        # ---- 3D 参数 ----
        self._3d_group = QGroupBox("3D 可视化")
        self._3d_group.setVisible(False)
        _3d_layout = QFormLayout(self._3d_group)

        self._chk_brain_surface = QCheckBox("显示脑表面")
        self._chk_brain_surface.setChecked(True)
        _3d_layout.addRow("", self._chk_brain_surface)

        self._chk_show_nodes = QCheckBox("显示节点")
        self._chk_show_nodes.setChecked(True)
        _3d_layout.addRow("", self._chk_show_nodes)

        self._chk_show_edges = QCheckBox("显示连接")
        self._chk_show_edges.setChecked(True)
        _3d_layout.addRow("", self._chk_show_edges)
        balance_form(_3d_layout)

        layout.addWidget(self._3d_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_plot = QPushButton("绘制连通性")
        self._btn_plot.setMinimumHeight(40)
        self._btn_plot.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_plot.clicked.connect(self._plot_connectivity)
        exec_layout.addWidget(self._btn_plot)

        self._btn_export = QPushButton("导出图形")
        self._btn_export.clicked.connect(self._export_figure)
        exec_layout.addWidget(self._btn_export)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._cmb_type.currentTextChanged.connect(self._on_type_changed)
        for w in [
            self._cmb_matrix_cmap, self._spin_vmin, self._spin_vmax,
            self._spin_threshold, self._cmb_layout, self._spin_node_size,
            self._spin_edge_scale, self._chk_brain_surface
        ]:
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(lambda *_: self._on_param_changed())
            elif isinstance(w, QCheckBox):
                w.toggled.connect(lambda *_: self._on_param_changed())
            else:
                w.valueChanged.connect(lambda *_: self._on_param_changed())

        # 初始同步
        self._sync_from_vm()

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    @Slot(str)
    def _on_type_changed(self, text: str):
        is_matrix = "矩阵" in text
        is_graph = "图" in text and "3D" not in text
        is_3d = "3D" in text

        self._matrix_group.setVisible(is_matrix)
        self._graph_group.setVisible(is_graph)
        self._3d_group.setVisible(is_3d)
        self._on_param_changed()

    def _sync_from_vm(self):
        params = self._vm.conn_params
        self._block_signals(True)
        try:
            self._cmb_type.setCurrentText(getattr(params, 'visualization_type', "连通性矩阵"))
            self._cmb_matrix_cmap.setCurrentText(params.matrix_cmap)
            self._spin_vmin.setValue(params.matrix_vmin)
            self._spin_vmax.setValue(params.matrix_vmax)
            self._spin_threshold.setValue(params.graph_threshold)
            self._cmb_layout.setCurrentText(params.graph_layout)
            self._spin_node_size.setValue(int(params.node_size))
            self._spin_edge_scale.setValue(params.edge_width_scale)
            self._chk_brain_surface.setChecked(getattr(params, 'show_brain_surface', True))
        finally:
            self._block_signals(False)

    @Slot()
    def _on_param_changed(self):
        params = ConnectivityPlotConfig(
            visualization_type=self._cmb_type.currentText(),
            matrix_cmap=self._cmb_matrix_cmap.currentText(),
            matrix_vmin=self._spin_vmin.value(),
            matrix_vmax=self._spin_vmax.value(),
            graph_threshold=self._spin_threshold.value(),
            graph_layout=self._cmb_layout.currentText(),
            node_size=float(self._spin_node_size.value()),
            edge_width_scale=self._spin_edge_scale.value(),
            show_brain_surface=self._chk_brain_surface.isChecked(),
            show_matrix="矩阵" in self._cmb_type.currentText(),
            show_graph=("图" in self._cmb_type.currentText() and "3D" not in self._cmb_type.currentText()),
            show_3d="3D" in self._cmb_type.currentText(),
        )
        self._vm.set_conn_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _plot_connectivity(self):
        if not self._vm.dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        self.status_message.emit("正在绘制连通性...")
        self._on_param_changed()
        self._vm.plot_connectivity()

    @Slot()
    def _export_figure(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出连通性图", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self._vm.export_figure(path=path)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_type, self._cmb_matrix_cmap, self._spin_vmin, self._spin_vmax,
            self._spin_threshold, self._cmb_layout, self._spin_node_size,
            self._spin_edge_scale, self._chk_brain_surface
        ]:
            w.blockSignals(block)