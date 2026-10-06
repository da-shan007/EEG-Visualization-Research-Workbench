"""3D 可视化面板"""
from __future__ import annotations
import base64
import io
from typing import Any, Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QListWidget, QListWidgetItem, QAbstractItemView
)

from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.services.source.preview_plots import (
    fig_stc_topomap, fig_dipoles_2d, fig_sensors_2d, fig_src_cloud,
    extract_sensor_xy, DIPOLE_VIEW_PLANES,
)
from eeg_workbench.utils.ui import balance_form, embed_figure


class Visualization3DWidget(QWidget):
    """3D 可视化面板"""

    status_message = Signal(str)

    def __init__(self, viewmodel: SourceViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
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
        self._spin_time_idx.valueChanged.connect(self._on_time_idx_changed)
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

        # ---- 在线预览（matplotlib 内嵌；完整 3D 交互需安装 pyvista） ----
        preview_group = QGroupBox("在线预览")
        preview_layout = QVBoxLayout(preview_group)
        self._lbl_preview_hint = QLabel(
            "计算逆向解/偶极子拟合后，在此显示 2D 预览（pyvista 未安装，无 Brain 交互窗口）。"
        )
        self._lbl_preview_hint.setStyleSheet("color: #888; font-size: 12px;")
        self._lbl_preview_hint.setWordWrap(True)
        preview_layout.addWidget(self._lbl_preview_hint)
        self._preview_layout = QVBoxLayout()
        preview_layout.addLayout(self._preview_layout)
        layout.addWidget(preview_group)

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
        self._btn_export_stl.setEnabled(False)
        self._btn_export_stl.setToolTip("需要 pyvista Brain 网格（当前未安装/未绘制），暂不可用")
        export_layout.addWidget(self._btn_export_stl)

        layout.addWidget(export_group)

        layout.addStretch()

        self._vis_type = "source"
        self._dipole_view = "dorsal"
        self._fig_canvas = None
        self._current_fig = None

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.inverse_solution_ready.connect(self._on_inverse_ready)
        self._vm.dipole_fit_ready.connect(self._on_dipole_ready)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_inverse_ready(self, result: Any) -> None:
        self._source_group.setEnabled(True)
        self._btn_source.setChecked(True)
        self._set_vis_type("source")

    def _on_dipole_ready(self, result: Any) -> None:
        self._btn_dipole.setEnabled(True)
        if self._vis_type == "dipole":
            self._render_current()

    def _set_vis_type(self, vis_type: str) -> None:
        self._vis_type = vis_type
        for btn, name in [(self._btn_source, "source"), (self._btn_dipole, "dipole"),
                          (self._btn_connectivity, "connectivity"), (self._btn_montage, "montage")]:
            btn.setChecked(name == vis_type)
        if vis_type == "source":
            self._source_group.setEnabled(True)
            self._render_current()
        elif vis_type == "dipole":
            self._render_current()
        elif vis_type == "connectivity":
            self.status_message.emit("源空间连通性：请先在特征提取模块计算连通性，再回到此处查看 3D 叠加")
            self._render_current()
        elif vis_type == "montage":
            self._render_current()

    def _set_view(self, view: str) -> None:
        """视图按钮：切换偶极子 2D 投影平面（标题如实标注平面，非 Brain 视角）。"""
        self._dipole_view = view
        plane = DIPOLE_VIEW_PLANES.get(view, DIPOLE_VIEW_PLANES["dorsal"])[2]
        self.status_message.emit(f"偶极子投影平面: {plane}")
        if self._vis_type == "dipole":
            self._render_current()

    def _on_time_idx_changed(self) -> None:
        if self._vis_type == "source":
            self._render_current()

    def _render_current(self) -> None:
        """按当前可视化类型渲染内嵌预览；失败只提示不抛错。"""
        try:
            if self._vis_type == "source":
                self._render_source()
            elif self._vis_type == "dipole":
                self._render_dipoles()
            elif self._vis_type == "montage":
                self._render_montage()
            elif self._vis_type == "connectivity":
                self._render_src_cloud()
        except Exception as e:
            self._lbl_preview_hint.setText(f"预览生成失败: {e}")
            self.status_message.emit(f"3D 预览失败: {e}")
        finally:
            has_brain = bool(getattr(getattr(self._vm, "_viz", None), "_brain", None))
            self._btn_export_stl.setEnabled(has_brain)

    def _render_source(self) -> None:
        inv = self._vm._inverse_result
        if not inv or not inv.stc:
            self._lbl_preview_hint.setText("请先计算逆向解。")
            return
        idx = min(self._spin_time_idx.value(), len(inv.stc.times) - 1)
        fig = fig_stc_topomap(inv.stc, idx)
        self._show_fig(fig, f"源估计地形 @ {float(inv.stc.times[idx]) * 1000:.0f} ms")

    def _render_dipoles(self) -> None:
        res = self._vm._dipole_result
        if not res:
            self._lbl_preview_hint.setText("请先进行偶极子拟合。")
            return
        fig = fig_dipoles_2d(res.dipoles, view=self._dipole_view)
        self._show_fig(fig, f"偶极子投影（{len(res.dipoles)} 个）")

    def _render_montage(self) -> None:
        if self._vm._dataset is None:
            self._lbl_preview_hint.setText("请先加载数据集。")
            return
        info = self._vm._dataset.to_mne_raw().info
        ch_pos, ch_names = extract_sensor_xy(info)
        if len(ch_names) == 0:
            self._lbl_preview_hint.setText("数据集中无带位置的 EEG 通道。")
            return
        fig = fig_sensors_2d(ch_pos, ch_names)
        self._show_fig(fig, "传感器分布")

    def _render_src_cloud(self) -> None:
        fwd = self._vm._forward_result
        if not fwd:
            self._lbl_preview_hint.setText("请先计算前向模型（连通性矩阵需在特征提取模块计算）。")
            return
        fig = fig_src_cloud(fwd.src)
        self._show_fig(fig, "源点分布")

    def _show_fig(self, fig: Any, hint: str) -> None:
        self._current_fig = fig
        self._fig_canvas = embed_figure(self._preview_layout, fig)
        self._lbl_preview_hint.setText(hint)

    @Slot()
    def _screenshot(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        if self._current_fig is None:
            self.status_message.emit("暂无预览图可保存：请先切换可视化类型生成预览")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "", "PNG 图片 (*.png)")
        if path:
            try:
                self._current_fig.savefig(path, dpi=150)
                self.status_message.emit(f"截图已保存: {path}")
            except Exception as e:
                self.status_message.emit(f"截图保存失败: {e}")

    @Slot()
    def _export_html(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        if self._current_fig is None:
            self.status_message.emit("暂无预览图可导出：请先切换可视化类型生成预览")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML", "", "HTML 文件 (*.html)")
        if not path:
            return
        self.export_html(path)

    def export_html(self, path: str) -> None:
        """把当前预览图写成自包含 HTML（无需文件对话框，供外部按路径导出）。"""
        if self._current_fig is None:
            self.status_message.emit("暂无预览图可导出：请先切换可视化类型生成预览")
            return
        try:
            buf = io.BytesIO()
            self._current_fig.savefig(buf, format="png", dpi=150)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>源定位预览</title></head><body>"
                f"<h3>{self._lbl_preview_hint.text()}</h3>"
                f"<img src='data:image/png;base64,{b64}'/></body></html>"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.status_message.emit(f"HTML 已导出: {path}")
        except Exception as e:
            self.status_message.emit(f"HTML 导出失败: {e}")

    @Slot()
    def _export_stl(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 STL", "", "STL 文件 (*.stl)")
        if path:
            self.export_stl(path)

    def export_stl(self, path: str) -> None:
        """把当前脑表面网格导出为 STL（需要 pyvista Brain，否则给出明确提示）。"""
        viz = getattr(self._vm, "_viz", None)
        brain = getattr(viz, "_brain", None) if viz else None
        if brain is None:
            self.status_message.emit("STL 导出需要 pyvista Brain 网格（当前未安装/未绘制）")
            return
        try:
            brain.export_stl(path)
            self.status_message.emit(f"STL 已导出: {path}")
        except Exception as e:
            self.status_message.emit(f"STL 导出失败: {e}")

    def export_3d_scene(self, path: str) -> None:
        """按扩展名导出 3D 场景（.html → 自包含预览页；.stl → 网格文件）。

        这是源定位页“导出 3D 场景”按钮的落点。
        """
        lower = path.lower()
        if lower.endswith(".html"):
            self.export_html(path)
        elif lower.endswith(".stl"):
            self.export_stl(path)
        else:
            self.status_message.emit(f"不支持的场景导出格式: {path}（支持 .html / .stl）")

    def _sync_params(self) -> None:
        # 同步可视化参数
        pass