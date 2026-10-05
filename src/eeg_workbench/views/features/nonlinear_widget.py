"""非线性分析面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QCheckBox,
    QLabel, QListWidget, QListWidgetItem, QAbstractItemView,
    QLineEdit
)

from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.models.features import NonlinearParams, NonlinearMeasure


class NonlinearWidget(QWidget):
    """非线性分析参数设置与执行面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: FeaturesViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 指标选择 ----
        select_group = QGroupBox("选择非线性指标")
        select_layout = QVBoxLayout(select_group)

        self._lst_measures = QListWidget()
        self._lst_measures.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._lst_measures.setMaximumHeight(200)
        select_layout.addWidget(self._lst_measures)

        # 预设按钮
        preset_layout = QHBoxLayout()
        self._btn_entropy_suite = QPushButton("熵指标套件")
        self._btn_entropy_suite.clicked.connect(lambda: self._apply_preset("entropy"))
        self._btn_fractal_suite = QPushButton("分形指标套件")
        self._btn_fractal_suite.clicked.connect(lambda: self._apply_preset("fractal"))
        self._btn_full_suite = QPushButton("全套指标")
        self._btn_full_suite.clicked.connect(lambda: self._apply_preset("full"))
        preset_layout.addWidget(self._btn_entropy_suite)
        preset_layout.addWidget(self._btn_fractal_suite)
        preset_layout.addWidget(self._btn_full_suite)
        preset_layout.addStretch()
        select_layout.addLayout(preset_layout)

        layout.addWidget(select_group)

        # ---- 参数设置 ----
        params_group = QGroupBox("参数设置")
        params_layout = QFormLayout(params_group)

        # 样本熵参数
        self._spin_sampen_m = QSpinBox()
        self._spin_sampen_m.setRange(1, 5)
        self._spin_sampen_m.setValue(2)
        params_layout.addRow("样本熵 m:", self._spin_sampen_m)

        self._spin_sampen_r = QDoubleSpinBox()
        self._spin_sampen_r.setRange(0.05, 1.0)
        self._spin_sampen_r.setDecimals(2)
        self._spin_sampen_r.setSingleStep(0.05)
        self._spin_sampen_r.setValue(0.2)
        params_layout.addRow("样本熵 r (×std):", self._spin_sampen_r)

        # 排列熵参数
        self._spin_perm_order = QSpinBox()
        self._spin_perm_order.setRange(2, 7)
        self._spin_perm_order.setValue(3)
        params_layout.addRow("排列熵阶数:", self._spin_perm_order)

        self._spin_perm_delay = QSpinBox()
        self._spin_perm_delay.setRange(1, 10)
        self._spin_perm_delay.setValue(1)
        params_layout.addRow("排列熵延迟:", self._spin_perm_delay)

        # DFA 参数
        self._edit_dfa_scales = QLineEdit()
        self._edit_dfa_scales.setPlaceholderText("可选: 逗号分隔，如 4,8,16,32,64,128")
        params_layout.addRow("DFA 尺度:", self._edit_dfa_scales)

        # Lyapunov 参数
        self._spin_lyap_min_sep = QSpinBox()
        self._spin_lyap_min_sep.setRange(1, 50)
        self._spin_lyap_min_sep.setValue(10)
        params_layout.addRow("Lyapunov 最小分离:", self._spin_lyap_min_sep)
        balance_form(params_layout)

        layout.addWidget(params_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("计算非线性指标")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_nonlinear)
        exec_layout.addWidget(self._btn_run)

        self._btn_from_epochs = QPushButton("从 Epochs 计算")
        self._btn_from_epochs.clicked.connect(self._run_from_epochs)
        exec_layout.addWidget(self._btn_from_epochs)

        layout.addLayout(exec_layout)

        layout.addStretch()

        # 初始化指标列表
        self._populate_measures_list()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.nonlinear_result.connect(self._on_result_ready)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _populate_measures_list(self):
        self._lst_measures.clear()
        for measure in NonlinearMeasure:
            item = QListWidgetItem(f"{measure.value}")
            item.setData(Qt.ItemDataRole.UserRole, measure)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._lst_measures.addItem(item)

        # 默认勾选常用指标
        defaults = ["sample_entropy", "permutation_entropy", "hurst", "dfa"]
        for i in range(self._lst_measures.count()):
            item = self._lst_measures.item(i)
            if item.data(Qt.ItemDataRole.UserRole).value in defaults:
                item.setCheckState(Qt.CheckState.Checked)

    def _apply_preset(self, preset: str):
        for i in range(self._lst_measures.count()):
            item = self._lst_measures.item(i)
            measure = item.data(Qt.ItemDataRole.UserRole)
            if preset == "entropy":
                item.setCheckState(Qt.CheckState.Checked if measure.value in [
                    "sample_entropy", "approx_entropy", "permutation_entropy"
                ] else Qt.CheckState.Unchecked)
            elif preset == "fractal":
                item.setCheckState(Qt.CheckState.Checked if measure.value in [
                    "hurst", "dfa", "correlation_dim"
                ] else Qt.CheckState.Unchecked)
            elif preset == "full":
                item.setCheckState(Qt.CheckState.Checked)

    def _sync_from_vm(self):
        params = self._vm.nonlinear_params
        self._block_signals(True)
        try:
            self._spin_sampen_m.setValue(params.sample_entropy_m)
            self._spin_sampen_r.setValue(params.sample_entropy_r)
            self._spin_perm_order.setValue(params.perm_entropy_order)
            self._spin_perm_delay.setValue(params.perm_entropy_delay)
            if params.dfa_scales is not None:
                self._edit_dfa_scales.setText(",".join(str(int(s)) for s in params.dfa_scales))
            self._spin_lyap_min_sep.setValue(params.lyap_min_sep)

            # 更新勾选状态
            for i in range(self._lst_measures.count()):
                item = self._lst_measures.item(i)
                measure = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(Qt.CheckState.Checked if measure in params.measures else Qt.CheckState.Unchecked)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._spin_sampen_m, self._spin_sampen_r, self._spin_perm_order,
            self._spin_perm_delay, self._edit_dfa_scales, self._spin_lyap_min_sep
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        # 收集勾选的指标
        measures = []
        for i in range(self._lst_measures.count()):
            item = self._lst_measures.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                measures.append(item.data(Qt.ItemDataRole.UserRole))

        params = NonlinearParams(
            measures=measures,
            sample_entropy_m=self._spin_sampen_m.value(),
            sample_entropy_r=self._spin_sampen_r.value(),
            perm_entropy_order=self._spin_perm_order.value(),
            perm_entropy_delay=self._spin_perm_delay.value(),
            dfa_scales=np.array([float(x.strip()) for x in self._edit_dfa_scales.text().split(",") if x.strip()]) if self._edit_dfa_scales.text().strip() else None,
            lyap_min_sep=self._spin_lyap_min_sep.value(),
        )
        self._vm.set_nonlinear_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_nonlinear(self):
        self._vm.run_nonlinear()

    @Slot()
    def _run_from_epochs(self):
        self.status_message.emit("请先定义事件和 Epochs 参数")

    @Slot(object)
    def _on_result_ready(self, result):
        if result and result.nonlinear:
            keys = list(result.nonlinear.keys())
            self.status_message.emit(f"非线性指标计算完成: {', '.join(keys)}")


# 需要导入 numpy
from eeg_workbench.models.features import NonlinearParams
from eeg_workbench.utils.ui import balance_form
import numpy as np