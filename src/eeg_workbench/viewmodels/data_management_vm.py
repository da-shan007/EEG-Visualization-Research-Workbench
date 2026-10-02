"""数据管理模块 ViewModel：暴露给 UI 的命令、状态、数据绑定"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from pathlib import Path
import numpy as np

from PySide6.QtCore import Signal, Slot, QObject, QUrl
from PySide6.QtWidgets import QFileDialog, QMessageBox

from eeg_workbench.core.base import ViewModelBase, Command, async_slot
from eeg_workbench.core.events import get_event_bus, EventType
from eeg_workbench.models.dataset import EEGDataset, Event, Montage, ChannelInfo
from eeg_workbench.models.metadata import DatasetMetadata, SubjectInfo, ExperimentCondition, Sex, GroupType, Handedness
from eeg_workbench.services.io import ReaderFactory, LoadResult
from eeg_workbench.services.events import EventEditor, import_vmrk, import_tsv, export_vmrk, export_tsv
from eeg_workbench.services.segmentation import crop_dataset, concatenate_datasets, CropResult
from eeg_workbench.utils.montage import load_elp, load_csd, standard_montage_names


@dataclass
class FileLoadProgress:
    """文件加载进度信息"""
    stage: str = ""
    current: int = 0
    total: int = 100
    message: str = ""


class DataManagementViewModel(ViewModelBase):
    """数据管理模块主 ViewModel

    职责：
    - 当前数据集状态管理
    - 文件加载/保存命令
    - 元数据编辑绑定
    - 事件编辑器代理
    - 裁剪/拼接操作
    - 进度/错误/状态反馈
    """

    # ---- 状态信号 (供 QML/Widget 绑定) ----
    dataset_changed = Signal(object)          # EEGDataset | None
    dataset_info_changed = Signal(str)        # 信息字符串
    channels_changed = Signal(list)           # list[str]
    events_changed = Signal(list)             # list[dict]
    metadata_changed = Signal(object)         # DatasetMetadata
    montage_changed = Signal(object)          # Montage | None
    recent_files_changed = Signal(list)       # list[str]
    loading_progress = Signal(object)         # FileLoadProgress
    event_editor_ready = Signal(object)       # EventEditor

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._dataset: Optional[EEGDataset] = None
        self._event_editor: Optional[EventEditor] = None
        self._metadata: Optional[DatasetMetadata] = None
        self._montage: Optional[Montage] = None

        # 订阅全局事件
        self._subs = []
        self._subs.append(get_event_bus().subscribe(EventType.DATASET_LOADED, self._on_dataset_loaded))
        self._subs.append(get_event_bus().subscribe(EventType.DATASET_MODIFIED, self._on_dataset_modified))
        self._subs.append(get_event_bus().subscribe(EventType.EVENTS_IMPORTED, self._on_events_imported))

        # 从配置恢复最近文件
        from eeg_workbench.core.config import get_config_manager
        self._config_mgr = get_config_manager()
        self.recent_files_changed.emit(self._config_mgr.config.recent_files)

    # ---- 只读属性 ----
    @property
    def dataset(self) -> Optional[EEGDataset]:
        return self._dataset

    @property
    def event_editor(self) -> Optional[EventEditor]:
        return self._event_editor

    @property
    def metadata(self) -> Optional[DatasetMetadata]:
        return self._metadata

    @property
    def montage(self) -> Optional[Montage]:
        return self._montage

    @property
    def has_dataset(self) -> bool:
        return self._dataset is not None

    @property
    def dataset_summary(self) -> str:
        if not self._dataset:
            return "未加载数据"
        ds = self._dataset
        return (f"{ds.name} | {ds.n_channels} 通道 | "
                f"{ds.sfreq:.1f} Hz | {ds.duration:.2f} s | "
                f"{len(ds.events)} 事件")

    # ---- 文件操作命令 ----
    @Slot()
    def load_file_dialog(self) -> None:
        """打开文件对话框加载数据"""
        filters = (
            "EEG 数据 (*.edf *.bdf *.vhdr *.vmrk *.eeg *.set *.csv *.tsv *.txt *.xlsx *.xls);;"
            "EDF/BDF (*.edf *.bdf);;"
            "BrainVision (*.vhdr);;"
            "EEGLAB (*.set);;"
            "表格文件 (*.csv *.tsv *.txt *.xlsx *.xls);;"
            "所有文件 (*.*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            None, "打开 EEG 数据文件", "", filters
        )
        if file_path:
            self.load_file(file_path)

    @async_slot
    def load_file(self, file_path: str, **kwargs) -> LoadResult:
        """异步加载文件（后台线程）"""
        self.show_status(f"正在加载: {Path(file_path).name}")
        self.loading_progress.emit(FileLoadProgress(stage="reading", current=10, total=100, message="读取文件..."))

        try:
            result = ReaderFactory.load_dataset(file_path, **kwargs)
        except Exception as e:
            self.error_occurred.emit(f"加载失败: {e}")
            self.loading_progress.emit(FileLoadProgress(stage="error", message=str(e)))
            raise

        self.loading_progress.emit(FileLoadProgress(stage="complete", current=100, total=100, message="完成"))
        self.show_status(f"已加载: {Path(file_path).name}")

        # 更新最近文件
        self._config_mgr.add_recent_file(file_path)
        self.recent_files_changed.emit(self._config_mgr.config.recent_files)

        # 落定数据集并通知各模块（与 DatasetLoaderWidget._on_load_finished 一致）
        if result and result.dataset:
            self._dataset = result.dataset
            self._event_editor = None
            self._metadata = result.dataset.metadata
            self.dataset_changed.emit(self._dataset)

        return result

    @async_slot
    def save_dataset(self, file_path: str, format: str = "auto") -> bool:
        """保存数据集（导出为 EDF/CSV/EEGLAB 等）"""
        if not self._dataset:
            self.error_occurred.emit("无数据可保存")
            return False

        try:
            self.loading_progress.emit(FileLoadProgress(stage="writing", current=50, total=100, message="写入文件..."))

            raw = self._dataset.to_mne_raw()

            if format == "auto":
                ext = Path(file_path).suffix.lower()
                if ext in (".edf", ".bdf"):
                    raw.export(file_path, fmt="edf", overwrite=True)
                elif ext == ".set":
                    raw.export(file_path, fmt="eeglab", overwrite=True)
                elif ext in (".csv", ".tsv"):
                    self._export_table(raw, file_path, ext)
                else:
                    raw.export(file_path, fmt="edf", overwrite=True)
            elif format == "edf":
                raw.export(file_path, fmt="edf", overwrite=True)
            elif format == "eeglab":
                raw.export(file_path, fmt="eeglab", overwrite=True)
            elif format == "csv":
                self._export_table(raw, file_path, ".csv")
            elif format == "tsv":
                self._export_table(raw, file_path, ".tsv")
            else:
                raise ValueError(f"不支持的导出格式: {format}")

            self.loading_progress.emit(FileLoadProgress(stage="complete", current=100, total=100, message="保存完成"))
            self.show_status(f"已保存: {Path(file_path).name}")
            return True

        except Exception as e:
            self.error_occurred.emit(f"保存失败: {e}")
            self.loading_progress.emit(FileLoadProgress(stage="error", message=str(e)))
            return False

    def _export_table(self, raw, file_path: str, ext: str) -> None:
        """导出为表格格式"""
        import pandas as pd
        data = raw.get_data() * 1e6  # V -> µV
        ch_names = raw.ch_names
        times = raw.times
        df = pd.DataFrame(data.T, columns=ch_names)
        df.insert(0, "time", times)
        if ext == ".csv":
            df.to_csv(file_path, index=False, float_format="%.6f")
        else:
            df.to_csv(file_path, sep="\t", index=False, float_format="%.6f")

    @Slot()
    def close_dataset(self) -> None:
        """关闭当前数据集"""
        if self._dataset:
            from eeg_workbench.core.events import get_event_bus, EventType
            get_event_bus().publish(EventType.DATASET_CLOSED, {"dataset_id": self._dataset.id}, source="DataManagementVM")
        self._dataset = None
        self._event_editor = None
        self._metadata = None
        self._montage = None
        self.dataset_changed.emit(None)
        self.dataset_info_changed.emit("未加载数据")
        self.channels_changed.emit([])
        self.events_changed.emit([])
        self.metadata_changed.emit(None)
        self.montage_changed.emit(None)

    # ---- 元数据编辑 ----
    def update_metadata(self, **fields) -> None:
        """更新元数据字段（绑定到表单）"""
        if not self._metadata:
            self._metadata = DatasetMetadata()

        for key, value in fields.items():
            if hasattr(self._metadata, key):
                setattr(self._metadata, key, value)

        # 同步到数据集
        if self._dataset:
            self._dataset.metadata = self._metadata
            self._dataset = self._dataset.add_processing_step({
                "step": "metadata_update",
                "params": fields
            })
            self.metadata_changed.emit(self._metadata)
            self.dataset_changed.emit(self._dataset)

    def create_subject_info(self, subject_id: str, age: int | None = None,
                            sex: str = "U", group: str = "other") -> SubjectInfo:
        """创建/更新受试者信息"""
        subj = SubjectInfo(
            subject_id=subject_id,
            age=age,
            sex=Sex(sex.upper()),
            group=GroupType(group.lower())
        )
        if self._metadata:
            self._metadata.subject = subj
            self.metadata_changed.emit(self._metadata)
        return subj

    def add_condition(self, name: str, description: str = "",
                      event_codes: list[int] = None,
                      tmin: float = -0.2, tmax: float = 0.8) -> ExperimentCondition:
        """添加实验条件"""
        cond = ExperimentCondition(
            name=name,
            description=description,
            event_codes=event_codes or [],
            tmin=tmin,
            tmax=tmax
        )
        if self._metadata:
            self._metadata.add_condition(cond)
            self.metadata_changed.emit(self._metadata)
        return cond

    # ---- 事件编辑代理 ----
    def get_event_editor(self) -> EventEditor:
        """获取或创建事件编辑器

        dataset 被替换后（montage/预处理等）旧编辑器持有过期快照，
        编辑结果会丢失后续变更（如 montage 字段），故惰性同步。
        """
        if self._dataset and (
            not self._event_editor
            or getattr(self._event_editor, "_dataset", None) is not self._dataset
        ):
            self._event_editor = EventEditor(self._dataset)
            self.event_editor_ready.emit(self._event_editor)
            self._refresh_events_view()
        return self._event_editor

    def add_event(self, onset: float, description: str, duration: float = 0.0,
                  value: int = 0) -> bool:
        """添加事件（简化接口）"""
        editor = self.get_event_editor()
        if not editor:
            return False
        ev = Event(onset=onset, duration=duration, description=description, value=value)
        self._dataset = editor.add_event(ev)
        editor.sync_dataset(self._dataset)
        self.dataset_changed.emit(self._dataset)
        return True

    def remove_event(self, index: int) -> bool:
        editor = self.get_event_editor()
        if not editor:
            return False
        self._dataset = editor.remove_event(index)
        editor.sync_dataset(self._dataset)
        self.dataset_changed.emit(self._dataset)
        return True

    def update_event(self, index: int, **kwargs) -> bool:
        editor = self.get_event_editor()
        if not editor or not (0 <= index < len(self._dataset.events)):
            return False
        old = self._dataset.events[index]
        new_ev = Event(
            onset=kwargs.get("onset", old.onset),
            duration=kwargs.get("duration", old.duration),
            description=kwargs.get("description", old.description),
            value=kwargs.get("value", old.value),
            sample=kwargs.get("sample", old.sample),
            channel=kwargs.get("channel", old.channel),
            confidence=kwargs.get("confidence", old.confidence),
            custom_meta={**old.custom_meta, **kwargs.get("custom_meta", {})}
        )
        self._dataset = editor.update_event(index, new_ev)
        editor.sync_dataset(self._dataset)
        self.dataset_changed.emit(self._dataset)
        return True

    def import_events_vmrk(self, file_path: str) -> bool:
        if not self._dataset:
            return False
        try:
            self._dataset = import_vmrk(file_path, self._dataset)
            self.dataset_changed.emit(self._dataset)
            return True
        except Exception as e:
            self.error_occurred.emit(f"导入 VMRK 失败: {e}")
            return False

    def import_events_tsv(self, file_path: str) -> bool:
        if not self._dataset:
            return False
        try:
            self._dataset = import_tsv(file_path, self._dataset)
            self.dataset_changed.emit(self._dataset)
            return True
        except Exception as e:
            self.error_occurred.emit(f"导入 TSV 失败: {e}")
            return False

    def export_events_vmrk(self, file_path: str) -> bool:
        if not self._dataset:
            return False
        try:
            export_vmrk(self._dataset, file_path)
            self.show_status(f"已导出 VMRK: {Path(file_path).name}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出 VMRK 失败: {e}")
            return False

    def export_events_tsv(self, file_path: str) -> bool:
        if not self._dataset:
            return False
        try:
            export_tsv(self._dataset, file_path)
            self.show_status(f"已导出 TSV: {Path(file_path).name}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"导出 TSV 失败: {e}")
            return False

    def auto_detect_bad_segments(self, threshold_uv: float = 100.0) -> int:
        """自动检测坏段"""
        editor = self.get_event_editor()
        if not editor:
            return 0
        new_events = editor.auto_detect_bad_segments(threshold_uv=threshold_uv)
        self.dataset_changed.emit(self._dataset)
        return len(new_events)

    # ---- 裁剪/拼接 ----
    @async_slot
    def crop(self, tmin: float, tmax: float) -> CropResult | None:
        """时间裁剪"""
        if not self._dataset:
            return None
        try:
            self.show_status(f"裁剪: {tmin:.2f}s - {tmax:.2f}s")
            result = crop_dataset(self._dataset, tmin, tmax)
            self._dataset = result.dataset
            self.dataset_changed.emit(self._dataset)
            self.show_status(f"裁剪完成，移除 {len(result.removed_events)} 个事件")
            return result
        except Exception as e:
            self.error_occurred.emit(f"裁剪失败: {e}")
            return None

    @async_slot
    def concatenate(self, file_paths: list[str], gap_seconds: float = 0.0) -> EEGDataset | None:
        """拼接多个文件"""
        if not self._dataset:
            self.error_occurred.emit("请先加载基础数据集")
            return None

        datasets = [self._dataset]
        for fp in file_paths:
            try:
                result = ReaderFactory.load_dataset(fp)
                datasets.append(result.dataset)
            except Exception as e:
                self.error_occurred.emit(f"加载拼接文件失败 {fp}: {e}")
                return None

        try:
            self.show_status(f"正在拼接 {len(datasets)} 个数据集...")
            new_ds = concatenate_datasets(datasets, gap_seconds=gap_seconds)
            self._dataset = new_ds
            self.dataset_changed.emit(self._dataset)
            self.show_status("拼接完成")
            return new_ds
        except Exception as e:
            self.error_occurred.emit(f"拼接失败: {e}")
            return None

    # ---- 蒙版管理 ----
    def load_montage_elp(self, file_path: str) -> bool:
        """加载 .elp 电极坐标文件"""
        try:
            montage = load_elp(file_path)
            if montage and self._dataset:
                self._dataset = self._dataset.set_montage(montage)
                self._montage = montage
                self.montage_changed.emit(montage)
                self.dataset_changed.emit(self._dataset)
                self.show_status(f"已加载蒙版: {Path(file_path).name}")
                return True
        except Exception as e:
            self.error_occurred.emit(f"加载 ELP 失败: {e}")
        return False

    def load_montage_csd(self, file_path: str) -> bool:
        """加载 .csd 电极坐标文件"""
        try:
            montage = load_csd(file_path)
            if montage and self._dataset:
                self._dataset = self._dataset.set_montage(montage)
                self._montage = montage
                self.montage_changed.emit(montage)
                self.dataset_changed.emit(self._dataset)
                self.show_status(f"已加载蒙版: {Path(file_path).name}")
                return True
        except Exception as e:
            self.error_occurred.emit(f"加载 CSD 失败: {e}")
        return False

    def apply_standard_montage(self, name: str) -> bool:
        """应用标准蒙版 (standard_1020, standard_1005 等)"""
        try:
            import mne
            mne_montage = mne.channels.make_standard_montage(name)
            montage = Montage.from_mne_montage(mne_montage, name=name)
            if self._dataset:
                self._dataset = self._dataset.set_montage(montage)
                self._montage = montage
                self.montage_changed.emit(montage)
                self.dataset_changed.emit(self._dataset)
                self.show_status(f"已应用标准蒙版: {name}")
                return True
        except Exception as e:
            self.error_occurred.emit(f"应用标准蒙版失败: {e}")
        return False

    def get_standard_montage_names(self) -> list[str]:
        return standard_montage_names()

    # ---- 通道管理 ----
    def set_bad_channels(self, ch_names: list[str]) -> bool:
        """标记坏道"""
        if not self._dataset:
            return False
        self._dataset = self._dataset.set_bad_channels(ch_names)
        self.dataset_changed.emit(self._dataset)
        self._refresh_channels_view()
        return True

    def reorder_channels(self, new_order: list[str]) -> bool:
        """重排通道顺序"""
        if not self._dataset:
            return False
        try:
            self._dataset = self._dataset.with_channels(new_order)
            self.dataset_changed.emit(self._dataset)
            self._refresh_channels_view()
            return True
        except Exception as e:
            self.error_occurred.emit(f"重排通道失败: {e}")
            return False

    # ---- 内部刷新 ----
    def _refresh_events_view(self) -> None:
        if self._dataset:
            events_data = [
                {
                    "index": i,
                    "onset": round(ev.onset, 6),
                    "duration": round(ev.duration, 6),
                    "description": ev.description,
                    "value": ev.value,
                    "sample": ev.sample,
                    "channel": ev.channel,
                    "confidence": ev.confidence,
                }
                for i, ev in enumerate(self._dataset.events)
            ]
            self.events_changed.emit(events_data)

    def _refresh_channels_view(self) -> None:
        if self._dataset:
            self.channels_changed.emit(self._dataset.ch_names.copy())

    # ---- 事件处理器 ----
    def _on_dataset_loaded(self, event) -> None:
        payload = event.payload
        # 这里不直接设置 dataset，由 load_file 返回的 LoadResult 处理
        pass

    def _on_dataset_modified(self, event) -> None:
        # 数据集被其他模块修改，刷新视图
        if self._dataset and event.payload.get("dataset_id") == self._dataset.id:
            self.dataset_changed.emit(self._dataset)
            self._refresh_events_view()
            self._refresh_channels_view()

    def _on_events_imported(self, event) -> None:
        payload = event.payload
        if self._dataset and payload.dataset_id == self._dataset.id:
            self._refresh_events_view()
            self.show_status(f"导入 {payload.count} 个事件来自 {Path(payload.source_file).name}")

    # ---- 清理 ----
    def cleanup(self) -> None:
        for unsub in self._subs:
            unsub()
        self._subs.clear()
        self.cancel_all_commands()