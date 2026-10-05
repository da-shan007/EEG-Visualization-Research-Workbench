"""核心领域模型：EEGDataset、ChannelInfo、Event、Montage、EpochData。

纯数据结构 + 业务规则验证，不依赖 UI/IO 框架。
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Optional, Literal, Any, TYPE_CHECKING
import numpy as np
from uuid import uuid4
from enum import Enum

if TYPE_CHECKING:
    from eeg_workbench.models.metadata import DatasetMetadata


class ChannelType(Enum):
    """通道类型枚举（兼容 MNE）"""
    EEG = "eeg"
    EOG = "eog"
    ECG = "ecg"
    EMG = "emg"
    MISC = "misc"
    STIM = "stim"
    RESP = "resp"
    TEMP = "temp"
    GSR = "gsr"


@dataclass(slots=True)
class ChannelInfo:
    """单通道元信息"""
    name: str
    type: ChannelType = ChannelType.EEG
    unit: str = "µV"
    location: tuple[float, float, float] | None = None
    montage_name: str = ""
    is_bad: bool = False
    custom_meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = ChannelType(self.type.lower())
        if self.location is not None:
            self.location = tuple(float(v) for v in self.location)


@dataclass(slots=True)
class Event:
    """单个事件标记"""
    onset: float
    duration: float = 0.0
    description: str = ""
    value: int = 0
    sample: int | None = None
    channel: str = ""
    confidence: float = 1.0
    custom_meta: dict[str, Any] = field(default_factory=dict)

    CUE = "Cue"
    STIMULUS = "Stimulus"
    RESPONSE = "Response"
    BAD_SEGMENT = "BAD_segment"
    EDGE = "EDGE"

    def __post_init__(self):
        if self.sample is not None and self.sample < 0:
            raise ValueError("sample 不能为负")

    @property
    def is_cue(self) -> bool:
        return self.description.startswith(self.CUE)

    @property
    def is_stimulus(self) -> bool:
        return self.description.startswith(self.STIMULUS)

    @property
    def is_response(self) -> bool:
        return self.description.startswith(self.RESPONSE)

    @property
    def is_bad_segment(self) -> bool:
        return self.description == self.BAD_SEGMENT


@dataclass(slots=True)
class Montage:
    """电极蒙版（通道坐标系）"""
    name: str
    positions: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    nasion: tuple[float, float, float] | None = None
    lpa: tuple[float, float, float] | None = None
    rpa: tuple[float, float, float] | None = None
    coord_frame: str = "head"
    custom_meta: dict[str, Any] = field(default_factory=dict)

    def get_position(self, ch_name: str) -> tuple[float, float, float] | None:
        return self.positions.get(ch_name)

    def has_position(self, ch_name: str) -> bool:
        return ch_name in self.positions

    def to_mne_montage(self):
        try:
            import mne
            ch_pos = {k: np.array(v) / 1000.0 for k, v in self.positions.items()}
            nasion = np.array(self.nasion) / 1000.0 if self.nasion else None
            lpa = np.array(self.lpa) / 1000.0 if self.lpa else None
            rpa = np.array(self.rpa) / 1000.0 if self.rpa else None
            return mne.channels.make_dig_montage(
                ch_pos=ch_pos, nasion=nasion, lpa=lpa, rpa=rpa,
                coord_frame=self.coord_frame
            )
        except Exception:
            return None

    @classmethod
    def from_mne_montage(cls, mne_montage, name: str = "imported") -> Montage:
        # mne 1.13 的 DigMontage 不再暴露 ch_pos/nasion/lpa/rpa 属性，统一走 get_positions()
        pos_info = mne_montage.get_positions()
        positions = {}
        ch_pos = pos_info.get("ch_pos") or {}
        for ch, pos in ch_pos.items():
            if pos is not None:
                positions[ch] = tuple(np.asarray(pos) * 1000)
        nasion = tuple(np.asarray(pos_info["nasion"]) * 1000) if pos_info.get("nasion") is not None else None
        lpa = tuple(np.asarray(pos_info["lpa"]) * 1000) if pos_info.get("lpa") is not None else None
        rpa = tuple(np.asarray(pos_info["rpa"]) * 1000) if pos_info.get("rpa") is not None else None
        return cls(name=name, positions=positions, nasion=nasion, lpa=lpa, rpa=rpa,
                   coord_frame=pos_info.get("coord_frame") or "head")


@dataclass(slots=True)
class EpochData:
    """单个 Epoch 数据容器"""
    data: np.ndarray
    times: np.ndarray
    event: Event
    ch_names: list[str]
    baseline_corrected: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.data.ndim != 2:
            raise ValueError("data 必须是二维数组 (n_channels, n_times)")
        if len(self.ch_names) != self.data.shape[0]:
            raise ValueError("ch_names 长度必须等于 n_channels")
        if len(self.times) != self.data.shape[1]:
            raise ValueError("times 长度必须等于 n_times")


class ReferenceType(Enum):
    AVERAGE = "average"
    MASTOID = "mastoid"
    CZ = "cz"
    SINGLE = "single"
    REST = "rest"
    CUSTOM = "custom"


# 导入 ObservableModel（避免循环导入）
from eeg_workbench.core.base import ObservableModel


@dataclass
class EEGDataset(ObservableModel):
    """EEG 数据集核心模型"""
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    name: str = "Untitled"
    file_path: str = ""

    data: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.float64))
    sfreq: float = 0.0
    ch_names: list[str] = field(default_factory=list)
    channel_info: dict[str, ChannelInfo] = field(default_factory=dict)

    events: list[Event] = field(default_factory=list)
    annotations: list[Event] = field(default_factory=list)

    montage: Montage | None = None
    metadata: "DatasetMetadata | None" = None

    processing_history: list[dict[str, Any]] = field(default_factory=list)
    _raw_ref: Any = field(default=None, repr=False)

    @property
    def n_channels(self) -> int:
        return len(self.ch_names)

    @property
    def n_samples(self) -> int:
        return self.data.shape[1] if self.data.ndim == 2 else 0

    @property
    def duration(self) -> float:
        return self.n_samples / self.sfreq if self.sfreq > 0 else 0.0

    @property
    def times(self) -> np.ndarray:
        return np.arange(self.n_samples) / self.sfreq if self.sfreq > 0 else np.array([])

    @property
    def eeg_channels(self) -> list[str]:
        return [ch for ch in self.ch_names
                if self.channel_info.get(ch, ChannelInfo(ch)).type == ChannelType.EEG]

    @property
    def bad_channels(self) -> list[str]:
        return [ch for ch, info in self.channel_info.items() if info.is_bad]

    @property
    def good_channels(self) -> list[str]:
        return [ch for ch in self.ch_names if ch not in self.bad_channels]

    def with_data(self, new_data: np.ndarray) -> EEGDataset:
        if new_data.shape[0] != self.n_channels:
            raise ValueError(f"通道数不匹配: 期望 {self.n_channels}, 得到 {new_data.shape[0]}")
        new = replace(self, data=new_data.astype(np.float64, copy=False))
        new._notify("data", self.data, new_data)
        return new

    def with_channels(self, new_ch_names: list[str],
                      new_channel_info: dict[str, ChannelInfo] | None = None) -> EEGDataset:
        if set(new_ch_names) - set(self.ch_names):
            raise ValueError("新通道列表包含不存在的通道")
        reorder_idx = [self.ch_names.index(ch) for ch in new_ch_names]
        new_data = self.data[reorder_idx, :]
        new_info = new_channel_info or {ch: self.channel_info[ch] for ch in new_ch_names}
        new = replace(self, data=new_data, ch_names=new_ch_names, channel_info=new_info)
        new._notify("ch_names", self.ch_names, new_ch_names)
        return new

    def add_event(self, event: Event) -> EEGDataset:
        new_events = self.events + [event]
        new = replace(self, events=new_events)
        new._notify("events", self.events, new_events)
        return new

    def remove_event(self, index: int) -> EEGDataset:
        if not 0 <= index < len(self.events):
            raise IndexError("事件索引越界")
        new_events = self.events[:index] + self.events[index+1:]
        new = replace(self, events=new_events)
        new._notify("events", self.events, new_events)
        return new

    def update_event(self, index: int, event: Event) -> EEGDataset:
        if not 0 <= index < len(self.events):
            raise IndexError("事件索引越界")
        new_events = self.events.copy()
        new_events[index] = event
        new = replace(self, events=new_events)
        new._notify("events", self.events, new_events)
        return new

    def set_bad_channels(self, bad_ch_names: list[str]) -> EEGDataset:
        new_info = self.channel_info.copy()
        for ch in self.ch_names:
            info = new_info.get(ch, ChannelInfo(ch))
            new_info[ch] = replace(info, is_bad=(ch in bad_ch_names))
        new = replace(self, channel_info=new_info)
        new._notify("channel_info", self.channel_info, new_info)
        return new

    def set_montage(self, montage: Montage) -> EEGDataset:
        new = replace(self, montage=montage)
        new._notify("montage", self.montage, montage)
        return new

    def add_processing_step(self, step: dict[str, Any]) -> EEGDataset:
        new_history = self.processing_history + [step]
        new = replace(self, processing_history=new_history)
        new._notify("processing_history", self.processing_history, new_history)
        return new

    def crop(self, tmin: float, tmax: float, include_tmax: bool = True) -> EEGDataset:
        if tmin < 0 or tmax > self.duration:
            raise ValueError(f"裁剪范围超出数据时长 [0, {self.duration:.3f}]")
        start = int(np.round(tmin * self.sfreq))
        end = int(np.round(tmax * self.sfreq)) + (1 if include_tmax else 0)
        new_data = self.data[:, start:end].copy()
        new_events = []
        for ev in self.events:
            if ev.onset >= tmin and ev.onset <= tmax:
                new_ev = replace(ev, onset=ev.onset - tmin)
                if ev.sample is not None:
                    new_ev = replace(new_ev, sample=ev.sample - start)
                new_events.append(new_ev)
        new = replace(self, data=new_data, events=new_events)
        new._notify("data", self.data, new_data)
        new._notify("events", self.events, new_events)
        return new

    def copy(self) -> EEGDataset:
        return replace(
            self,
            data=self.data.copy(),
            ch_names=self.ch_names.copy(),
            channel_info=self.channel_info.copy(),
            events=self.events.copy(),
            annotations=self.annotations.copy(),
            montage=self.montage,
            metadata=self.metadata,
            processing_history=self.processing_history.copy(),
        )

    def to_mne_raw(self, copy: bool = True, copy_data: bool | None = None):
        try:
            import mne
            if copy_data is not None:
                copy = copy_data
            info = mne.create_info(
                ch_names=self.ch_names,
                sfreq=self.sfreq,
                ch_types=[self.channel_info.get(ch, ChannelInfo(ch)).type.value for ch in self.ch_names]
            )
            data = self.data.copy() if copy else self.data
            raw = mne.io.RawArray(data * 1e-6, info)
            if self.montage:
                raw.set_montage(self.montage.to_mne_montage(), on_missing="warn")

            annotations = self.annotations if self.annotations else [
                Event(
                    onset=ev.onset,
                    duration=ev.duration,
                    description=ev.description,
                    value=ev.value,
                    sample=ev.sample,
                    channel=ev.channel,
                    confidence=ev.confidence,
                    custom_meta=ev.custom_meta.copy()
                )
                for ev in self.events
            ]
            if annotations:
                onset = [a.onset for a in annotations]
                duration = [a.duration for a in annotations]
                description = [a.description for a in annotations]
                raw.set_annotations(mne.Annotations(onset, duration, description))
            return raw
        except Exception as e:
            raise RuntimeError(f"转换到 MNE Raw 失败: {e}")

    @classmethod
    def from_mne_raw(cls, raw, name: str | None = None, file_path: str = "") -> EEGDataset:
        import mne
        data = raw.get_data() * 1e6
        ch_names = raw.ch_names
        sfreq = raw.info["sfreq"]
        ch_info = {}
        for ch, ch_type in zip(ch_names, raw.get_channel_types()):
            loc = None
            if raw.info["chs"]:
                for ch_dict in raw.info["chs"]:
                    if ch_dict["ch_name"] == ch:
                        loc = tuple(ch_dict["loc"][:3] * 1000) if ch_dict["loc"][0] != 0 else None
                        break
            ch_info[ch] = ChannelInfo(name=ch, type=ChannelType(ch_type), location=loc)
        montage = None
        if raw.get_montage() is not None:
            montage = Montage.from_mne_montage(raw.get_montage(), name=name or "imported")
        events = []
        if raw.annotations is not None:
            for ann in raw.annotations:
                events.append(Event(onset=ann["onset"], duration=ann["duration"],
                                   description=ann["description"], value=0))
        return cls(
            id=uuid4().hex[:8],
            name=name or raw.filenames[0] if raw.filenames else "Imported",
            file_path=file_path,
            data=data,
            sfreq=sfreq,
            ch_names=ch_names,
            channel_info=ch_info,
            events=events,
            annotations=events.copy(),
            montage=montage,
        )