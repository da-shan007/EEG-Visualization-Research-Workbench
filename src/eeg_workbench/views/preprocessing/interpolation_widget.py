"""坏道插值面板：通道选择、插值方法、执行"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QCheckBox, QAbstractItemView, QMessageBox
)

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.preprocessing import BadChannelInterpolationParams, InterpolationMethod
from eeg_workbench.utils.ui import balance_form


class InterpolationWidget(QWidget):
    """坏道插值面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: PreprocessingViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 坏道列表 ----
        bad_group = QGroupBox("坏道管理")
        bad_layout = QVBoxLayout(bad_group)

        # 当前坏道显示
        self._lbl_bad_count = QLabel("当前坏道: 0 个")
        self._lbl_bad_count.setStyleSheet("font-weight: bold;")
        bad_layout.addWidget(self._lbl_bad_count)

        # 可用通道选择
        bad_layout.addWidget(QLabel("标记坏道:"))
        self._lst_available = QListWidget()
        self._lst_available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_available.setMaximumHeight(150)
        bad_layout.addWidget(self._lst_available)

        # 按钮
        btn_layout = QHBoxLayout()
        self._btn_mark_bad = QPushButton("标记为坏道 →")
        self._btn_mark_bad.clicked.connect(self._mark_bad)
        self._btn_unmark_bad = QPushButton("← 取消坏道")
        self._btn_unmark_bad.clicked.connect(self._unmark_bad)
        self._btn_auto_detect = QPushButton("自动检测坏道")
        self._btn_auto_detect.clicked.connect(self._auto_detect_bad)
        btn_layout.addWidget(self._btn_mark_bad)
        btn_layout.addWidget(self._btn_unmark_bad)
        btn_layout.addWidget(self._btn_auto_detect)
        btn_layout.addStretch()
        bad_layout.addLayout(btn_layout)

        layout.addWidget(bad_group)

        # ---- 插值设置 ----
        interp_group = QGroupBox("插值设置")
        interp_layout = QFormLayout(interp_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems([m.value for m in InterpolationMethod])
        self._cmb_method.setCurrentText("spherical")
        self._cmb_method.currentTextChanged.connect(self._on_param_changed)
        interp_layout.addRow("插值方法:", self._cmb_method)

        # 待插值通道选择
        interp_layout.addWidget(QLabel("待插值通道:"))
        self._lst_interp = QListWidget()
        self._lst_interp.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_interp.setMaximumHeight(120)
        interp_layout.addRow("", self._lst_interp)

        interp_btn_layout = QHBoxLayout()
        self._btn_use_bad = QPushButton("使用所有坏道")
        self._btn_use_bad.clicked.connect(self._use_all_bad)
        self._btn_clear_interp = QPushButton("清空")
        self._btn_clear_interp.clicked.connect(self._clear_interp)
        interp_btn_layout.addWidget(self._btn_use_bad)
        interp_btn_layout.addWidget(self._btn_clear_interp)
        interp_btn_layout.addStretch()
        interp_layout.addRow("", interp_btn_layout)

        self._chk_reset_bads = QCheckBox("插值后重置坏道标记")
        self._chk_reset_bads.setChecked(True)
        self._chk_reset_bads.toggled.connect(self._on_param_changed)
        interp_layout.addRow("", self._chk_reset_bads)
        balance_form(interp_layout)

        layout.addWidget(interp_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("执行插值")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_interpolation)
        exec_layout.addWidget(self._btn_run)
        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.available_channels_changed.connect(self._update_channel_lists)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._update_channel_lists(dataset.ch_names)
            self._update_bad_count()

    def _update_channel_lists(self, channels: list[str]) -> None:
        # 更新可用通道列表
        current_available = set()
        for i in range(self._lst_available.count()):
            current_available.add(self._lst_available.item(i).text())

        for ch in channels:
            if ch not in current_available:
                self._lst_available.addItem(ch)

        # 更新待插值列表
        self._lst_interp.clear()

    def _update_bad_count(self) -> None:
        if self._vm.dataset:
            bad = self._vm.dataset.bad_channels
            self._lbl_bad_count.setText(f"当前坏道: {len(bad)} 个")
            if bad:
                self._lbl_bad_count.setStyleSheet("font-weight: bold; color: #e74c3c;")
            else:
                self._lbl_bad_count.setStyleSheet("font-weight: bold; color: #27ae60;")

    def _sync_from_vm(self) -> None:
        params = self._vm.interpolation_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method.value)
            self._chk_reset_bads.setChecked(params.reset_bads)
            self._lst_interp.clear()
            for ch in params.bad_channels:
                self._lst_interp.addItem(ch)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [self._cmb_method, self._chk_reset_bads]:
            w.blockSignals(block)

    @Slot()
    def _mark_bad(self) -> None:
        if not self._vm.dataset:
            return
        for item in self._lst_available.selectedItems():
            ch = item.text()
            if ch not in self._vm.dataset.bad_channels:
                self._vm.dataset.set_bad_channels(self._vm.dataset.bad_channels + [ch])
        self._update_bad_count()
        self._vm.dataset_changed.emit(self._vm.dataset)

    @Slot()
    def _unmark_bad(self) -> None:
        if not self._vm.dataset:
            return
        for item in self._lst_available.selectedItems():
            ch = item.text()
            if ch in self._vm.dataset.bad_channels:
                new_bad = [b for b in self._vm.dataset.bad_channels if b != ch]
                self._vm.dataset.set_bad_channels(new_bad)
        self._update_bad_count()
        self._vm.dataset_changed.emit(self._vm.dataset)

    @Slot()
    def _auto_detect_bad(self) -> None:
        if not self._vm.dataset:
            return
        # 使用数据管理模块的自动检测
        count = self._vm._data_vm.auto_detect_bad_segments(threshold_uv=100.0)
        self._update_bad_count()
        self.status_message.emit(f"自动检测到 {count} 个坏段")

    @Slot()
    def _use_all_bad(self) -> None:
        if not self._vm.dataset:
            return
        self._lst_interp.clear()
        for ch in self._vm.dataset.bad_channels:
            self._lst_interp.addItem(ch)

    @Slot()
    def _clear_interp(self) -> None:
        self._lst_interp.clear()

    @Slot()
    def _on_param_changed(self) -> None:
        params = BadChannelInterpolationParams(
            method=InterpolationMethod(self._cmb_method.currentText()),
            bad_channels=[self._lst_interp.item(i).text() for i in range(self._lst_interp.count())],
            reset_bads=self._chk_reset_bads.isChecked(),
        )
        self._vm.set_interpolation_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_interpolation(self) -> None:
        if not self._vm.dataset:
            return
        if self._lst_interp.count() == 0:
            QMessageBox.warning(self, "参数错误", "请先选择待插值的通道")
            return
        self._vm.run_interpolation()