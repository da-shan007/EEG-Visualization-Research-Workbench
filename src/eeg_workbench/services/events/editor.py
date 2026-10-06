"""事件编辑器核心逻辑：增删改查、撤销/重做、批量操作"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional
import numpy as np
from copy import deepcopy

from eeg_workbench.models.dataset import EEGDataset, Event
from eeg_workbench.core.events import get_event_bus, EventType, EventMarkerPayload, EventsImportedPayload


@dataclass
class EditorAction:
    """单个编辑动作（用于撤销栈）"""
    action_type: str  # "add", "remove", "update", "batch"
    dataset_id: str
    # 存储足够信息以撤销
    index: int = -1
    old_event: Optional[Event] = None
    new_event: Optional[Event] = None
    events: Optional[list[Event]] = None  # 批量操作时用
    description: str = ""


class EventEditor:
    """事件编辑器：管理单个 EEGDataset 的事件列表，支持撤销/重做"""

    def __init__(self, dataset: EEGDataset) -> None:
        self._dataset = dataset
        self._undo_stack: list[EditorAction] = []
        self._redo_stack: list[EditorAction] = []
        self._max_history = 100

    @property
    def dataset(self) -> EEGDataset:
        return self._dataset

    def sync_dataset(self, dataset: EEGDataset) -> None:
        """编辑产生新数据集后同步内部快照

        保留撤销栈：dataset id 未变时栈内动作只回滚 events 字段，
        对外部字段变更（如 montage）安全；id 变化则清栈。
        """
        if dataset.id != self._dataset.id:
            self._undo_stack.clear()
            self._redo_stack.clear()
        self._dataset = dataset

    @property
    def events(self) -> list[Event]:
        return self._dataset.events

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    # ---- 基础 CRUD ----
    def add_event(self, event: Event, index: int | None = None) -> EEGDataset:
        """添加事件，可指定插入位置（默认按时间排序）"""
        if index is None:
            # 按 onset 排序插入
            onset = event.onset
            index = 0
            for i, ev in enumerate(self._dataset.events):
                if ev.onset > onset:
                    index = i
                    break
            else:
                index = len(self._dataset.events)

        new_ds = self._dataset.add_event(event)
        self._push_undo(EditorAction(
            action_type="add",
            dataset_id=self._dataset.id,
            index=index,
            new_event=event,
            description=f"添加事件: {event.description} @ {event.onset:.3f}s"
        ))
        self._dataset = new_ds
        self._publish_event_added(index, event)
        return new_ds

    def remove_event(self, index: int) -> EEGDataset:
        """按索引移除事件"""
        if not 0 <= index < len(self._dataset.events):
            raise IndexError("事件索引越界")
        old_event = self._dataset.events[index]
        new_ds = self._dataset.remove_event(index)
        self._push_undo(EditorAction(
            action_type="remove",
            dataset_id=self._dataset.id,
            index=index,
            old_event=old_event,
            description=f"删除事件: {old_event.description} @ {old_event.onset:.3f}s"
        ))
        self._dataset = new_ds
        self._publish_event_removed(index, old_event)
        return new_ds

    def update_event(self, index: int, event: Event) -> EEGDataset:
        """更新事件"""
        if not 0 <= index < len(self._dataset.events):
            raise IndexError("事件索引越界")
        old_event = self._dataset.events[index]
        new_ds = self._dataset.update_event(index, event)
        self._push_undo(EditorAction(
            action_type="update",
            dataset_id=self._dataset.id,
            index=index,
            old_event=old_event,
            new_event=event,
            description=f"修改事件: {old_event.description} -> {event.description}"
        ))
        self._dataset = new_ds
        self._publish_event_updated(index, event)
        return new_ds

    def move_event(self, from_index: int, to_index: int) -> EEGDataset:
        """移动事件位置"""
        if not (0 <= from_index < len(self._dataset.events) and 0 <= to_index < len(self._dataset.events)):
            raise IndexError("索引越界")
        events = self._dataset.events.copy()
        ev = events.pop(from_index)
        events.insert(to_index, ev)
        new_ds = replace(self._dataset, events=events)
        self._push_undo(EditorAction(
            action_type="batch",
            dataset_id=self._dataset.id,
            events=self._dataset.events.copy(),
            description=f"移动事件 {from_index} -> {to_index}"
        ))
        self._dataset = new_ds
        self._publish_events_changed()
        return new_ds

    # ---- 批量操作 ----
    def add_events(self, events: list[Event]) -> EEGDataset:
        """批量添加事件（按时间合并排序）"""
        all_events = self._dataset.events + events
        all_events.sort(key=lambda e: e.onset)
        new_ds = replace(self._dataset, events=all_events)
        self._push_undo(EditorAction(
            action_type="batch",
            dataset_id=self._dataset.id,
            events=self._dataset.events.copy(),
            description=f"批量添加 {len(events)} 个事件"
        ))
        self._dataset = new_ds
        self._publish_events_changed()
        return new_ds

    def remove_events(self, indices: list[int]) -> EEGDataset:
        """批量删除事件（索引从大到小删除避免位移）"""
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._dataset.events):
                self._dataset.events.pop(idx)
        new_ds = replace(self._dataset, events=self._dataset.events.copy())
        self._push_undo(EditorAction(
            action_type="batch",
            dataset_id=self._dataset.id,
            events=self._dataset.events.copy(),
            description=f"批量删除 {len(indices)} 个事件"
        ))
        self._dataset = new_ds
        self._publish_events_changed()
        return new_ds

    def clear_events(self, keep_types: list[str] | None = None) -> EEGDataset:
        """清空事件，可保留特定类型"""
        old_events = self._dataset.events.copy()
        if keep_types:
            new_events = [e for e in old_events if e.description.split("/")[0] in keep_types]
        else:
            new_events = []
        new_ds = replace(self._dataset, events=new_events)
        self._push_undo(EditorAction(
            action_type="batch",
            dataset_id=self._dataset.id,
            events=old_events,
            description=f"清空事件 (保留: {keep_types or '无'})"
        ))
        self._dataset = new_ds
        self._publish_events_changed()
        return new_ds

    # ---- 智能操作 ----
    def auto_detect_bad_segments(
        self,
        threshold_uv: float = 100.0,
        min_duration: float = 0.1,
        max_duration: float = 30.0,
        channel: str | None = None
    ) -> list[Event]:
        """基于振幅阈值自动检测坏段，返回新增的 Event 列表"""
        if self._dataset.data.size == 0:
            return []

        ch_idx = 0
        if channel and channel in self._dataset.ch_names:
            ch_idx = self._dataset.ch_names.index(channel)
        data = self._dataset.data[ch_idx, :]
        sfreq = self._dataset.sfreq

        # 简单阈值检测
        bad_mask = np.abs(data) > threshold_uv
        # 找连续段
        diff = np.diff(bad_mask.astype(int))
        starts = np.where(diff == 1)[0] + 1
        ends = np.where(diff == -1)[0] + 1
        if bad_mask[0]:
            starts = np.insert(starts, 0, 0)
        if bad_mask[-1]:
            ends = np.append(ends, len(bad_mask))

        new_events = []
        for s, e in zip(starts, ends):
            dur = (e - s) / sfreq
            if min_duration <= dur <= max_duration:
                onset = s / sfreq
                ev = Event(
                    onset=onset,
                    duration=dur,
                    description=Event.BAD_SEGMENT,
                    value=-1,
                    sample=s,
                    custom_meta={"threshold_uv": threshold_uv, "channel": self._dataset.ch_names[ch_idx]}
                )
                new_events.append(ev)

        if new_events:
            self.add_events(new_events)
        return new_events

    def rename_event_type(self, old_prefix: str, new_prefix: str) -> int:
        """批量重命名事件类型前缀 (如 "Stimulus/" -> "Target/")"""
        count = 0
        for i, ev in enumerate(self._dataset.events):
            if ev.description.startswith(old_prefix):
                new_desc = ev.description.replace(old_prefix, new_prefix, 1)
                new_ev = Event(
                    onset=ev.onset,
                    duration=ev.duration,
                    description=new_desc,
                    value=ev.value,
                    sample=ev.sample,
                    channel=ev.channel,
                    confidence=ev.confidence,
                    custom_meta=ev.custom_meta.copy()
                )
                self.update_event(i, new_ev)
                count += 1
        return count

    # ---- 撤销/重做 ----
    def undo(self) -> EEGDataset | None:
        if not self.can_undo:
            return None
        action = self._undo_stack.pop()
        self._redo_stack.append(action)
        self._dataset = self._revert_action(action)
        self._publish_events_changed()
        return self._dataset

    def redo(self) -> EEGDataset | None:
        if not self.can_redo:
            return None
        action = self._redo_stack.pop()
        self._undo_stack.append(action)
        self._dataset = self._apply_action(action)
        self._publish_events_changed()
        return self._dataset

    def _push_undo(self, action: EditorAction) -> None:
        self._undo_stack.append(action)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _revert_action(self, action: EditorAction) -> EEGDataset:
        if action.action_type == "add":
            return self._dataset.remove_event(action.index)
        elif action.action_type == "remove":
            assert action.old_event is not None, "撤销删除需要 old_event"
            events = self._dataset.events.copy()
            events.insert(action.index, action.old_event)
            return replace(self._dataset, events=events)
        elif action.action_type == "update":
            assert action.old_event is not None, "撤销更新需要 old_event"
            events = self._dataset.events.copy()
            events[action.index] = action.old_event
            return replace(self._dataset, events=events)
        elif action.action_type == "batch":
            assert action.events is not None, "撤销批量操作需要 events"
            return replace(self._dataset, events=action.events)
        return self._dataset

    def _apply_action(self, action: EditorAction) -> EEGDataset:
        if action.action_type == "add":
            assert action.new_event is not None, "新增事件需要 new_event"
            events = self._dataset.events.copy()
            events.insert(action.index, action.new_event)
            return replace(self._dataset, events=events)
        elif action.action_type == "remove":
            return self._dataset.remove_event(action.index)
        elif action.action_type == "update":
            assert action.new_event is not None, "更新事件需要 new_event"
            return self._dataset.update_event(action.index, action.new_event)
        elif action.action_type == "batch":
            assert action.events is not None, "批量操作需要 events"
            return replace(self._dataset, events=action.events)
        return self._dataset

    # ---- 事件发布 ----
    def _publish_event_added(self, index: int, event: Event) -> None:
        get_event_bus().publish(
            EventType.EVENT_ADDED,
            EventMarkerPayload(dataset_id=self._dataset.id, event=event, index=index),
            source="EventEditor"
        )

    def _publish_event_removed(self, index: int, event: Event) -> None:
        get_event_bus().publish(
            EventType.EVENT_REMOVED,
            EventMarkerPayload(dataset_id=self._dataset.id, event=event, index=index),
            source="EventEditor"
        )

    def _publish_event_updated(self, index: int, event: Event) -> None:
        get_event_bus().publish(
            EventType.EVENT_UPDATED,
            EventMarkerPayload(dataset_id=self._dataset.id, event=event, index=index),
            source="EventEditor"
        )

    def _publish_events_changed(self) -> None:
        get_event_bus().publish(
            EventType.DATASET_MODIFIED,
            EventsImportedPayload(dataset_id=self._dataset.id, count=len(self._dataset.events), source_file="editor"),
            source="EventEditor"
        )


# 便捷函数
def create_event_editor(dataset: EEGDataset) -> EventEditor:
    return EventEditor(dataset)