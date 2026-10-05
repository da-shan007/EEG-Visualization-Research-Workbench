"""ERP 条件设置面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QMessageBox,
    QLabel
)

from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.models.erp import EpochParams, ERPComponent, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY
from eeg_workbench.utils.ui import balance_form


class ERPConditionWidget(QWidget):
    """ERP 条件与参数设置面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: ERPViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 条件列表 ----
        cond_group = QGroupBox("ERP 条件")
        cond_layout = QVBoxLayout(cond_group)

        self._cond_table = QTableWidget(0, 6)
        self._cond_table.setHorizontalHeaderLabels([
            "条件名", "触发事件", "时间窗", "基线", "拒绝阈值", "ICA去伪影"
        ])
        self._cond_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._cond_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cond_layout.addWidget(self._cond_table)

        btn_layout = QHBoxLayout()
        self._btn_add_cond = QPushButton("添加条件")
        self._btn_add_cond.clicked.connect(self._add_condition_dialog)
        self._btn_edit_cond = QPushButton("编辑条件")
        self._btn_edit_cond.clicked.connect(self._edit_condition)
        self._btn_del_cond = QPushButton("删除条件")
        self._btn_del_cond.clicked.connect(self._delete_condition)
        btn_layout.addWidget(self._btn_add_cond)
        btn_layout.addWidget(self._btn_edit_cond)
        btn_layout.addWidget(self._btn_del_cond)
        btn_layout.addStretch()
        cond_layout.addLayout(btn_layout)

        layout.addWidget(cond_group)

        # ---- 差分对比 ----
        contrast_group = QGroupBox("差分波对比")
        contrast_layout = QVBoxLayout(contrast_group)

        self._contrast_list = QTableWidget(0, 2)
        self._contrast_list.setHorizontalHeaderLabels(["条件 A", "条件 B"])
        self._contrast_list.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        contrast_layout.addWidget(self._contrast_list)

        contrast_btn = QHBoxLayout()
        self._btn_add_contrast = QPushButton("添加对比")
        self._btn_add_contrast.clicked.connect(self._add_contrast_dialog)
        self._btn_del_contrast = QPushButton("删除对比")
        self._btn_del_contrast.clicked.connect(self._delete_contrast)
        contrast_btn.addWidget(self._btn_add_contrast)
        contrast_btn.addWidget(self._btn_del_contrast)
        contrast_btn.addStretch()
        contrast_layout.addLayout(contrast_btn)

        layout.addWidget(contrast_group)

        # ---- 平均与统计 ----
        stats_group = QGroupBox("平均与统计选项")
        stats_layout = QFormLayout(stats_group)

        self._cmb_avg_method = QComboBox()
        self._cmb_avg_method.addItems(["mean", "median", "robust"])
        stats_layout.addRow("平均方法:", self._cmb_avg_method)

        self._chk_peak_detect = QCheckBox("自动峰值检测")
        self._chk_peak_detect.setChecked(True)
        stats_layout.addRow("", self._chk_peak_detect)

        self._cmb_stats_test = QComboBox()
        self._cmb_stats_test.addItems(["none", "ttest", "wilcoxon", "permutation"])
        stats_layout.addRow("统计检验:", self._cmb_stats_test)

        self._spin_perms = QSpinBox()
        self._spin_perms.setRange(100, 10000)
        self._spin_perms.setValue(1000)
        stats_layout.addRow("置换次数:", self._spin_perms)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems(["none", "fdr", "bonferroni", "cluster"])
        stats_layout.addRow("多重比较校正:", self._cmb_correction)
        balance_form(stats_layout)

        layout.addWidget(stats_group)

        # ---- 峰值检测参数 ----
        peak_group = QGroupBox("峰值检测参数")
        peak_layout = QVBoxLayout(peak_group)

        self._peak_table = QTableWidget(0, 5)
        self._peak_table.setHorizontalHeaderLabels(["成分", "时间窗(秒)", "极性", "最小间距", "启用"])
        self._peak_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        peak_layout.addWidget(self._peak_table)

        peak_btn = QHBoxLayout()
        self._btn_reset_peaks = QPushButton("重置为默认")
        self._btn_reset_peaks.clicked.connect(self._reset_peak_defaults)
        peak_btn.addWidget(self._btn_reset_peaks)
        peak_btn.addStretch()
        peak_layout.addLayout(peak_btn)

        layout.addWidget(peak_group)

        layout.addStretch()

        # 初始化峰值表格
        self._populate_peak_table()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _populate_peak_table(self):
        """填充默认峰值参数"""
        self._peak_table.setRowCount(0)
        for comp in [
            ERPComponent.P1, ERPComponent.N1, ERPComponent.P2,
            ERPComponent.N2, ERPComponent.P3
        ]:
            row = self._peak_table.rowCount()
            self._peak_table.insertRow(row)
            tmin, tmax = DEFAULT_ERP_PEAK_WINDOWS[comp]
            polarity = DEFAULT_ERP_POLARITY[comp]
            
            self._peak_table.setItem(row, 0, QTableWidgetItem(comp.value))
            self._peak_table.setItem(row, 1, QTableWidgetItem(f"{tmin:.2f} - {tmax:.2f}"))
            self._peak_table.setItem(row, 2, QTableWidgetItem(polarity))
            self._peak_table.setItem(row, 3, QTableWidgetItem("0.02"))
            
            chk = QCheckBox()
            chk.setChecked(True)
            self._peak_table.setCellWidget(row, 4, chk)

    @Slot()
    def _add_condition_dialog(self):
        dlg = ConditionDialog(self, events_list=self._vm.events_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
            self._vm.add_erp_condition(
                name=params["name"],
                event_descriptions=params["event_descriptions"],
                tmin=params["tmin"],
                tmax=params["tmax"],
                baseline=params["baseline"]
            )
            self._refresh_condition_table()
            self.status_message.emit(f"已添加条件: {params['name']}")

    @Slot()
    def _edit_condition(self):
        row = self._cond_table.currentRow()
        if row < 0:
            return
        name = self._cond_table.item(row, 0).text()
        # 这里需要实现编辑对话框
        self.status_message.emit("编辑功能待实现")

    @Slot()
    def _delete_condition(self):
        row = self._cond_table.currentRow()
        if row < 0:
            return
        name = self._cond_table.item(row, 0).text()
        self._vm.remove_condition(name, "erp")
        self._refresh_condition_table()

    def _refresh_condition_table(self):
        self._cond_table.setRowCount(0)
        for name, ep in self._vm.erp_params.conditions.items():
            row = self._cond_table.rowCount()
            self._cond_table.insertRow(row)
            self._cond_table.setItem(row, 0, QTableWidgetItem(name))
            self._cond_table.setItem(row, 1, QTableWidgetItem(", ".join(ep.event_descriptions)))
            self._cond_table.setItem(row, 2, QTableWidgetItem(f"{ep.tmin:.2f} - {ep.tmax:.2f}"))
            self._cond_table.setItem(row, 3, QTableWidgetItem(f"{ep.baseline}" if ep.baseline else "无"))
            self._cond_table.setItem(row, 4, QTableWidgetItem(str(ep.reject) if ep.reject else "无"))
            self._cond_table.setItem(row, 5, QTableWidgetItem("是" if ep.apply_ica else "否"))

    @Slot()
    def _add_contrast_dialog(self):
        dlg = ContrastDialog(self, conditions=list(self._vm.erp_params.conditions.keys()))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            a, b = dlg.get_contrast()
            self._vm.add_contrast(a, b)
            self._refresh_contrast_table()

    def _refresh_contrast_table(self):
        self._contrast_list.setRowCount(0)
        for a, b in self._vm.erp_params.contrast_pairs:
            row = self._contrast_list.rowCount()
            self._contrast_list.insertRow(row)
            self._contrast_list.setItem(row, 0, QTableWidgetItem(a))
            self._contrast_list.setItem(row, 1, QTableWidgetItem(b))

    @Slot()
    def _delete_contrast(self):
        row = self._contrast_list.currentRow()
        if row < 0:
            return
        # 实现删除
        pass

    @Slot()
    def _reset_peak_defaults(self):
        self._populate_peak_table()
        self.status_message.emit("已重置为默认峰值参数")


class ConditionDialog(QDialog):
    """添加/编辑条件对话框"""

    def __init__(self, parent=None, events_list: list[str] = None, condition: dict = None):
        super().__init__(parent)
        self.setWindowTitle("添加条件" if not condition else "编辑条件")
        self.setModal(True)
        self.resize(400, 400)
        self._events_list = events_list or []
        self._condition = condition
        self._setup_ui()
        if condition:
            self._load_condition(condition)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("如: Target, NonTarget")
        form.addRow("条件名称 *:", self._edit_name)

        # 事件选择
        self._lst_events = QListWidget()
        self._lst_events.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for ev in self._events_list:
            self._lst_events.addItem(ev)
        form.addRow("触发事件:", self._lst_events)

        # 时间窗
        row = QHBoxLayout()
        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-10, 10)
        self._spin_tmin.setDecimals(3)
        self._spin_tmin.setValue(-0.2)
        self._spin_tmin.setSuffix(" s")
        row.addWidget(self._spin_tmin)
        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-10, 10)
        self._spin_tmax.setDecimals(3)
        self._spin_tmax.setValue(0.8)
        self._spin_tmax.setSuffix(" s")
        row.addWidget(self._spin_tmax)
        form.addRow("时间窗:", row)

        # 基线
        row = QHBoxLayout()
        self._chk_baseline = QCheckBox("启用基线")
        self._chk_baseline.setChecked(True)
        row.addWidget(self._chk_baseline)
        self._spin_b_tmin = QDoubleSpinBox()
        self._spin_b_tmin.setRange(-10, 0)
        self._spin_b_tmin.setDecimals(3)
        self._spin_b_tmin.setValue(-0.2)
        row.addWidget(self._spin_b_tmin)
        self._spin_b_tmax = QDoubleSpinBox()
        self._spin_b_tmax.setRange(-10, 0)
        self._spin_b_tmax.setDecimals(3)
        self._spin_b_tmax.setValue(0.0)
        row.addWidget(self._spin_b_tmax)
        form.addRow("基线窗:", row)

        # 进阶选项
        self._chk_ica = QCheckBox("应用 ICA 去伪影")
        form.addRow("", self._chk_ica)

        self._spin_resample = QDoubleSpinBox()
        self._spin_resample.setRange(0, 2000)
        self._spin_resample.setDecimals(1)
        self._spin_resample.setSpecialValueText("不重采样")
        form.addRow("重采样频率:", self._spin_resample)
        balance_form(form)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_condition(self, cond: dict):
        self._edit_name.setText(cond.get("name", ""))
        events = cond.get("event_descriptions", [])
        for i in range(self._lst_events.count()):
            if self._lst_events.item(i).text() in events:
                self._lst_events.item(i).setSelected(True)
        self._spin_tmin.setValue(cond.get("tmin", -0.2))
        self._spin_tmax.setValue(cond.get("tmax", 0.8))
        if cond.get("baseline"):
            self._chk_baseline.setChecked(True)
            self._spin_b_tmin.setValue(cond["baseline"][0])
            self._spin_b_tmax.setValue(cond["baseline"][1])
        self._chk_ica.setChecked(cond.get("apply_ica", False))
        self._spin_resample.setValue(cond.get("resample_sfreq", 0))

    def get_params(self) -> dict:
        events = [item.text() for item in self._lst_events.selectedItems()]
        baseline = None
        if self._chk_baseline.isChecked():
            baseline = (self._spin_b_tmin.value(), self._spin_b_tmax.value())
        return {
            "name": self._edit_name.text().strip(),
            "event_descriptions": events,
            "tmin": self._spin_tmin.value(),
            "tmax": self._spin_tmax.value(),
            "baseline": baseline,
            "apply_ica": self._chk_ica.isChecked(),
            "resample_sfreq": self._spin_resample.value() if self._spin_resample.value() > 0 else None,
        }


class ContrastDialog(QDialog):
    """添加对比对话框"""

    def __init__(self, parent=None, conditions: list[str] = None):
        super().__init__(parent)
        self.setWindowTitle("添加差分对比")
        self.setModal(True)
        self._conditions = conditions or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._cmb_a = QComboBox()
        self._cmb_a.addItems(self._conditions)
        form.addRow("条件 A (被减数):", self._cmb_a)

        self._cmb_b = QComboBox()
        self._cmb_b.addItems(self._conditions)
        form.addRow("条件 B (减数):", self._cmb_b)
        balance_form(form)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_contrast(self) -> tuple[str, str]:
        return self._cmb_a.currentText(), self._cmb_b.currentText()


# 需要导入
from PySide6.QtWidgets import QListWidget