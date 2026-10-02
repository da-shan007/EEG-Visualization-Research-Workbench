"""预处理主面板：整合滤波、重参考、重采样、ICA、插值"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QSplitter,
    QGroupBox, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar
)

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.views.preprocessing import (
    FilterWidget, ReferenceWidget, ResampleWidget, ICAWidget, InterpolationWidget
)
from eeg_workbench.models.dataset import EEGDataset


class PreprocessingMainWidget(QWidget):
    """预处理模块主面板：标签页式集成所有预处理功能"""

    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: PreprocessingViewModel, parent: Optional[QWidget] = None):
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

        self._btn_standard_pipeline = QPushButton("标准流程")
        self._btn_standard_pipeline.setToolTip("一键运行：滤波 → 平均参考 → ICA → 坏道插值")
        self._btn_standard_pipeline.clicked.connect(self._run_standard_pipeline)
        info_layout.addWidget(self._btn_standard_pipeline)

        self._btn_reset = QPushButton("重置数据")
        self._btn_reset.setToolTip("恢复到原始数据")
        self._btn_reset.clicked.connect(self._reset_dataset)
        info_layout.addWidget(self._btn_reset)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        # 创建各子面板
        self._filter_widget = FilterWidget(self._vm)
        self._reference_widget = ReferenceWidget(self._vm)
        self._resample_widget = ResampleWidget(self._vm)
        self._ica_widget = ICAWidget(self._vm)
        self._interp_widget = InterpolationWidget(self._vm)

        self._tabs.addTab(self._filter_widget, "滤波")
        self._tabs.addTab(self._reference_widget, "重参考")
        self._tabs.addTab(self._resample_widget, "重采样")
        self._tabs.addTab(self._ica_widget, "ICA")
        self._tabs.addTab(self._interp_widget, "坏道插值")

        layout.addWidget(self._tabs, 1)

        # ---- 底部流程历史 ----
        history_group = QGroupBox("预处理历史")
        history_layout = QVBoxLayout(history_group)

        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(120)
        history_layout.addWidget(self._history_list)

        history_btn_layout = QHBoxLayout()
        self._btn_undo = QPushButton("撤销最后一步")
        self._btn_undo.clicked.connect(self._undo_last)
        self._btn_export = QPushButton("导出流程")
        self._btn_export.clicked.connect(self._export_pipeline)
        self._btn_import = QPushButton("导入流程")
        self._btn_import.clicked.connect(self._import_pipeline)
        history_btn_layout.addWidget(self._btn_undo)
        history_btn_layout.addStretch()
        history_btn_layout.addWidget(self._btn_export)
        history_btn_layout.addWidget(self._btn_import)
        history_layout.addLayout(history_btn_layout)

        layout.addWidget(history_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self):
        # ViewModel 信号
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.preprocessing_steps_changed.connect(self._update_history)
        self._vm.status_message.connect(self.status_message.emit)

        # 子面板信号
        self._filter_widget.status_message.connect(self.status_message.emit)
        self._reference_widget.status_message.connect(self.status_message.emit)
        self._resample_widget.status_message.connect(self.status_message.emit)
        self._ica_widget.status_message.connect(self.status_message.emit)
        self._interp_widget.status_message.connect(self.status_message.emit)

    @Slot(object)
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]):
        self._dataset = dataset
        enabled = dataset is not None
        self.setEnabled(enabled)

        if dataset:
            self._lbl_dataset_name.setText(dataset.name)
            self._lbl_info.setText(
                f"通道: {dataset.n_channels} | 采样率: {dataset.sfreq:.1f} Hz | 时长: {dataset.duration:.2f} s | "
                f"坏道: {len(dataset.bad_channels)}"
            )
        else:
            self._lbl_dataset_name.setText("未加载数据")
            self._lbl_info.setText("通道: -- | 采样率: -- Hz | 时长: -- s")

        # 向下传播
        self.dataset_changed.emit(dataset)

    @Slot(list)
    def _update_history(self, steps: list):
        self._history_list.clear()
        for step in steps:
            status = "✓" if step.applied else "○"
            item = QListWidgetItem(f"{status} {step.name}: {step.description}")
            item.setToolTip(str(step.params))
            self._history_list.addItem(item)

    @Slot()
    def _run_standard_pipeline(self):
        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return

        reply = QMessageBox.question(
            self, "确认标准流程",
            "将执行标准预处理流程：\n"
            "1. 滤波 (0.1-40Hz + 50Hz陷波)\n"
            "2. 平均参考\n"
            "3. ICA 拟合与自动伪影去除\n"
            "4. 坏道插值 (如有坏道)\n\n"
            "此操作会修改当前数据，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._btn_standard_pipeline.setEnabled(False)
            self._btn_standard_pipeline.setText("运行中...")
            # 异步执行
            result = self._vm.run_standard_pipeline()
            self._btn_standard_pipeline.setEnabled(True)
            self._btn_standard_pipeline.setText("标准流程")

    @Slot()
    def _reset_dataset(self):
        if not self._dataset:
            return
        reply = QMessageBox.question(
            self, "重置确认",
            "将恢复到原始加载的数据，所有预处理步骤将丢失。\n确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 这里需要数据管理模块支持重置
            self.status_message.emit("重置功能需要数据管理模块支持")

    @Slot()
    def _undo_last(self):
        if self._vm.undo_last_step():
            self.status_message.emit("已撤销最后一步")
        else:
            self.status_message.emit("无法撤销")

    @Slot()
    def _export_pipeline(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出预处理流程", "", "JSON 文件 (*.json)")
        if path:
            self._vm.export_pipeline(path)

    @Slot()
    def _import_pipeline(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "导入预处理流程", "", "JSON 文件 (*.json)")
        if path:
            self._vm.import_pipeline(path)