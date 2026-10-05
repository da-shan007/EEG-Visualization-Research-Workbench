"""报告生成面板"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QAbstractItemView,
    QMessageBox, QFileDialog, QDialog, QDialogButtonBox
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.models.visualization import ReportConfig, ExportFormat
from eeg_workbench.utils.ui import balance_form


class ReportWidget(QWidget):
    """报告生成面板"""

    status_message = Signal(str)

    def __init__(self, viewmodel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 基本设置 ----
        basic_group = QGroupBox("报告基本信息")
        basic_layout = QFormLayout(basic_group)

        self._edit_title = QLineEdit("EEG 分析报告")
        basic_layout.addRow("标题:", self._edit_title)

        self._edit_author = QLineEdit()
        basic_layout.addRow("作者:", self._edit_author)

        self._edit_institution = QLineEdit()
        basic_layout.addRow("机构:", self._edit_institution)

        self._cmb_format = QComboBox()
        self._cmb_format.addItems([fmt.value for fmt in ExportFormat])
        self._cmb_format.setCurrentText("pdf")
        basic_layout.addRow("输出格式:", self._cmb_format)
        balance_form(basic_layout)

        layout.addWidget(basic_group)

        # ---- 章节选择 ----
        sections_group = QGroupBox("报告章节")
        sections_layout = QVBoxLayout(sections_group)

        self._lst_sections = QListWidget()
        self._lst_sections.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        default_sections = [
            ("overview", "概览", True),
            ("methods", "方法", True),
            ("preprocessing", "预处理", True),
            ("erp", "ERP 分析", True),
            ("time_frequency", "时频分析", True),
            ("connectivity", "连通性分析", True),
            ("source_localization", "源定位", True),
            ("statistics", "统计分析", True),
            ("conclusion", "结论", False),
        ]
        
        for key, label, default in default_sections:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setCheckState(Qt.CheckState.Checked if default else Qt.CheckState.Unchecked)
            self._lst_sections.addItem(item)
        
        sections_layout.addWidget(self._lst_sections)

        layout.addWidget(sections_group)

        # ---- 选项设置 ----
        options_group = QGroupBox("报告选项")
        options_layout = QFormLayout(options_group)

        self._chk_toc = QCheckBox("包含目录")
        self._chk_toc.setChecked(True)
        options_layout.addRow("", self._chk_toc)

        self._chk_methods = QCheckBox("包含方法章节")
        self._chk_methods.setChecked(True)
        options_layout.addRow("", self._chk_methods)

        self._chk_results = QCheckBox("包含结果章节")
        self._chk_results.setChecked(True)
        options_layout.addRow("", self._chk_results)

        self._chk_discussion = QCheckBox("包含讨论章节")
        options_layout.addRow("", self._chk_discussion)

        self._chk_references = QCheckBox("包含参考文献")
        options_layout.addRow("", self._chk_references)

        self._spin_dpi = QSpinBox()
        self._spin_dpi.setRange(72, 600)
        self._spin_dpi.setValue(300)
        options_layout.addRow("图片 DPI:", self._spin_dpi)

        self._spin_fig_width = QDoubleSpinBox()
        self._spin_fig_width.setRange(5, 30)
        self._spin_fig_width.setDecimals(1)
        self._spin_fig_width.setSingleStep(0.5)
        self._spin_fig_width.setValue(16)
        self._spin_fig_width.setSuffix(" cm")
        options_layout.addRow("图片宽度:", self._spin_fig_width)

        self._spin_fig_height = QDoubleSpinBox()
        self._spin_fig_height.setRange(5, 30)
        self._spin_fig_height.setDecimals(1)
        self._spin_fig_height.setSingleStep(0.5)
        self._spin_fig_height.setValue(12)
        self._spin_fig_height.setSuffix(" cm")
        options_layout.addRow("图片高度:", self._spin_fig_height)
        balance_form(options_layout)

        layout.addWidget(options_group)

        # ---- 模板 ----
        template_group = QGroupBox("自定义模板")
        template_layout = QVBoxLayout(template_group)

        self._btn_load_template = QPushButton("加载自定义模板")
        self._btn_load_template.clicked.connect(self._load_template)
        template_layout.addWidget(self._btn_load_template)

        self._lbl_template = QLabel("当前使用默认模板")
        self._lbl_template.setStyleSheet("color: #666; font-size: 11px;")
        template_layout.addWidget(self._lbl_template)

        layout.addWidget(template_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_preview = QPushButton("预览报告")
        self._btn_preview.clicked.connect(self._preview_report)
        exec_layout.addWidget(self._btn_preview)

        self._btn_generate = QPushButton("生成报告")
        self._btn_generate.setMinimumHeight(40)
        self._btn_generate.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_generate.clicked.connect(self._generate_report)
        exec_layout.addWidget(self._btn_generate)

        layout.addLayout(exec_layout)

        layout.addStretch()

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset):
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _sync_from_vm(self):
        params = self._vm.report_params
        self._block_signals(True)
        try:
            self._edit_title.setText(params.title)
            self._edit_author.setText(params.author)
            self._edit_institution.setText(params.institution)
            self._cmb_format.setCurrentText(params.output_format.value)
            self._chk_toc.setChecked(params.include_toc)
            self._chk_methods.setChecked(params.include_methods)
            self._chk_results.setChecked(params.include_results)
            self._spin_dpi.setValue(params.figure_dpi)
            self._spin_fig_width.setValue(params.figure_width_cm)
            self._spin_fig_height.setValue(params.figure_height_cm)
            
            # 更新章节勾选
            for i in range(self._lst_sections.count()):
                item = self._lst_sections.item(i)
                key = item.data(Qt.ItemDataRole.UserRole)
                if key in params.sections:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool):
        for w in [
            self._edit_title, self._edit_author, self._edit_institution,
            self._cmb_format, self._chk_toc, self._chk_methods,
            self._chk_results, self._chk_discussion, self._chk_references,
            self._spin_dpi, self._spin_fig_width, self._spin_fig_height
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self):
        sections = []
        for i in range(self._lst_sections.count()):
            item = self._lst_sections.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                sections.append(item.data(Qt.ItemDataRole.UserRole))

        params = ReportConfig(
            title=self._edit_title.text(),
            author=self._edit_author.text(),
            institution=self._edit_institution.text(),
            output_format=ExportFormat(self._cmb_format.currentText()),
            include_toc=self._chk_toc.isChecked(),
            include_methods=self._chk_methods.isChecked(),
            include_results=self._chk_results.isChecked(),
            include_discussion=self._chk_discussion.isChecked(),
            include_references=self._chk_references.isChecked(),
            figure_dpi=self._spin_dpi.value(),
            figure_width_cm=self._spin_fig_width.value(),
            figure_height_cm=self._spin_fig_height.value(),
            sections=sections,
        )
        self._vm.set_report_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _load_template(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "加载模板", "", "HTML 模板 (*.html);;Jinja2 模板 (*.j2 *.jinja2)")
        if path:
            self._lbl_template.setText(f"当前模板: {path}")
            self.status_message.emit(f"已加载模板: {path}")

    @Slot()
    def _preview_report(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "预览", "预览功能待实现")

    @Slot()
    def _generate_report(self):
        self._on_param_changed()
        fmt = self._cmb_format.currentText().lower()
        self.status_message.emit(f"正在生成 {fmt.upper()} 报告...")
        self._vm.generate_report(format=fmt)