"""元数据编辑器 Widget：受试者信息、实验条件、采集参数"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QDialogButtonBox, QCheckBox, QScrollArea,
    QLabel
)
from PySide6.QtGui import QAction

from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.models.metadata import SubjectInfo, ExperimentCondition, Sex, GroupType, Handedness


class ConditionDialog(QDialog):
    """实验条件编辑对话框"""

    def __init__(self, parent=None, condition: ExperimentCondition = None):
        super().__init__(parent)
        self.setWindowTitle("编辑实验条件" if condition else "新建实验条件")
        self.setModal(True)
        self.resize(400, 350)
        self._condition = condition
        self._setup_ui()
        if condition:
            self._load_condition(condition)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("如: Target_Stimulus")
        form.addRow("条件名称 *:", self._edit_name)

        self._edit_desc = QTextEdit()
        self._edit_desc.setMaximumHeight(60)
        form.addRow("描述:", self._edit_desc)

        self._edit_codes = QLineEdit()
        self._edit_codes.setPlaceholderText("如: 1,2,3 (逗号分隔)")
        form.addRow("事件编码:", self._edit_codes)

        self._edit_desc_list = QLineEdit()
        self._edit_desc_list.setPlaceholderText("如: Stimulus/S1,Stimulus/S2")
        form.addRow("事件描述:", self._edit_desc_list)

        # 时间窗
        row = QHBoxLayout()
        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(-10, 10)
        self._spin_tmin.setDecimals(3)
        self._spin_tmin.setSingleStep(0.1)
        self._spin_tmin.setValue(-0.2)
        row.addWidget(QLabel("tmin:"))
        row.addWidget(self._spin_tmin)

        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(-10, 10)
        self._spin_tmax.setDecimals(3)
        self._spin_tmax.setSingleStep(0.1)
        self._spin_tmax.setValue(0.8)
        row.addWidget(QLabel("tmax:"))
        row.addWidget(self._spin_tmax)
        form.addRow("时间窗:", row)

        # 基线
        row = QHBoxLayout()
        self._chk_baseline = QCheckBox("启用基线校正")
        self._chk_baseline.setChecked(True)
        row.addWidget(self._chk_baseline)
        self._spin_b_tmin = QDoubleSpinBox()
        self._spin_b_tmin.setRange(-10, 0)
        self._spin_b_tmin.setDecimals(3)
        self._spin_b_tmin.setValue(-0.2)
        row.addWidget(QLabel("基线 tmin:"))
        row.addWidget(self._spin_b_tmin)
        self._spin_b_tmax = QDoubleSpinBox()
        self._spin_b_tmax.setRange(-10, 0)
        self._spin_b_tmax.setDecimals(3)
        self._spin_b_tmax.setValue(0.0)
        row.addWidget(QLabel("基线 tmax:"))
        row.addWidget(self._spin_b_tmax)
        form.addRow("基线窗:", row)

        # 触发类型
        self._cmb_trigger = QComboBox()
        self._cmb_trigger.addItems(["stimulus", "response", "cue", "custom"])
        form.addRow("触发类型:", self._cmb_trigger)

        layout.addLayout(form)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_condition(self, cond: ExperimentCondition):
        self._edit_name.setText(cond.name)
        self._edit_desc.setPlainText(cond.description)
        self._edit_codes.setText(",".join(map(str, cond.event_codes)))
        self._edit_desc_list.setText(",".join(cond.event_descriptions))
        self._spin_tmin.setValue(cond.tmin)
        self._spin_tmax.setValue(cond.tmax)
        if cond.baseline_tmin is not None:
            self._spin_b_tmin.setValue(cond.baseline_tmin)
        if cond.baseline_tmax is not None:
            self._spin_b_tmax.setValue(cond.baseline_tmax)
        self._chk_baseline.setChecked(cond.baseline_tmin is not None)
        idx = self._cmb_trigger.findText(cond.trigger_type)
        if idx >= 0:
            self._cmb_trigger.setCurrentIndex(idx)

    def get_condition(self) -> ExperimentCondition:
        codes = []
        if self._edit_codes.text().strip():
            codes = [int(x.strip()) for x in self._edit_codes.text().split(",") if x.strip()]
        descs = []
        if self._edit_desc_list.text().strip():
            descs = [x.strip() for x in self._edit_desc_list.text().split(",") if x.strip()]

        baseline_tmin = self._spin_b_tmin.value() if self._chk_baseline.isChecked() else None
        baseline_tmax = self._spin_b_tmax.value() if self._chk_baseline.isChecked() else None

        return ExperimentCondition(
            name=self._edit_name.text().strip(),
            description=self._edit_desc.toPlainText().strip(),
            event_codes=codes,
            event_descriptions=descs,
            tmin=self._spin_tmin.value(),
            tmax=self._spin_tmax.value(),
            baseline_tmin=baseline_tmin,
            baseline_tmax=baseline_tmax,
            trigger_type=self._cmb_trigger.currentText(),
        )


class MetadataEditorWidget(QWidget):
    """元数据编辑面板"""

    metadata_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: DataManagementViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # ---- 受试者信息 ----
        self._grp_subject = QGroupBox("受试者信息")
        subj_layout = QFormLayout(self._grp_subject)

        self._edit_subj_id = QLineEdit()
        self._edit_subj_id.setPlaceholderText("如: sub-01")
        self._edit_subj_id.editingFinished.connect(self._on_subject_changed)
        subj_layout.addRow("被试 ID *:", self._edit_subj_id)

        self._spin_age = QSpinBox()
        self._spin_age.setRange(0, 120)
        self._spin_age.setSpecialValueText("未设置")
        self._spin_age.valueChanged.connect(self._on_subject_changed)
        subj_layout.addRow("年龄:", self._spin_age)

        self._cmb_sex = QComboBox()
        self._cmb_sex.addItems([s.value for s in Sex])
        self._cmb_sex.currentTextChanged.connect(self._on_subject_changed)
        subj_layout.addRow("性别:", self._cmb_sex)

        self._cmb_handedness = QComboBox()
        self._cmb_handedness.addItems([h.value for h in Handedness])
        self._cmb_handedness.currentTextChanged.connect(self._on_subject_changed)
        subj_layout.addRow("惯用手:", self._cmb_handedness)

        self._cmb_group = QComboBox()
        self._cmb_group.addItems([g.value for g in GroupType])
        self._cmb_group.currentTextChanged.connect(self._on_subject_changed)
        subj_layout.addRow("分组:", self._cmb_group)

        self._edit_diagnosis = QLineEdit()
        self._edit_diagnosis.setPlaceholderText("ICD-10 编码等")
        self._edit_diagnosis.editingFinished.connect(self._on_subject_changed)
        subj_layout.addRow("诊断:", self._edit_diagnosis)

        self._spin_education = QSpinBox()
        self._spin_education.setRange(0, 30)
        self._spin_education.setSpecialValueText("未设置")
        self._spin_education.valueChanged.connect(self._on_subject_changed)
        subj_layout.addRow("受教育年限:", self._spin_education)

        self._edit_medication = QLineEdit()
        self._edit_medication.setPlaceholderText("用药情况")
        self._edit_medication.editingFinished.connect(self._on_subject_changed)
        subj_layout.addRow("用药:", self._edit_medication)

        self._edit_session = QLineEdit("ses-01")
        self._edit_session.editingFinished.connect(self._on_subject_changed)
        subj_layout.addRow("Session ID:", self._edit_session)

        self._edit_task = QLineEdit()
        self._edit_task.setPlaceholderText("任务名称")
        self._edit_task.editingFinished.connect(self._on_subject_changed)
        subj_layout.addRow("任务名称:", self._edit_task)

        self._content_layout.addWidget(self._grp_subject)

        # ---- 采集参数 ----
        self._grp_acq = QGroupBox("采集参数")
        acq_layout = QFormLayout(self._grp_acq)

        self._edit_institution = QLineEdit()
        self._edit_institution.editingFinished.connect(self._on_acq_changed)
        acq_layout.addRow("机构:", self._edit_institution)

        self._edit_manufacturer = QLineEdit()
        self._edit_manufacturer.editingFinished.connect(self._on_acq_changed)
        acq_layout.addRow("设备厂商:", self._edit_manufacturer)

        self._edit_model = QLineEdit()
        self._edit_model.editingFinished.connect(self._on_acq_changed)
        acq_layout.addRow("设备型号:", self._edit_model)

        self._edit_ref = QLineEdit()
        self._edit_ref.setPlaceholderText("如: FCz, A1+A2, Average")
        self._edit_ref.editingFinished.connect(self._on_acq_changed)
        acq_layout.addRow("参考电极:", self._edit_ref)

        self._edit_ground = QLineEdit()
        self._edit_ground.editingFinished.connect(self._on_acq_changed)
        acq_layout.addRow("接地电极:", self._edit_ground)

        self._cmb_scheme = QComboBox()
        self._cmb_scheme.addItems(["10-20", "10-10", "10-05", "custom"])
        self._cmb_scheme.currentTextChanged.connect(self._on_acq_changed)
        acq_layout.addRow("电极布局:", self._cmb_scheme)

        self._spin_powerline = QDoubleSpinBox()
        self._spin_powerline.setRange(0, 100)
        self._spin_powerline.setValue(50.0)
        self._spin_powerline.setSuffix(" Hz")
        self._spin_powerline.valueChanged.connect(self._on_acq_changed)
        acq_layout.addRow("工频:", self._spin_powerline)

        self._content_layout.addWidget(self._grp_acq)

        # ---- 电极位置 (Montage) ----
        self._grp_montage = QGroupBox("电极位置 (Montage)")
        montage_layout = QFormLayout(self._grp_montage)

        self._cmb_montage = QComboBox()
        self._cmb_montage.addItems([
            "standard_1020", "standard_1005", "biosemi64",
            "biosemi128", "montreal09",
        ])
        montage_layout.addRow("标准蒙太奇:", self._cmb_montage)

        btn_row_montage = QHBoxLayout()
        self._btn_apply_montage = QPushButton("应用蒙太奇")
        self._btn_apply_montage.clicked.connect(self._apply_montage)
        btn_row_montage.addWidget(self._btn_apply_montage)
        btn_row_montage.addStretch()
        self._lbl_montage_status = QLabel("地形图/源定位需要电极位置")
        self._lbl_montage_status.setStyleSheet("color: #666;")
        btn_row_montage.addWidget(self._lbl_montage_status)
        montage_layout.addRow("", btn_row_montage)

        self._content_layout.addWidget(self._grp_montage)

        # ---- 实验条件表格 ----
        self._grp_conditions = QGroupBox("实验条件")
        cond_layout = QVBoxLayout(self._grp_conditions)

        self._tbl_conditions = QTableWidget(0, 5)
        self._tbl_conditions.setHorizontalHeaderLabels([
            "名称", "描述", "事件编码", "时间窗", "触发类型"
        ])
        self._tbl_conditions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl_conditions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_conditions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cond_layout.addWidget(self._tbl_conditions)

        btn_row = QHBoxLayout()
        self._btn_add_cond = QPushButton("添加")
        self._btn_add_cond.clicked.connect(self._add_condition)
        self._btn_edit_cond = QPushButton("编辑")
        self._btn_edit_cond.clicked.connect(self._edit_condition)
        self._btn_del_cond = QPushButton("删除")
        self._btn_del_cond.clicked.connect(self._delete_condition)
        btn_row.addWidget(self._btn_add_cond)
        btn_row.addWidget(self._btn_edit_cond)
        btn_row.addWidget(self._btn_del_cond)
        btn_row.addStretch()
        cond_layout.addLayout(btn_row)

        self._content_layout.addWidget(self._grp_conditions)

        # ---- 任务描述 ----
        self._grp_task = QGroupBox("任务描述")
        task_layout = QVBoxLayout(self._grp_task)
        self._edit_task_desc = QTextEdit()
        self._edit_task_desc.setPlaceholderText("实验范式描述、刺激材料、流程等...")
        self._edit_task_desc.setMaximumHeight(100)
        self._edit_task_desc.textChanged.connect(self._on_task_changed)
        task_layout.addWidget(self._edit_task_desc)
        self._content_layout.addWidget(self._grp_task)

        self._content_layout.addStretch()

        # 初始禁用（无数据集时）
        self.setEnabled(False)

    def _connect_signals(self):
        self._vm.metadata_changed.connect(self._on_metadata_updated)
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    @Slot(object)
    def _on_dataset_changed(self, dataset):
        self.setEnabled(dataset is not None)
        if dataset and dataset.metadata:
            self._load_metadata(dataset.metadata)

    @Slot(object)
    def _on_metadata_updated(self, metadata):
        if metadata:
            self._load_metadata(metadata)

    def _load_metadata(self, meta):
        # 防止递归触发
        self._block_signals(True)
        try:
            # 受试者
            if meta.subject:
                self._edit_subj_id.setText(meta.subject.subject_id)
                self._spin_age.setValue(meta.subject.age or 0)
                self._cmb_sex.setCurrentText(meta.subject.sex.value)
                self._cmb_handedness.setCurrentText(meta.subject.handedness.value)
                self._cmb_group.setCurrentText(meta.subject.group.value)
                self._edit_diagnosis.setText(meta.subject.diagnosis)
                self._spin_education.setValue(meta.subject.education_years or 0)
                self._edit_medication.setText(meta.subject.medication)
                self._edit_session.setText(meta.subject.session_id)
                self._edit_task.setText(meta.subject.task_name)

            # 采集参数
            self._edit_institution.setText(meta.institution_name)
            self._edit_manufacturer.setText(meta.manufacturer)
            self._edit_model.setText(meta.manufacturers_model_name)
            self._edit_ref.setText(meta.eeg_reference)
            self._edit_ground.setText(meta.eeg_ground)
            idx = self._cmb_scheme.findText(meta.eeg_placement_scheme)
            if idx >= 0:
                self._cmb_scheme.setCurrentIndex(idx)
            self._spin_powerline.setValue(meta.power_line_frequency)

            # 任务描述
            self._edit_task_desc.setPlainText(meta.task_description)

            # 条件表格
            self._tbl_conditions.setRowCount(0)
            for cond in meta.conditions:
                self._add_condition_row(cond)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._edit_subj_id, self._spin_age, self._cmb_sex, self._cmb_handedness,
            self._cmb_group, self._edit_diagnosis, self._spin_education, self._edit_medication,
            self._edit_session, self._edit_task,
            self._edit_institution, self._edit_manufacturer, self._edit_model,
            self._edit_ref, self._edit_ground, self._cmb_scheme, self._spin_powerline,
            self._edit_task_desc,
        ]:
            w.blockSignals(block)

    # ---- 受试者变更 ----
    @Slot()
    def _on_subject_changed(self):
        if not self._vm.metadata:
            self._vm.create_subject_info("sub-01")
        subj = self._vm.metadata.subject
        subj.subject_id = self._edit_subj_id.text()
        subj.age = self._spin_age.value() or None
        subj.sex = Sex(self._cmb_sex.currentText())
        subj.handedness = Handedness(self._cmb_handedness.currentText())
        subj.group = GroupType(self._cmb_group.currentText())
        subj.diagnosis = self._edit_diagnosis.text()
        subj.education_years = self._spin_education.value() or None
        subj.medication = self._edit_medication.text()
        subj.session_id = self._edit_session.text()
        subj.task_name = self._edit_task.text()
        self._vm.metadata_changed.emit(self._vm.metadata)
        self.metadata_changed.emit()

    @Slot()
    def _on_acq_changed(self):
        if not self._vm.metadata:
            return
        meta = self._vm.metadata
        meta.institution_name = self._edit_institution.text()
        meta.manufacturer = self._edit_manufacturer.text()
        meta.manufacturers_model_name = self._edit_model.text()
        meta.eeg_reference = self._edit_ref.text()
        meta.eeg_ground = self._edit_ground.text()
        meta.eeg_placement_scheme = self._cmb_scheme.currentText()
        meta.power_line_frequency = self._spin_powerline.value()
        self._vm.metadata_changed.emit(meta)
        self.metadata_changed.emit()

    @Slot()
    def _apply_montage(self):
        """应用标准蒙太奇到当前数据集（电极位置供地形图/源定位使用）"""
        name = self._cmb_montage.currentText()
        try:
            ok = self._vm.apply_standard_montage(name)
        except Exception as exc:  # mne 对不匹配的通道名会抛异常
            self._lbl_montage_status.setText(f"应用失败: {exc}")
            self._lbl_montage_status.setStyleSheet("color: #b00;")
            return
        if ok:
            self._lbl_montage_status.setText(f"已应用 {name}")
            self._lbl_montage_status.setStyleSheet("color: #080;")
        else:
            self._lbl_montage_status.setText(f"失败：通道名与 {name} 不匹配")
            self._lbl_montage_status.setStyleSheet("color: #b00;")

    @Slot()
    def _on_task_changed(self):
        if not self._vm.metadata:
            return
        self._vm.metadata.task_description = self._edit_task_desc.toPlainText()
        self._vm.metadata_changed.emit(self._vm.metadata)
        self.metadata_changed.emit()

    # ---- 条件表格操作 ----
    def _add_condition_row(self, cond: ExperimentCondition):
        row = self._tbl_conditions.rowCount()
        self._tbl_conditions.insertRow(row)
        self._tbl_conditions.setItem(row, 0, QTableWidgetItem(cond.name))
        self._tbl_conditions.setItem(row, 1, QTableWidgetItem(cond.description))
        self._tbl_conditions.setItem(row, 2, QTableWidgetItem(",".join(map(str, cond.event_codes))))
        self._tbl_conditions.setItem(row, 3, QTableWidgetItem(f"[{cond.tmin:.2f}, {cond.tmax:.2f}]"))
        self._tbl_conditions.setItem(row, 4, QTableWidgetItem(cond.trigger_type))
        # 存储完整对象
        self._tbl_conditions.item(row, 0).setData(Qt.ItemDataRole.UserRole, cond)

    def _add_condition(self):
        dlg = ConditionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cond = dlg.get_condition()
            if not cond.name:
                QMessageBox.warning(self, "错误", "条件名称不能为空")
                return
            self._vm.add_condition(cond)
            self._add_condition_row(cond)
            self.metadata_changed.emit()

    def _edit_condition(self):
        row = self._tbl_conditions.currentRow()
        if row < 0:
            return
        item = self._tbl_conditions.item(row, 0)
        cond = item.data(Qt.ItemDataRole.UserRole)
        dlg = ConditionDialog(self, cond)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cond = dlg.get_condition()
            # 更新元数据
            if self._vm.metadata:
                for i, c in enumerate(self._vm.metadata.conditions):
                    if c.name == cond.name:
                        self._vm.metadata.conditions[i] = new_cond
                        break
            # 更新表格
            self._tbl_conditions.item(row, 0).setText(new_cond.name)
            self._tbl_conditions.item(row, 0).setData(Qt.ItemDataRole.UserRole, new_cond)
            self._tbl_conditions.item(row, 1).setText(new_cond.description)
            self._tbl_conditions.item(row, 2).setText(",".join(map(str, new_cond.event_codes)))
            self._tbl_conditions.item(row, 3).setText(f"[{new_cond.tmin:.2f}, {new_cond.tmax:.2f}]")
            self._tbl_conditions.item(row, 4).setText(new_cond.trigger_type)
            self.metadata_changed.emit()

    def _delete_condition(self):
        row = self._tbl_conditions.currentRow()
        if row < 0:
            return
        item = self._tbl_conditions.item(row, 0)
        cond_name = item.text()
        if self._vm.metadata:
            self._vm.metadata.conditions = [c for c in self._vm.metadata.conditions if c.name != cond_name]
        self._tbl_conditions.removeRow(row)
        self.metadata_changed.emit()