"""统计分析主面板：整合 t检验、ANOVA、非参数、置换、相关性、校正、效应量"""
from __future__ import annotations
from typing import Any, Optional

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QMessageBox, QListWidget, QListWidgetItem,
    QSplitter, QMenu
)

from eeg_workbench.utils.ui import relay_status, wrap_scroll
from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.views.statistics.ttest_widget import TTestWidget
from eeg_workbench.views.statistics.anova_widget import ANOVAWidget
from eeg_workbench.views.statistics.nonparametric_widget import NonparametricWidget
from eeg_workbench.views.statistics.permutation_widget import PermutationWidget
from eeg_workbench.views.statistics.correlation_widget import CorrelationWidget
from eeg_workbench.views.statistics.correction_widget import CorrectionWidget
from eeg_workbench.views.statistics.effect_size_widget import EffectSizeWidget
from eeg_workbench.models.dataset import EEGDataset


class StatisticsMainWidget(QWidget):
    """统计分析模块主面板"""

    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: StatisticsViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._vm = viewmodel
        self._dataset: Optional[EEGDataset] = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ---- 顶部信息栏 ----
        info_bar = QGroupBox("数据集状态")
        info_layout = QHBoxLayout(info_bar)

        self._lbl_dataset_name = QLabel("未加载数据")
        self._lbl_dataset_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        info_layout.addWidget(self._lbl_dataset_name)

        self._lbl_info = QLabel("通道: -- | 采样率: -- Hz | 时长: -- s")
        self._lbl_info.setStyleSheet("color: #666;")
        info_layout.addWidget(self._lbl_info, 1)

        self._btn_preset = QPushButton("预设设计")
        self._btn_preset.setMenu(self._create_preset_menu())
        info_layout.addWidget(self._btn_preset)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        self._ttest_widget = TTestWidget(self._vm)
        self._anova_widget = ANOVAWidget(self._vm)
        self._nonparam_widget = NonparametricWidget(self._vm)
        self._perm_widget = PermutationWidget(self._vm)
        self._corr_widget = CorrelationWidget(self._vm)
        self._corr_widget2 = CorrectionWidget(self._vm)
        self._effect_widget = EffectSizeWidget(self._vm)

        self._tabs.addTab(wrap_scroll(self._ttest_widget), "T 检验")
        self._tabs.addTab(wrap_scroll(self._anova_widget), "ANOVA")
        self._tabs.addTab(wrap_scroll(self._nonparam_widget), "非参数")
        self._tabs.addTab(wrap_scroll(self._perm_widget), "置换检验")
        self._tabs.addTab(wrap_scroll(self._corr_widget), "相关性")
        self._tabs.addTab(wrap_scroll(self._corr_widget2), "多重校正")
        self._tabs.addTab(wrap_scroll(self._effect_widget), "效应量")

        layout.addWidget(self._tabs, 1)

        # ---- 底部历史 ----
        history_group = QGroupBox("分析历史")
        history_layout = QVBoxLayout(history_group)

        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(100)
        history_layout.addWidget(self._history_list)

        history_btn = QHBoxLayout()
        self._btn_export = QPushButton("导出结果")
        self._btn_export.clicked.connect(self._export_results)
        self._btn_clear = QPushButton("清空历史")
        self._btn_clear.clicked.connect(self._clear_history)
        history_btn.addWidget(self._btn_export)
        history_btn.addWidget(self._btn_clear)
        history_btn.addStretch()
        history_layout.addLayout(history_btn)

        layout.addWidget(history_group)

        # 初始禁用
        self.setEnabled(False)

    def _create_preset_menu(self) -> QMenu:
        menu = QMenu(self)
        
        designs = [
            ("两组比较", "two_group"),
            ("多组比较", "multi_group"),
            ("重复测量", "repeated"),
            ("相关性分析", "correlation"),
        ]
        
        for name, design in designs:
            act = menu.addAction(name)
            act.triggered.connect(lambda checked, d=design: self._apply_preset(d))
        
        return menu

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.ttest_result.connect(self._on_ttest_result)
        self._vm.anova_result.connect(self._on_anova_result)
        self._vm.permutation_result.connect(self._on_permutation_result)
        self._vm.correlation_result.connect(self._on_correlation_result)
        self._vm.correction_result.connect(self._on_correction_result)
        self._vm.effect_size_result.connect(self._on_effect_size_result)
        self._vm.processing_steps_changed.connect(self._update_history)
        self._vm.status_message.connect(self.status_message.emit)

        # 子面板信号
        relay_status(
            [self._ttest_widget, self._anova_widget, self._nonparam_widget,
             self._perm_widget, self._corr_widget, self._effect_widget],
            self.status_message,
        )

    @Slot(object)
    def _on_dataset_changed(self, dataset: Optional[EEGDataset]) -> None:
        self._dataset = dataset
        enabled = dataset is not None
        self.setEnabled(enabled)

        if dataset:
            self._lbl_dataset_name.setText(dataset.name)
            self._lbl_info.setText(
                f"通道: {dataset.n_channels} | 采样率: {dataset.sfreq:.1f} Hz | 时长: {dataset.duration:.2f} s"
            )
        else:
            self._lbl_dataset_name.setText("未加载数据")
            self._lbl_info.setText("通道: -- | 采样率: -- Hz | 时长: -- s")

        self.dataset_changed.emit(dataset)

    @Slot()
    def _apply_preset(self, design: str) -> None:
        self._vm.apply_preset(design)
        self.status_message.emit(f"已应用预设: {design}")

    @Slot(object)
    def _on_ttest_result(self, result: Any) -> None:
        self._add_history(f"T检验: p={result.p_value:.4f}, d={result.effect_size:.3f}" if result.effect_size else f"T检验: p={result.p_value:.4f}")

    @Slot(object)
    def _on_anova_result(self, result: Any) -> None:
        self._add_history(f"ANOVA 完成")

    @Slot(object)
    def _on_permutation_result(self, result: Any) -> None:
        self._add_history(f"置换检验: p={result.result.p_value:.4f}")

    @Slot(object)
    def _on_correlation_result(self, result: Any) -> None:
        self._add_history(f"相关性: {len(result.results)} 对变量")

    @Slot(object)
    def _on_correction_result(self, result: Any) -> None:
        self._add_history(f"多重校正: {sum(result['rejected'])}/{len(result['rejected'])} 显著")

    @Slot(object)
    def _on_effect_size_result(self, result: Any) -> None:
        if result:
            self._add_history(f"效应量: {result['effect_size_type']}={result['value']:.3f} ({result['interpretation']})")

    def _add_history(self, desc: str) -> None:
        item = QListWidgetItem(f"✓ {desc}")
        self._history_list.addItem(item)

    @Slot(list)
    def _update_history(self, steps: list[Any]) -> None:
        """从 ViewModel 的处理步骤列表刷新历史"""
        if not steps:
            return
        for s in steps:
            if isinstance(s, str):
                self._add_history(s)
            else:
                name = getattr(s, "name", str(s))
                desc = getattr(s, "description", "")
                t = getattr(s, "processing_time_ms", 0)
                suffix = f" ({t:.0f} ms)" if t else ""
                self._add_history(f"{name}: {desc}{suffix}")

    @Slot()
    def _export_results(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "导出统计结果", "", "NPZ 文件 (*.npz);;CSV 文件 (*.csv);;JSON 文件 (*.json)")
        if path:
            self.status_message.emit(f"导出功能待实现: {path}")

    @Slot()
    def _clear_history(self) -> None:
        self._history_list.clear()