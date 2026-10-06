"""ERD/ERS 分析面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Any, Literal, Optional, cast

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit, QHeaderView,
    QAbstractItemView, QLabel, QDialog, QDialogButtonBox,
    QListWidget
)

from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.models.erp import BaselineMode, EpochParams
from eeg_workbench.utils.ui import balance_form, require_table_item


class ERDSWidget(QWidget):
    """ERD/ERS 分析参数设置与执行面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: ERPViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 条件列表 ----
        cond_group = QGroupBox("ERD/ERS 条件")
        cond_layout = QVBoxLayout(cond_group)

        self._cond_table = QTableWidget(0, 5)
        self._cond_table.setHorizontalHeaderLabels([
            "条件名", "触发事件", "时间窗", "基线", "拒绝阈值"
        ])
        self._cond_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cond_layout.addWidget(self._cond_table)

        btn_layout = QHBoxLayout()
        self._btn_add_cond = QPushButton("添加条件")
        self._btn_add_cond.clicked.connect(self._add_condition_dialog)
        self._btn_del_cond = QPushButton("删除条件")
        self._btn_del_cond.clicked.connect(self._delete_condition)
        btn_layout.addWidget(self._btn_add_cond)
        btn_layout.addWidget(self._btn_del_cond)
        btn_layout.addStretch()
        cond_layout.addLayout(btn_layout)

        layout.addWidget(cond_group)

        # ---- 频段设置 ----
        bands_group = QGroupBox("频段定义")
        bands_layout = QVBoxLayout(bands_group)

        self._bands_table = QTableWidget(0, 3)
        self._bands_table.setHorizontalHeaderLabels(["频段名", "低频 (Hz)", "高频 (Hz)"])
        self._bands_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        bands_layout.addWidget(self._bands_table)

        bands_btn = QHBoxLayout()
        self._btn_add_band = QPushButton("添加频段")
        self._btn_add_band.clicked.connect(self._add_band)
        self._btn_del_band = QPushButton("删除频段")
        self._btn_del_band.clicked.connect(self._del_band)
        bands_btn.addWidget(self._btn_add_band)
        bands_btn.addWidget(self._btn_del_band)
        bands_btn.addStretch()
        bands_layout.addLayout(bands_btn)

        layout.addWidget(bands_group)

        # ---- 时频参数 ----
        tf_group = QGroupBox("时频分析参数")
        tf_layout = QFormLayout(tf_group)

        self._cmb_tf_method = QComboBox()
        self._cmb_tf_method.addItems(["morlet", "multitaper", "stockwell"])
        self._cmb_tf_method.setCurrentText("morlet")
        tf_layout.addRow("方法:", self._cmb_tf_method)

        self._spin_n_cycles = QDoubleSpinBox()
        self._spin_n_cycles.setRange(1, 20)
        self._spin_n_cycles.setDecimals(1)
        self._spin_n_cycles.setValue(7.0)
        tf_layout.addRow("Morlet 周期数:", self._spin_n_cycles)

        # 全局时间窗
        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-5, 5)
        self._spin_tmin.setDecimals(2)
        self._spin_tmin.setValue(-1.0)
        self._spin_tmin.setSuffix(" s")
        tf_layout.addRow("全局 tmin:", self._spin_tmin)

        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-5, 5)
        self._spin_tmax.setDecimals(2)
        self._spin_tmax.setValue(2.0)
        self._spin_tmax.setSuffix(" s")
        tf_layout.addRow("全局 tmax:", self._spin_tmax)

        # 基线
        self._chk_baseline = QCheckBox("基线校正")
        self._chk_baseline.setChecked(True)
        tf_layout.addRow("", self._chk_baseline)

        base_row = QHBoxLayout()
        self._spin_base_tmin = QDoubleSpinBox()
        self._spin_base_tmin.setRange(-5, 0)
        self._spin_base_tmin.setDecimals(2)
        self._spin_base_tmin.setValue(-1.0)
        self._spin_base_tmin.setSuffix(" s")
        base_row.addWidget(self._spin_base_tmin)
        self._spin_base_tmax = QDoubleSpinBox()
        self._spin_base_tmax.setRange(-5, 0)
        self._spin_base_tmax.setDecimals(2)
        self._spin_base_tmax.setValue(-0.5)
        self._spin_base_tmax.setSuffix(" s")
        base_row.addWidget(self._spin_base_tmax)
        tf_layout.addRow("基线窗:", base_row)

        self._cmb_base_mode = QComboBox()
        self._cmb_base_mode.addItems(["mean", "ratio", "logratio", "zscore"])
        self._cmb_base_mode.setCurrentText("logratio")
        tf_layout.addRow("校正模式:", self._cmb_base_mode)
        balance_form(tf_layout)

        layout.addWidget(tf_group)

        # ---- 统计选项 ----
        stat_group = QGroupBox("统计检验")
        stat_layout = QFormLayout(stat_group)

        self._cmb_stats = QComboBox()
        self._cmb_stats.addItems(["none", "ttest", "permutation"])
        stat_layout.addRow("检验方法:", self._cmb_stats)

        self._spin_perms = QSpinBox()
        self._spin_perms.setRange(100, 10000)
        self._spin_perms.setValue(1000)
        stat_layout.addRow("置换次数:", self._spin_perms)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems(["none", "fdr", "cluster"])
        stat_layout.addRow("校正方法:", self._cmb_correction)
        balance_form(stat_layout)

        layout.addWidget(stat_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("计算 ERD/ERS")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_erds)
        exec_layout.addWidget(self._btn_run)

        self._btn_topo = QPushButton("绘制地形图")
        self._btn_topo.clicked.connect(self._plot_topomaps)
        exec_layout.addWidget(self._btn_topo)

        layout.addLayout(exec_layout)

        layout.addStretch()

        # 初始化默认频段
        self._populate_default_bands()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.erds_result.connect(self._on_result_ready)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _populate_default_bands(self) -> None:
        default_bands = {
            "Theta": (4, 8),
            "Alpha": (8, 13),
            "Beta": (13, 30),
            "LowGamma": (30, 50),
            "HighGamma": (60, 90),
        }
        for name, (low, high) in default_bands.items():
            row = self._bands_table.rowCount()
            self._bands_table.insertRow(row)
            self._bands_table.setItem(row, 0, QTableWidgetItem(name))
            self._bands_table.setItem(row, 1, QTableWidgetItem(str(low)))
            self._bands_table.setItem(row, 2, QTableWidgetItem(str(high)))

    @Slot()
    def _add_condition_dialog(self) -> None:
        dlg = ERDSConditionDialog(self, events_list=self._vm.events_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
            self._vm.add_erds_condition(
                name=params["name"],
                event_descriptions=params["event_descriptions"],
                tmin=params["tmin"],
                tmax=params["tmax"],
                baseline=params["baseline"]
            )
            self._refresh_condition_table()
            self.status_message.emit(f"已添加条件: {params['name']}")

    def _refresh_condition_table(self) -> None:
        self._cond_table.setRowCount(0)
        for name, ep in self._vm.erds_params.conditions.items():
            row = self._cond_table.rowCount()
            self._cond_table.insertRow(row)
            self._cond_table.setItem(row, 0, QTableWidgetItem(name))
            self._cond_table.setItem(row, 1, QTableWidgetItem(", ".join(ep.event_descriptions)))
            self._cond_table.setItem(row, 2, QTableWidgetItem(f"{ep.tmin:.2f} - {ep.tmax:.2f}"))
            self._cond_table.setItem(row, 3, QTableWidgetItem(f"{ep.baseline}" if ep.baseline else "无"))
            self._cond_table.setItem(row, 4, QTableWidgetItem(str(ep.reject) if ep.reject else "无"))

    @Slot()
    def _delete_condition(self) -> None:
        row = self._cond_table.currentRow()
        if row < 0:
            return
        name = require_table_item(self._cond_table, row, 0).text()
        self._vm.remove_condition(name, "erds")
        self._refresh_condition_table()

    @Slot()
    def _add_band(self) -> None:
        row = self._bands_table.rowCount()
        self._bands_table.insertRow(row)
        self._bands_table.setItem(row, 0, QTableWidgetItem(f"Band{row+1}"))
        self._bands_table.setItem(row, 1, QTableWidgetItem("8"))
        self._bands_table.setItem(row, 2, QTableWidgetItem("13"))

    @Slot()
    def _del_band(self) -> None:
        rows = sorted(set(item.row() for item in self._bands_table.selectedItems()), reverse=True)
        for row in rows:
            self._bands_table.removeRow(row)

    def _sync_params(self) -> None:
        """同步 UI 参数到 ViewModel"""
        # 频段
        bands = {}
        for row in range(self._bands_table.rowCount()):
            name_item = self._bands_table.item(row, 0)
            low_item = self._bands_table.item(row, 1)
            high_item = self._bands_table.item(row, 2)
            if name_item is None or low_item is None or high_item is None:
                continue
            name = name_item.text()
            try:
                low = float(low_item.text())
                high = float(high_item.text())
                bands[name] = (low, high)
            except (ValueError, AttributeError):
                continue
        self._vm.erds_params.bands = bands

        # 时频参数
        self._vm.erds_params.tf_method = self._cmb_tf_method.currentText()
        self._vm.erds_params.n_cycles = self._spin_n_cycles.value()
        self._vm.erds_params.tmin = self._spin_tmin.value()
        self._vm.erds_params.tmax = self._spin_tmax.value()
        self._vm.erds_params.baseline = (
            self._spin_base_tmin.value(), self._spin_base_tmax.value()
        ) if self._chk_baseline.isChecked() else None
        self._vm.erds_params.baseline_mode = BaselineMode(self._cmb_base_mode.currentText())

        # 统计（下拉框选项与模型 Literal 一致，错配即程序错误，大声失败）
        stats_text = self._cmb_stats.currentText()
        assert stats_text in ("none", "ttest", "permutation"), f"未知统计检验: {stats_text}"
        self._vm.erds_params.stats_test = cast(
            Literal["none", "ttest", "permutation"], stats_text)
        self._vm.erds_params.n_permutations = self._spin_perms.value()
        correction_text = self._cmb_correction.currentText()
        assert correction_text in ("none", "fdr", "cluster"), f"未知多重比较校正: {correction_text}"
        self._vm.erds_params.correction = cast(
            Literal["none", "fdr", "cluster"], correction_text)

    @Slot()
    def _run_erds(self) -> None:
        self._sync_params()
        self._vm.run_erds_analysis()

    @Slot()
    def _plot_topomaps(self) -> None:
        if not self._vm._erds_result:
            self.status_message.emit("请先运行 ERD/ERS 分析")
            return
        # 打开地形图选择对话框
        self._show_topomap_dialog()

    def _show_topomap_dialog(self) -> None:
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QComboBox
        dlg = QDialog(self)
        dlg.setWindowTitle("绘制 ERD/ERS 地形图")
        layout = QFormLayout(dlg)

        cond_combo = QComboBox()
        if self._vm._erds_result:
            cond_combo.addItems(list(self._vm._erds_result.result.avg_tfrs.keys()))
        layout.addRow("条件:", cond_combo)

        band_combo = QComboBox()
        band_combo.addItems(list(self._vm.erds_params.bands.keys()))
        layout.addRow("频段:", band_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        balance_form(layout)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._vm.plot_erds_topomaps(
                cond_combo.currentText(),
                band_combo.currentText()
            )

    @Slot(object)
    def _on_result_ready(self, result: Any) -> None:
        self.status_message.emit(f"ERD/ERS 完成: {list(result.result.tfrs.keys())}")


class ERDSConditionDialog(QDialog):
    """ERD/ERS 条件添加对话框"""

    def __init__(self, parent: QWidget | None = None, events_list: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加 ERD/ERS 条件")
        self.setModal(True)
        self.resize(400, 400)
        self._events_list = events_list or []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("如: LeftHand, RightHand")
        form.addRow("条件名称 *:", self._edit_name)

        self._lst_events = QListWidget()
        self._lst_events.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for ev in self._events_list:
            self._lst_events.addItem(ev)
        form.addRow("触发事件:", self._lst_events)

        # 时间窗 (ERD/ERS 通常更长)
        row = QHBoxLayout()
        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-10, 10)
        self._spin_tmin.setDecimals(2)
        self._spin_tmin.setValue(-1.0)
        self._spin_tmin.setSuffix(" s")
        row.addWidget(self._spin_tmin)
        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-10, 10)
        self._spin_tmax.setDecimals(2)
        self._spin_tmax.setValue(2.0)
        self._spin_tmax.setSuffix(" s")
        row.addWidget(self._spin_tmax)
        form.addRow("时间窗:", row)

        # 基线
        row = QHBoxLayout()
        self._chk_baseline = QCheckBox("基线校正")
        self._chk_baseline.setChecked(True)
        row.addWidget(self._chk_baseline)
        self._spin_b_tmin = QDoubleSpinBox()
        self._spin_b_tmin.setRange(-10, 0)
        self._spin_b_tmin.setDecimals(2)
        self._spin_b_tmin.setValue(-1.0)
        row.addWidget(self._spin_b_tmin)
        self._spin_b_tmax = QDoubleSpinBox()
        self._spin_b_tmax.setRange(-10, 0)
        self._spin_b_tmax.setDecimals(2)
        self._spin_b_tmax.setValue(-0.5)
        row.addWidget(self._spin_b_tmax)
        form.addRow("基线窗:", row)
        balance_form(form)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_params(self) -> dict[str, Any]:
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
        }