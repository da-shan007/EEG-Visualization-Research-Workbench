"""方差分析面板"""
from __future__ import annotations
from eeg_workbench.models.dataset import EEGDataset
from typing import Optional, cast

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLabel, QLineEdit, QMessageBox
)

from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.models.statistics import ANOVAParams, MultipleComparisonCorrection, EffectSize, ANOVADesign, PostHocMethod, SphericityCorrection
from eeg_workbench.utils.ui import balance_form


class ANOVAWidget(QWidget):
    """方差分析面板"""

    params_changed = Signal()
    status_message = Signal(str)

    def __init__(self, viewmodel: StatisticsViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 设计类型 ----
        design_group = QGroupBox("ANOVA 设计")
        design_layout = QFormLayout(design_group)

        self._cmb_design = QComboBox()
        self._cmb_design.addItems(["one_way", "two_way", "repeated", "mixed"])
        self._cmb_design.setCurrentText("one_way")
        self._cmb_design.currentTextChanged.connect(self._on_design_changed)
        design_layout.addRow("设计类型:", self._cmb_design)

        self._edit_factors = QLineEdit()
        self._edit_factors.setPlaceholderText("因子名，逗号分隔 (如: Group,Condition)")
        design_layout.addRow("因子:", self._edit_factors)

        self._edit_subject = QLineEdit()
        self._edit_subject.setPlaceholderText("受试者因子名 (重复测量必填)")
        self._edit_subject.setVisible(False)
        design_layout.addRow("受试者因子:", self._edit_subject)
        balance_form(design_layout)

        layout.addWidget(design_group)

        # ---- 单因素/双因素设置 ----
        self._between_group = QGroupBox("组间设置")
        between_layout = QFormLayout(self._between_group)

        self._chk_posthoc = QCheckBox("事后检验")
        self._chk_posthoc.setChecked(True)
        between_layout.addRow("", self._chk_posthoc)

        self._cmb_posthoc = QComboBox()
        self._cmb_posthoc.addItems(["tukey", "bonferroni", "scheffe", "games_howell"])
        self._cmb_posthoc.setCurrentText("tukey")
        between_layout.addRow("事后方法:", self._cmb_posthoc)

        self._cmb_correction = QComboBox()
        self._cmb_correction.addItems([m.value for m in MultipleComparisonCorrection])
        self._cmb_correction.setCurrentText("fdr_bh")
        between_layout.addRow("多重校正:", self._cmb_correction)
        balance_form(between_layout)

        layout.addWidget(self._between_group)

        # ---- 重复测量设置 ----
        self._repeated_group = QGroupBox("重复测量设置")
        self._repeated_group.setVisible(False)
        repeated_layout = QFormLayout(self._repeated_group)

        self._cmb_sphericity = QComboBox()
        self._cmb_sphericity.addItems(["none", "greenhouse_geisser", "huynh_feldt"])
        self._cmb_sphericity.setCurrentText("greenhouse_geisser")
        repeated_layout.addRow("球形校正:", self._cmb_sphericity)
        balance_form(repeated_layout)

        layout.addWidget(self._repeated_group)

        # ---- 效应量 ----
        effect_group = QGroupBox("效应量")
        effect_layout = QFormLayout(effect_group)

        self._cmb_effect_size = QComboBox()
        self._cmb_effect_size.addItems([e.value for e in EffectSize])
        self._cmb_effect_size.setCurrentText("eta_squared")
        effect_layout.addRow("效应量类型:", self._cmb_effect_size)
        balance_form(effect_layout)

        layout.addWidget(effect_group)

        # ---- 执行按钮 ----
        exec_layout = QHBoxLayout()
        self._btn_run = QPushButton("运行 ANOVA")
        self._btn_run.setMinimumHeight(40)
        self._btn_run.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_run.clicked.connect(self._run_anova)
        exec_layout.addWidget(self._btn_run)

        layout.addLayout(exec_layout)

        # ---- 结果显示 ----
        result_group = QGroupBox("结果")
        result_layout = QVBoxLayout(result_group)

        self._result_text = QLabel("等待运行...")
        self._result_text.setWordWrap(True)
        self._result_text.setStyleSheet("font-family: monospace; font-size: 12px;")
        result_layout.addWidget(self._result_text)

        layout.addWidget(result_group)

        layout.addStretch()

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    def _on_dataset_changed(self, dataset: EEGDataset | None) -> None:
        enabled = dataset is not None
        self.setEnabled(enabled)

    def _on_design_changed(self, design: str) -> None:
        is_repeated = design in ("repeated", "mixed")
        self._repeated_group.setVisible(is_repeated)
        self._between_group.setVisible(not is_repeated)
        self._edit_subject.setVisible(is_repeated)
        self._on_param_changed()

    def _sync_from_vm(self) -> None:
        params = self._vm.anova_params
        self._block_signals(True)
        try:
            self._cmb_design.setCurrentText(params.design)
            self._edit_factors.setText(",".join(params.factors))
            self._edit_subject.setText(params.subject_factor or "")
            self._chk_posthoc.setChecked(params.post_hoc)
            self._cmb_posthoc.setCurrentText(params.post_hoc_method)
            self._cmb_correction.setCurrentText(params.corrections[0].value if params.corrections else "fdr_bh")
            self._cmb_sphericity.setCurrentText(params.sphericity_correction)
            self._cmb_effect_size.setCurrentText(params.effect_size.value)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        for w in [
            self._cmb_design, self._edit_factors, self._edit_subject,
            self._chk_posthoc, self._cmb_posthoc, self._cmb_correction,
            self._cmb_sphericity, self._cmb_effect_size
        ]:
            w.blockSignals(block)

    @Slot()
    def _on_param_changed(self) -> None:
        params = ANOVAParams(
            design=cast(ANOVADesign, self._cmb_design.currentText()),
            factors=[f.strip() for f in self._edit_factors.text().split(",") if f.strip()],
            subject_factor=self._edit_subject.text() or None,
            post_hoc=self._chk_posthoc.isChecked(),
            post_hoc_method=cast(PostHocMethod, self._cmb_posthoc.currentText()),
            corrections=[MultipleComparisonCorrection(self._cmb_correction.currentText())],
            sphericity_correction=cast(SphericityCorrection, self._cmb_sphericity.currentText()),
            effect_size=EffectSize(self._cmb_effect_size.currentText()),
        )
        self._vm.set_anova_params(**params.__dict__)
        self.params_changed.emit()

    @Slot()
    def _run_anova(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "请先在特征提取/ERP模块准备分组数据，然后调用 run_anova 方法")