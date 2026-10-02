"""数据裁剪与拼接 Widget"""
from __future__ import annotations
from typing import Optional
from pathlib import Path

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QDoubleSpinBox, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QCheckBox,
    QSplitter, QFrame, QAbstractItemView, QLineEdit
)

from eeg_workbench.viewmodels.data_management_vm import DataManagementViewModel
from eeg_workbench.services.segmentation import crop_dataset, concatenate_datasets, CropResult


class ConcatenateDialog(QDialog):
    """多文件拼接对话框"""

    def __init__(self, base_dataset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("拼接数据集")
        self.setModal(True)
        self.resize(500, 400)
        self._base_dataset = base_dataset
        self._file_paths = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel(f"基础数据集: {self._base_dataset.name} ({self._base_dataset.n_channels}ch, {self._base_dataset.sfreq:.1f}Hz)")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(info)

        # 文件列表
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list)

        # 工具栏
        toolbar = QHBoxLayout()
        btn_add = QPushButton("添加文件")
        btn_add.clicked.connect(self._add_files)
        btn_remove = QPushButton("移除选中")
        btn_remove.clicked.connect(self._remove_selected)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_list)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_remove)
        toolbar.addWidget(btn_clear)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 间隙设置
        gap_layout = QHBoxLayout()
        gap_layout.addWidget(QLabel("拼接间隙:"))
        self._spin_gap = QDoubleSpinBox()
        self._spin_gap.setRange(0, 60)
        self._spin_gap.setDecimals(3)
        self._spin_gap.setSingleStep(0.1)
        self._spin_gap.setSuffix(" s")
        gap_layout.addWidget(self._spin_gap)
        gap_layout.addStretch()
        layout.addLayout(gap_layout)

        # 边界事件
        self._chk_boundary = QCheckBox("在拼接点添加边界事件")
        self._chk_boundary.setChecked(True)
        layout.addWidget(self._chk_boundary)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_files(self):
        filters = "EEG 数据 (*.edf *.bdf *.vhdr *.set *.csv *.tsv *.xlsx);;所有文件 (*.*)"
        files, _ = QFileDialog.getOpenFileNames(self, "选择要拼接的文件", "", filters)
        for f in files:
            if f not in self._file_paths:
                self._file_paths.append(f)
                item = QListWidgetItem(f)
                item.setToolTip(f)
                self._list.addItem(item)

    def _remove_selected(self):
        for item in self._list.selectedItems():
            path = item.text()
            if path in self._file_paths:
                self._file_paths.remove(path)
            self._list.takeItem(self._list.row(item))

    def _clear_list(self):
        self._file_paths.clear()
        self._list.clear()

    def get_file_paths(self) -> list[str]:
        return self._file_paths

    def get_gap_seconds(self) -> float:
        return self._spin_gap.value()

    def get_add_boundary_events(self) -> bool:
        return self._chk_boundary.isChecked()


class SegmentationWidget(QWidget):
    """裁剪与拼接面板"""

    dataset_changed = Signal(object)  # EEGDataset
    status_message = Signal(str)

    def __init__(self, viewmodel: DataManagementViewModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._vm = viewmodel
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ---- 裁剪区域 ----
        crop_group = QGroupBox("时间裁剪")
        crop_layout = QFormLayout(crop_group)

        # 当前数据集时长显示
        self._lbl_duration = QLabel("未加载数据")
        self._lbl_duration.setStyleSheet("color: #666;")
        crop_layout.addRow("数据时长:", self._lbl_duration)

        # 裁剪范围
        row = QHBoxLayout()
        self._spin_tmin = QDoubleSpinBox()
        self._spin_tmin.setRange(0, 86400)
        self._spin_tmin.setDecimals(3)
        self._spin_tmin.setSingleStep(0.1)
        self._spin_tmin.setSuffix(" s")
        row.addWidget(self._spin_tmin)

        self._spin_tmax = QDoubleSpinBox()
        self._spin_tmax.setRange(0, 86400)
        self._spin_tmax.setDecimals(3)
        self._spin_tmax.setSingleStep(0.1)
        self._spin_tmax.setSuffix(" s")
        row.addWidget(self._spin_tmax)
        crop_layout.addRow("裁剪范围:", row)

        self._chk_include_tmax = QCheckBox("包含结束时刻")
        self._chk_include_tmax.setChecked(True)
        crop_layout.addRow("", self._chk_include_tmax)

        self._chk_keep_events = QCheckBox("保留范围内事件 (时间归零)")
        self._chk_keep_events.setChecked(True)
        crop_layout.addRow("", self._chk_keep_events)

        # 快速按钮
        quick_row = QHBoxLayout()
        self._btn_crop_first_10 = QPushButton("前 10 秒")
        self._btn_crop_first_10.clicked.connect(lambda: self._quick_crop(0, 10))
        self._btn_crop_last_10 = QPushButton("后 10 秒")
        self._btn_crop_last_10.clicked.connect(self._crop_last_10)
        self._btn_crop_middle = QPushButton("中间 30 秒")
        self._btn_crop_middle.clicked.connect(self._crop_middle_30)
        quick_row.addWidget(self._btn_crop_first_10)
        quick_row.addWidget(self._btn_crop_last_10)
        quick_row.addWidget(self._btn_crop_middle)
        quick_row.addStretch()
        crop_layout.addRow("快速裁剪:", quick_row)

        # 执行裁剪
        self._btn_crop = QPushButton("执行裁剪")
        self._btn_crop.setStyleSheet("font-weight: bold; padding: 8px;")
        self._btn_crop.clicked.connect(self._do_crop)
        crop_layout.addRow("", self._btn_crop)

        layout.addWidget(crop_group)

        # ---- 拼接区域 ----
        concat_group = QGroupBox("数据拼接")
        concat_layout = QVBoxLayout(concat_group)

        info = QLabel("将多个同通道、同采样率的数据集按时间顺序拼接")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 12px;")
        concat_layout.addWidget(info)

        self._btn_concat = QPushButton("选择文件并拼接...")
        self._btn_concat.setMinimumHeight(36)
        self._btn_concat.clicked.connect(self._do_concatenate)
        concat_layout.addWidget(self._btn_concat)

        layout.addWidget(concat_group)

        # ---- 分割区域 ----
        split_group = QGroupBox("按事件分割 (生成 Epochs)")
        split_layout = QFormLayout(split_group)

        self._edit_split_events = QLineEdit()
        self._edit_split_events.setPlaceholderText("事件描述，逗号分隔 (如: Stimulus/Target,Stimulus/NonTarget)")
        split_layout.addRow("触发事件:", self._edit_split_events)

        row = QHBoxLayout()
        self._spin_split_tmin = QDoubleSpinBox()
        self._spin_split_tmin.setRange(-10, 10)
        self._spin_split_tmin.setDecimals(3)
        self._spin_split_tmin.setValue(-0.2)
        self._spin_split_tmin.setSuffix(" s")
        row.addWidget(self._spin_split_tmin)

        self._spin_split_tmax = QDoubleSpinBox()
        self._spin_split_tmax.setRange(-10, 10)
        self._spin_split_tmax.setDecimals(3)
        self._spin_split_tmax.setValue(0.8)
        self._spin_split_tmax.setSuffix(" s")
        row.addWidget(self._spin_split_tmax)
        split_layout.addRow("时间窗:", row)

        self._chk_split_baseline = QCheckBox("应用基线校正")
        self._chk_split_baseline.setChecked(True)
        split_layout.addRow("", self._chk_split_baseline)

        self._btn_split = QPushButton("分割并导出 Epochs")
        self._btn_split.clicked.connect(self._do_split)
        split_layout.addRow("", self._btn_split)

        layout.addWidget(split_group)

        layout.addStretch()

        # 初始禁用
        self.setEnabled(False)

    def _connect_signals(self):
        self._vm.dataset_changed.connect(self._on_dataset_changed)

    @Slot(object)
    def _on_dataset_changed(self, dataset):
        self.setEnabled(dataset is not None)
        if dataset:
            self._lbl_duration.setText(f"{dataset.duration:.3f} 秒 ({dataset.n_samples} 样本点)")
            self._spin_tmin.setMaximum(dataset.duration)
            self._spin_tmax.setMaximum(dataset.duration)
            self._spin_tmax.setValue(dataset.duration)

    def _quick_crop(self, tmin: float, tmax: float):
        ds = self._vm.dataset
        if not ds:
            return
        tmax = min(tmax, ds.duration)
        self._spin_tmin.setValue(tmin)
        self._spin_tmax.setValue(tmax)
        self._do_crop()

    def _crop_last_10(self):
        ds = self._vm.dataset
        if not ds:
            return
        tmin = max(0, ds.duration - 10)
        tmax = ds.duration
        self._spin_tmin.setValue(tmin)
        self._spin_tmax.setValue(tmax)
        self._do_crop()

    def _crop_middle_30(self):
        ds = self._vm.dataset
        if not ds:
            return
        mid = ds.duration / 2
        tmin = max(0, mid - 15)
        tmax = min(ds.duration, mid + 15)
        self._spin_tmin.setValue(tmin)
        self._spin_tmax.setValue(tmax)
        self._do_crop()

    @Slot()
    def _do_crop(self):
        ds = self._vm.dataset
        if not ds:
            return

        tmin = self._spin_tmin.value()
        tmax = self._spin_tmax.value()

        if tmin >= tmax:
            QMessageBox.warning(self, "参数错误", "起始时间必须小于结束时间")
            return

        if tmax > ds.duration:
            QMessageBox.warning(self, "参数错误", f"结束时间超出数据时长 ({ds.duration:.3f}s)")
            return

        self._btn_crop.setEnabled(False)
        self._btn_crop.setText("裁剪中...")

        # 使用 ViewModel 的异步方法
        result = self._vm.crop(tmin, tmax)
        if result:
            self._vm.dataset_changed.emit(result.dataset)
            self.status_message.emit(f"裁剪完成: {tmin:.2f}s - {tmax:.2f}s, 移除 {len(result.removed_events)} 事件")

        self._btn_crop.setEnabled(True)
        self._btn_crop.setText("执行裁剪")

    @Slot()
    def _do_concatenate(self):
        ds = self._vm.dataset
        if not ds:
            return

        dlg = ConcatenateDialog(ds, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            files = dlg.get_file_paths()
            if not files:
                return

            gap = dlg.get_gap_seconds()
            add_boundary = dlg.get_add_boundary_events()

            self._btn_concat.setEnabled(False)
            self._btn_concat.setText("拼接中...")

            result = self._vm.concatenate(files, gap_seconds=gap)
            if result:
                self._vm.dataset_changed.emit(result)
                self.status_message.emit(f"拼接完成: 共 {len(files)+1} 个数据集")

            self._btn_concat.setEnabled(True)
            self._btn_concat.setText("选择文件并拼接...")

    @Slot()
    def _do_split(self):
        ds = self._vm.dataset
        if not ds:
            return

        event_text = self._edit_split_events.text().strip()
        if not event_text:
            QMessageBox.warning(self, "参数错误", "请输入触发事件描述")
            return

        event_descs = [e.strip() for e in event_text.split(",") if e.strip()]
        tmin = self._spin_split_tmin.value()
        tmax = self._spin_split_tmax.value()

        if tmin >= tmax:
            QMessageBox.warning(self, "参数错误", "起始时间必须小于结束时间")
            return

        from eeg_workbench.services.segmentation import extract_epochs_as_dataset
        baseline = (tmin, 0.0) if self._chk_split_baseline.isChecked() else None

        try:
            epochs = extract_epochs_as_dataset(ds, event_descs, tmin, tmax, baseline)
            if not epochs:
                QMessageBox.information(self, "结果", "未找到匹配的事件")
                return

            # 让用户选择保存目录
            dir_path = QFileDialog.getExistingDirectory(self, "选择 Epochs 保存目录")
            if not dir_path:
                return

            from eeg_workbench.services.io import ReaderFactory
            saved = 0
            for ep in epochs:
                fname = f"{ep.name}.edf"
                fpath = Path(dir_path) / fname
                try:
                    raw = ep.to_mne_raw()
                    raw.export(str(fpath), fmt="edf", overwrite=True)
                    saved += 1
                except Exception as e:
                    print(f"保存 {fname} 失败: {e}")

            self.status_message.emit(f"已导出 {saved} 个 Epochs 到 {dir_path}")
            QMessageBox.information(self, "完成", f"成功导出 {saved} 个 Epochs\n保存目录: {dir_path}")

        except Exception as e:
            QMessageBox.critical(self, "分割失败", str(e))