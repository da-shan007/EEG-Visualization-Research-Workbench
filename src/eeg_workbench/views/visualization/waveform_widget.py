"""波形图面板"""
from __future__ import annotations
from typing import Literal, Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QListWidget, QListWidgetItem, QAbstractItemView,
    QMessageBox, QFileDialog
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.dataset import EEGDataset, Event
from eeg_workbench.models.visualization import WaveformPlotConfig, PlotType, WaveformPicks
from eeg_workbench.utils.ui import balance_form


class WaveformWidget(QWidget):
    """波形图面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: VisualizationViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 通道选择 ----
        ch_group = QGroupBox("通道选择")
        ch_layout = QVBoxLayout(ch_group)

        self._cmb_picks = QComboBox()
        self._cmb_picks.addItems(["所有通道", "仅 EEG", "仅 EOG", "仅 ECG", "自定义"])
        self._cmb_picks.currentTextChanged.connect(self._on_picks_changed)
        ch_layout.addWidget(QLabel("通道范围:"))
        ch_layout.addWidget(self._cmb_picks)

        self._lst_channels = QListWidget()
        self._lst_channels.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_channels.setMaximumHeight(150)
        ch_layout.addWidget(QLabel("可用通道:"))
        ch_layout.addWidget(self._lst_channels)

        btn_layout = QHBoxLayout()
        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.clicked.connect(lambda: self._lst_channels.selectAll())
        self._btn_clear_sel = QPushButton("取消选择")
        self._btn_clear_sel.clicked.connect(lambda: self._lst_channels.clearSelection())
        self._btn_invert_sel = QPushButton("反选")
        self._btn_invert_sel.clicked.connect(self._invert_selection)
        btn_layout.addWidget(self._btn_select_all)
        btn_layout.addWidget(self._btn_clear_sel)
        btn_layout.addWidget(self._btn_invert_sel)
        btn_layout.addStretch()
        ch_layout.addLayout(btn_layout)

        layout.addWidget(ch_group)

        # ---- 时间范围 ----
        time_group = QGroupBox("时间范围")
        time_layout = QFormLayout(time_group)

        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-100, 1000)
        self._spin_tmin.setDecimals(3)
        self._spin_tmin.setSingleStep(0.1)
        self._spin_tmin.setSuffix(" s")
        self._spin_tmin.setSpecialValueText("自动 (从头)")
        time_layout.addRow("开始时间:", self._spin_tmin)

        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-100, 1000)
        self._spin_tmax.setDecimals(3)
        self._spin_tmax.setSingleStep(0.1)
        self._spin_tmax.setSuffix(" s")
        self._spin_tmax.setSpecialValueText("自动 (到尾)")
        time_layout.addRow("结束时间:", self._spin_tmax)
        balance_form(time_layout)

        layout.addWidget(time_group)

        # ---- 显示选项 ----
        display_group = QGroupBox("显示选项")
        display_layout = QFormLayout(display_group)

        self._spin_n_per_plot = QSpinBox()
        self._spin_n_per_plot.setRange(1, 64)
        self._spin_n_per_plot.setValue(20)
        display_layout.addRow("每图通道数:", self._spin_n_per_plot)

        self._spin_offset = QDoubleSpinBox()
        self._spin_offset.setRange(0.1, 10)
        self._spin_offset.setDecimals(1)
        self._spin_offset.setSingleStep(0.1)
        self._spin_offset.setValue(1.0)
        display_layout.addRow("通道偏移:", self._spin_offset)

        self._spin_line_width = QDoubleSpinBox()
        self._spin_line_width.setRange(0.1, 5)
        self._spin_line_width.setDecimals(1)
        self._spin_line_width.setSingleStep(0.1)
        self._spin_line_width.setValue(0.8)
        display_layout.addRow("线宽:", self._spin_line_width)

        self._cmb_unit = QComboBox()
        self._cmb_unit.addItems(["µV", "mV", "V"])
        display_layout.addRow("单位:", self._cmb_unit)

        self._chk_grid = QCheckBox("显示网格")
        self._chk_grid.setChecked(True)
        display_layout.addRow("", self._chk_grid)

        self._chk_events = QCheckBox("显示事件标记")
        self._chk_events.setChecked(True)
        display_layout.addRow("", self._chk_events)

        self._chk_channel_names = QCheckBox("显示通道名")
        self._chk_channel_names.setChecked(True)
        display_layout.addRow("", self._chk_channel_names)
        balance_form(display_layout)

        layout.addWidget(display_group)

        # ---- 事件过滤 ----
        event_group = QGroupBox("事件标记过滤")
        event_layout = QVBoxLayout(event_group)

        self._lst_events = QListWidget()
        self._lst_events.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_events.setMaximumHeight(100)
        event_layout.addWidget(QLabel("显示的事件类型:"))
        event_layout.addWidget(self._lst_events)

        layout.addWidget(event_group)

        # ---- 导出/绘制 ----
        exec_layout = QHBoxLayout()
        self._btn_plot = QPushButton("绘制波形")
        self._btn_plot.setMinimumHeight(40)
        self._btn_plot.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_plot.clicked.connect(self._plot_waveform)
        exec_layout.addWidget(self._btn_plot)

        self._btn_export = QPushButton("导出图形")
        self._btn_export.clicked.connect(self._export_figure)
        exec_layout.addWidget(self._btn_export)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._update_channel_list(dataset.ch_names)
            self._update_event_list(dataset.events)
            self._spin_tmax.setValue(dataset.duration)

    def _update_channel_list(self, channels: list[str]) -> None:
        self._lst_channels.clear()
        for ch in channels:
            self._lst_channels.addItem(ch)

    def _update_event_list(self, events: list[Event] | None) -> None:
        self._lst_events.clear()
        # 获取唯一的事件描述
        descs = set()
        for ev in events or []:
            descs.add(ev.description)
        for desc in sorted(descs):
            self._lst_events.addItem(desc)
        # 默认全选
        for i in range(self._lst_events.count()):
            self._lst_events.item(i).setSelected(True)

    def _invert_selection(self) -> None:
        for i in range(self._lst_channels.count()):
            item = self._lst_channels.item(i)
            item.setSelected(not item.isSelected())

    @Slot()
    def _on_picks_changed(self, text: str) -> None:
        self._on_param_changed()

    def _collect_config(self) -> WaveformPlotConfig:
        """从界面控件收集波形图配置"""
        # 通道范围
        picks_text = self._cmb_picks.currentText()
        pick_map: dict[str, Literal["all", "eeg", "eog", "ecg"]] = {
            "所有通道": "all", "仅 EEG": "eeg",
            "仅 EOG": "eog", "仅 ECG": "ecg",
        }
        picks: WaveformPicks
        if picks_text in pick_map:
            picks = pick_map[picks_text]
        else:
            # 自定义：使用列表中选中的通道
            selected = [
                item.text() for item in self._lst_channels.selectedItems()
            ]
            picks = selected if selected else "all"

        # 时间范围（-100 为"自动"特殊值）
        tmin_v = self._spin_tmin.value()
        tmax_v = self._spin_tmax.value()
        tmin = None if tmin_v <= -99.0 else tmin_v
        tmax = None if tmax_v <= -99.0 else tmax_v

        return WaveformPlotConfig(
            tmin=tmin,
            tmax=tmax,
            picks=picks,
            n_channels_per_plot=self._spin_n_per_plot.value(),
            line_width=self._spin_line_width.value(),
            offset_step=self._spin_offset.value(),
            unit=self._cmb_unit.currentText(),
            show_grid=self._chk_grid.isChecked(),
            show_events=self._chk_events.isChecked(),
            show_channel_names=self._chk_channel_names.isChecked(),
        )

    @Slot()
    def _on_param_changed(self) -> None:
        cfg = self._collect_config()
        self._vm.set_waveform_config(**cfg.__dict__)
        self.params_changed.emit()

    @Slot()
    def _plot_waveform(self) -> None:
        if self._vm.dataset is None:
            self.status_message.emit("请先加载数据集")
            return
        try:
            self._on_param_changed()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "参数错误", str(e))
            return
        self.status_message.emit("正在绘制波形...")
        self._vm.plot_waveform()

    @Slot()
    def _export_figure(self) -> None:
        if self._vm.dataset is None:
            self.status_message.emit("请先加载数据集")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出波形图", "",
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;EPS (*.eps);;HTML (*.html)"
        )
        if not path:
            return
        self._vm.export_figure(path=path)