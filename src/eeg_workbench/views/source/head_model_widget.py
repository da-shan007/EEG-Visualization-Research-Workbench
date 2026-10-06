"""头模型构建面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QLineEdit, QDoubleSpinBox, QCheckBox,
    QSpinBox, QLabel, QFileDialog, QMessageBox
)

from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.models.source import HeadModelParams, HeadModelType, STANDARD_HEAD_MODELS
from eeg_workbench.services.source.head_model import HeadModelService
from eeg_workbench.services.source.preview_plots import (
    fig_bem_geometry, fig_sphere_geometry, extract_sensor_xy,
)
from eeg_workbench.utils.ui import balance_form, embed_figure


class HeadModelWidget(QWidget):
    """头模型构建面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: SourceViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 预设选择 ----
        preset_group = QGroupBox("头模型预设")
        preset_layout = QHBoxLayout(preset_group)

        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(STANDARD_HEAD_MODELS.keys()))
        self._cmb_preset.setCurrentText("fsaverage_bem")
        preset_layout.addWidget(QLabel("预设:"))
        preset_layout.addWidget(self._cmb_preset)

        self._btn_apply_preset = QPushButton("应用预设")
        self._btn_apply_preset.clicked.connect(self._apply_preset)
        preset_layout.addWidget(self._btn_apply_preset)
        preset_layout.addStretch()

        layout.addWidget(preset_group)

        # ---- 模型类型 ----
        type_group = QGroupBox("模型类型")
        type_layout = QFormLayout(type_group)

        self._cmb_type = QComboBox()
        # 只列出本机可构建的类型（FEM/多层需外部求解器，后端不支持）
        self._cmb_type.addItems(
            [m.value for m in HeadModelService.SUPPORTED_MODEL_TYPES]
        )
        self._cmb_type.setCurrentText("bem")
        self._cmb_type.currentTextChanged.connect(self._on_type_changed)
        type_layout.addRow("类型:", self._cmb_type)
        balance_form(type_layout)

        layout.addWidget(type_group)

        # ---- BEM 参数 ----
        self._bem_group = QGroupBox("BEM 参数 (3层模型)")
        bem_layout = QFormLayout(self._bem_group)

        self._spin_scalp = QDoubleSpinBox()
        self._spin_scalp.setRange(0.1, 1.0)
        self._spin_scalp.setDecimals(3)
        self._spin_scalp.setSingleStep(0.01)
        self._spin_scalp.setValue(0.3)
        self._spin_scalp.setSuffix(" S/m")
        bem_layout.addRow("头皮导电率:", self._spin_scalp)

        self._spin_skull = QDoubleSpinBox()
        self._spin_skull.setRange(0.001, 0.1)
        self._spin_skull.setDecimals(4)
        self._spin_skull.setSingleStep(0.001)
        self._spin_skull.setValue(0.006)
        self._spin_skull.setSuffix(" S/m")
        bem_layout.addRow("颅骨导电率:", self._spin_skull)

        self._spin_brain = QDoubleSpinBox()
        self._spin_brain.setRange(0.1, 1.0)
        self._spin_brain.setDecimals(3)
        self._spin_brain.setSingleStep(0.01)
        self._spin_brain.setValue(0.3)
        self._spin_brain.setSuffix(" S/m")
        bem_layout.addRow("脑导电率:", self._spin_brain)

        self._edit_subject = QLineEdit("fsaverage")
        self._edit_subject.setPlaceholderText("fsaverage 或自定义 subject")
        bem_layout.addRow("Subject:", self._edit_subject)

        self._edit_subjects_dir = QLineEdit()
        self._edit_subjects_dir.setPlaceholderText("可选: SUBJECTS_DIR 路径")
        self._btn_browse_subjects = QPushButton("浏览...")
        self._btn_browse_subjects.clicked.connect(self._browse_subjects_dir)
        row = QHBoxLayout()
        row.addWidget(self._edit_subjects_dir)
        row.addWidget(self._btn_browse_subjects)
        bem_layout.addRow("Subjects Dir:", row)

        self._chk_custom_trans = QCheckBox("使用自定义变换文件")
        bem_layout.addRow("", self._chk_custom_trans)

        self._edit_trans_file = QLineEdit()
        self._edit_trans_file.setEnabled(False)
        self._edit_trans_file.setPlaceholderText("选择 .trans.fif 文件")
        self._btn_browse_trans = QPushButton("浏览...")
        self._btn_browse_trans.setEnabled(False)
        self._btn_browse_trans.clicked.connect(self._browse_trans)
        trans_row = QHBoxLayout()
        trans_row.addWidget(self._edit_trans_file)
        trans_row.addWidget(self._btn_browse_trans)
        bem_layout.addRow("变换文件:", trans_row)
        balance_form(bem_layout)

        self._chk_custom_trans.toggled.connect(self._edit_trans_file.setEnabled)
        self._chk_custom_trans.toggled.connect(self._btn_browse_trans.setEnabled)

        layout.addWidget(self._bem_group)

        # ---- 球形模型参数 ----
        self._sphere_group = QGroupBox("球形模型参数")
        self._sphere_group.setVisible(False)
        sphere_layout = QFormLayout(self._sphere_group)

        self._spin_sphere_radius = QDoubleSpinBox()
        self._spin_sphere_radius.setRange(0.05, 0.2)
        self._spin_sphere_radius.setDecimals(3)
        self._spin_sphere_radius.setSingleStep(0.005)
        self._spin_sphere_radius.setValue(0.1)
        self._spin_sphere_radius.setSuffix(" m")
        sphere_layout.addRow("半径:", self._spin_sphere_radius)

        self._spin_sphere_x = QDoubleSpinBox()
        self._spin_sphere_x.setRange(-0.1, 0.1)
        self._spin_sphere_x.setDecimals(3)
        self._spin_sphere_x.setValue(0.0)
        sphere_layout.addRow("中心 X:", self._spin_sphere_x)

        self._spin_sphere_y = QDoubleSpinBox()
        self._spin_sphere_y.setRange(-0.1, 0.1)
        self._spin_sphere_y.setDecimals(3)
        self._spin_sphere_y.setValue(0.0)
        sphere_layout.addRow("中心 Y:", self._spin_sphere_y)

        self._spin_sphere_z = QDoubleSpinBox()
        self._spin_sphere_z.setRange(-0.1, 0.1)
        self._spin_sphere_z.setDecimals(3)
        self._spin_sphere_z.setValue(0.04)
        sphere_layout.addRow("中心 Z:", self._spin_sphere_z)
        balance_form(sphere_layout)

        layout.addWidget(self._sphere_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_build = QPushButton("构建头模型")
        self._btn_build.setMinimumHeight(40)
        self._btn_build.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_build.clicked.connect(self._run_build)
        exec_layout.addWidget(self._btn_build)
        layout.addLayout(exec_layout)

        # ---- 在线预览 ----
        preview_group = QGroupBox("在线预览")
        preview_layout = QVBoxLayout(preview_group)
        self._lbl_preview_hint = QLabel("构建头模型后，在此显示几何预览。")
        self._lbl_preview_hint.setStyleSheet("color: #888; font-size: 12px;")
        self._lbl_preview_hint.setWordWrap(True)
        preview_layout.addWidget(self._lbl_preview_hint)
        self._preview_layout = QVBoxLayout()
        preview_layout.addLayout(self._preview_layout)
        layout.addWidget(preview_group)

        layout.addStretch()

        self._fig_canvas = None
        self._connect_type_signals()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.head_model_ready.connect(self._on_head_model_preview)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _connect_type_signals(self) -> None:
        self._cmb_type.currentTextChanged.connect(self._on_type_changed)

    @Slot(str)
    def _on_type_changed(self, type_str: str) -> None:
        is_bem = type_str == "bem"
        is_sphere = type_str == "spherical"

        self._bem_group.setVisible(is_bem)
        self._sphere_group.setVisible(is_sphere)
        self._on_param_changed()

    def _apply_preset(self) -> None:
        preset = self._cmb_preset.currentText()
        self._vm.apply_head_model_preset(preset)
        self._sync_from_vm()
        self.status_message.emit(f"已应用预设: {preset}")

    def _sync_from_vm(self) -> None:
        params = self._vm.head_model_params
        self._block_signals(True)
        try:
            self._cmb_type.setCurrentText(params.model_type.value)
            self._spin_scalp.setValue(params.conductivity[0] if len(params.conductivity) > 0 else 0.3)
            self._spin_skull.setValue(params.conductivity[1] if len(params.conductivity) > 1 else 0.006)
            self._spin_brain.setValue(params.conductivity[2] if len(params.conductivity) > 2 else 0.3)
            self._edit_subject.setText(params.subject)
            self._edit_subjects_dir.setText(params.subjects_dir or "")
            if params.sphere_radius:
                self._spin_sphere_radius.setValue(params.sphere_radius)
            if params.sphere_center:
                self._spin_sphere_x.setValue(params.sphere_center[0])
                self._spin_sphere_y.setValue(params.sphere_center[1])
                self._spin_sphere_z.setValue(params.sphere_center[2])
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [self._cmb_type, self._spin_scalp, self._spin_skull, self._spin_brain,
                  self._edit_subject, self._edit_subjects_dir, self._spin_sphere_radius,
                  self._spin_sphere_x, self._spin_sphere_y, self._spin_sphere_z]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self) -> None:
        params = HeadModelParams(
            model_type=HeadModelType(self._cmb_type.currentText()),
            conductivity=(self._spin_scalp.value(), self._spin_skull.value(), self._spin_brain.value()),
            subject=self._edit_subject.text(),
            subjects_dir=self._edit_subjects_dir.text() or None,
            sphere_radius=self._spin_sphere_radius.value(),
            sphere_center=(self._spin_sphere_x.value(), self._spin_sphere_y.value(), self._spin_sphere_z.value()),
        )
        self._vm.set_head_model_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _browse_subjects_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, "选择 SUBJECTS_DIR")
        if dir_path:
            self._edit_subjects_dir.setText(dir_path)

    @Slot()
    def _browse_trans(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "选择变换文件", "", "FIF 文件 (*.fif *.trans.fif)")
        if path:
            self._edit_trans_file.setText(path)

    @Slot()
    def _run_build(self) -> None:
        self._vm.run_head_model()

    @Slot(object)
    def _on_head_model_preview(self, result: Any) -> None:
        """构建完成后渲染几何预览（失败只提示，不弹错）。"""
        try:
            if result.model_type == HeadModelType.BEM:
                fig = fig_bem_geometry(result.model)
                hint = "BEM 三层表面几何（MRI 坐标；传感器对齐需 trans 文件）"
            else:
                ch_pos, ch_names = None, None
                if self._vm._dataset is not None:
                    info = self._vm._dataset.to_mne_raw().info
                    ch_pos, ch_names = extract_sensor_xy(info)
                fig = fig_sphere_geometry(result.model, ch_pos, ch_names)
                hint = "球形头模型截面 + 传感器投影"
            self._fig_canvas = embed_figure(self._preview_layout, fig)
            self._lbl_preview_hint.setText(hint)
        except Exception as e:
            self._lbl_preview_hint.setText(f"预览生成失败: {e}")
            self.status_message.emit(f"头模型预览失败: {e}")