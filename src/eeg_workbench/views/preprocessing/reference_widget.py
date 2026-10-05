"""重参考面板：平均参考、乳突参考、Cz、单电极、REST、自定义"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QCheckBox, QLineEdit, QDialog, QDialogButtonBox,
    QAbstractItemView, QMessageBox
)

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.models.preprocessing import ReferenceParams, ReferenceType, REFERENCE_PRESETS
from eeg_workbench.utils.ui import balance_form


class ReferenceWidget(QWidget):
    """重参考参数设置与执行面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: PreprocessingViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 预设选择 ----
        preset_group = QGroupBox("参考预设")
        preset_layout = QHBoxLayout(preset_group)

        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(REFERENCE_PRESETS.keys()))
        self._cmb_preset.setCurrentText("average")
        self._cmb_preset.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(QLabel("预设:"))
        preset_layout.addWidget(self._cmb_preset)

        self._btn_apply_preset = QPushButton("应用预设")
        self._btn_apply_preset.clicked.connect(self._apply_preset)
        preset_layout.addWidget(self._btn_apply_preset)
        preset_layout.addStretch()

        layout.addWidget(preset_group)

        # ---- 参考类型选择 ----
        type_group = QGroupBox("参考类型")
        type_layout = QFormLayout(type_group)

        self._cmb_ref_type = QComboBox()
        self._cmb_ref_type.addItems([rt.value for rt in ReferenceType])
        self._cmb_ref_type.setCurrentText("average")
        self._cmb_ref_type.currentTextChanged.connect(self._on_ref_type_changed)
        type_layout.addRow("类型:", self._cmb_ref_type)
        balance_form(type_layout)

        layout.addWidget(type_group)

        # ---- 动态参数区域 ----
        self._param_stack = QWidget()
        self._param_layout = QVBoxLayout(self._param_stack)
        self._param_layout.setContentsMargins(0, 0, 0, 0)

        # 单电极/自定义参考通道选择器
        self._channel_selector = self._create_channel_selector()
        self._param_layout.addWidget(self._channel_selector)

        # 投影选项
        self._chk_projection = QCheckBox("使用投影算子 (不修改数据，仅标记)")
        self._chk_projection.setChecked(False)
        self._chk_projection.toggled.connect(self._on_param_changed)
        self._param_layout.addWidget(self._chk_projection)

        self._param_layout.addStretch()
        layout.addWidget(self._param_stack, 1)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("执行重参考")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_reference)
        exec_layout.addWidget(self._btn_run)
        layout.addLayout(exec_layout)

        # 初始同步
        self._sync_from_vm()
        self._on_ref_type_changed(self._cmb_ref_type.currentText())

    def _create_channel_selector(self) -> QWidget:
        """创建通道选择器"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 说明标签
        self._lbl_selector_hint = QLabel("请选择参考通道")
        self._lbl_selector_hint.setWordWrap(True)
        self._lbl_selector_hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._lbl_selector_hint)

        # 可用通道列表
        self._lst_available = QListWidget()
        self._lst_available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(QLabel("可用通道:"))
        layout.addWidget(self._lst_available)

        # 已选通道
        self._lst_selected = QListWidget()
        self._lst_selected.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(QLabel("已选参考通道:"))
        layout.addWidget(self._lst_selected)

        # 按钮
        btn_layout = QHBoxLayout()
        self._btn_add = QPushButton("添加 →")
        self._btn_add.clicked.connect(self._add_channels)
        self._btn_remove = QPushButton("← 移除")
        self._btn_remove.clicked.connect(self._remove_channels)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._clear_selected)
        btn_layout.addWidget(self._btn_add)
        btn_layout.addWidget(self._btn_remove)
        btn_layout.addWidget(self._btn_clear)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.available_channels_changed.connect(self._update_channel_list)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._update_channel_list(dataset.ch_names)

    def _update_channel_list(self, channels: list[str]):
        self._lst_available.clear()
        for ch in channels:
            item = QListWidgetItem(ch)
            # 高亮 EEG 通道
            item.setData(Qt.ItemDataRole.UserRole, ch)
            self._lst_available.addItem(item)
        self._lst_selected.clear()

    def _sync_from_vm(self):
        params = self._vm.reference_params
        self._block_signals(True)
        try:
            self._cmb_ref_type.setCurrentText(params.ref_type.value)
            self._chk_projection.setChecked(params.projection)
            self._lst_selected.clear()
            for ch in params.ref_channels:
                self._lst_selected.addItem(ch)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [self._cmb_ref_type, self._chk_projection, self._cmb_preset]:
            w.blockSignals(block)

    @Slot(str)
    def _on_preset_changed(self, preset: str):
        # 预设下拉变化时仅提示说明，实际应用仍由"应用预设"按钮触发
        self.status_message.emit(f"已选择参考预设: {preset}，点击应用后生效")

    @Slot()
    def _apply_preset(self):
        preset = self._cmb_preset.currentText()
        self._vm.apply_reference_preset(preset)
        self._sync_from_vm()
        self.status_message.emit(f"已应用预设: {preset}")

    @Slot(str)
    def _on_ref_type_changed(self, ref_type_str: str):
        ref_type = ReferenceType(ref_type_str)
        params = self._vm.reference_params
        params.ref_type = ref_type

        # 显示/隐藏通道选择器
        show_selector = ref_type in (ReferenceType.SINGLE, ReferenceType.CUSTOM)
        self._channel_selector.setVisible(show_selector)

        # 更新提示文本
        if ref_type == ReferenceType.SINGLE:
            self._lbl_selector_hint.setText("单电极参考：请选择 1 个通道作为参考")
            self._lst_available.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        elif ref_type == ReferenceType.CUSTOM:
            self._lbl_selector_hint.setText("自定义参考：请选择多个通道，将计算其平均作为参考")
            self._lst_available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        else:
            self._lbl_selector_hint.setText(f"{ref_type.value} 参考不需要手动选择通道")
            self._channel_selector.setVisible(False)

        self._on_param_changed()

    @Slot()
    def _add_channels(self):
        for item in self._lst_available.selectedItems():
            ch = item.data(Qt.ItemDataRole.UserRole)
            if not self._find_in_selected(ch):
                self._lst_selected.addItem(ch)

    @Slot()
    def _remove_channels(self):
        for item in self._lst_selected.selectedItems():
            self._lst_selected.takeItem(self._lst_selected.row(item))

    @Slot()
    def _clear_selected(self):
        self._lst_selected.clear()

    def _find_in_selected(self, channel: str) -> bool:
        for i in range(self._lst_selected.count()):
            if self._lst_selected.item(i).text() == channel:
                return True
        return False

    @Slot()
    def _on_param_changed(self):
        params = self._vm.reference_params
        params.ref_type = ReferenceType(self._cmb_ref_type.currentText())
        params.projection = self._chk_projection.isChecked()

        # 收集已选通道
        selected = []
        for i in range(self._lst_selected.count()):
            selected.append(self._lst_selected.item(i).text())
        params.ref_channels = selected

        self._vm.set_reference_params(**self._reference_params_to_dict(params))
        self.params_changed.emit()

    def _reference_params_to_dict(self, params: ReferenceParams) -> dict:
        return {
            "ref_type": params.ref_type,
            "ref_channels": params.ref_channels,
            "projection": params.projection,
        }

    @Slot()
    def _run_reference(self):
        self._vm.run_reference()