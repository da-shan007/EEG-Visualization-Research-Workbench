"""IO 服务基类与工厂：统一入口 load_dataset(path) -> EEGDataset"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import numpy as np

from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, Event, Montage, ChannelType
from eeg_workbench.models.metadata import DatasetMetadata, SubjectInfo, ExperimentCondition
from eeg_workbench.core.events import get_event_bus, EventType, DatasetLoadedPayload


@dataclass
class LoadResult:
    """加载结果容器"""
    dataset: EEGDataset
    warnings: list[str] = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}


class BaseReader(ABC):
    """所有格式读取器的抽象基类"""

    # 子类需定义
    EXTENSIONS: tuple[str, ...] = ()
    FORMAT_NAME: str = "Unknown"

    @abstractmethod
    def read(self, file_path: str, **kwargs) -> LoadResult:
        """读取文件，返回 LoadResult"""
        pass

    def _create_dataset(self, raw, file_path: str, **kwargs) -> EEGDataset:
        """通用：从 MNE Raw 构建 EEGDataset"""
        name = kwargs.get("name", Path(file_path).stem)
        ds = EEGDataset.from_mne_raw(raw, name=name, file_path=file_path)

        # 尝试读取伴随的元数据文件
        meta = self._load_sidecar_metadata(file_path)
        if meta:
            ds.metadata = meta

        # 发布加载事件
        get_event_bus().publish(
            EventType.DATASET_LOADED,
            DatasetLoadedPayload(
                dataset_id=ds.id,
                file_path=file_path,
                n_channels=ds.n_channels,
                duration=ds.duration,
                sfreq=ds.sfreq
            ),
            source=self.FORMAT_NAME
        )
        return ds

    def _load_sidecar_metadata(self, file_path: str) -> DatasetMetadata | None:
        """尝试加载同名 .json / .yaml 元数据文件"""
        path = Path(file_path)
        for ext in (".json", ".yaml", ".yml"):
            meta_path = path.with_suffix(ext)
            if meta_path.exists():
                try:
                    if ext == ".json":
                        import json
                        with open(meta_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    else:
                        import yaml
                        with open(meta_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                    return DatasetMetadata.from_bids_sidecar(data)
                except Exception:
                    pass
        return None


class ReaderFactory:
    """读取器工厂：根据扩展名自动选择读取器"""

    _readers: dict[str, BaseReader] = {}

    @classmethod
    def register(cls, reader: BaseReader) -> None:
        for ext in reader.EXTENSIONS:
            cls._readers[ext.lower()] = reader

    @classmethod
    def get_reader(cls, file_path: str) -> BaseReader:
        ext = Path(file_path).suffix.lower()
        if ext in cls._readers:
            return cls._readers[ext]
        # 尝试双后缀 .vhdr/.vmrk 等
        for known_ext, reader in cls._readers.items():
            if file_path.lower().endswith(known_ext):
                return reader
        raise ValueError(f"不支持的文件格式: {ext} (文件: {file_path})")

    @classmethod
    def load_dataset(cls, file_path: str, **kwargs) -> LoadResult:
        """统一加载入口"""
        reader = cls.get_reader(file_path)
        return reader.read(file_path, **kwargs)

    @classmethod
    def supported_extensions(cls) -> list[str]:
        return sorted(set(cls._readers.keys()))


def register_default_readers() -> None:
    """注册默认文件读取器，避免工厂在导入时为空。"""
    from .edf import EDFReader, BDFReader
    from .brainvision import BrainVisionReader
    from .eeglab import EEGLABReader
    from .csv_excel import TableReader

    for reader in (EDFReader(), BDFReader(), BrainVisionReader(), EEGLABReader(), TableReader()):
        ReaderFactory.register(reader)


# 在模块导入时自动注册具体读取器，避免工厂为空。
register_default_readers()