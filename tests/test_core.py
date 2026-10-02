"""核心模型与服务单元测试"""
import dataclasses

import numpy as np
import pytest

from eeg_workbench.models.dataset import (
    EEGDataset, ChannelInfo, Event, Montage, EpochData, ChannelType
)
from eeg_workbench.models.metadata import (
    DatasetMetadata, SubjectInfo, ExperimentCondition, Sex, GroupType
)
from eeg_workbench.services.events import EventEditor, import_vmrk, import_tsv
from eeg_workbench.services.segmentation import crop_dataset, concatenate_datasets
from eeg_workbench.utils.montage import load_elp, normalize_channel_name
from eeg_workbench.utils.validators import validate_dataset_complete


# ---- 测试辅助 ----
def make_test_dataset(n_ch=4, n_samples=1000, sfreq=250.0) -> EEGDataset:
    """创建测试用数据集"""
    data = np.random.randn(n_ch, n_samples) * 10  # µV
    ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    events = [
        Event(onset=0.5, description="Stimulus/S1", value=1),
        Event(onset=1.0, description="Response/Left", value=2),
    ]
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
        events=events,
    )


# ---- Models 测试 ----
class TestChannelInfo:
    def test_defaults(self):
        ch = ChannelInfo(name="Fp1")
        assert ch.type == ChannelType.EEG
        assert ch.unit == "µV"
        assert ch.is_bad is False

    def test_type_conversion(self):
        ch = ChannelInfo(name="EOG", type="eog")
        assert ch.type == ChannelType.EOG


class TestEvent:
    def test_properties(self):
        ev = Event(onset=1.0, description="Stimulus/Target", value=1)
        assert ev.is_stimulus
        assert not ev.is_cue
        assert not ev.is_response

    def test_bad_segment(self):
        ev = Event(onset=1.0, description="BAD_segment")
        assert ev.is_bad_segment


class TestMontage:
    def test_positions(self):
        mont = Montage(name="test", positions={"Fp1": (-30, 80, -5), "Fp2": (30, 80, -5)})
        assert mont.get_position("Fp1") == (-30, 80, -5)
        assert not mont.has_position("Cz")


class TestEEGDataset:
    def test_creation(self):
        ds = make_test_dataset()
        assert ds.n_channels == 4
        assert ds.n_samples == 1000
        assert abs(ds.duration - 4.0) < 0.01
        assert len(ds.events) == 2

    def test_immutability(self):
        ds = make_test_dataset()
        new_ds = ds.with_data(ds.data * 2)
        assert np.allclose(new_ds.data, ds.data * 2)
        # 原对象未变
        assert not np.allclose(ds.data, ds.data * 2)

    def test_add_remove_event(self):
        ds = make_test_dataset()
        orig_len = len(ds.events)
        new_ds = ds.add_event(Event(onset=2.0, description="Cue/Start"))
        assert len(new_ds.events) == orig_len + 1
        # 原对象未变
        assert len(ds.events) == orig_len

        # 移除
        new_ds2 = new_ds.remove_event(0)
        assert len(new_ds2.events) == orig_len

    def test_crop(self):
        ds = make_test_dataset(n_samples=2500, sfreq=250.0)  # 10秒
        cropped = ds.crop(2.0, 6.0)  # 裁剪中间 4 秒
        assert abs(cropped.duration - 4.0) < 0.01
        # 事件时间归零
        for ev in cropped.events:
            assert 0 <= ev.onset <= 4.0

    def test_set_bad_channels(self):
        ds = make_test_dataset()
        new_ds = ds.set_bad_channels(["Ch0", "Ch1"])
        assert new_ds.channel_info["Ch0"].is_bad
        assert new_ds.channel_info["Ch1"].is_bad
        assert not new_ds.channel_info["Ch2"].is_bad


class TestMetadata:
    def test_subject_info(self):
        subj = SubjectInfo(subject_id="sub-01", age=25, sex=Sex.FEMALE, group=GroupType.CONTROL)
        d = subj.to_bids_dict()
        assert d["participant_id"] == "sub-01"
        assert d["sex"] == "F"
        assert d["group"] == "control"

    def test_experiment_condition(self):
        cond = ExperimentCondition(
            name="Target",
            event_codes=[1, 2],
            tmin=-0.2, tmax=0.8
        )
        assert cond.matches_event("Stimulus/Target", 1)
        assert not cond.matches_event("Stimulus/NonTarget", 3)

    def test_dataset_metadata_bids(self):
        meta = DatasetMetadata(
            dataset_name="Test",
            subject=SubjectInfo(subject_id="sub-01"),
            sampling_frequency=250.0,
        )
        meta.add_condition(ExperimentCondition(name="Cond1"))
        bids = meta.to_bids_sidecar()
        assert bids["DatasetName"] == "Test"
        assert bids["Subject"]["participant_id"] == "sub-01"
        assert len(bids["Conditions"]) == 1


# ---- Services 测试 ----
class TestEventEditor:
    def test_crud(self):
        ds = make_test_dataset()
        editor = EventEditor(ds)

        # 添加
        ds2 = editor.add_event(Event(onset=3.0, description="Cue/Test"))
        assert len(ds2.events) == 3

        # 更新
        ds3 = editor.update_event(0, Event(onset=0.5, description="Stimulus/Updated", value=99))
        assert ds3.events[0].description == "Stimulus/Updated"
        assert ds3.events[0].value == 99

        # 删除
        ds4 = editor.remove_event(0)
        assert len(ds4.events) == 2

    def test_undo_redo(self):
        ds = make_test_dataset()
        editor = EventEditor(ds)

        ds2 = editor.add_event(Event(onset=3.0, description="New"))
        assert len(ds2.events) == 3

        ds3 = editor.undo()
        assert len(ds3.events) == 2

        ds4 = editor.redo()
        assert len(ds4.events) == 3

    def test_batch_operations(self):
        ds = make_test_dataset()
        editor = EventEditor(ds)

        new_events = [Event(onset=i, description=f"Event{i}") for i in range(5, 8)]
        ds2 = editor.add_events(new_events)
        assert len(ds2.events) == 5

        ds3 = editor.remove_events([0, 1])
        assert len(ds3.events) == 3


class TestSegmentation:
    def test_crop(self):
        ds = make_test_dataset(n_samples=2500, sfreq=250.0)  # 10秒
        result = crop_dataset(ds, 2.0, 6.0)
        assert result.dataset.duration == pytest.approx(4.0, abs=0.01)
        # 修正错误断言：0.5s 与 1.0s 两个事件都在 [2.0, 6.0] 窗口外，均应被移除
        assert len(result.removed_events) == 2  # 窗口外的 0.5s 和 1.0s 事件全部移除

    def test_concatenate(self):
        ds1 = make_test_dataset(n_samples=1000, sfreq=250.0)  # 4秒
        ds2 = make_test_dataset(n_samples=1000, sfreq=250.0)  # 4秒
        ds2 = dataclasses.replace(ds2, id="ds2", name="Test2")

        concat = concatenate_datasets([ds1, ds2], gap_seconds=0.5)
        assert concat.duration == pytest.approx(8.5, abs=0.01)  # 4 + 0.5 + 4
        assert len(concat.events) > len(ds1.events)  # 包含边界事件


# ---- Utils 测试 ----
class TestMontageUtils:
    def test_normalize_channel_name(self):
        assert normalize_channel_name("FP1") == "Fp1"
        assert normalize_channel_name("CZ") == "Cz"
        assert normalize_channel_name("T3") == "T7"
        assert normalize_channel_name("Unknown") == "Unknown"

    def test_infer_channel_types(self):
        from eeg_workbench.utils.montage import infer_channel_types
        types = infer_channel_types(["Fp1", "EOG1", "ECG", "STIM", "EMG1"])
        assert types["Fp1"] == "eeg"
        assert types["EOG1"] == "eog"
        assert types["ECG"] == "ecg"
        assert types["STIM"] == "stim"
        assert types["EMG1"] == "emg"


class TestValidators:
    def test_validate_complete(self):
        ds = make_test_dataset()
        result = validate_dataset_complete(ds)
        assert result.is_valid
        assert result.has_warnings  # 会有蒙版缺失警告

    def test_parameter_validator(self):
        from eeg_workbench.utils.validators import ParameterValidator
        errors = ParameterValidator.validate_filter_params(0.1, 40, 50)
        assert len(errors) == 0

        errors = ParameterValidator.validate_filter_params(50, 40)  # 高通 > 低通
        assert len(errors) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])