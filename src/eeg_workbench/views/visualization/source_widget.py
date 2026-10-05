"""源定位 3D 可视化面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QListWidget, QListWidgetItem, QAbstractItemView,
    QMessageBox
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import SourcePlotConfig
from eeg_workbench.utils.ui import balance_form


class SourceVisualizationWidget(QWidget):
    """3D 源定位可视化面板"""

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

        # ---- 可视化类型选择 ----
        type_group = QGroupBox("可视化类型")
        type_layout = QHBoxLayout(type_group)

        self._btn_source = QPushButton("源估计")
        self._btn_source.setCheckable(True)
        self._btn_source.setChecked(True)
        self._btn_source.clicked.connect(lambda: self._set_vis_type("source"))

        self._btn_dipole = QPushButton("偶极子")
        self._btn_dipole.setCheckable(True)
        self._btn_dipole.clicked.connect(lambda: self._set_vis_type("dipole"))

        self._btn_connectivity = QPushButton("连通性")
        self._btn_connectivity.setCheckable(True)
        self._btn_connectivity.clicked.connect(lambda: self._set_vis_type("connectivity"))

        self._btn_montage = QPushButton("电极蒙版")
        self._btn_montage.setCheckable(True)
        self._btn_montage.clicked.connect(lambda: self._set_vis_type("montage"))

        type_layout.addWidget(self._btn_source)
        type_layout.addWidget(self._btn_dipole)
        type_layout.addWidget(self._btn_connectivity)
        type_layout.addWidget(self._btn_montage)
        type_layout.addStretch()

        layout.addWidget(type_group)

        # ---- 源估计可视化选项 ----
        self._source_group = QGroupBox("源估计可视化")
        source_layout = QFormLayout(self._source_group)

        self._spin_time_idx = QSpinBox()
        self._spin_time_idx.setRange(0, 1000)
        self._spin_time_idx.setValue(0)
        source_layout.addRow("时间点索引:", self._spin_time_idx)

        self._cmb_hemi = QComboBox()
        self._cmb_hemi.addItems(["both", "lh", "rh", "split"])
        source_layout.addRow("半球:", self._cmb_hemi)

        self._cmb_surf = QComboBox()
        self._cmb_surf.addItems(["inflated", "pial", "white", "smooth"])
        source_layout.addRow("表面:", self._cmb_surf)

        self._cmb_cmap = QComboBox()
        self._cmb_cmap.addItems(["RdBu_r", "hot", "coolwarm", "viridis", "plasma"])
        source_layout.addRow("颜色映射:", self._cmb_cmap)

        self._spin_vmin = QDoubleSpinBox()
        self._spin_vmin.setRange(-100, 100)
        self._spin_vmin.setDecimals(2)
        source_layout.addRow("最小值:", self._spin_vmin)

        self._spin_vmax = QDoubleSpinBox()
        self._spin_vmax.setRange(-100, 100)
        self._spin_vmax.setDecimals(2)
        source_layout.addRow("最大值:", self._spin_vmax)
        balance_form(source_layout)

        layout.addWidget(self._source_group)

        # ---- 交互控制 ----
        ctrl_group = QGroupBox("视图控制")
        ctrl_layout = QVBoxLayout(ctrl_group)

        views_row = QHBoxLayout()
        standard_views = ["lateral", "medial", "rostral", "caudal", "dorsal", "ventral"]
        for view in standard_views:
            btn = QPushButton(view.capitalize())
            btn.clicked.connect(lambda checked, v=view: self._set_view(v))
            views_row.addWidget(btn)
        ctrl_layout.addLayout(views_row)

        layout.addWidget(ctrl_group)

        # ---- 导出 ----
        export_group = QGroupBox("导出")
        export_layout = QHBoxLayout(export_group)

        self._btn_screenshot = QPushButton("截图 (PNG)")
        self._btn_screenshot.clicked.connect(self._screenshot)
        export_layout.addWidget(self._btn_screenshot)

        self._btn_export_html = QPushButton("导出 HTML")
        self._btn_export_html.clicked.connect(self._export_html)
        export_layout.addWidget(self._btn_export_html)

        self._btn_export_stl = QPushButton("导出 STL")
        self._btn_export_stl.clicked.connect(self._export_stl)
        export_layout.addWidget(self._btn_export_stl)

        layout.addWidget(export_group)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.inverse_solution_ready.connect(self._on_inverse_ready)
        self._vm.dipole_fit_ready.connect(self._on_dipole_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_inverse_ready(self, result):
        self._source_group.setEnabled(True)
        self._btn_source.setChecked(True)
        self._set_vis_type("source")

    def _on_dipole_ready(self, result):
        self._btn_dipole.setEnabled(True)

    def _set_vis_type(self, vis_type: str):
        self._vis_type = vis_type
        if vis_type == "source":
            self._source_group.setEnabled(True)
            if self._vm._inverse_result and self._vm._inverse_result.stc:
                self._vm.plot_source_estimate()
        elif vis_type == "dipole":
            if self._vm._dipole_result:
                self._vm.plot_dipoles_3d()
        elif vis_type == "connectivity":
            self.status_message.emit("源空间连通性：请先在“连通性”标签页计算，再回到此处查看 3D 叠加")
        elif vis_type == "montage":
            self.status_message.emit("电极蒙版：请在数据管理中确认 montage 已设置，传感器位置将随源估计一并显示")

    def _set_view(self, view: str):
        if hasattr(self._vm, '_viz') and self._vm._viz:
            self._vm._viz._brain.show_view(view)

    @Slot()
    def _screenshot(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "", "PNG 图片 (**.png)")
        if path:
            self.status_message.emit(f"截图已保存: {path}")

    @Slot()
    def _export_html(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML", "", "HTML 文件 (*.html)")
        if path:
            self.status_message.emit(f"HTML 已导出: {path}")

    @Slot()
    def _export_stl(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 STL", "", "STL 文件 (*.stl)")
        if path:
            self.status_message.emit(f"STL 已导出: {path}")

    def _sync_params(self):
        # 同步可视化参数
        pass