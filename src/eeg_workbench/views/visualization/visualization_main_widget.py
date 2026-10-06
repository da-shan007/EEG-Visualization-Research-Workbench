"""主可视化面板：整合波形、频谱、时频、连通性、统计、源定位、报告"""
from __future__ import annotations
from typing import Optional, Any
from pathlib import Path

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGroupBox,
    QLabel, QPushButton, QComboBox, QSplitter, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QProgressBar, QMenu
)

from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.views.visualization.waveform_widget import WaveformWidget
from eeg_workbench.views.visualization.spectral_widget import SpectralWidget
from eeg_workbench.views.visualization.tfr_widget import TFRWidget
from eeg_workbench.views.visualization.connectivity_widget import ConnectivityWidget
from eeg_workbench.views.visualization.statistical_widget import StatisticalWidget
from eeg_workbench.views.visualization.source_widget import SourceVisualizationWidget
from eeg_workbench.views.visualization.report_widget import ReportWidget
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.utils.ui import balance_form, wrap_scroll

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
except Exception:  # pragma: no cover - matplotlib 缺失时绘图功能整体不可用
    Figure = None  # type: ignore
    FigureCanvasQTAgg = None  # type: ignore


class VisualizationMainWidget(QWidget):
    """可视化模块主面板"""
    status_message = Signal(str)
    dataset_changed = Signal(object)  # EEGDataset

    def __init__(self, viewmodel: VisualizationViewModel, parent: Optional[QWidget] = None) -> None:
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

        self._btn_export_figure = QPushButton("导出当前图形")
        self._btn_export_figure.clicked.connect(self._export_current_figure)
        info_layout.addWidget(self._btn_export_figure)

        self._btn_generate_report = QPushButton("生成报告")
        self._btn_generate_report.clicked.connect(self._generate_report_dialog)
        info_layout.addWidget(self._btn_generate_report)

        layout.addWidget(info_bar)

        # ---- 标签页 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)

        self._waveform_widget = WaveformWidget(self._vm)
        self._spectral_widget = SpectralWidget(self._vm)
        self._tfr_widget = TFRWidget(self._vm)
        self._conn_widget = ConnectivityWidget(self._vm)
        self._stat_widget = StatisticalWidget(self._vm)
        self._source_widget = SourceVisualizationWidget(self._vm)
        self._report_widget = ReportWidget(self._vm)

        # 参数面板内容高（波形面板自然高度约 850px），直接放入标签页会在小窗口下
        # 被纵向挤压；用滚动区包裹，挤不下时出滚动条而非压缩控件。
        self._waveform_scroll = wrap_scroll(self._waveform_widget)
        self._spectral_scroll = wrap_scroll(self._spectral_widget)
        self._tfr_scroll = wrap_scroll(self._tfr_widget)
        self._conn_scroll = wrap_scroll(self._conn_widget)
        self._stat_scroll = wrap_scroll(self._stat_widget)
        self._source_scroll = wrap_scroll(self._source_widget)
        self._report_scroll = wrap_scroll(self._report_widget)

        self._tabs.addTab(self._waveform_scroll, "波形图")
        self._tabs.addTab(self._spectral_scroll, "频谱图")
        self._tabs.addTab(self._tfr_scroll, "时频图")
        self._tabs.addTab(self._conn_scroll, "连通性")
        self._tabs.addTab(self._stat_scroll, "统计图")
        self._tabs.addTab(self._source_scroll, "源定位")
        self._tabs.addTab(self._report_scroll, "报告生成")

        # ---- 图形显示区（订阅 figure_ready，绘图结果显示在界面） ----
        fig_group = QGroupBox("图形显示")
        fig_layout = QVBoxLayout(fig_group)

        self._lbl_fig_title = QLabel("尚未绘制图形 —— 在上方标签页设置参数后点击绘制")
        self._lbl_fig_title.setStyleSheet("color: #666;")
        fig_layout.addWidget(self._lbl_fig_title)

        self._fig_container = QWidget()
        self._fig_container_layout = QVBoxLayout(self._fig_container)
        self._fig_container_layout.setContentsMargins(0, 0, 0, 0)
        self._fig_canvas: Any = None  # 当前 FigureCanvasQTAgg
        self._fig_container.setMinimumHeight(200)
        fig_layout.addWidget(self._fig_container, 1)

        # 上下分栏：参数标签页 / 图形显示（参数面板内容更高，分给它更多空间）
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._tabs)
        splitter.addWidget(fig_group)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        # ---- 底部导出进度 ----
        export_group = QGroupBox("导出进度")
        export_layout = QVBoxLayout(export_group)

        self._export_progress = QProgressBar()
        self._export_progress.setVisible(False)
        export_layout.addWidget(self._export_progress)

        self._lbl_export_status = QLabel("就绪")
        export_layout.addWidget(self._lbl_export_status)

        layout.addWidget(export_group)

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self) -> None:
        self._vm.dataset_changed.connect(self._on_dataset_changed)
        self._vm.status_message.connect(self.status_message.emit)
        fig_sig = getattr(self._vm, "figure_ready", None)
        if fig_sig is not None:
            fig_sig.connect(self._on_figure_ready)
        for sig_name, slot in (
            ("export_finished", self._on_export_finished),
            ("error_occurred", self._on_export_failed),
        ):
            sig = getattr(self._vm, sig_name, None)
            if sig is not None:
                sig.connect(slot)

    @Slot(object)
    def _on_figure_ready(self, result: Any) -> None:
        """figure_ready 槽：把绘制结果显示到共享画布，并切到对应标签页。"""
        if result is None:
            return
        fig = getattr(result, "figure", None)
        cfg = getattr(result, "config", None)

        # 按配置类型路由到对应标签页
        try:
            from eeg_workbench.models.visualization import (
                WaveformPlotConfig, SpectralPlotConfig, TFRPlotConfig,
                ConnectivityPlotConfig, StatisticalPlotConfig, SourcePlotConfig,
            )
            for ctype, idx in (
                (WaveformPlotConfig, 0), (SpectralPlotConfig, 1),
                (TFRPlotConfig, 2), (ConnectivityPlotConfig, 3),
                (StatisticalPlotConfig, 4), (SourcePlotConfig, 5),
            ):
                if isinstance(cfg, ctype):
                    self._tabs.setCurrentIndex(idx)
                    break
        except Exception:
            pass

        title = type(cfg).__name__.replace("PlotConfig", "") if cfg is not None else "图形"
        info = getattr(result, "data_info", None) or {}

        # matplotlib Figure → 画布渲染；其他（如 mne Brain）→ 提示独立窗口
        if Figure is not None and isinstance(fig, Figure):
            self._lbl_fig_title.setText(f"当前图形: {title}  {info}")
            # 释放旧 figure 资源
            if self._fig_canvas is not None:
                try:
                    import matplotlib.pyplot as plt
                    plt.close(self._fig_canvas.figure)
                except Exception:
                    pass
                self._fig_container_layout.removeWidget(self._fig_canvas)
                self._fig_canvas.deleteLater()
                self._fig_canvas = None
            canvas = FigureCanvasQTAgg(fig)  # type: ignore[no-untyped-call]
            self._fig_canvas = canvas
            self._fig_container_layout.addWidget(canvas)
            canvas.draw_idle()  # type: ignore[no-untyped-call]
        else:
            self._lbl_fig_title.setText(
                f"当前图形: {title} 为 3D/交互类型，已在独立窗口中打开"
            )

    @Slot(str)
    def _on_export_finished(self, path: str) -> None:
        self._export_progress.setVisible(False)
        self._export_progress.setRange(0, 100)
        self._export_progress.setValue(100)
        self._lbl_export_status.setText(f"已导出: {path}")

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._export_progress.setVisible(False)
        self._lbl_export_status.setText(f"失败: {message}")

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

    def show_waveform_marker(self, time: float, desc: str) -> None:
        """外部请求在波形上定位事件：切到波形标签页并提示事件位置"""
        self._tabs.setCurrentWidget(self._waveform_scroll)
        self._lbl_fig_title.setText(f"事件标记: {desc} @ {time:.3f}s —— 点击波形图绘制查看")
        self.status_message.emit(f"已定位到事件: {desc} @ {time:.3f}s")

    @Slot()
    def _export_current_figure(self) -> None:
        current_tab = self._tabs.currentIndex()
        tab_names = ["波形图", "频谱图", "时频图", "连通性", "统计图", "源定位", "报告生成"]

        if current_tab < 0:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, f"导出 {tab_names[current_tab]}", "",
            "PNG 图片 (*.png);;PDF 文件 (*.pdf);;SVG 矢量图 (*.svg);;EPS (*.eps);;HTML (*.html)"
        )

        if not path:
            return

        self._export_progress.setVisible(True)
        self._export_progress.setRange(0, 0)
        self._lbl_export_status.setText(f"正在导出 {tab_names[current_tab]}...")

        # 结果由 vm 的 export_finished / error_occurred 信号回报
        self._vm.export_figure(path=path)

    @Slot()
    def _generate_report_dialog(self) -> None:
        """生成报告对话框"""
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QCheckBox, QLineEdit, QSpinBox, QComboBox

        if not self._dataset:
            QMessageBox.warning(self, "提示", "请先加载数据集")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("生成报告")
        dlg.setModal(True)
        dlg.resize(400, 500)

        layout = QFormLayout(dlg)

        self._rpt_title = QLineEdit("EEG 分析报告")
        layout.addRow("标题:", self._rpt_title)

        self._rpt_author = QLineEdit()
        layout.addRow("作者:", self._rpt_author)

        self._rpt_institution = QLineEdit()
        layout.addRow("机构:", self._rpt_institution)

        self._cmb_format = QComboBox()
        self._cmb_format.addItems(["PDF", "HTML", "DOCX", "PPTX"])
        layout.addRow("输出格式:", self._cmb_format)

        self._chk_toc = QCheckBox("包含目录")
        self._chk_toc.setChecked(True)
        layout.addRow("", self._chk_toc)

        self._chk_methods = QCheckBox("包含方法章节")
        self._chk_methods.setChecked(True)
        layout.addRow("", self._chk_methods)

        self._chk_results = QCheckBox("包含结果章节")
        self._chk_results.setChecked(True)
        layout.addRow("", self._chk_results)

        self._spin_dpi = QSpinBox()
        self._spin_dpi.setRange(72, 600)
        self._spin_dpi.setValue(300)
        layout.addRow("图片 DPI:", self._spin_dpi)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)
        balance_form(layout)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._generate_report(
                self._rpt_title.text(),
                self._rpt_author.text(),
                self._cmb_format.currentText(),
                self._chk_toc.isChecked(),
                self._chk_methods.isChecked(),
                self._chk_results.isChecked(),
                self._spin_dpi.value()
            )

    @Slot()
    def _generate_report(self, title: str, author: str, format_str: str, include_toc: bool, include_methods: bool, include_results: bool, dpi: int) -> None:
        """生成报告"""
        from eeg_workbench.models.visualization import ReportConfig, ExportFormat

        fmt = ExportFormat(format_str.lower())

        # 输出路径（默认落在 outputs/reports/，避免堆在项目根目录）
        ext = fmt.value
        default_dir = Path.cwd() / "outputs" / "reports"
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # 目录不可写时退回对话框的当前目录
        path, _ = QFileDialog.getSaveFileName(
            self, "保存报告", str(default_dir / f"eeg_report.{ext}"),
            f"{fmt.value.upper()} (*.{ext});;所有文件 (*)"
        )
        if not path:
            self._lbl_export_status.setText("就绪")
            return

        sections = []
        if include_methods:
            sections.append("methods")
        if include_results:
            sections.append("results")

        config = ReportConfig(
            title=title,
            author=author,
            output_format=fmt,
            figure_dpi=dpi,
        )
        config.include_toc = include_toc
        config.sections = sections

        self._export_progress.setVisible(True)
        self._export_progress.setRange(0, 0)
        self._lbl_export_status.setText("正在生成报告...")

        # 结果由 export_finished / error_occurred 信号回报
        self._vm.generate_report(format=fmt.value, path=path, config=config)