"""事件编辑器 Widget：表格编辑、波形标记、导入/导出"""
from __future__ import annotations
from typing import Any, Optional
import numpy as np

from PySide6.QtCore import Signal, Slot, Qt, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QPoint, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableView,
    QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QMenu, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QFormLayout, QCheckBox, QLabel,
    QSplitter, QFrame, QToolBar
)
from PySide6.QtGui import QAction, QColor, QBrush

from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.models.dataset import EEGDataset, Event
from eeg_workbench.services.events import import_vmrk, import_tsv, export_vmrk, export_tsv, EventEditor
from eeg_workbench.utils.ui import balance_form


class EventTableModel(QAbstractTableModel):
    """事件表格数据模型"""

    COLUMNS = ["索引", "起始(s)", "持续(s)", "描述", "值", "样本点", "通道", "置信度"]

    def __init__(self, events: list[Event] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._events = events or []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._events)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        ev = self._events[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(index.row())
            elif col == 1:
                return f"{ev.onset:.6f}"
            elif col == 2:
                return f"{ev.duration:.6f}"
            elif col == 3:
                return ev.description
            elif col == 4:
                return str(ev.value)
            elif col == 5:
                return str(ev.sample) if ev.sample is not None else ""
            elif col == 6:
                return ev.channel
            elif col == 7:
                return f"{ev.confidence:.2f}"
        elif role == Qt.ItemDataRole.EditRole:
            if col == 1:
                return ev.onset
            elif col == 2:
                return ev.duration
            elif col == 3:
                return ev.description
            elif col == 4:
                return ev.value
            elif col == 5:
                return ev.sample
            elif col == 6:
                return ev.channel
            elif col == 7:
                return ev.confidence
        elif role == Qt.ItemDataRole.ForegroundRole:
            # 坏段标红
            if ev.is_bad_segment:
                return QBrush(QColor("#e74c3c"))
            # Cue/Stimulus/Response 不同颜色
            if ev.is_cue:
                return QBrush(QColor("#3498db"))
            if ev.is_stimulus:
                return QBrush(QColor("#27ae60"))
            if ev.is_response:
                return QBrush(QColor("#f39c12"))
        elif role == Qt.ItemDataRole.ToolTipRole:
            return f"Event: {ev.description}\nOnset: {ev.onset:.3f}s\nValue: {ev.value}"
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # 允许编辑除索引外的所有列
        if index.column() == 0:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def setData(self, index: QModelIndex | QPersistentModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        ev = self._events[index.row()]
        col = index.column()
        try:
            if col == 1:
                ev.onset = float(value)
            elif col == 2:
                ev.duration = float(value)
            elif col == 3:
                ev.description = str(value)
            elif col == 4:
                ev.value = int(value)
            elif col == 5:
                ev.sample = int(value) if value else None
            elif col == 6:
                ev.channel = str(value)
            elif col == 7:
                ev.confidence = float(value)
            self.dataChanged.emit(index, index)
            return True
        except (ValueError, TypeError):
            return False

    def set_events(self, events: list[Event]) -> None:
        self.beginResetModel()
        self._events = events
        self.endResetModel()

    def add_event(self, event: Event) -> None:
        self.beginInsertRows(QModelIndex(), len(self._events), len(self._events))
        self._events.append(event)
        self.endInsertRows()

    def remove_event(self, row: int) -> None:
        if 0 <= row < len(self._events):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._events.pop(row)
            self.endRemoveRows()

    def get_event(self, row: int) -> Event | None:
        if 0 <= row < len(self._events):
            return self._events[row]
        return None

    def get_all_events(self) -> list[Event]:
        return self._events


class EventEditorWidget(QWidget):
    """事件编辑面板：表格 + 工具栏 + 导入导出"""

    events_changed = Signal(list)  # list[Event]
    status_message = Signal(str)
    request_waveform_marker = Signal(float, str)  # 请求在波形上标记 (time, desc)

    def __init__(self, viewmodel: DataManagementViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._editor: EventEditor | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 工具栏 ----
        toolbar = QToolBar()
        toolbar.setObjectName("eventEditorToolbar")
        from PySide6.QtCore import QSize
        toolbar.setIconSize(QSize(16, 16))

        self._btn_add = QAction("添加", self)
        self._btn_add.triggered.connect(self._add_event_dialog)
        toolbar.addAction(self._btn_add)

        self._btn_edit = QAction("编辑", self)
        self._btn_edit.triggered.connect(self._edit_selected)
        toolbar.addAction(self._btn_edit)

        self._btn_delete = QAction("删除", self)
        self._btn_delete.triggered.connect(self._delete_selected)
        toolbar.addAction(self._btn_delete)

        toolbar.addSeparator()

        self._btn_import_vmrk = QAction("导入 VMRK", self)
        self._btn_import_vmrk.triggered.connect(self._import_vmrk)
        toolbar.addAction(self._btn_import_vmrk)

        self._btn_import_tsv = QAction("导入 TSV", self)
        self._btn_import_tsv.triggered.connect(self._import_tsv)
        toolbar.addAction(self._btn_import_tsv)

        self._btn_export_vmrk = QAction("导出 VMRK", self)
        self._btn_export_vmrk.triggered.connect(self._export_vmrk)
        toolbar.addAction(self._btn_export_vmrk)

        self._btn_export_tsv = QAction("导出 TSV", self)
        self._btn_export_tsv.triggered.connect(self._export_tsv)
        toolbar.addAction(self._btn_export_tsv)

        toolbar.addSeparator()

        self._btn_auto_bad = QAction("自动检测坏段", self)
        self._btn_auto_bad.triggered.connect(self._auto_detect_bad)
        toolbar.addAction(self._btn_auto_bad)

        self._spin_threshold = QDoubleSpinBox()
        self._spin_threshold.setRange(1, 500)
        self._spin_threshold.setValue(100)
        self._spin_threshold.setSuffix(" µV")
        self._spin_threshold.setToolTip("振幅阈值")
        toolbar.addWidget(self._spin_threshold)

        toolbar.addSeparator()

        self._lbl_count = QLabel("事件: 0")
        toolbar.addWidget(self._lbl_count)

        layout.addWidget(toolbar)

        # ---- 表格视图 ----
        self._model = EventTableModel()
        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._view.setAlternatingRowColors(True)
        self._view.setSortingEnabled(True)
        self._view.horizontalHeader().setStretchLastSection(True)
        self._view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._view.verticalHeader().setVisible(False)
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._view)

        # ---- 底部快速添加栏 ----
        quick_group = QGroupBox("快速添加事件")
        quick_layout = QHBoxLayout(quick_group)

        quick_layout.addWidget(QLabel("时间:"))
        self._quick_time = QDoubleSpinBox()
        self._quick_time.setRange(0, 86400)
        self._quick_time.setDecimals(3)
        self._quick_time.setSingleStep(0.1)
        quick_layout.addWidget(self._quick_time)

        quick_layout.addWidget(QLabel("类型:"))
        self._quick_type = QComboBox()
        self._quick_type.addItems(["Cue", "Stimulus", "Response", "自定义"])
        quick_layout.addWidget(self._quick_type)

        quick_layout.addWidget(QLabel("描述:"))
        self._quick_desc = QLineEdit()
        self._quick_desc.setPlaceholderText("如: Target, Left, Correct")
        quick_layout.addWidget(self._quick_desc, 1)

        quick_layout.addWidget(QLabel("值:"))
        self._quick_value = QSpinBox()
        self._quick_value.setRange(-32768, 32767)
        quick_layout.addWidget(self._quick_value)

        self._btn_quick_add = QPushButton("添加到表格")
        self._btn_quick_add.clicked.connect(self._quick_add_event)
        quick_layout.addWidget(self._btn_quick_add)

        layout.addWidget(quick_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self) -> None:
        self._vm.event_editor_ready.connect(self._on_editor_ready)
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    @Slot(object)
    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        self.setEnabled(dataset is not None)
        if dataset:
            self._editor = self._vm.get_event_editor()
            self._refresh_table()
        else:
            self._model.set_events([])
            self._lbl_count.setText("事件: 0")

    @Slot(object)
    def _on_editor_ready(self, editor: EventEditor | None) -> None:
        self._editor = editor
        self._refresh_table()

    def _refresh_table(self) -> None:
        if self._editor:
            self._model.set_events(self._editor.events)
            self._lbl_count.setText(f"事件: {len(self._editor.events)}")

    # ---- 表格交互 ----
    @Slot(QModelIndex)
    def _on_double_clicked(self, index: QModelIndex) -> None:
        self._edit_selected()

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self._view.indexAt(pos)
        menu = QMenu(self)
        if index.isValid():
            act_edit = QAction("编辑", self)
            act_edit.triggered.connect(self._edit_selected)
            act_delete = QAction("删除", self)
            act_delete.triggered.connect(self._delete_selected)
            act_mark = QAction("在波形标记", self)
            act_mark.triggered.connect(lambda: self._mark_on_waveform(index.row()))
            menu.addAction(act_edit)
            menu.addAction(act_delete)
            menu.addSeparator()
            menu.addAction(act_mark)
        else:
            act_add = QAction("添加事件", self)
            act_add.triggered.connect(self._add_event_dialog)
            menu.addAction(act_add)
        menu.exec(self._view.viewport().mapToGlobal(pos))

    def _add_event_dialog(self) -> None:
        dlg = EventEditDialog(self, dataset=self._vm.dataset)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ev = dlg.get_event()
            if self._editor:
                self._vm._dataset = self._editor.add_event(ev)
                self._vm.dataset_changed.emit(self._vm._dataset)
                self.status_message.emit(f"已添加事件: {ev.description} @ {ev.onset:.3f}s")

    def _edit_selected(self) -> None:
        rows = self._view.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        ev = self._model.get_event(row)
        dlg = EventEditDialog(self, event=ev, dataset=self._vm.dataset)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_ev = dlg.get_event()
            if self._editor:
                self._vm._dataset = self._editor.update_event(row, new_ev)
                self._vm.dataset_changed.emit(self._vm._dataset)
                self.status_message.emit(f"已更新事件: {new_ev.description}")

    def _delete_selected(self) -> None:
        rows = sorted([r.row() for r in self._view.selectionModel().selectedRows()], reverse=True)
        if not rows:
            return
        if self._editor:
            for row in rows:
                self._vm._dataset = self._editor.remove_event(row)
            self._vm.dataset_changed.emit(self._vm._dataset)
            self.status_message.emit(f"已删除 {len(rows)} 个事件")

    def _mark_on_waveform(self, row: int) -> None:
        ev = self._model.get_event(row)
        if ev:
            self.request_waveform_marker.emit(ev.onset, ev.description)

    # ---- 导入导出 ----
    def _import_vmrk(self) -> None:
        if not self._vm.dataset:
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 VMRK", "", "VMRK 文件 (*.vmrk);;所有文件 (*.*)")
        if path:
            if self._vm.import_events_vmrk(path):
                self._refresh_table()
                self.status_message.emit(f"已导入 VMRK: {path}")

    def _import_tsv(self) -> None:
        if not self._vm.dataset:
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 TSV", "", "TSV 文件 (*.tsv);;所有文件 (*.*)")
        if path:
            if self._vm.import_events_tsv(path):
                self._refresh_table()
                self.status_message.emit(f"已导入 TSV: {path}")

    def _export_vmrk(self) -> None:
        if not self._vm.dataset:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 VMRK", "", "VMRK 文件 (*.vmrk)")
        if path:
            if self._vm.export_events_vmrk(path):
                self.status_message.emit(f"已导出 VMRK: {path}")

    def _export_tsv(self) -> None:
        if not self._vm.dataset:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 TSV", "", "TSV 文件 (*.tsv)")
        if path:
            if self._vm.export_events_tsv(path):
                self.status_message.emit(f"已导出 TSV: {path}")

    # ---- 自动检测 ----
    def _auto_detect_bad(self) -> None:
        if not self._editor:
            return
        threshold = self._spin_threshold.value()
        count = self._vm.auto_detect_bad_segments(threshold_uv=threshold)
        self._refresh_table()
        self.status_message.emit(f"自动检测到 {count} 个坏段 (阈值 {threshold} µV)")

    # ---- 快速添加 ----
    def _quick_add_event(self) -> None:
        if not self._editor or not self._vm.dataset:
            return
        onset = self._quick_time.value()
        ev_type = self._quick_type.currentText()
        desc = self._quick_desc.text().strip() or ev_type
        value = self._quick_value.value()

        # 根据类型生成标准描述
        if ev_type != "自定义":
            full_desc = f"{ev_type}/{desc}"
        else:
            full_desc = desc

        ev = Event(onset=onset, duration=0, description=full_desc, value=value)
        self._vm._dataset = self._editor.add_event(ev)
        self._vm.dataset_changed.emit(self._vm._dataset)
        self.status_message.emit(f"已快速添加: {full_desc} @ {onset:.3f}s")


class EventEditDialog(QDialog):
    """事件编辑对话框"""

    def __init__(self, parent: QWidget | None = None, event: Event | None = None, dataset: EEGDataset | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑事件" if event else "新建事件")
        self.setModal(True)
        self.resize(350, 300)
        self._event = event
        self._dataset = dataset
        self._setup_ui()
        if event:
            self._load_event(event)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._spin_onset = QDoubleSpinBox()
        self._spin_onset.setRange(0, 86400)
        self._spin_onset.setDecimals(6)
        self._spin_onset.setSingleStep(0.01)
        form.addRow("起始时间 (s):", self._spin_onset)

        self._spin_duration = QDoubleSpinBox()
        self._spin_duration.setRange(0, 86400)
        self._spin_duration.setDecimals(6)
        self._spin_duration.setSingleStep(0.01)
        form.addRow("持续时间 (s):", self._spin_duration)

        self._cmb_type = QComboBox()
        self._cmb_type.addItems(["Cue", "Stimulus", "Response", "BAD_segment", "自定义"])
        self._cmb_type.currentTextChanged.connect(self._on_type_changed)
        form.addRow("事件类型:", self._cmb_type)

        self._edit_desc = QLineEdit()
        self._edit_desc.setPlaceholderText("如: Target, Left, Correct")
        form.addRow("描述:", self._edit_desc)

        self._spin_value = QSpinBox()
        self._spin_value.setRange(-32768, 32767)
        form.addRow("数值:", self._spin_value)

        self._spin_sample = QSpinBox()
        self._spin_sample.setRange(-1, 2_000_000_000)
        self._spin_sample.setSpecialValueText("自动计算")
        form.addRow("样本点:", self._spin_sample)

        self._edit_channel = QLineEdit()
        self._edit_channel.setPlaceholderText("关联通道 (可选)")
        form.addRow("通道:", self._edit_channel)

        self._spin_confidence = QDoubleSpinBox()
        self._spin_confidence.setRange(0, 1)
        self._spin_confidence.setDecimals(2)
        self._spin_confidence.setSingleStep(0.1)
        self._spin_confidence.setValue(1.0)
        form.addRow("置信度:", self._spin_confidence)
        balance_form(form)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, text: str) -> None:
        if text != "自定义" and not self._edit_desc.text():
            self._edit_desc.setText(text)

    def _load_event(self, ev: Event) -> None:
        self._spin_onset.setValue(ev.onset)
        self._spin_duration.setValue(ev.duration)
        # 推断类型
        if ev.is_cue:
            self._cmb_type.setCurrentText("Cue")
        elif ev.is_stimulus:
            self._cmb_type.setCurrentText("Stimulus")
        elif ev.is_response:
            self._cmb_type.setCurrentText("Response")
        elif ev.is_bad_segment:
            self._cmb_type.setCurrentText("BAD_segment")
        else:
            self._cmb_type.setCurrentText("自定义")
        self._edit_desc.setText(ev.description)
        self._spin_value.setValue(ev.value)
        self._spin_sample.setValue(ev.sample if ev.sample is not None else -1)
        self._edit_channel.setText(ev.channel)
        self._spin_confidence.setValue(ev.confidence)

    def get_event(self) -> Event:
        sample = self._spin_sample.value()
        return Event(
            onset=self._spin_onset.value(),
            duration=self._spin_duration.value(),
            description=self._edit_desc.text().strip() or self._cmb_type.currentText(),
            value=self._spin_value.value(),
            sample=sample if sample >= 0 else None,
            channel=self._edit_channel.text().strip(),
            confidence=self._spin_confidence.value(),
        )