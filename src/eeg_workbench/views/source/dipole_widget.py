"""偶极子拟合面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox
)

from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.models.source import DipoleFitParams


class DipoleFitWidget(QWidget):
    """偶极子拟合面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: SourceViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 拟合方法 ----
        method_group = QGroupBox("拟合方法")
        method_layout = QFormLayout(method_group)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems(["least_squares", "nelder_mead", "differential_evolution"])
        self._cmb_method.setCurrentText("least_squares")
        method_layout.addRow("优化方法:", self._cmb_method)

        self._spin_max_dipoles = QSpinBox()
        self._spin_max_dipoles.setRange(1, 10)
        self._spin_max_dipoles.setValue(1)
        method_layout.addRow("最大偶极子数:", self._spin_max_dipoles)

        self._spin_gof_threshold = QDoubleSpinBox()
        self._spin_gof_threshold.setRange(0, 1)
        self._spin_gof_threshold.setDecimals(2)
        self._spin_gof_threshold.setSingleStep(0.01)
        self._spin_gof_threshold.setValue(0.9)
        method_layout.addRow("GOF 阈值:", self._spin_gof_threshold)

        layout.addWidget(method_group)

        # ---- 初始猜测 ----
        guess_group = QGroupBox("初始位置猜测")
        guess_layout = QFormLayout(guess_group)

        self._chk_auto_guess = QCheckBox("自动猜测")
        self._chk_auto_guess.setChecked(True)
        guess_layout.addRow("", self._chk_auto_guess)

        row = QHBoxLayout()
        self._spin_guess_x = QDoubleSpinBox()
        self._spin_guess_x.setRange(-0.15, 0.15)
        self._spin_guess_x.setDecimals(3)
        self._spin_guess_x.setValue(0.0)
        self._spin_guess_x.setSuffix(" m")
        row.addWidget(self._spin_guess_x)

        self._spin_guess_y = QDoubleSpinBox()
        self._spin_guess_y.setRange(-0.15, 0.15)
        self._spin_guess_y.setDecimals(3)
        self._spin_guess_y.setValue(0.0)
        self._spin_guess_y.setSuffix(" m")
        row.addWidget(self._spin_guess_y)

        self._spin_guess_z = QDoubleSpinBox()
        self._spin_guess_z.setRange(0, 0.15)
        self._spin_guess_z.setDecimals(3)
        self._spin_guess_z.setValue(0.04)
        self._spin_guess_z.setSuffix(" m")
        row.addWidget(self._spin_guess_z)

        guess_layout.addRow("位置 (x,y,z):", row)

        layout.addWidget(guess_group)

        # ---- 位置约束 ----
        bounds_group = QGroupBox("位置搜索边界")
        bounds_layout = QFormLayout(bounds_group)

        self._spin_x_min = QDoubleSpinBox()
        self._spin_x_min.setRange(-0.15, 0.15)
        self._spin_x_min.setDecimals(3)
        self._spin_x_min.setValue(-0.1)
        self._spin_x_min.setSuffix(" m")
        self._spin_x_max = QDoubleSpinBox()
        self._spin_x_max.setRange(-0.15, 0.15)
        self._spin_x_max.setDecimals(3)
        self._spin_x_max.setValue(0.1)
        self._spin_x_max.setSuffix(" m")
        _row_x = QHBoxLayout()
        _row_x.addWidget(self._spin_x_min)
        _row_x.addWidget(self._spin_x_max)
        bounds_layout.addRow("X 范围:", _row_x)

        self._spin_y_min = QDoubleSpinBox()
        self._spin_y_min.setRange(-0.15, 0.15)
        self._spin_y_min.setDecimals(3)
        self._spin_y_min.setValue(-0.1)
        self._spin_y_max = QDoubleSpinBox()
        self._spin_y_max.setRange(-0.15, 0.15)
        self._spin_y_max.setDecimals(3)
        self._spin_y_max.setValue(0.1)
        _row_y = QHBoxLayout()
        _row_y.addWidget(self._spin_y_min)
        _row_y.addWidget(self._spin_y_max)
        bounds_layout.addRow("Y 范围:", _row_y)

        self._spin_z_min = QDoubleSpinBox()
        self._spin_z_min.setRange(0, 0.15)
        self._spin_z_min.setDecimals(3)
        self._spin_z_min.setValue(0)
        self._spin_z_max = QDoubleSpinBox()
        self._spin_z_max.setRange(0, 0.15)
        self._spin_z_max.setDecimals(3)
        self._spin_z_max.setValue(0.15)
        _row_z = QHBoxLayout()
        _row_z.addWidget(self._spin_z_min)
        _row_z.addWidget(self._spin_z_max)
        bounds_layout.addRow("Z 范围:", _row_z)

        layout.addWidget(bounds_group)

        # ---- 结果表格 ----
        result_group = QGroupBox("拟合结果")
        result_layout = QVBoxLayout(result_group)

        self._result_table = QTableWidget(0, 7)
        self._result_table.setHorizontalHeaderLabels([
            "索引", "X (mm)", "Y (mm)", "Z (mm)", "GOF", "幅度 (nAm)", "时间 (ms)"
        ])
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self._result_table)

        layout.addWidget(result_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_fit = QPushButton("拟合偶极子")
        self._btn_fit.setMinimumHeight(40)
        self._btn_fit.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_fit.clicked.connect(self._run_fit)
        exec_layout.addWidget(self._btn_fit)

        self._btn_multi = QPushButton("多偶极子拟合")
        self._btn_multi.clicked.connect(self._run_multi_fit)
        exec_layout.addWidget(self._btn_multi)

        self._btn_plot = QPushButton("3D 显示偶极子")
        self._btn_plot.clicked.connect(self._plot_dipoles)
        exec_layout.addWidget(self._btn_plot)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.dipole_fit_ready.connect(self._on_result_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _sync_from_vm(self):
        params = self._vm.dipole_params
        self._block_signals(True)
        try:
            self._cmb_method.setCurrentText(params.method)
            self._spin_max_dipoles.setValue(params.max_dipoles)
            self._spin_gof_threshold.setValue(params.goodness_of_fit_threshold)
            self._chk_auto_guess.setChecked(params.initial_pos is None)
            if params.initial_pos is not None:
                self._spin_guess_x.setValue(params.initial_pos[0])
                self._spin_guess_y.setValue(params.initial_pos[1])
                self._spin_guess_z.setValue(params.initial_pos[2])
            if params.pos_bounds:
                self._spin_x_min.setValue(params.pos_bounds[0][0])
                self._spin_x_max.setValue(params.pos_bounds[0][1])
                self._spin_y_min.setValue(params.pos_bounds[1][0])
                self._spin_y_max.setValue(params.pos_bounds[1][1])
                self._spin_z_min.setValue(params.pos_bounds[2][0])
                self._spin_z_max.setValue(params.pos_bounds[2][1])
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._cmb_method, self._spin_max_dipoles, self._spin_gof_threshold,
            self._chk_auto_guess, self._spin_guess_x, self._spin_guess_y, self._spin_guess_z,
            self._spin_x_min, self._spin_x_max, self._spin_y_min, self._spin_y_max,
            self._spin_z_min, self._spin_z_max
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        bounds = (
            (self._spin_x_min.value(), self._spin_x_max.value()),
            (self._spin_y_min.value(), self._spin_y_max.value()),
            (self._spin_z_min.value(), self._spin_z_max.value()),
        )
        initial_pos = None
        if not self._chk_auto_guess.isChecked():
            initial_pos = (self._spin_guess_x.value(), self._spin_guess_y.value(), self._spin_guess_z.value())

        params = DipoleFitParams(
            method=self._cmb_method.currentText(),
            max_dipoles=self._spin_max_dipoles.value(),
            goodness_of_fit_threshold=self._spin_gof_threshold.value(),
            initial_pos=initial_pos,
            pos_bounds=bounds,
        )
        self._vm.set_dipole_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_fit(self):
        if not self._vm._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return
        self._btn_fit.setEnabled(False)
        self._btn_fit.setText("拟合中...")
        self._vm.run_dipole_fit()
        self._btn_fit.setEnabled(True)
        self._btn_fit.setText("拟合偶极子")

    @Slot()
    def _run_multi_fit(self):
        if not self._vm._dataset:
            return
        self._vm.run_dipole_fit()  # 简化：使用同一接口

    @Slot()
    def _plot_dipoles(self):
        if not self._vm._dipole_result:
            return
        self._vm.plot_dipoles_3d()

    @Slot(object)
    def _on_result_ready(self, result):
        self._result_table.setRowCount(0)
        for i, dip in enumerate(result.dipoles):
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            pos = dip.get("pos", [0,0,0]) * 1000  # m -> mm
            self._result_table.setItem(row, 0, QTableWidgetItem(str(i)))
            self._result_table.setItem(row, 1, QTableWidgetItem(f"{pos[0]:.1f}"))
            self._result_table.setItem(row, 2, QTableWidgetItem(f"{pos[1]:.1f}"))
            self._result_table.setItem(row, 3, QTableWidgetItem(f"{pos[2]:.1f}"))
            self._result_table.setItem(row, 4, QTableWidgetItem(f"{dip.get('gof', 0):.3f}"))
            self._result_table.setItem(row, 5, QTableWidgetItem(f"{dip.get('amplitude', 0)*1e9:.1f}"))
            self._result_table.setItem(row, 6, QTableWidgetItem(f"{dip.get('time', 0)*1000:.1f}"))

        self.status_message.emit(f"偶极子拟合完成: {len(result.dipoles)} 个")