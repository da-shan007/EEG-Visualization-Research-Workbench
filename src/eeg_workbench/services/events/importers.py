"""事件文件导入/导出：.vmrk (BrainVision), .tsv (BIDS)"""
from __future__ import annotations
from pathlib import Path
from dataclasses import replace
from typing import Any
import re
import pandas as pd

from eeg_workbench.models.dataset import Event, EEGDataset
from eeg_workbench.core.events import get_event_bus, EventType, EventsImportedPayload


# ---- .vmrk 解析 ----
_VMRK_HEADER = re.compile(r"^\[.*\]$")
_VMRK_MARKER = re.compile(
    r"^Mk(\d+)=(\w+),(\w+),(\d+),(\d+),(\d+),(\d+)$"
)  # Mk1=Stimulus,S  1,1,0,1000


def import_vmrk(file_path: str, dataset: EEGDataset) -> EEGDataset:
    """导入 BrainVision .vmrk 标记文件"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"VMRK 文件不存在: {file_path}")

    events = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 简单逐行解析
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        m = _VMRK_MARKER.match(line)
        if m:
            idx, mtype, desc, onset_samples, duration_samples, channel = m.groups()
            onset = int(onset_samples) / dataset.sfreq if dataset.sfreq > 0 else 0
            duration = int(duration_samples) / dataset.sfreq if dataset.sfreq > 0 else 0
            ev = Event(
                onset=onset,
                duration=duration,
                description=desc,
                value=int(idx),
                sample=int(onset_samples),
                channel=channel if channel != "0" else "",
                custom_meta={"source": "vmrk", "marker_type": mtype}
            )
            events.append(ev)

    if events:
        new_ds = _merge_events(dataset, events)
        get_event_bus().publish(
            EventType.EVENTS_IMPORTED,
            EventsImportedPayload(dataset_id=new_ds.id, count=len(events), source_file=str(path)),
            source="VMRKImporter"
        )
        return new_ds
    return dataset


# ---- .tsv 解析 (BIDS events.tsv) ----
_REQUIRED_TSV_COLS = {"onset", "duration", "trial_type"}  # BIDS 必需列
_OPTIONAL_TSV_COLS = {"value", "sample", "channel", "confidence", "description"}


def import_tsv(file_path: str, dataset: EEGDataset) -> EEGDataset:
    """导入 BIDS 格式 events.tsv"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"TSV 文件不存在: {file_path}")

    df = pd.read_csv(file_path, sep="\t")
    cols = set(df.columns)

    # 验证必需列
    missing = _REQUIRED_TSV_COLS - cols
    if missing:
        raise ValueError(f"TSV 缺少必需列: {missing}")

    events = []
    for _, row in df.iterrows():
        onset = float(row["onset"])
        duration = float(row.get("duration", 0.0))
        desc = str(row.get("trial_type", ""))
        value = int(row.get("value", 0)) if "value" in cols else 0
        sample = int(row.get("sample", onset * dataset.sfreq)) if dataset.sfreq > 0 else None
        channel = str(row.get("channel", "")) if "channel" in cols else ""
        confidence = float(row.get("confidence", 1.0)) if "confidence" in cols else 1.0

        ev = Event(
            onset=onset,
            duration=duration,
            description=desc,
            value=value,
            sample=sample,
            channel=channel,
            confidence=confidence,
            custom_meta={k: row[k] for k in cols - _REQUIRED_TSV_COLS - _OPTIONAL_TSV_COLS}
        )
        events.append(ev)

    if events:
        new_ds = _merge_events(dataset, events)
        get_event_bus().publish(
            EventType.EVENTS_IMPORTED,
            EventsImportedPayload(dataset_id=new_ds.id, count=len(events), source_file=str(path)),
            source="TSVImporter"
        )
        return new_ds
    return dataset


# ---- 导出 ----
def export_vmrk(dataset: EEGDataset, file_path: str) -> None:
    """导出为 BrainVision .vmrk 格式"""
    path = Path(file_path)
    lines = [
        "BrainVision Data Marker File",
        "Version=1.0",
        f"DataFile={dataset.name}.eeg",
        "",
        "[Marker Infos]",
        "; Each marker line: Mk<index>=<type>,<description>,<onset_samples>,<duration_samples>,<channel>,<value>",
    ]
    for i, ev in enumerate(dataset.events, 1):
        onset_samp = ev.sample if ev.sample is not None else int(round(ev.onset * dataset.sfreq))
        dur_samp = int(round(ev.duration * dataset.sfreq))
        ch = ev.channel if ev.channel else "0"
        mtype = "Stimulus" if ev.is_stimulus else ("Response" if ev.is_response else "Comment")
        lines.append(f"Mk{i}={mtype},{ev.description},{onset_samp},{dur_samp},{ch},{ev.value}")

    path.write_text("\n".join(lines), encoding="utf-8")


def export_tsv(dataset: EEGDataset, file_path: str) -> None:
    """导出为 BIDS events.tsv 格式"""
    path = Path(file_path)
    rows = []
    for ev in dataset.events:
        row = {
            "onset": round(ev.onset, 6),
            "duration": round(ev.duration, 6),
            "trial_type": ev.description,
            "value": ev.value,
        }
        if ev.sample is not None:
            row["sample"] = ev.sample
        if ev.channel:
            row["channel"] = ev.channel
        if ev.confidence != 1.0:
            row["confidence"] = ev.confidence
        # 扩展字段
        for k, v in ev.custom_meta.items():
            row[k] = v
        rows.append(row)

    df = pd.DataFrame(rows)
    # 保证列顺序
    preferred = ["onset", "duration", "trial_type", "value", "sample", "channel", "confidence"]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]
    df.to_csv(path, sep="\t", index=False, float_format="%.6f")


# ---- 内部辅助 ----
def _merge_events(dataset: EEGDataset, new_events: list[Event]) -> EEGDataset:
    """合并事件：按 onset 排序，去重（同 onset+desc 视为重复）"""
    all_events = dataset.events + new_events
    # 去重
    seen = set()
    unique = []
    for ev in all_events:
        key = (round(ev.onset, 6), ev.description)
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    unique.sort(key=lambda e: e.onset)
    return replace(dataset, events=unique)