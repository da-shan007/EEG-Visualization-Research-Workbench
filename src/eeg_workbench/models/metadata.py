"""元数据模型：受试者信息、实验条件、数据集元数据。

符合 BIDS / EEG-BIDS 规范的字段设计，支持扩展。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Literal
from datetime import date, datetime
from enum import Enum
import json


class Sex(Enum):
    MALE = "M"
    FEMALE = "F"
    OTHER = "O"
    UNKNOWN = "U"


class Handedness(Enum):
    RIGHT = "R"
    LEFT = "L"
    AMBIDEXTROUS = "A"
    UNKNOWN = "U"


class GroupType(Enum):
    CONTROL = "control"
    PATIENT = "patient"
    EXPERIMENTAL = "experimental"
    OTHER = "other"


@dataclass
class SubjectInfo:
    """受试者/被试信息 (对应 BIDS participants.tsv 核心字段)"""
    # 必填
    subject_id: str                    # 如 "sub-01"
    # 人口学
    age: int | None = None             # 岁
    sex: Sex = Sex.UNKNOWN
    handedness: Handedness = Handedness.UNKNOWN
    # 分组
    group: GroupType = GroupType.OTHER
    diagnosis: str = ""                # 诊断编码 (如 ICD-10)
    # 实验相关
    session_id: str = "ses-01"         # 如 "ses-01"
    task_name: str = ""                # 任务名称
    # 扩展
    education_years: int | None = None
    medication: str = ""               # 用药情况
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.sex, str):
            self.sex = Sex(self.sex.upper())
        if isinstance(self.handedness, str):
            self.handedness = Handedness(self.handedness.upper())
        if isinstance(self.group, str):
            self.group = GroupType(self.group.lower())

    def to_bids_dict(self) -> dict[str, Any]:
        """导出为 BIDS participants.tsv 兼容字典"""
        d = {
            "participant_id": self.subject_id,
            "age": self.age,
            "sex": self.sex.value,
            "handedness": self.handedness.value,
            "group": self.group.value,
        }
        if self.diagnosis:
            d["diagnosis"] = self.diagnosis
        if self.education_years is not None:
            d["education_years"] = self.education_years
        if self.medication:
            d["medication"] = self.medication
        d.update(self.custom_fields)
        return d

    @classmethod
    def from_bids_dict(cls, data: dict[str, Any]) -> SubjectInfo:
        return cls(
            subject_id=data.get("participant_id", "sub-unknown"),
            age=data.get("age"),
            sex=Sex(data.get("sex", "U")),
            handedness=Handedness(data.get("handedness", "U")),
            group=GroupType(data.get("group", "other")),
            diagnosis=data.get("diagnosis", ""),
            education_years=data.get("education_years"),
            medication=data.get("medication", ""),
            custom_fields={k: v for k, v in data.items()
                           if k not in {"participant_id", "age", "sex", "handedness",
                                        "group", "diagnosis", "education_years", "medication"}}
        )


@dataclass
class ExperimentCondition:
    """单个实验条件定义"""
    name: str                          # 条件标识，如 "Cue_Target", "Rest_EyesClosed"
    description: str = ""              # 人类可读描述
    event_codes: list[int] = field(default_factory=list)  # 对应的事件 value 编码
    event_descriptions: list[str] = field(default_factory=list)  # 对应的事件 description
    # 时间窗 (相对事件起始，秒)
    tmin: float = -0.2
    tmax: float = 0.8
    # 基线校正窗
    baseline_tmin: float | None = None
    baseline_tmax: float | None = 0.0
    # 触发方式
    trigger_type: Literal["stimulus", "response", "cue", "custom"] = "stimulus"
    # 关联的反应键/按钮
    response_mapping: dict[str, str] = field(default_factory=dict)  # {"left": "button1", "right": "button2"}
    # 扩展
    custom_meta: dict[str, Any] = field(default_factory=dict)

    def matches_event(self, event_desc: str, event_value: int) -> bool:
        """判断事件是否属于此条件"""
        if self.event_descriptions and event_desc in self.event_descriptions:
            return True
        if self.event_codes and event_value in self.event_codes:
            return True
        return False


@dataclass
class DatasetMetadata:
    """数据集级元数据（对应 BIDS sidecar JSON 字段）"""
    # 标识
    dataset_name: str = ""
    dataset_version: str = "1.0.0"
    bids_version: str = "1.8.0"

    # 记录信息
    recording_date: date | None = None
    recording_duration: float = 0.0    # 秒
    institution_name: str = ""
    institution_address: str = ""
    manufacturer: str = ""             # 设备厂商
    manufacturers_model_name: str = "" # 设备型号
    device_serial_number: str = ""
    software_version: str = ""         # 采集软件版本

    # 采集参数
    eeg_reference: str = ""            # 参考电极描述
    eeg_ground: str = ""               # 接地电极
    eeg_placement_scheme: str = "10-20"  # 电极布局方案
    channel_count: int = 0
    sampling_frequency: float = 0.0    # Hz
    power_line_frequency: float = 50.0 # 50/60 Hz

    # 实验设计
    task_name: str = ""
    task_description: str = ""
    instructions: str = ""
    conditions: list[ExperimentCondition] = field(default_factory=list)

    # 受试者
    subject: SubjectInfo | None = None

    # 处理历史摘要
    processing_steps: list[dict[str, Any]] = field(default_factory=list)

    # 质控指标
    qc_metrics: dict[str, Any] = field(default_factory=dict)

    # 扩展
    custom_meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.recording_date, str):
            self.recording_date = datetime.fromisoformat(self.recording_date).date()

    def to_bids_sidecar(self) -> dict[str, Any]:
        """导出为 BIDS _eeg.json 兼容字典"""
        d = {
            "DatasetName": self.dataset_name,
            "DatasetVersion": self.dataset_version,
            "BIDSVersion": self.bids_version,
            "InstitutionName": self.institution_name,
            "InstitutionAddress": self.institution_address,
            "Manufacturer": self.manufacturer,
            "ManufacturersModelName": self.manufacturers_model_name,
            "DeviceSerialNumber": self.device_serial_number,
            "SoftwareVersions": self.software_version,
            "EEGReference": self.eeg_reference,
            "EEGGround": self.eeg_ground,
            "EEGPlacementScheme": self.eeg_placement_scheme,
            "ChannelCount": self.channel_count,
            "SamplingFrequency": self.sampling_frequency,
            "PowerLineFrequency": self.power_line_frequency,
            "TaskName": self.task_name,
            "TaskDescription": self.task_description,
            "Instructions": self.instructions,
        }
        if self.recording_date:
            d["RecordingDate"] = self.recording_date.isoformat()
        if self.recording_duration:
            d["RecordingDuration"] = self.recording_duration
        if self.subject:
            d["Subject"] = self.subject.to_bids_dict()
        if self.conditions:
            d["Conditions"] = [asdict(c) for c in self.conditions]
        if self.processing_steps:
            d["ProcessingSteps"] = self.processing_steps
        if self.qc_metrics:
            d["QCMetrics"] = self.qc_metrics
        d.update(self.custom_meta)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_bids_sidecar(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_bids_sidecar(cls, data: dict[str, Any]) -> DatasetMetadata:
        subject = None
        if "Subject" in data:
            subject = SubjectInfo.from_bids_dict(data["Subject"])
        conditions = []
        for c in data.get("Conditions", []):
            conditions.append(ExperimentCondition(**c))
        return cls(
            dataset_name=data.get("DatasetName", ""),
            dataset_version=data.get("DatasetVersion", "1.0.0"),
            bids_version=data.get("BIDSVersion", "1.8.0"),
            recording_date=datetime.fromisoformat(data["RecordingDate"]).date() if "RecordingDate" in data else None,
            recording_duration=data.get("RecordingDuration", 0.0),
            institution_name=data.get("InstitutionName", ""),
            institution_address=data.get("InstitutionAddress", ""),
            manufacturer=data.get("Manufacturer", ""),
            manufacturers_model_name=data.get("ManufacturersModelName", ""),
            device_serial_number=data.get("DeviceSerialNumber", ""),
            software_version=data.get("SoftwareVersions", ""),
            eeg_reference=data.get("EEGReference", ""),
            eeg_ground=data.get("EEGGround", ""),
            eeg_placement_scheme=data.get("EEGPlacementScheme", "10-20"),
            channel_count=data.get("ChannelCount", 0),
            sampling_frequency=data.get("SamplingFrequency", 0.0),
            power_line_frequency=data.get("PowerLineFrequency", 50.0),
            task_name=data.get("TaskName", ""),
            task_description=data.get("TaskDescription", ""),
            instructions=data.get("Instructions", ""),
            subject=subject,
            conditions=conditions,
            processing_steps=data.get("ProcessingSteps", []),
            qc_metrics=data.get("QCMetrics", {}),
            custom_meta={k: v for k, v in data.items()
                         if k not in {"DatasetName", "DatasetVersion", "BIDSVersion",
                                      "RecordingDate", "RecordingDuration",
                                      "InstitutionName", "InstitutionAddress",
                                      "Manufacturer", "ManufacturersModelName",
                                      "DeviceSerialNumber", "SoftwareVersions",
                                      "EEGReference", "EEGGround", "EEGPlacementScheme",
                                      "ChannelCount", "SamplingFrequency",
                                      "PowerLineFrequency", "TaskName",
                                      "TaskDescription", "Instructions",
                                      "Subject", "Conditions", "ProcessingSteps", "QCMetrics"}}
        )

    def add_condition(self, condition: ExperimentCondition) -> None:
        """添加实验条件（去重）"""
        if not any(c.name == condition.name for c in self.conditions):
            self.conditions.append(condition)

    def get_condition(self, name: str) -> ExperimentCondition | None:
        for c in self.conditions:
            if c.name == name:
                return c
        return None