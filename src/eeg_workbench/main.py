"""主窗口：整合所有模块的顶层 UI"""
from __future__ import annotations
import sys
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt, QTimer, QSettings
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QMenuBar, QStatusBar, QToolBar, QFileDialog,
    QMessageBox, QDockWidget, QLabel, QProgressBar, QStyle,
    QPushButton
)
from PySide6.QtGui import QAction, QIcon, QKeySequence, QCloseEvent

from eeg_workbench.utils.ui import wrap_scroll
from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.viewmodels.preprocessing_vm import PreprocessingViewModel
from eeg_workbench.viewmodels.features_vm import FeaturesViewModel
from eeg_workbench.viewmodels.erp_vm import ERPViewModel
from eeg_workbench.viewmodels.source_vm import SourceViewModel
from eeg_workbench.viewmodels.statistics_vm import StatisticsViewModel
from eeg_workbench.viewmodels.visualization_vm import VisualizationViewModel
from eeg_workbench.views.data_management import (
    DatasetLoaderWidget, MetadataEditorWidget, EventEditorWidget, SegmentationWidget
)
from eeg_workbench.views.preprocessing import PreprocessingMainWidget
from eeg_workbench.views.features import FeaturesMainWidget
from eeg_workbench.views.erp import ERPMainWidget
from eeg_workbench.views.source import SourceMainWidget
from eeg_workbench.views.statistics import StatisticsMainWidget
from eeg_workbench.views.visualization import VisualizationMainWidget
from eeg_workbench.core.config import get_config_manager
from eeg_workbench.core.events import get_event_bus, EventType


class MainWindow(QMainWindow):
    """EEG Workbench 主窗口"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowTitle("EEG Visualization Research Workbench")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 700)

        # 核心 ViewModel（按依赖链初始化）
        self._data_vm = DataManagementViewModel(self)
        self._preproc_vm = PreprocessingViewModel(self._data_vm, self)
        self._features_vm = FeaturesViewModel(self._data_vm, self._preproc_vm, self)
        self._erp_vm = ERPViewModel(self._data_vm, self._preproc_vm, self._features_vm, self)
        self._source_vm = SourceViewModel(self._data_vm, self._preproc_vm, self._features_vm, self._erp_vm, self)
        self._stats_vm = StatisticsViewModel(self._data_vm, self._preproc_vm, self._features_vm, self._erp_vm, self._source_vm, self)
        self._viz_vm = VisualizationViewModel(self._data_vm, self._preproc_vm, self._features_vm, self._erp_vm, self._source_vm, self._stats_vm, self)

        # UI 组件
        self._loader_widget: Optional[DatasetLoaderWidget] = None
        self._meta_widget: Optional[MetadataEditorWidget] = None
        self._event_widget: Optional[EventEditorWidget] = None
        self._seg_widget: Optional[SegmentationWidget] = None
        self._preproc_widget: Optional[PreprocessingMainWidget] = None
        self._features_widget: Optional[FeaturesMainWidget] = None
        self._erp_widget: Optional[ERPMainWidget] = None
        self._source_widget: Optional[SourceMainWidget] = None
        self._stats_widget: Optional[StatisticsMainWidget] = None
        self._viz_widget: Optional[VisualizationMainWidget] = None

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_status_bar()
        self._connect_signals()
        self._restore_settings()

        # 欢迎页
        self._show_welcome()

    def _setup_ui(self):
        # 中央部件：标签页容器
        self._central_tabs = QTabWidget()
        self._central_tabs.setTabsClosable(False)
        self._central_tabs.setMovable(True)
        self.setCentralWidget(self._central_tabs)

        # 创建数据管理标签页
        self._create_data_management_tab()

        # 创建各分析模块标签页
        self._create_preprocessing_tab()
        self._create_features_tab()
        self._create_erp_tab()
        self._create_source_tab()
        self._create_statistics_tab()
        self._create_visualization_tab()

        # 侧边栏：数据集加载器 (可停靠)
        self._create_loader_dock()

    def _create_data_management_tab(self):
        """创建数据管理主标签页：元数据 | 事件 | 裁剪拼接"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # 顶部信息栏
        self._info_bar = QLabel("未加载数据集")
        self._info_bar.setStyleSheet("""
            QLabel {
                background: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        self._info_bar.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._info_bar)

        # 子标签页
        sub_tabs = QTabWidget()

        # 元数据编辑
        self._meta_widget = MetadataEditorWidget(self._data_vm)
        sub_tabs.addTab(wrap_scroll(self._meta_widget), "元数据")

        # 事件编辑
        self._event_widget = EventEditorWidget(self._data_vm)
        sub_tabs.addTab(wrap_scroll(self._event_widget), "事件编辑")

        # 裁剪拼接
        self._seg_widget = SegmentationWidget(self._data_vm)
        sub_tabs.addTab(wrap_scroll(self._seg_widget), "裁剪/拼接")

        layout.addWidget(sub_tabs, 1)

        self._central_tabs.addTab(tab, "数据管理")

    def _create_preprocessing_tab(self):
        """创建信号预处理标签页"""
        self._preproc_widget = PreprocessingMainWidget(self._preproc_vm)
        self._central_tabs.addTab(self._preproc_widget, "信号预处理")

    def _create_features_tab(self):
        """创建特征提取标签页"""
        self._features_widget = FeaturesMainWidget(self._features_vm)
        self._central_tabs.addTab(self._features_widget, "特征提取")

    def _create_erp_tab(self):
        """创建 ERP/ERD/ERS 标签页"""
        self._erp_widget = ERPMainWidget(self._erp_vm)
        self._central_tabs.addTab(self._erp_widget, "ERP/ERD/ERS")

    def _create_source_tab(self):
        """创建源定位与脑区分析标签页"""
        self._source_widget = SourceMainWidget(self._source_vm)
        self._central_tabs.addTab(self._source_widget, "源定位")

    def _create_statistics_tab(self):
        """创建统计与对比标签页"""
        self._stats_widget = StatisticsMainWidget(self._stats_vm)
        self._central_tabs.addTab(self._stats_widget, "统计分析")

    def _create_visualization_tab(self):
        """创建可视化与报告标签页"""
        self._viz_widget = VisualizationMainWidget(self._viz_vm)
        self._central_tabs.addTab(self._viz_widget, "可视化与报告")

        # 占位：后续模块的标签页
        self._placeholder_tabs = {}

    def _create_loader_dock(self):
        """创建可停靠的数据加载面板"""
        dock = QDockWidget("数据加载", self)
        dock.setObjectName("loaderDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                         QDockWidget.DockWidgetFeature.DockWidgetClosable)

        self._loader_widget = DatasetLoaderWidget(self._data_vm)
        dock.setWidget(self._loader_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        # 菜单视图动作
        self._act_toggle_loader = dock.toggleViewAction()
        self._act_toggle_loader.setShortcut(QKeySequence("Ctrl+L"))

    def _setup_menu_bar(self):
        mb = self.menuBar()

        # 文件菜单
        file_menu = mb.addMenu("文件(&F)")

        act_new = QAction("新建数据集", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._new_dataset)
        file_menu.addAction(act_new)

        act_open = QAction("打开...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._loader_widget._browse_file if self._loader_widget else lambda: None)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_save = QAction("保存数据集...", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._save_dataset)
        file_menu.addAction(act_save)

        act_save_as = QAction("另存为...", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self._save_dataset_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        # 最近文件子菜单
        self._recent_menu = file_menu.addMenu("最近文件")
        self._update_recent_menu()

        file_menu.addSeparator()

        act_exit = QAction("退出", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # 编辑菜单
        edit_menu = mb.addMenu("编辑(&E)")

        act_undo = QAction("撤销", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(act_undo)

        act_redo = QAction("重做", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(act_redo)

        # 视图菜单
        view_menu = mb.addMenu("视图(&V)")
        view_menu.addAction(self._act_toggle_loader)

        # 工具菜单
        tools_menu = mb.addMenu("工具(&T)")

        act_preprocess = QAction("预处理...", self)
        act_preprocess.setShortcut(QKeySequence("Ctrl+P"))
        act_preprocess.triggered.connect(lambda: self._switch_to_tab("信号预处理"))
        tools_menu.addAction(act_preprocess)

        act_features = QAction("特征提取...", self)
        act_features.triggered.connect(lambda: self._switch_to_tab("特征提取"))
        tools_menu.addAction(act_features)

        act_erp = QAction("ERP/ERD 分析...", self)
        act_erp.triggered.connect(lambda: self._switch_to_tab("ERP/ERD/ERS"))
        tools_menu.addAction(act_erp)

        act_source = QAction("源定位...", self)
        act_source.triggered.connect(lambda: self._switch_to_tab("源定位"))
        tools_menu.addAction(act_source)

        act_stats = QAction("统计分析...", self)
        act_stats.triggered.connect(lambda: self._switch_to_tab("统计分析"))
        tools_menu.addAction(act_stats)

        act_viz = QAction("可视化与报告...", self)
        act_viz.triggered.connect(lambda: self._switch_to_tab("可视化与报告"))
        tools_menu.addAction(act_viz)

        # 帮助菜单
        help_menu = mb.addMenu("帮助(&H)")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _setup_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setObjectName("mainToolBar")
        tb.setMovable(False)
        from PySide6.QtCore import QSize
        tb.setIconSize(QSize(32, 32))
        self.addToolBar(tb)

        # 新建
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "新建")
        act.setShortcut(QKeySequence.StandardKey.New)
        act.triggered.connect(self._new_dataset)

        # 打开
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "打开")
        act.setShortcut(QKeySequence.StandardKey.Open)
        act.triggered.connect(lambda: self._loader_widget._browse_file() if self._loader_widget else None)

        # 保存
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "保存")
        act.setShortcut(QKeySequence.StandardKey.Save)
        act.triggered.connect(self._save_dataset)

        tb.addSeparator()

        # 切换加载面板
        tb.addAction(self._act_toggle_loader)

        tb.addSeparator()

        # 运行预处理
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "预处理")
        act.triggered.connect(lambda: self._switch_to_tab("信号预处理"))
        tb.addAction(act)

        # 特征提取
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), "特征")
        act.triggered.connect(lambda: self._switch_to_tab("特征提取"))
        tb.addAction(act)

        # ERP
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton), "ERP")
        act.triggered.connect(lambda: self._switch_to_tab("ERP/ERD/ERS"))
        tb.addAction(act)

        # 统计
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "统计")
        act.triggered.connect(lambda: self._switch_to_tab("统计分析"))
        tb.addAction(act)

        # 可视化
        act = tb.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon), "可视化")
        act.triggered.connect(lambda: self._switch_to_tab("可视化与报告"))
        tb.addAction(act)

    def _setup_status_bar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # 左侧状态
        self._lbl_status = QLabel("就绪")
        self._status_bar.addWidget(self._lbl_status, 1)

        # 右侧进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress_bar)

        # 右侧内存/性能信息
        self._lbl_perf = QLabel("")
        self._status_bar.addPermanentWidget(self._lbl_perf)

    def _connect_signals(self):
        # ViewModel 信号
        self._data_vm.dataset_changed.connect(self._on_dataset_changed)
        self._data_vm.dataset_info_changed.connect(self._on_info_changed)
        self._data_vm.status_message.connect(self._on_status_message)
        self._data_vm.loading_progress.connect(self._on_loading_progress)
        self._data_vm.recent_files_changed.connect(self._update_recent_menu)

        # EventWidget 信号
        if self._event_widget:
            self._event_widget.status_message.connect(self._on_status_message)
            self._event_widget.request_waveform_marker.connect(self._on_waveform_marker_request)

        # SegmentationWidget 信号
        if self._seg_widget:
            self._seg_widget.status_message.connect(self._on_status_message)
            self._seg_widget.dataset_changed.connect(self._on_dataset_changed)

        # 各模块主 Widget 状态消息
        for w in [self._preproc_widget, self._features_widget, self._erp_widget,
                  self._source_widget, self._stats_widget, self._viz_widget]:
            if w is not None and hasattr(w, 'status_message'):
                w.status_message.connect(self._on_status_message)

    # ---- 槽函数 ----
    @Slot(object)
    def _on_dataset_changed(self, dataset):
        if dataset:
            self._info_bar.setText(
                f"<b>{dataset.name}</b>  |  "
                f"通道: {dataset.n_channels}  |  "
                f"采样率: {dataset.sfreq:.1f} Hz  |  "
                f"时长: {dataset.duration:.2f} s  |  "
                f"事件: {len(dataset.events)}"
            )
            self.setWindowTitle(f"EEG Workbench - {dataset.name}")
        else:
            self._info_bar.setText("未加载数据集")
            self.setWindowTitle("EEG Visualization Research Workbench")

    @Slot(str)
    def _on_info_changed(self, info: str):
        self._info_bar.setText(info)

    @Slot(str)
    def _on_status_message(self, msg: str):
        self._lbl_status.setText(msg)
        # 3秒后自动清除非持久消息
        if not msg.startswith("已"):
            QTimer.singleShot(3000, lambda: self._lbl_status.setText("就绪") if self._lbl_status.text() == msg else None)

    @Slot(object)
    def _on_loading_progress(self, progress):
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, progress.total)
        self._progress_bar.setValue(progress.current)
        self._progress_bar.setFormat(progress.message)
        if progress.stage == "complete":
            QTimer.singleShot(1500, lambda: self._progress_bar.setVisible(False))
        elif progress.stage == "error":
            self._progress_bar.setStyleSheet("QProgressBar::chunk { background: #e74c3c; }")

    @Slot(float, str)
    def _on_waveform_marker_request(self, time: float, desc: str):
        self._lbl_status.setText(f"波形标记请求: {desc} @ {time:.3f}s")
        viz_index = self._central_tabs.indexOf(self._viz_widget)
        if viz_index >= 0:
            self._central_tabs.setCurrentIndex(viz_index)
        self._viz_widget.show_waveform_marker(time, desc)

    # ---- 菜单动作 ----
    def _new_dataset(self):
        if self._data_vm.dataset and self._data_vm.dataset.is_dirty:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "当前数据集有未保存的更改，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        self._data_vm.close_dataset()

    def _save_dataset(self):
        if not self._data_vm.dataset:
            QMessageBox.information(self, "提示", "没有数据可保存")
            return
        if self._data_vm.dataset.file_path:
            self._data_vm.save_dataset(self._data_vm.dataset.file_path)
        else:
            self._save_dataset_as()

    def _save_dataset_as(self):
        if not self._data_vm.dataset:
            return
        filters = "EDF 文件 (*.edf);;EEGLAB (*.set);;CSV (*.csv);;TSV (*.tsv)"
        path, selected = QFileDialog.getSaveFileName(self, "保存数据集", "", filters)
        if path:
            fmt = "edf"
            if selected and "EEGLAB" in selected:
                fmt = "eeglab"
            elif selected and "CSV" in selected:
                fmt = "csv"
            elif selected and "TSV" in selected:
                fmt = "tsv"
            self._data_vm.save_dataset(path, format=fmt)

    def _update_recent_menu(self):
        self._recent_menu.clear()
        files = self._data_vm._config_mgr.config.recent_files
        if not files:
            act = QAction("(无最近文件)", self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
            return
        for i, f in enumerate(files[:10]):
            name = f.split("/")[-1].split("\\")[-1]
            act = QAction(f"&{i+1} {name}", self)
            act.setToolTip(f)
            act.triggered.connect(lambda checked, p=f: self._loader_widget._load_file(p) if self._loader_widget else None)
            self._recent_menu.addAction(act)

    def _switch_to_tab(self, tab_name: str):
        """切换到指定标签页"""
        for i in range(self._central_tabs.count()):
            if self._central_tabs.tabText(i) == tab_name:
                self._central_tabs.setCurrentIndex(i)
                return
        # 如果找不到，显示占位页
        self._show_placeholder(tab_name)

    def _show_placeholder(self, module_name: str):
        """显示未实现模块的占位标签页"""
        if module_name not in self._placeholder_tabs:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            label = QLabel(f"<h2>{module_name} 模块</h2><p>该模块正在开发中...</p>")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)
            self._placeholder_tabs[module_name] = widget
            self._central_tabs.addTab(widget, module_name)
        self._central_tabs.setCurrentWidget(self._placeholder_tabs[module_name])

    def _show_welcome(self):
        """显示欢迎页面"""
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("<h1>EEG Visualization Research Workbench</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("<p style='color:#666; font-size:16px;'>脑电数据可视化与分析工作台</p>")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(30)

        btn_open = QPushButton("打开数据文件")
        btn_open.setMinimumSize(200, 50)
        btn_open.setStyleSheet("font-size: 16px;")
        btn_open.clicked.connect(lambda: self._loader_widget._browse_file() if self._loader_widget else None)
        layout.addWidget(btn_open, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_new = QPushButton("新建空白数据集")
        btn_new.setMinimumSize(200, 50)
        btn_new.clicked.connect(self._new_dataset)
        layout.addWidget(btn_new, alignment=Qt.AlignmentFlag.AlignCenter)

        self._central_tabs.addTab(welcome, "欢迎")
        self._central_tabs.setCurrentWidget(welcome)

    def _show_about(self):
        QMessageBox.about(self, "关于 EEG Workbench",
            "<h3>EEG Visualization Research Workbench v0.1</h3>"
            "<p>脑电数据可视化与分析工作台</p>"
            "<p>技术栈: Python + PySide6 + MNE-Python + NumPy/SciPy</p>"
            "<p>© 2024 Research Team</p>"
        )

    def _restore_settings(self):
        settings = QSettings("EEGWorkbench", "MainWindow")
        self.restoreGeometry(settings.value("geometry", b""))
        self.restoreState(settings.value("windowState", b""))

    def _save_settings(self):
        settings = QSettings("EEGWorkbench", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

    def closeEvent(self, event: QCloseEvent):
        if self._data_vm.dataset and self._data_vm.dataset.is_dirty:
            reply = QMessageBox.question(
                self, "退出确认",
                "当前数据集有未保存的更改，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self._save_settings()
        self._data_vm.cleanup()
        super().closeEvent(event)


def main():
    """程序入口"""
    import os

    # 设置高 DPI 缩放 (PySide6 默认启用)
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("EEG Workbench")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Research Team")

    # 设置应用样式
    app.setStyle("Fusion")

    # 配置 matplotlib 中文字体（否则图形中文显示为方框）
    try:
        from eeg_workbench.utils.fonts import ensure_cjk_font
        _cjk = ensure_cjk_font()
    except Exception:
        _cjk = None

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())