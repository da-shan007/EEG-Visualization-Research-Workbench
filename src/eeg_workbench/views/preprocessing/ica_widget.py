"""ICA 面板：拟合、自动识别、成分可视化、手动排除"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QLabel,
    QCheckBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QSplitter, QFrame, QProgressBar, QMessageBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtGui import QColor, QBrush

from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.models.preprocessing import ICAParams, ICAComponentType
from eeg_workbench.services.preprocessing import ICAService, ICAResult


class ICAFitWorker(QObject):
    """ICA 拟合工作线程"""
    finished = Signal(object)  # ICAResult
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, vm: PreprocessingViewModel, params: ICAParams):
        super().__init__()
        self._vm = vm
        self._params = params

    def run(self):
        try:
            service = ICAService()
            result = service.fit(self._vm.dataset, self._params)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ICAWidget(QWidget):
    """ICA 面板：参数设置、拟合、成分管理、可视化"""

    status_message = Signal(str)

    def __init__(self, viewmodel: PreprocessingViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._ica_result: Optional[ICAResult] = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[ICAFitWorker] = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()

        self._btn_fit = QPushButton("拟合 ICA")
        self._btn_fit.setMinimumHeight(36)
        self._btn_fit.clicked.connect(self._run_fit)
        toolbar.addWidget(self._btn_fit)

        self._btn_apply = QPushButton("应用 ICA")
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._run_apply)
        toolbar.addWidget(self._btn_apply)

        self._btn_fit_apply = QPushButton("拟合并应用")
        self._btn_fit_apply.clicked.connect(self._run_fit_apply)
        toolbar.addWidget(self._btn_fit_apply)

        toolbar.addStretch()

        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setVisible(False)
        toolbar.addWidget(self._progress)

        layout.addLayout(toolbar)

        # ---- 主分割器 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：参数与成分列表
        left_widget = self._create_left_panel()
        splitter.addWidget(left_widget)

        # 右侧：可视化选项
        right_widget = self._create_right_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter, 1)

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板：参数 + 成分表格"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 参数组
        param_group = QGroupBox("ICA 参数")
        param_layout = QFormLayout(param_group)

        self._spin_n_components = QSpinBox()
        self._spin_n_components.setRange(1, 256)
        self._spin_n_components.setSpecialValueText("自动 (0.999 方差)")
        self._spin_n_components.setValue(0)
        self._spin_n_components.valueChanged.connect(self._on_param_changed)
        param_layout.addRow("成分数:", self._spin_n_components)

        self._cmb_method = QComboBox()
        self._cmb_method.addItems(["fastica", "infomax", "extended-infomax", "picard"])
        self._cmb_method.setCurrentText("fastica")
        self._cmb_method.currentTextChanged.connect(self._on_param_changed)
        param_layout.addRow("算法:", self._cmb_method)

        self._spin_max_iter = QSpinBox()
        self._spin_max_iter.setRange(100, 5000)
        self._spin_max_iter.setValue(500)
        self._spin_max_iter.setSingleStep(100)
        param_layout.addRow("最大迭代:", self._spin_max_iter)

        self._spin_decim = QSpinBox()
        self._spin_decim.setRange(1, 10)
        self._spin_decim.setValue(3)
        param_layout.addRow("降采样因子:", self._spin_decim)

        self._spin_random_state = QSpinBox()
        self._spin_random_state.setRange(0, 999999)
        self._spin_random_state.setValue(42)
        param_layout.addRow("随机种子:", self._spin_random_state)

        # 自动识别选项
        self._chk_auto_find = QCheckBox("自动识别伪影成分")
        self._chk_auto_find.setChecked(True)
        self._chk_auto_find.toggled.connect(self._on_param_changed)
        param_layout.addRow("", self._chk_auto_find)

        self._cmb_eog_ch = QComboBox()
        self._cmb_eog_ch.addItems(["自动检测", "VEOG", "HEOG", "EOG1", "EOG2"])
        self._cmb_eog_ch.setEditable(True)
        param_layout.addRow("EOG 通道:", self._cmb_eog_ch)

        self._cmb_ecg_ch = QComboBox()
        self._cmb_ecg_ch.addItems(["自动检测", "ECG", "EKG"])
        self._cmb_ecg_ch.setEditable(True)
        param_layout.addRow("ECG 通道:", self._cmb_ecg_ch)

        self._spin_eog_thresh = QDoubleSpinBox()
        self._spin_eog_thresh.setRange(0, 1)
        self._spin_eog_thresh.setDecimals(2)
        self._spin_eog_thresh.setSingleStep(0.05)
        self._spin_eog_thresh.setValue(0.3)
        param_layout.addRow("EOG 阈值:", self._spin_eog_thresh)

        self._spin_ecg_thresh = QDoubleSpinBox()
        self._spin_ecg_thresh.setRange(0, 1)
        self._spin_ecg_thresh.setDecimals(2)
        self._spin_ecg_thresh.setSingleStep(0.05)
        self._spin_ecg_thresh.setValue(0.3)
        param_layout.addRow("ECG 阈值:", self._spin_ecg_thresh)

        self._spin_muscle_thresh = QDoubleSpinBox()
        self._spin_muscle_thresh.setRange(0, 1)
        self._spin_muscle_thresh.setDecimals(2)
        self._spin_muscle_thresh.setSingleStep(0.05)
        self._spin_muscle_thresh.setValue(0.5)
        param_layout.addRow("肌肉阈值:", self._spin_muscle_thresh)

        layout.addWidget(param_group)

        # 成分表格
        comp_group = QGroupBox("ICA 成分")
        comp_layout = QVBoxLayout(comp_group)

        self._comp_table = QTableWidget(0, 5)
        self._comp_table.setHorizontalHeaderLabels(["索引", "类型", "EOG相关", "ECG相关", "肌肉比"])
        self._comp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._comp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._comp_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._comp_table.itemSelectionChanged.connect(self._on_component_selection_changed)
        comp_layout.addWidget(self._comp_table)

        # 成分操作按钮
        comp_btn_layout = QHBoxLayout()
        self._btn_exclude = QPushButton("标记为排除")
        self._btn_exclude.clicked.connect(lambda: self._mark_components("exclude"))
        self._btn_include = QPushButton("标记为保留")
        self._btn_include.clicked.connect(lambda: self._mark_components("include"))
        self._btn_clear_mark = QPushButton("清除标记")
        self._btn_clear_mark.clicked.connect(lambda: self._mark_components("clear"))
        comp_btn_layout.addWidget(self._btn_exclude)
        comp_btn_layout.addWidget(self._btn_include)
        comp_btn_layout.addWidget(self._btn_clear_mark)
        comp_btn_layout.addStretch()
        comp_layout.addLayout(comp_btn_layout)

        layout.addWidget(comp_group, 1)

        return widget

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板：可视化控制"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 可视化选项标签页
        tabs = QTabWidget()

        # 成分地形图
        topo_tab = QWidget()
        topo_layout = QVBoxLayout(topo_tab)
        self._btn_plot_components = QPushButton("绘制成分地形图")
        self._btn_plot_components.clicked.connect(self._plot_components)
        topo_layout.addWidget(self._btn_plot_components)
        self._btn_plot_sources = QPushButton("绘制成分时间序列")
        self._btn_plot_sources.clicked.connect(self._plot_sources)
        topo_layout.addWidget(self._btn_plot_sources)
        self._btn_plot_properties = QPushButton("绘制选中成分属性")
        self._btn_plot_properties.clicked.connect(self._plot_properties)
        topo_layout.addWidget(self._btn_plot_properties)
        topo_layout.addStretch()
        tabs.addTab(topo_tab, "可视化")

        # 成分详情
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        self._lbl_comp_detail = QLabel("选中成分查看详情")
        self._lbl_comp_detail.setWordWrap(True)
        self._lbl_comp_detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.addWidget(self._lbl_comp_detail)
        tabs.addTab(detail_tab, "成分详情")

        layout.addWidget(tabs)

        return widget

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.ica_ready.connect(self._on_ica_ready)
        self._vm.ica_component_selected.connect(self._on_component_selected)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            # 更新通道下拉框
            self._update_channel_combos(dataset.ch_names)
            # 设置默认成分数
            self._spin_n_components.setMaximum(dataset.n_channels)

    def _update_channel_combos(self, channels: list[str]):
        # EOG 通道
        self._cmb_eog_ch.clear()
        self._cmb_eog_ch.addItem("自动检测")
        eog_candidates = [ch for ch in channels if any(x in ch.upper() for x in ["EOG", "VEOG", "HEOG"])]
        for ch in eog_candidates or channels:
            self._cmb_eog_ch.addItem(ch)

        # ECG 通道
        self._cmb_ecg_ch.clear()
        self._cmb_ecg_ch.addItem("自动检测")
        ecg_candidates = [ch for ch in channels if any(x in ch.upper() for x in ["ECG", "EKG"])]
        for ch in ecg_candidates or channels:
            self._cmb_ecg_ch.addItem(ch)

    def _sync_from_vm(self):
        params = self._vm.ica_params
        self._block_signals(True)
        try:
            self._spin_n_components.setValue(int(params.n_components or 0))
            self._cmb_method.setCurrentText(params.method)
            self._spin_max_iter.setValue(params.max_iter)
            self._spin_decim.setValue(params.decim)
            self._spin_random_state.setValue(params.random_state)
            self._chk_auto_find.setChecked(params.auto_find)
            self._spin_eog_thresh.setValue(params.eog_threshold)
            self._spin_ecg_thresh.setValue(params.ecg_threshold)
            self._spin_muscle_thresh.setValue(params.muscle_threshold)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._spin_n_components, self._cmb_method, self._spin_max_iter,
            self._spin_decim, self._spin_random_state, self._chk_auto_find,
            self._spin_eog_thresh, self._spin_ecg_thresh, self._spin_muscle_thresh,
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        params = ICAParams(
            n_components=self._spin_n_components.value() if self._spin_n_components.value() > 0 else None,
            method=self._cmb_method.currentText(),
            max_iter=self._spin_max_iter.value(),
            decim=self._spin_decim.value(),
            random_state=self._spin_random_state.value(),
            auto_find=self._chk_auto_find.isChecked(),
            eog_channels=[self._cmb_eog_ch.currentText()] if self._cmb_eog_ch.currentText() != "自动检测" else [],
            ecg_channels=[self._cmb_ecg_ch.currentText()] if self._cmb_ecg_ch.currentText() != "自动检测" else [],
            eog_threshold=self._spin_eog_thresh.value(),
            ecg_threshold=self._spin_ecg_thresh.value(),
            muscle_threshold=self._spin_muscle_thresh.value(),
        )
        self._vm.set_ica_params(**params.__dict__)

    @Slot()
    def _run_fit(self):
        if not self._vm.dataset:
            return
        self._btn_fit.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)  # 不定进度

        self._worker_thread = QThread()
        self._worker = ICAFitWorker(self._vm, self._vm.ica_params)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_fit_finished)
        self._worker.error.connect(self._on_fit_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    @Slot(object)
    def _on_fit_finished(self, result: ICAResult):
        self._worker_thread = None
        self._worker = None
        self._btn_fit.setEnabled(True)
        self._progress.setVisible(False)
        # 结果通过 ica_ready 信号传递

    @Slot(str)
    def _on_fit_error(self, error: str):
        self._btn_fit.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "ICA 拟合失败", error)

    @Slot(object)
    def _on_ica_ready(self, result: ICAResult):
        self._ica_result = result
        self._btn_apply.setEnabled(True)
        self._populate_component_table(result)
        self.status_message.emit(f"ICA 拟合完成: {result.ica.n_components_} 个成分")

    def _populate_component_table(self, result: ICAResult):
        self._comp_table.setRowCount(0)
        n_comp = result.ica.n_components_
        self._comp_table.setRowCount(n_comp)

        for i in range(n_comp):
            # 索引
            self._comp_table.setItem(i, 0, QTableWidgetItem(str(i)))

            # 类型
            label = result.component_labels.get(i, "未识别")
            item = QTableWidgetItem(label)
            if "exclude" in label or label in ("eye_blink", "eye_movement", "heartbeat", "muscle", "line_noise"):
                item.setBackground(QBrush(QColor("#ffeaea")))
            self._comp_table.setItem(i, 1, item)

            # EOG 相关性
            eog_corr = result.component_properties.get(i, {}).get("eog_correlation", 0)
            self._comp_table.setItem(i, 2, QTableWidgetItem(f"{eog_corr:.3f}"))

            # ECG 相关性
            ecg_corr = result.component_properties.get(i, {}).get("ecg_correlation", 0)
            self._comp_table.setItem(i, 3, QTableWidgetItem(f"{ecg_corr:.3f}"))

            # 肌肉比
            muscle_ratio = result.component_properties.get(i, {}).get("muscle_ratio", 0)
            self._comp_table.setItem(i, 4, QTableWidgetItem(f"{muscle_ratio:.3f}"))

        # 选中自动排除的
        for i in result.components_excluded:
            self._comp_table.selectRow(i)

    @Slot()
    def _on_component_selection_changed(self):
        rows = self._comp_table.selectionModel().selectedRows()
        if rows and self._ica_result:
            idx = rows[0].row()
            props = self._ica_result.component_properties.get(idx, {})
            label = self._ica_result.component_labels.get(idx, "未识别")
            self._lbl_comp_detail.setText(
                f"<b>成分 {idx}</b> - {label}<br>"
                f"EOG 相关: {props.get('eog_correlation', 0):.3f}<br>"
                f"ECG 相关: {props.get('ecg_correlation', 0):.3f}<br>"
                f"肌肉比: {props.get('muscle_ratio', 0):.3f}<br>"
                f"工频功率: {props.get('line_power', 0):.3f}"
            )
            self._vm.ica_component_selected.emit(idx, props)

    @Slot(int, dict)
    def _on_component_selected(self, comp_idx: int, properties: dict):
        if 0 <= comp_idx < self._comp_table.rowCount():
            self._comp_table.selectRow(comp_idx)

    @Slot()
    def _mark_components(self, action: str):
        if not self._ica_result:
            return
        rows = self._comp_table.selectionModel().selectedRows()
        if not rows:
            return

        indices = [r.row() for r in rows]
        if action == "exclude":
            for idx in indices:
                if idx not in self._ica_result.components_excluded:
                    self._ica_result.components_excluded.append(idx)
                self._ica_result.component_labels[idx] = "manual_exclude"
        elif action == "include":
            for idx in indices:
                if idx in self._ica_result.components_excluded:
                    self._ica_result.components_excluded.remove(idx)
                self._ica_result.component_labels.pop(idx, None)
        elif action == "clear":
            for idx in indices:
                self._ica_result.component_labels.pop(idx, None)

        self._populate_component_table(self._ica_result)
        self._vm.set_ica_exclude(self._ica_result.components_excluded)

    @Slot()
    def _run_apply(self):
        if not self._ica_result:
            return
        self._vm.run_ica_apply(self._ica_result.components_excluded)

    @Slot()
    def _run_fit_apply(self):
        self._vm.run_ica_fit_apply()

    @Slot()
    def _plot_components(self):
        if self._ica_result:
            self._vm.plot_ica_components()

    @Slot()
    def _plot_sources(self):
        if self._ica_result and self._vm.dataset:
            self._vm.plot_ica_sources()

    @Slot()
    def _plot_properties(self):
        rows = self._comp_table.selectionModel().selectedRows()
        if rows and self._ica_result and self._vm.dataset:
            picks = [r.row() for r in rows]
            self._vm.plot_ica_properties(picks)