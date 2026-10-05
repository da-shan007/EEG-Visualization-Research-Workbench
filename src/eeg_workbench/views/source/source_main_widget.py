"""源定位主面板：整合头模型、前向模型、逆向解、偶极子拟合、3D可视化"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QMessageBox, QListWidget, QListWidgetItem,
    QSplitter
)

from eeg_workbench.utils.ui import relay_status, wrap_scroll
from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.views.source.head_model_widget import HeadModelWidget
from eeg_workbench.views.source.forward_widget import ForwardModelWidget
from eeg_workbench.views.source.inverse_widget import InverseSolutionWidget
from eeg_workbench.views.source.dipole_widget import DipoleFitWidget
from eeg_workbench.views.source.visualization_3d_widget import Visualization3DWidget
from eeg_workbench.models.dataset import EEGDataset


class SourceMainWidget(QWidget):
    """源定位模块主面板"""

    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: SourceViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._dataset: Optional[EEGDataset] = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部信息栏 ----
        info_bar = QGroupBox("数据集状态")
        info_layout = QHBoxLayout(info_bar)

        self._lbl_dataset_name = QLabel("未加载数据")
        self._lbl_dataset_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        info_layout.addWidget(self._lbl_dataset_name)

        self._lbl_info = QLabel("通道: -- | 采样率: -- Hz | 时长: -- s")
        self._lbl_info.setStyleSheet("color: #666;")
        info_layout.addWidget(self._lbl_info, 1)

        self._btn_full_pipeline = QPushButton("一键完整流程")
        self._btn_full_pipeline.setToolTip("依次运行：头模型 → 前向模型 → 逆向解")
        self._btn_full_pipeline.clicked.connect(self._run_full_pipeline)
        info_layout.addWidget(self._btn_full_pipeline)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        self._head_widget = HeadModelWidget(self._vm)
        self._forward_widget = ForwardModelWidget(self._vm)
        self._inverse_widget = InverseSolutionWidget(self._vm)
        self._dipole_widget = DipoleFitWidget(self._vm)
        self._viz_widget = Visualization3DWidget(self._vm)

        self._tabs.addTab(wrap_scroll(self._head_widget), "头模型")
        self._tabs.addTab(wrap_scroll(self._forward_widget), "前向模型")
        self._tabs.addTab(wrap_scroll(self._inverse_widget), "逆向解")
        self._tabs.addTab(wrap_scroll(self._dipole_widget), "偶极子拟合")
        self._tabs.addTab(wrap_scroll(self._viz_widget), "3D 可视化")

        layout.addWidget(self._tabs, 1)

        # ---- 底部历史 ----
        history_group = QGroupBox("分析历史")
        history_layout = QVBoxLayout(history_group)

        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(100)
        history_layout.addWidget(self._history_list)

        history_btn = QHBoxLayout()
        self._btn_export_scene = QPushButton("导出 3D 场景")
        self._btn_export_scene.clicked.connect(self._export_scene)
        history_btn.addWidget(self._btn_export_scene)
        history_btn.addStretch()
        history_layout.addLayout(history_btn)

        layout.addWidget(history_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.head_model_ready.connect(self._on_head_model_ready)
        self._vm.forward_model_ready.connect(self._on_forward_ready)
        self._vm.inverse_solution_ready.connect(self._on_inverse_ready)
        self._vm.dipole_fit_ready.connect(self._on_dipole_ready)
        self._vm.status_message.connect(self.status_message.emit)

        # 子面板信号
        relay_status(
            [self._head_widget, self._forward_widget, self._inverse_widget,
             self._dipole_widget, self._viz_widget],
            self.status_message,
        )

    @Slot(object)
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]):
        self._dataset = dataset
        enabled = dataset is not None
        self.setEnabled(enabled)

        if dataset:
            self._lbl_dataset_name.setText(dataset.name)
            self._lbl_info.setText(
                f"通道: {dataset.n_channels} | 采样率: {dataset.sfreq:.1f} Hz | 时长: {dataset.duration:.2f} s"
            )
        else:
            self._lbl_dataset_name.setText("未加载数据")
            self._lbl_info.setText("通道: -- | 采样率: -- Hz | 时长: -- s")

        self.dataset_changed.emit(dataset)

    @Slot(object)
    def _on_head_model_ready(self, result):
        self._add_history(f"头模型: {result.model_type.value} ({result.subject})")
        self._tabs.setTabEnabled(1, True)  # 启用前向模型标签
        self.status_message.emit(f"头模型构建完成 ({result.model_type.value})")

    @Slot(object)
    def _on_forward_ready(self, result):
        info = result.leadfield_info
        self._add_history(f"前向模型: {info['n_sources']} 源 × {info['n_channels']} 通道")
        self._tabs.setTabEnabled(2, True)  # 启用逆向解标签
        self.status_message.emit("前向模型计算完成")

    @Slot(object)
    def _on_inverse_ready(self, result):
        self._add_history(f"逆向解: {result.method}")
        self._tabs.setTabEnabled(3, True)  # 启用偶极子拟合标签
        self._tabs.setTabEnabled(4, True)  # 启用 3D 可视化标签
        self.status_message.emit(f"逆向解计算完成 ({result.method})")

    @Slot(object)
    def _on_dipole_ready(self, result):
        self._add_history(f"偶极子拟合: {len(result.dipoles)} 个")
        self.status_message.emit(f"偶极子拟合完成: {len(result.dipoles)} 个")

    def _add_history(self, desc: str):
        item = QListWidgetItem(f"✓ {desc}")
        self._history_list.addItem(item)

    @Slot()
    def _run_full_pipeline(self):
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return

        reply = QMessageBox.question(
            self, "确认完整流程",
            "将依次执行：\n"
            "1. 构建头模型\n"
            "2. 计算前向模型 (导场矩阵)\n"
            "3. 计算逆向解 (MNE/dSPM/sLORETA/LCMV 等)\n\n"
            "此过程可能需要几分钟，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._btn_full_pipeline.setEnabled(False)
            self._btn_full_pipeline.setText("运行中...")
            # 异步执行
            self._vm.run_full_pipeline()
            self._btn_full_pipeline.setEnabled(True)
            self._btn_full_pipeline.setText("一键完整流程")

    @Slot()
    def _export_scene(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出 3D 场景", "", "HTML 文件 (*.html);;STL 文件 (*.stl)")
        if path:
            self._viz_widget.export_3d_scene(path)
            self.status_message.emit(f"3D 场景已导出: {path}")