"""数据集加载器 Widget：文件选择、最近文件、加载进度"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal, Slot, Qt, QThread, QObject, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QProgressBar, QFileDialog,
    QMessageBox, QMenu, QInputDialog, QLineEdit
)
from PySide6.QtGui import QAction, QIcon

from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel, FileLoadProgress


class LoadWorker(QObject):
    """后台加载工作线程"""
    progress = Signal(object)  # FileLoadProgress
    finished = Signal(object)  # LoadResult
    error = Signal(str)

    def __init__(self, vm: DataManagementViewModel, file_path: str, kwargs: dict):
        super().__init__()
        self._vm = vm
        self._file_path = file_path
        self._kwargs = kwargs

    def run(self):
        try:
            from eeg_workbench.services.io import ReaderFactory
            result = ReaderFactory.load_dataset(self._file_path, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DatasetLoaderWidget(QWidget):
    """数据集加载面板：左侧最近文件，右侧加载控制"""

    dataset_loaded = Signal(object)  # EEGDataset
    status_message = Signal(str)

    def __init__(self, viewmodel: DataManagementViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[LoadWorker] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 左侧：最近文件列表 ----
        left_group = QGroupBox("最近文件")
        left_layout = QVBoxLayout(left_group)

        self._recent_list = QListWidget()
        self._recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recent_list.customContextMenuRequested.connect(self._show_recent_context_menu)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        left_layout.addWidget(self._recent_list)

        # 最近文件工具栏
        recent_toolbar = QHBoxLayout()
        self._btn_clear_recent = QPushButton("清空")
        self._btn_clear_recent.setToolTip("清空最近文件列表")
        self._btn_clear_recent.clicked.connect(self._clear_recent)
        self._btn_pin = QPushButton("固定")
        self._btn_pin.setCheckable(True)
        self._btn_pin.setToolTip("固定选中文件到列表顶部")
        recent_toolbar.addStretch()
        recent_toolbar.addWidget(self._btn_clear_recent)
        recent_toolbar.addWidget(self._btn_pin)
        left_layout.addLayout(recent_toolbar)

        layout.addWidget(left_group, 1)

        # ---- 右侧：加载控制 ----
        right_group = QGroupBox("加载数据")
        right_layout = QVBoxLayout(right_group)

        # 文件选择按钮
        self._btn_browse = QPushButton("浏览并加载...")
        self._btn_browse.setMinimumHeight(40)
        self._btn_browse.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._btn_browse.clicked.connect(self._browse_file)
        right_layout.addWidget(self._btn_browse)

        # 分隔线
        right_layout.addWidget(self._separator())

        # 高级选项
        adv_group = QGroupBox("高级选项")
        adv_layout = QVBoxLayout(adv_group)

        # 预加载
        self._chk_preload = QPushButton("预加载到内存")
        self._chk_preload.setCheckable(True)
        self._chk_preload.setChecked(True)
        self._chk_preload.setToolTip("将所有数据读入内存（大文件时慎用）")
        adv_layout.addWidget(self._chk_preload)

        # 表格格式参数（CSV/Excel）
        self._grp_table = QGroupBox("表格格式参数")
        self._grp_table.setVisible(False)
        table_layout = QVBoxLayout(self._grp_table)

        row = QHBoxLayout()
        row.addWidget(QLabel("采样率 (Hz):"))
        self._edit_sfreq = QLineEdit("250")
        self._edit_sfreq.setPlaceholderText("必填，如 250")
        row.addWidget(self._edit_sfreq)
        table_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("时间列:"))
        self._edit_time_col = QLineEdit()
        self._edit_time_col.setPlaceholderText("可选：列名或索引")
        row.addWidget(self._edit_time_col)
        table_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("单位:"))
        self._cmb_unit = QLineEdit("uV")
        self._cmb_unit.setPlaceholderText("uV / mV / V")
        row.addWidget(self._cmb_unit)
        table_layout.addLayout(row)

        adv_layout.addWidget(self._grp_table)

        right_layout.addWidget(adv_group)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("就绪")
        self._progress.setVisible(False)
        right_layout.addWidget(self._progress)

        # 状态标签
        self._lbl_status = QLabel("未加载数据")
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet("color: #666; font-size: 12px;")
        right_layout.addWidget(self._lbl_status)

        right_layout.addStretch()
        layout.addWidget(right_group, 2)

        # 初始填充最近文件
        self._update_recent_list(self._vm._config_mgr.config.recent_files)

    def _connect_signals(self):
        self._vm.recent_files_changed.connect(self._update_recent_list)
        self._vm.loading_progress.connect(self._on_loading_progress)
        self._vm.status_message.connect(self._on_status_message)
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    @Slot(list)
    def _update_recent_list(self, files: list[str]):
        self._recent_list.clear()
        for f in files:
            item = QListWidgetItem(f)
            item.setToolTip(f)
            self._recent_list.addItem(item)

    @Slot(object)
    def _on_loading_progress(self, progress: FileLoadProgress):
        self._progress.setVisible(True)
        if progress.stage == "reading":
            self._progress.setRange(0, progress.total)
            self._progress.setValue(progress.current)
            self._progress.setFormat(f"{progress.message} ({progress.current}/{progress.total})")
        elif progress.stage == "writing":
            self._progress.setRange(0, progress.total)
            self._progress.setValue(progress.current)
            self._progress.setFormat(f"保存中... {progress.current}%")
        elif progress.stage == "complete":
            self._progress.setValue(self._progress.maximum())
            self._progress.setFormat("完成")
            QTimer.singleShot(2000, lambda: self._progress.setVisible(False))
        elif progress.stage == "error":
            self._progress.setFormat(f"错误: {progress.message}")
            self._progress.setStyleSheet("QProgressBar::chunk { background: #e74c3c; }")

    @Slot(str)
    def _on_status_message(self, msg: str):
        self._lbl_status.setText(msg)
        self.status_message.emit(msg)

    @Slot(object)
    def _on_dataset_changed(self, dataset):
        if dataset:
            self._lbl_status.setText(
                f"已加载: {dataset.name} | {dataset.n_channels}ch | "
                f"{dataset.sfreq:.1f}Hz | {dataset.duration:.2f}s"
            )
            self.dataset_loaded.emit(dataset)
        else:
            self._lbl_status.setText("未加载数据")

    # ---- 交互槽 ----
    @Slot()
    def _browse_file(self):
        filters = (
            "EEG 数据 (*.edf *.bdf *.vhdr *.vmrk *.eeg *.set *.csv *.tsv *.txt *.xlsx *.xls);;"
            "EDF/BDF (*.edf *.bdf);;"
            "BrainVision (*.vhdr);;"
            "EEGLAB (*.set);;"
            "表格文件 (*.csv *.tsv *.txt *.xlsx *.xls);;"
            "所有文件 (*.*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, "打开 EEG 数据", "", filters)
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str):
        """启动后台加载"""
        # 检查是否为表格格式，显示参数输入
        ext = Path(file_path).suffix.lower()
        table_exts = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ods"}
        if ext in table_exts:
            self._grp_table.setVisible(True)

        kwargs = {}
        if self._chk_preload.isChecked():
            kwargs["preload"] = True

        if ext in table_exts:
            try:
                kwargs["sfreq"] = float(self._edit_sfreq.text())
            except ValueError:
                QMessageBox.warning(self, "参数错误", "请输入有效的采样率")
                return
            if self._edit_time_col.text():
                try:
                    kwargs["time_column"] = int(self._edit_time_col.text())
                except ValueError:
                    kwargs["time_column"] = self._edit_time_col.text()
            kwargs["unit"] = self._cmb_unit.text() or "uV"

        # 创建工作线程
        self._worker_thread = QThread()
        self._worker = LoadWorker(self._vm, file_path, kwargs)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.error.connect(self._on_load_error)
        self._worker.progress.connect(self._vm.loading_progress.emit)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

        self._btn_browse.setEnabled(False)
        self._btn_browse.setText("加载中...")

    @Slot(object)
    def _on_load_finished(self, result):
        self._btn_browse.setEnabled(True)
        self._btn_browse.setText("浏览并加载...")
        self._grp_table.setVisible(False)
        if result and result.dataset:
            self._vm._dataset = result.dataset
            self._vm._event_editor = None
            self._vm._metadata = result.dataset.metadata
            self._vm.dataset_changed.emit(result.dataset)

    @Slot(str)
    def _on_load_error(self, error: str):
        self._btn_browse.setEnabled(True)
        self._btn_browse.setText("浏览并加载...")
        self._grp_table.setVisible(False)
        QMessageBox.critical(self, "加载失败", error)

    @Slot()
    def _clear_recent(self):
        self._vm._config_mgr.config.recent_files.clear()
        self._vm._config_mgr.save()
        self._update_recent_list([])

    @Slot()
    def _show_recent_context_menu(self, pos):
        item = self._recent_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_open = QAction("打开", self)
        act_open.triggered.connect(lambda: self._load_file(item.text()))
        act_remove = QAction("从列表移除", self)
        act_remove.triggered.connect(lambda: self._remove_recent(item.text()))
        act_copy = QAction("复制路径", self)
        act_copy.triggered.connect(lambda: self._copy_path(item.text()))
        menu.addAction(act_open)
        menu.addAction(act_remove)
        menu.addSeparator()
        menu.addAction(act_copy)
        menu.exec(self._recent_list.mapToGlobal(pos))

    def _remove_recent(self, path: str):
        files = self._vm._config_mgr.config.recent_files
        if path in files:
            files.remove(path)
            self._vm._config_mgr.save()
            self._update_recent_list(files)

    def _copy_path(self, path: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(path)
        self.status_message.emit(f"已复制: {path}")

    @Slot(QListWidgetItem)
    def _on_recent_double_clicked(self, item: QListWidgetItem):
        self._load_file(item.text())

    @staticmethod
    def _separator():
        from PySide6.QtWidgets import QFrame
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line