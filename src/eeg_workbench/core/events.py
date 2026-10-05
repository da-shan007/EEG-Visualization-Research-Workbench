"""事件总线与领域事件定义（发布-订阅模式，解耦模块间通信）。"""
from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, TypeVar, Generic, TYPE_CHECKING
from collections import defaultdict
from threading import Lock
import uuid
from datetime import datetime

if TYPE_CHECKING:
    # 仅用于类型注解，避免 core <-> models 循环导入
    from eeg_workbench.models.dataset import Event


class EventType(Enum):
    """领域事件类型枚举"""
    # 数据集生命周期
    DATASET_LOADED = auto()
    DATASET_SAVED = auto()
    DATASET_CLOSED = auto()
    DATASET_MODIFIED = auto()
    # 元数据
    METADATA_CHANGED = auto()
    # 事件标记
    EVENT_ADDED = auto()
    EVENT_REMOVED = auto()
    EVENT_UPDATED = auto()
    EVENTS_IMPORTED = auto()
    # 预处理
    PREPROCESSING_STARTED = auto()
    PREPROCESSING_FINISHED = auto()
    # 裁剪/拼接
    DATASET_CROPPED = auto()
    DATASETS_CONCATENATED = auto()
    # 通用
    ERROR_OCCURRED = auto()
    PROGRESS_UPDATE = auto()


T = TypeVar("T")


@dataclass
class DomainEvent(Generic[T]):
    """领域事件基类"""
    type: EventType
    payload: T
    source: str = ""  # 发送者标识
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: datetime = field(default_factory=datetime.now)


# 具体事件载荷类型
@dataclass
class DatasetLoadedPayload:
    dataset_id: str
    file_path: str
    n_channels: int
    duration: float
    sfreq: float


@dataclass
class MetadataChangedPayload:
    dataset_id: str
    field: str
    old_value: Any
    new_value: Any


@dataclass
class EventMarkerPayload:
    dataset_id: str
    event: "Event"  # 前向引用，运行时解析
    index: int


@dataclass
class EventsImportedPayload:
    dataset_id: str
    count: int
    source_file: str


@dataclass
class PreprocessingPayload:
    dataset_id: str
    step: str
    params: dict


@dataclass
class ErrorPayload:
    message: str
    details: str = ""
    recoverable: bool = True


@dataclass
class ProgressPayload:
    task: str
    current: int
    total: int
    message: str = ""


Callback = Callable[[DomainEvent], None]


class EventBus:
    """全局事件总线（线程安全），支持同步/异步分发"""

    _instance: "EventBus | None" = None
    _lock = Lock()
    _initialized: bool = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._subscribers: Dict[EventType, List[Callback]] = defaultdict(list)
        self._wildcard_subscribers: List[Callback] = []  # 订阅所有事件
        self._initialized = True

    def subscribe(self, event_type: EventType, callback: Callback) -> Callable[[], None]:
        """订阅特定事件类型，返回取消订阅函数"""
        self._subscribers[event_type].append(callback)

        def unsubscribe():
            self._subscribers[event_type].remove(callback)

        return unsubscribe

    def subscribe_all(self, callback: Callback) -> Callable[[], None]:
        """订阅所有事件"""
        self._wildcard_subscribers.append(callback)

        def unsubscribe():
            self._wildcard_subscribers.remove(callback)

        return unsubscribe

    def publish(self, event_or_type: DomainEvent | EventType, payload: Any = None, source: str = "") -> None:
        """同步发布事件，兼容两种调用方式：
        - publish(DomainEvent(...))
        - publish(EventType.X, payload, source='...')
        """
        event = event_or_type if isinstance(event_or_type, DomainEvent) else DomainEvent(
            type=event_or_type,
            payload=payload,
            source=source,
        )

        # 先分发给特定订阅者
        for cb in self._subscribers.get(event.type, []):
            try:
                cb(event)
            except Exception as e:
                # 避免一个异常阻断其他订阅者
                print(f"[EventBus] Subscriber error: {e}")
        # 再分发给通配符订阅者
        for cb in self._wildcard_subscribers:
            try:
                cb(event)
            except Exception as e:
                print(f"[EventBus] Wildcard subscriber error: {e}")

    def publish_async(self, event_or_type: DomainEvent | EventType, payload: Any = None, source: str = "") -> None:
        """异步发布（投递到 Qt 事件循环或线程池）"""
        # 这里简单用 QTimer.singleShot 0 延迟到事件循环
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.publish(event_or_type, payload, source))
        except ImportError:
            # 非 Qt 环境直接同步
            self.publish(event_or_type, payload, source)


# 便捷全局函数
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def publish_event(event_type: EventType, payload: Any, source: str = "") -> None:
    """快捷发布"""
    event = DomainEvent(type=event_type, payload=payload, source=source)
    get_event_bus().publish(event)