"""数据裁剪与拼接服务"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any
import numpy as np

from eeg_workbench.models.dataset import EEGDataset, Event
from eeg_workbench.core.events import get_event_bus, EventType


@dataclass
class CropResult:
    dataset: EEGDataset
    removed_events: list[Event]


def crop_dataset(
    dataset: EEGDataset,
    tmin: float,
    tmax: float,
    include_tmax: bool = True,
    keep_events: bool = True
) -> CropResult:
    """时间段裁剪，返回新数据集 + 被移除的事件列表

    Args:
        tmin: 起始时间 (秒)
        tmax: 结束时间 (秒)
        include_tmax: 是否包含 tmax 时刻
        keep_events: 是否保留落在范围内的事件（时间重新归零）
    """
    if tmin < 0 or tmax > dataset.duration:
        raise ValueError(f"裁剪范围超出数据时长 [0, {dataset.duration:.3f}]")
    if tmin >= tmax:
        raise ValueError("tmin 必须小于 tmax")

    start = int(np.round(tmin * dataset.sfreq))
    end = int(np.round(tmax * dataset.sfreq)) + (1 if include_tmax else 0)

    new_data = dataset.data[:, start:end].copy()

    kept_events = []
    removed_events = []
    if keep_events:
        for ev in dataset.events:
            if ev.onset >= tmin and ev.onset <= tmax:
                new_ev = Event(
                    onset=ev.onset - tmin,
                    duration=ev.duration,
                    description=ev.description,
                    value=ev.value,
                    sample=(ev.sample - start) if ev.sample is not None else None,
                    channel=ev.channel,
                    confidence=ev.confidence,
                    custom_meta=ev.custom_meta.copy()
                )
                kept_events.append(new_ev)
            else:
                removed_events.append(ev)
    else:
        removed_events = dataset.events.copy()

    new_ds = replace(
        dataset,
        data=new_data,
        events=kept_events,
        annotations=[e for e in kept_events if not e.is_bad_segment],
    )
    new_ds = new_ds.add_processing_step({
        "step": "crop",
        "params": {"tmin": tmin, "tmax": tmax, "include_tmax": include_tmax}
    })

    get_event_bus().publish(
        EventType.DATASET_CROPPED,
        {"dataset_id": new_ds.id, "tmin": tmin, "tmax": tmax, "removed_events": len(removed_events)},
        source="SegmentationService"
    )

    return CropResult(dataset=new_ds, removed_events=removed_events)


def concatenate_datasets(
    datasets: list[EEGDataset],
    gap_seconds: float = 0.0,
    add_boundary_events: bool = True
) -> EEGDataset:
    """拼接多个同通道、同采样率的数据集

    Args:
        datasets: 待拼接的数据集列表（按顺序）
        gap_seconds: 数据集间插入的静默间隙 (秒)
        add_boundary_events: 是否在拼接点添加 EDGE 事件
    """
    if not datasets:
        raise ValueError("数据集列表为空")
    if len(datasets) == 1:
        return datasets[0]

    # 验证兼容性
    ref = datasets[0]
    for i, ds in enumerate(datasets[1:], 1):
        if ds.n_channels != ref.n_channels:
            raise ValueError(f"数据集 {i} 通道数不匹配: {ds.n_channels} vs {ref.n_channels}")
        if ds.ch_names != ref.ch_names:
            raise ValueError(f"数据集 {i} 通道名/顺序不匹配")
        if abs(ds.sfreq - ref.sfreq) > 1e-6:
            raise ValueError(f"数据集 {i} 采样率不匹配: {ds.sfreq} vs {ref.sfreq}")

    gap_samples = int(round(gap_seconds * ref.sfreq)) if gap_seconds > 0 else 0

    # 拼接数据
    data_parts = []
    event_parts = []
    time_offset = 0.0
    sample_offset = 0

    for i, ds in enumerate(datasets):
        data_parts.append(ds.data)
        # 事件时间偏移
        for ev in ds.events:
            new_ev = Event(
                onset=ev.onset + time_offset,
                duration=ev.duration,
                description=ev.description,
                value=ev.value,
                sample=(ev.sample + sample_offset) if ev.sample is not None else None,
                channel=ev.channel,
                confidence=ev.confidence,
                custom_meta={**ev.custom_meta, "source_dataset": ds.id, "concat_index": i}
            )
            event_parts.append(new_ev)

        time_offset += ds.duration
        sample_offset += ds.n_samples

        # 插入间隙
        if i < len(datasets) - 1 and gap_samples > 0:
            gap_data = np.zeros((ref.n_channels, gap_samples), dtype=np.float64)
            data_parts.append(gap_data)
            if add_boundary_events:
                edge_ev = Event(
                    onset=time_offset,
                    duration=0.0,
                    description=Event.EDGE,
                    value=0,
                    sample=sample_offset,
                    custom_meta={"type": "concat_gap", "gap_seconds": gap_seconds}
                )
                event_parts.append(edge_ev)
            time_offset += gap_seconds
            sample_offset += gap_samples

    # 添加首尾边界事件
    if add_boundary_events:
        event_parts.insert(0, Event(
            onset=0.0, duration=0.0, description=Event.EDGE, value=0, sample=0,
            custom_meta={"type": "concat_start"}
        ))
        event_parts.append(Event(
            onset=time_offset, duration=0.0, description=Event.EDGE, value=0, sample=sample_offset,
            custom_meta={"type": "concat_end"}
        ))

    new_data = np.concatenate(data_parts, axis=1)
    new_ds = replace(
        ref,
        id=f"concat_{ref.id}",
        name=f"{ref.name}_concat_{len(datasets)}",
        data=new_data,
        events=event_parts,
        annotations=[e for e in event_parts if not e.is_bad_segment],
        processing_history=ref.processing_history + [{
            "step": "concatenate",
            "params": {"datasets": [d.id for d in datasets], "gap_seconds": gap_seconds}
        }]
    )

    get_event_bus().publish(
        EventType.DATASETS_CONCATENATED,
        {"dataset_id": new_ds.id, "source_ids": [d.id for d in datasets], "gap_seconds": gap_seconds},
        source="SegmentationService"
    )

    return new_ds


def split_by_events(
    dataset: EEGDataset,
    event_descriptions: list[str],
    tmin: float = -0.2,
    tmax: float = 0.8
) -> list[EEGDataset]:
    """按事件类型分割成多个短数据集（用于 Epoch 级分析）

    返回每个匹配事件对应的裁剪数据集列表
    """
    results = []
    for ev in dataset.events:
        if ev.description in event_descriptions:
            start = ev.onset + tmin
            end = ev.onset + tmax
            if start < 0 or end > dataset.duration:
                continue
            crop_res = crop_dataset(dataset, start, end, keep_events=True)
            crop_res.dataset = replace(
                crop_res.dataset,
                name=f"{dataset.name}_{ev.description}_{ev.onset:.3f}",
                metadata=None  # 避免重复元数据
            )
            results.append(crop_res.dataset)
    return results


def extract_epochs_as_dataset(
    dataset: EEGDataset,
    event_descriptions: list[str],
    tmin: float = -0.2,
    tmax: float = 0.8,
    baseline: tuple[float, float] | None = (-0.2, 0.0)
) -> list[EEGDataset]:
    """提取 Epochs 并转为独立的 EEGDataset（每个 epoch 一个）"""
    from eeg_workbench.models.dataset import EpochData

    epochs: list[EEGDataset] = []
    for ev in dataset.events:
        if ev.description in event_descriptions:
            start = ev.onset + tmin
            end = ev.onset + tmax
            if start < 0 or end > dataset.duration:
                continue
            s = int(round(start * dataset.sfreq))
            e = int(round(end * dataset.sfreq))
            ep_data = dataset.data[:, s:e].copy()
            ep_times = np.arange(e - s) / dataset.sfreq + tmin

            # 基线校正
            if baseline is not None:
                b_start = int(round((baseline[0] - tmin) * dataset.sfreq))
                b_end = int(round((baseline[1] - tmin) * dataset.sfreq))
                if 0 <= b_start < b_end <= ep_data.shape[1]:
                    baseline_mean = ep_data[:, b_start:b_end].mean(axis=1, keepdims=True)
                    ep_data -= baseline_mean

            epochs.append(EEGDataset(
                id=f"{dataset.id}_ep_{len(epochs)}",
                name=f"{dataset.name}_epoch_{len(epochs)}_{ev.description}",
                file_path="",
                data=ep_data,
                sfreq=dataset.sfreq,
                ch_names=dataset.ch_names.copy(),
                channel_info=dataset.channel_info.copy(),
                events=[Event(onset=0, duration=0, description=ev.description, value=ev.value)],
                montage=dataset.montage,
            ))
    return epochs