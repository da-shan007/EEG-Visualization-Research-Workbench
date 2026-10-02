"""ERP 峰值检测与结果显示面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDoubleSpinBox, QLabel, QHeaderView, QAbstractItemView,
    QSplitter, QTabWidget, QMessageBox, QFrame
)

from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.models.erp import ERPComponent, PeakResult


class ERPPeakWidget(QWidget):
    """ERP 峰值检测与结果显示面板"""

    status_message = Signal(str)

    def __init__(self, viewmodel: ERPViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._peak_results: dict = {}
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()

        self._btn_detect = QPushButton("自动检测峰值")
        self._btn_detect.setMinimumHeight(36)
        self._btn_detect.clicked.connect(self._run_detection)
        toolbar.addWidget(self._btn_detect)

        self._btn_custom = QPushButton("自定义检测")
        self._btn_custom.clicked.connect(self._custom_detection)
        toolbar.addWidget(self._btn_custom)

        # 垂直分隔线
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar.addWidget(_sep)

        self._cmb_condition = QComboBox()
        self._cmb_condition.setMinimumWidth(150)
        toolbar.addWidget(QLabel("条件:"))
        toolbar.addWidget(self._cmb_condition)

        toolbar.addStretch()

        self._lbl_status = QLabel("未检测")
        self._lbl_status.setStyleSheet("color: #666;")
        toolbar.addWidget(self._lbl_status)

        layout.addLayout(toolbar)

        # ---- 主分割器 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：峰值结果表格
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._peak_table = QTableWidget(0, 6)
        self._peak_table.setHorizontalHeaderLabels([
            "条件", "成分", "潜伏期(ms)", "幅度(µV)", "通道", "极性"
        ])
        self._peak_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._peak_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._peak_table.setAlternatingRowColors(True)
        left_layout.addWidget(self._peak_table)

        # 快速操作
        peak_btn = QHBoxLayout()
        self._btn_plot_topo = QPushButton("绘制该峰值地形图")
        self._btn_plot_topo.clicked.connect(self._plot_selected_topomap)
        self._btn_plot_joint = QPushButton("绘制联合图")
        self._btn_plot_joint.clicked.connect(self._plot_joint)
        peak_btn.addWidget(self._btn_plot_topo)
        peak_btn.addWidget(self._btn_plot_joint)
        peak_btn.addStretch()
        left_layout.addLayout(peak_btn)

        splitter.addWidget(left_widget)

        # 右侧：详细信息与自定义检测
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 自定义检测
        custom_group = QGroupBox("自定义峰值检测")
        custom_layout = QFormLayout(custom_group)

        self._custom_time_min = QDoubleSpinBox()
        self._custom_time_min.setRange(0, 2)
        self._custom_time_min.setDecimals(3)
        self._custom_time_min.setValue(0.2)
        self._custom_time_min.setSuffix(" s")

        self._custom_time_max = QDoubleSpinBox()
        self._custom_time_max.setRange(0, 2)
        self._custom_time_max.setDecimals(3)
        self._custom_time_max.setValue(0.5)
        self._custom_time_max.setSuffix(" s")

        time_row = QHBoxLayout()
        time_row.addWidget(self._custom_time_min)
        time_row.addWidget(QLabel("到"))
        time_row.addWidget(self._custom_time_max)
        custom_layout.addRow("时间窗:", time_row)

        self._cmb_custom_polarity = QComboBox()
        self._cmb_custom_polarity.addItems(["both", "pos", "neg"])
        custom_layout.addRow("极性:", self._cmb_custom_polarity)

        self._btn_custom_detect = QPushButton("检测")
        self._btn_custom_detect.clicked.connect(self._run_custom_detection)
        custom_layout.addRow("", self._btn_custom_detect)

        right_layout.addWidget(custom_group)

        # 峰值详情
        detail_group = QGroupBox("峰值详情")
        detail_layout = QVBoxLayout(detail_group)
        self._lbl_detail = QLabel("选择表格行查看详情")
        self._lbl_detail.setWordWrap(True)
        self._lbl_detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self._lbl_detail)
        right_layout.addWidget(detail_group)

        # 可视化按钮
        vis_group = QGroupBox("可视化")
        vis_layout = QVBoxLayout(vis_group)

        self._btn_topo_times = QPushButton("批量绘制峰值时刻地形图")
        self._btn_topo_times.clicked.connect(self._plot_all_topomaps)
        vis_layout.addWidget(self._btn_topo_times)

        self._btn_joint = QPushButton("绘制联合图 (波形+地形图)")
        self._btn_joint.clicked.connect(self._plot_joint)
        vis_layout.addWidget(self._btn_joint)

        right_layout.addWidget(vis_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 400])
        layout.addWidget(splitter, 1)

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.peaks_detected.connect(self._on_peaks_detected)
        self._vm.erp_result.connect(self._on_erp_result)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._update_condition_combo()

    def _on_erp_result(self, result):
        self._update_condition_combo()

    def _update_condition_combo(self):
        self._cmb_condition.clear()
        if self._vm._erp_result:
            for cond in self._vm._erp_result.result.evokeds.keys():
                self._cmb_condition.addItem(cond)

    @Slot()
    def _run_detection(self):
        self._vm.run_peak_detection()

    @Slot(dict)
    def _on_peaks_detected(self, peaks: dict):
        """更新峰值表格"""
        self._peak_table.setRowCount(0)
        row = 0
        for cond_name, cond_peaks in peaks.items():
            for comp_str, peak_data in cond_peaks.items():
                self._peak_table.insertRow(row)
                self._peak_table.setItem(row, 0, QTableWidgetItem(cond_name))
                self._peak_table.setItem(row, 1, QTableWidgetItem(comp_str))
                self._peak_table.setItem(row, 2, QTableWidgetItem(f"{peak_data['latency']*1000:.1f}"))
                self._peak_table.setItem(row, 3, QTableWidgetItem(f"{peak_data['amplitude']:.2f}"))
                self._peak_table.setItem(row, 4, QTableWidgetItem(peak_data['channel']))
                self._peak_table.setItem(row, 5, QTableWidgetItem(peak_data['polarity']))
                row += 1

        self._lbl_status.setText(f"检测完成: {row} 个峰值")
        self._lbl_status.setStyleSheet("color: #27ae60; font-weight: bold;")

    @Slot()
    def _custom_detection(self):
        # 打开自定义对话框
        self._run_custom_detection()

    @Slot()
    def _run_custom_detection(self):
        cond = self._cmb_condition.currentText()
        if not cond:
            return
        tmin = self._custom_time_min.value()
        tmax = self._custom_time_max.value()
        polarity = self._cmb_custom_polarity.currentText()
        
        result = self._vm.run_custom_peak_detection(cond, (tmin, tmax), polarity)
        if result:
            self.status_message.emit(f"自定义检测: {result.component.value} @ {result.latency*1000:.1f}ms")

    @Slot()
    def _plot_selected_topomap(self):
        rows = self._peak_table.selectionModel().selectedRows()
        if not rows or not self._vm._erp_result:
            return
        row = rows[0].row()
        cond = self._peak_table.item(row, 0).text()
        comp_str = self._peak_table.item(row, 1).text()
        latency = float(self._peak_table.item(row, 2).text()) / 1000
        self._vm.generate_topomap(cond, latency)
        self._vm.plot_topomaps(times=[latency], condition=cond)

    @Slot()
    def _plot_joint(self):
        self._vm.plot_joint()

    @Slot()
    def _plot_all_topomaps(self):
        if not self._vm._erp_result:
            return
        times = []
        for peaks in self._vm._erp_result.result.peaks.values():
            for peak in peaks.values():
                if "latency" in peak:
                    times.append(peak["latency"])
        self._vm.plot_topomaps(times=list(set(times)))