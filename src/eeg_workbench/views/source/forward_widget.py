"""前向模型 (导场矩阵) 面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QLabel, QMessageBox
)

from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.models.source import ForwardModelParams, SourceSpaceType
from eeg_workbench.utils.ui import balance_form, embed_figure


class ForwardModelWidget(QWidget):
    """前向模型计算面板"""

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

        # ---- 状态信息 ----
        self._lbl_info = QLabel("数据集: --")
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self._lbl_info)

        self._lbl_head_model = QLabel("头模型: --")
        self._lbl_head_model.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self._lbl_head_model)

        self._lbl_fwd_info = QLabel("导场矩阵: --")
        self._lbl_fwd_info.setWordWrap(True)
        self._lbl_fwd_info.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self._lbl_fwd_info)

        # ---- 源空间设置 ----
        src_group = QGroupBox("源空间设置")
        src_layout = QFormLayout(src_group)

        self._cmb_src_type = QComboBox()
        self._cmb_src_type.addItems([s.value for s in SourceSpaceType])
        self._cmb_src_type.setCurrentText("surface")
        src_layout.addRow("源空间类型:", self._cmb_src_type)

        self._cmb_spacing = QComboBox()
        self._cmb_spacing.addItems(["oct6", "oct5", "ico5", "ico4", "all"])
        self._cmb_spacing.setCurrentText("oct6")
        src_layout.addRow("皮层间距:", self._cmb_spacing)

        self._spin_volume_spacing = QDoubleSpinBox()
        self._spin_volume_spacing.setRange(2, 20)
        self._spin_volume_spacing.setDecimals(1)
        self._spin_volume_spacing.setSingleStep(0.5)
        self._spin_volume_spacing.setValue(7.0)
        self._spin_volume_spacing.setSuffix(" mm")
        self._spin_volume_spacing.setVisible(False)
        src_layout.addRow("体积间距:", self._spin_volume_spacing)

        self._chk_add_dist = QCheckBox("计算源-传感器距离")
        self._chk_add_dist.setChecked(True)
        src_layout.addRow("", self._chk_add_dist)

        self._chk_fixed = QCheckBox("固定法向朝向")
        self._chk_fixed.setChecked(True)
        src_layout.addRow("", self._chk_fixed)

        self._chk_use_cps = QCheckBox("皮层面补偿 (CPS)")
        self._chk_use_cps.setChecked(True)
        src_layout.addRow("", self._chk_use_cps)
        balance_form(src_layout)

        layout.addWidget(src_group)

        # ---- 导场计算设置 ----
        fwd_group = QGroupBox("导场计算")
        fwd_layout = QFormLayout(fwd_group)

        self._chk_eeg = QCheckBox("EEG")
        self._chk_eeg.setChecked(True)
        self._chk_eeg.setEnabled(False)  # 本项目主要做 EEG
        fwd_layout.addRow("", self._chk_eeg)

        self._chk_meg = QCheckBox("MEG")
        fwd_layout.addRow("", self._chk_meg)

        self._spin_mindist = QDoubleSpinBox()
        self._spin_mindist.setRange(0.001, 0.05)
        self._spin_mindist.setDecimals(3)
        self._spin_mindist.setSingleStep(0.001)
        self._spin_mindist.setValue(0.005)
        self._spin_mindist.setSuffix(" m")
        fwd_layout.addRow("最小源-传感器距离:", self._spin_mindist)

        self._spin_n_jobs = QSpinBox()
        self._spin_n_jobs.setRange(-1, 64)
        self._spin_n_jobs.setValue(-1)
        self._spin_n_jobs.setSpecialValueText("自动 (所有核心)")
        fwd_layout.addRow("并行作业数:", self._spin_n_jobs)
        balance_form(fwd_layout)

        layout.addWidget(fwd_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_compute = QPushButton("计算导场矩阵")
        self._btn_compute.setMinimumHeight(40)
        self._btn_compute.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_compute.clicked.connect(self._run_forward)
        exec_layout.addWidget(self._btn_compute)

        self._btn_plot_sensitivity = QPushButton("绘制敏感度图")
        self._btn_plot_sensitivity.clicked.connect(self._plot_sensitivity)
        exec_layout.addWidget(self._btn_plot_sensitivity)

        layout.addLayout(exec_layout)

        # ---- 在线预览 ----
        preview_group = QGroupBox("在线预览")
        preview_layout = QVBoxLayout(preview_group)
        self._lbl_preview_hint = QLabel("计算导场矩阵后，在此显示敏感度预览。")
        self._lbl_preview_hint.setStyleSheet("color: #888; font-size: 12px;")
        self._lbl_preview_hint.setWordWrap(True)
        preview_layout.addWidget(self._lbl_preview_hint)
        self._preview_layout = QVBoxLayout()
        preview_layout.addLayout(self._preview_layout)
        layout.addWidget(preview_group)

        layout.addStretch()

        self._fig_canvas = None

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.head_model_ready.connect(self._on_head_model_ready)
        self._vm.forward_model_ready.connect(self._on_forward_ready)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)
        if dataset:
            self._lbl_info.setText(f"数据集: {dataset.name} | {dataset.n_channels} 通道 | {dataset.sfreq:.1f} Hz")

    def _on_head_model_ready(self, result: Any) -> None:
        self._lbl_head_model.setText(f"头模型: {result.model_type.value} ({result.subject})")
        self._btn_compute.setEnabled(True)

    def _on_forward_ready(self, result: Any) -> None:
        info = result.leadfield_info
        self._lbl_fwd_info.setText(
            f"导场矩阵: {info['n_sources']} 源 × {info['n_channels']} 通道 | "
            f"类型: {info['src_type']}"
        )
        self.status_message.emit(f"导场矩阵计算完成: {info['n_sources']} 个源")
        self._render_sensitivity()

    @Slot()
    def _run_forward(self) -> None:
        if not self._vm._head_model_result:
            QMessageBox.warning(self, "提示", "请先构建头模型")
            return
        self._btn_compute.setEnabled(False)
        self._btn_compute.setText("计算中...")
        self._vm.run_forward_model()
        self._btn_compute.setEnabled(True)
        self._btn_compute.setText("计算导场矩阵")

    @Slot()
    def _plot_sensitivity(self) -> None:
        self._render_sensitivity()

    def _render_sensitivity(self) -> None:
        """敏感度图内嵌渲染（替代原来的外部弹窗）。"""
        if not self._vm._forward_result:
            return
        try:
            from eeg_workbench.services.source import ForwardModelService
            fig = ForwardModelService.plot_sensitivity(self._vm._forward_result.fwd)
            self._fig_canvas = embed_figure(self._preview_layout, fig)
            self._lbl_preview_hint.setText("导场敏感度：源位置投影着色（体/面源通用）")
        except Exception as e:
            self._lbl_preview_hint.setText(f"敏感度图生成失败: {e}")
            self.status_message.emit(f"敏感度图失败: {e}")

    def _sync_from_vm(self) -> None:
        params = self._vm.forward_params
        self._block_signals(True)
        try:
            self._cmb_src_type.setCurrentText(params.source_space_type.value)
            self._cmb_spacing.setCurrentText(params.spacing if isinstance(params.spacing, str) else "oct6")
            self._spin_volume_spacing.setValue(params.spacing if isinstance(params.spacing, (int, float)) else 7.0)
            self._chk_add_dist.setChecked(params.add_dist)
            self._chk_fixed.setChecked(params.fixed)
            self._chk_use_cps.setChecked(params.use_cps)
            self._chk_eeg.setChecked(params.eeg)
            self._chk_meg.setChecked(params.meg)
            self._spin_mindist.setValue(params.mindist)
            self._spin_n_jobs.setValue(params.n_jobs)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [
            self._cmb_src_type, self._cmb_spacing, self._spin_volume_spacing,
            self._chk_add_dist, self._chk_fixed, self._chk_use_cps,
            self._chk_meg, self._spin_mindist, self._spin_n_jobs
        ]:
            w.blockSignals(block)

    @Slot(str)
    def _on_src_type_changed(self, type_str: str) -> None:
        is_volume = type_str == "volume"
        self._spin_volume_spacing.setVisible(is_volume)
        self._cmb_spacing.setVisible(not is_volume)
        self._chk_fixed.setVisible(not is_volume)
        self._chk_use_cps.setVisible(not is_volume)

    @Slot()
    def _on_param_changed(self) -> None:
        params = ForwardModelParams(
            source_space_type=SourceSpaceType(self._cmb_src_type.currentText()),
            spacing=self._cmb_spacing.currentText() if self._cmb_src_type.currentText() != "volume" else self._spin_volume_spacing.value(),
            add_dist=self._chk_add_dist.isChecked(),
            fixed=self._chk_fixed.isChecked(),
            use_cps=self._chk_use_cps.isChecked(),
            eeg=self._chk_eeg.isChecked(),
            meg=self._chk_meg.isChecked(),
            mindist=self._spin_mindist.value(),
            n_jobs=self._spin_n_jobs.value(),
        )
        self._vm.set_forward_params(**params.__dict__)
        self.params_changed.emit()