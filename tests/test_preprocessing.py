"""预处理模块单元测试"""
import dataclasses

import numpy as np
import pytest

from eeg_workbench.models.preprocessing import (
    FilterParams, ReferenceParams, ResampleParams, ICAParams,
    BadChannelInterpolationParams,
    FilterType, ReferenceType, ResampleMethod, ICAComponentType, InterpolationMethod,
    FILTER_PRESETS, REFERENCE_PRESETS,
    create_filter_params, create_reference_params
)
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
from eeg_workbench.services.preprocessing import (
    FilterService, ReferenceService, ResampleService, ICAService, InterpolationService
)


# ---- 测试辅助 ----
def make_test_dataset(n_ch=4, n_samples=1000, sfreq=250.0, ch_names=None) -> EEGDataset:
    """创建测试用数据集"""
    data = np.random.randn(n_ch, n_samples) * 10  # µV
    if ch_names is None:
        ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
    )


def make_test_dataset_with_mastoid(n_ch=4, n_samples=1000, sfreq=250.0) -> EEGDataset:
    """创建带有乳突通道的测试数据集"""
    data = np.random.randn(n_ch, n_samples) * 10
    ch_names = ["Fp1", "Fp2", "A1", "A2"]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
    )


# ---- Models 测试 ----
class TestFilterParams:
    def test_bandpass_validation(self):
        params = FilterParams(filter_type=FilterType.BANDPASS, l_freq=0.1, h_freq=40.0)
        errors = params.validate()
        assert len(errors) == 0

    def test_highpass_validation(self):
        params = FilterParams(filter_type=FilterType.HIGHPASS, l_freq=1.0)
        errors = params.validate()
        assert len(errors) == 0

    def test_lowpass_validation(self):
        params = FilterParams(filter_type=FilterType.LOWPASS, h_freq=40.0)
        errors = params.validate()
        assert len(errors) == 0

    def test_notch_validation(self):
        params = FilterParams(filter_type=FilterType.NOTCH, notch_freq=50.0)
        errors = params.validate()
        assert len(errors) == 0

    def test_invalid_bandpass(self):
        params = FilterParams(filter_type=FilterType.BANDPASS, l_freq=40.0, h_freq=0.1)
        errors = params.validate()
        assert len(errors) > 0

    def test_missing_freq(self):
        params = FilterParams(filter_type=FilterType.BANDPASS, l_freq=0.1)
        errors = params.validate()
        assert any("h_freq" in e for e in errors)


class TestReferenceParams:
    def test_average_reference(self):
        params = ReferenceParams(ref_type=ReferenceType.AVERAGE)
        errors = params.validate(["Fp1", "Fp2", "Cz"])
        assert len(errors) == 0

    def test_mastoid_reference(self):
        params = ReferenceParams(ref_type=ReferenceType.MAStoid)
        # 有乳突通道
        errors = params.validate(["Fp1", "Fp2", "A1", "A2"])
        assert len(errors) == 0
        # 无乳突通道
        errors = params.validate(["Fp1", "Fp2", "Cz"])
        assert len(errors) > 0

    def test_single_reference(self):
        params = ReferenceParams(ref_type=ReferenceType.SINGLE, ref_channels=["Cz"])
        errors = params.validate(["Fp1", "Fp2", "Cz"])
        assert len(errors) == 0
        # 通道不存在
        params = ReferenceParams(ref_type=ReferenceType.SINGLE, ref_channels=["Pz"])
        errors = params.validate(["Fp1", "Fp2", "Cz"])
        assert len(errors) > 0


class TestResampleParams:
    def test_downsample_validation(self):
        params = ResampleParams(sfreq=125.0)
        errors = params.validate(250.0)
        assert len(errors) == 0

    def test_upsample_validation(self):
        params = ResampleParams(sfreq=500.0)
        errors = params.validate(250.0)
        assert len(errors) == 0

    def test_extreme_ratios(self):
        params = ResampleParams(sfreq=2000.0)
        errors = params.validate(250.0)
        assert any("上采样倍数过大" in e for e in errors)


class TestICAParams:
    def test_default_validation(self):
        params = ICAParams()
        errors = params.validate(32, 250.0)
        assert len(errors) == 0

    def test_n_components_validation(self):
        params = ICAParams(n_components=64)
        errors = params.validate(32, 250.0)
        assert any("不能大于通道数" in e for e in errors)

    def test_n_components_ratio(self):
        params = ICAParams(n_components=0.99)
        errors = params.validate(32, 250.0)
        assert len(errors) == 0

    def test_invalid_method(self):
        params = ICAParams(method="invalid")
        errors = params.validate(32, 250.0)
        assert len(errors) > 0


class TestInterpolationParams:
    def test_spherical_requires_positions(self):
        params = BadChannelInterpolationParams(
            method=InterpolationMethod.SPHERICAL,
            bad_channels=["Fp1"]
        )
        errors = params.validate(["Fp1", "Fp2"], {"Fp2": (0,0,0)})  # Fp1 无位置
        assert len(errors) > 0

    def test_nearest_no_positions_needed(self):
        params = BadChannelInterpolationParams(
            method=InterpolationMethod.NEAREST,
            bad_channels=["Fp1"]
        )
        errors = params.validate(["Fp1", "Fp2"], {})
        assert len(errors) == 0


class TestPresets:
    def test_filter_presets(self):
        for name in ["standard", "erp", "high_gamma", "resting", "ica_prep"]:
            params = create_filter_params(name)
            assert isinstance(params, FilterParams)
            assert params.l_freq is not None or params.h_freq is not None

    def test_reference_presets(self):
        for name in ["average", "mastoid", "cz", "rest"]:
            params = create_reference_params(name)
            assert isinstance(params, ReferenceParams)


# ---- Services 测试 ----
class TestFilterService:
    def test_bandpass_filter(self):
        ds = make_test_dataset()
        params = FilterParams(filter_type=FilterType.BANDPASS, l_freq=1.0, h_freq=40.0)
        result = FilterService.apply(ds, params)
        assert result.dataset is not None
        assert result.dataset.sfreq == ds.sfreq
        assert result.dataset.n_channels == ds.n_channels

    def test_highpass_filter(self):
        ds = make_test_dataset()
        result = FilterService.highpass(ds, l_freq=1.0)
        assert result.dataset is not None

    def test_lowpass_filter(self):
        ds = make_test_dataset()
        result = FilterService.lowpass(ds, h_freq=40.0)
        assert result.dataset is not None

    def test_notch_filter(self):
        ds = make_test_dataset()
        result = FilterService.notch(ds, freqs=50.0)
        assert result.dataset is not None

    def test_standard_preprocessing(self):
        ds = make_test_dataset()
        result = FilterService.standard_preprocessing(ds)
        assert result.dataset is not None

    def test_ica_preparation(self):
        ds = make_test_dataset()
        result = FilterService.ica_preparation(ds)
        assert result.dataset is not None
        # 验证是高通
        assert result.params_used.filter_type == FilterType.HIGHPASS


class TestReferenceService:
    def test_average_reference(self):
        ds = make_test_dataset()
        result = ReferenceService.average(ds)
        assert result.dataset is not None

    def test_cz_reference(self):
        ds = make_test_dataset(n_ch=3, ch_names=["Fp1", "Cz", "Pz"])
        result = ReferenceService.cz(ds)
        assert result.dataset is not None

    def test_mastoid_reference(self):
        ds = make_test_dataset_with_mastoid()
        result = ReferenceService.mastoid(ds)
        assert result.dataset is not None

    def test_single_reference(self):
        ds = make_test_dataset()
        result = ReferenceService.single(ds, "Ch0")
        assert result.dataset is not None

    def test_custom_reference(self):
        ds = make_test_dataset()
        result = ReferenceService.custom(ds, ["Ch0", "Ch1"])
        assert result.dataset is not None


class TestResampleService:
    def test_downsample(self):
        ds = make_test_dataset(sfreq=500.0)
        result = ResampleService.downsample(ds, factor=2)
        assert result.dataset is not None
        assert abs(result.dataset.sfreq - 250.0) < 1e-6

    def test_upsample(self):
        ds = make_test_dataset(sfreq=125.0)
        result = ResampleService.upsample(ds, factor=2)
        assert result.dataset is not None
        assert abs(result.dataset.sfreq - 250.0) < 1e-6

    def test_resample_to(self):
        ds = make_test_dataset(sfreq=250.0)
        result = ResampleService.resample_to(ds, 100.0)
        assert result.dataset is not None
        assert abs(result.dataset.sfreq - 100.0) < 1e-6


class TestICAService:
    def test_ica_fit(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)  # 需要足够样本点
        params = ICAParams(n_components=4, auto_find=False)
        service = ICAService()
        result = service.fit(ds, params)
        assert result.ica is not None
        assert result.ica.n_components_ == 4

    def test_ica_fit_apply(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        params = ICAParams(n_components=4, auto_find=False)
        service = ICAService()
        result = service.fit_apply(ds, params)
        assert result.dataset is not None

    def test_auto_find_artifacts(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        # 添加模拟 EOG 通道
        ds = dataclasses.replace(ds, ch_names=ds.ch_names + ["EOG1", "EOG2"])
        # n_channels 是从 data 派生的只读属性，不是 init 字段，无需（也不能）单独 replace
        ds = dataclasses.replace(ds, data=np.vstack([ds.data, np.random.randn(2, 5000) * 50]))
        
        params = ICAParams(n_components=4, auto_find=True, eog_channels=["EOG1"])
        service = ICAService()
        result = service.fit(ds, params)
        assert result.ica is not None


class TestInterpolationService:
    # 8 通道稀疏布局做球面拟合时，MNE 一定会报这三类信息性 RuntimeWarning
    #（数字化点少/头模半径外推/拟合原点偏移），属预期行为而非产品 bug，此处显式忽略。
    @pytest.mark.filterwarnings(
        "ignore:Only \\d+ head digitization points.*:RuntimeWarning",
        "ignore:Estimated head radius.*:RuntimeWarning",
        "ignore:.*more than 20 mm from head frame origin:RuntimeWarning",
    )
    def test_spherical_interpolation(self):
        ch_names = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"]
        ds = make_test_dataset(n_ch=8, n_samples=1000, ch_names=ch_names)
        # 标记坏道
        ds = ds.set_bad_channels(["Fp1"])
        # 真实 10-20 位置（标准蒙版单位为米，Montage 模型使用毫米）
        from eeg_workbench.models.dataset import Montage
        from eeg_workbench.utils.montage import make_standard_montage_compat
        std_pos = make_standard_montage_compat("standard_1020").get_positions()["ch_pos"]
        positions = {ch: tuple(np.asarray(std_pos[ch]) * 1000) for ch in ch_names}
        montage = Montage(name="standard_1020", positions=positions)
        ds = ds.set_montage(montage)

        params = BadChannelInterpolationParams(
            method=InterpolationMethod.SPHERICAL,
            bad_channels=["Fp1"]
        )
        result = InterpolationService.apply(ds, params)
        assert result.dataset is not None
        assert "Fp1" not in result.dataset.bad_channels  # 已重置

    def test_nearest_neighbor_interpolation(self):
        ds = make_test_dataset(n_ch=8, n_samples=1000)
        ds = ds.set_bad_channels(["Ch0"])

        params = BadChannelInterpolationParams(
            method=InterpolationMethod.NEAREST,
            bad_channels=["Ch0"]
        )
        result = InterpolationService.apply(ds, params)
        assert result.dataset is not None


# ---- 集成测试 ----
class TestPreprocessingPipeline:
    def test_standard_pipeline(self):
        # 标准预处理含 0.1Hz 高通，其 auto FIR 长度约 8251 点；
        # 用 9000 点（36 秒）仿真更接近真实记录长度，避免 MNE 短信号失真警告。
        ds = make_test_dataset(n_ch=8, n_samples=9000)

        # 1. 滤波
        result = FilterService.standard_preprocessing(ds)
        ds = result.dataset

        # 2. 重参考
        result = ReferenceService.average(ds)
        ds = result.dataset

        # 3. ICA
        params = ICAParams(n_components=4, auto_find=False)
        service = ICAService()
        result = service.fit_apply(ds, params)
        ds = result.dataset

        # 4. 重采样
        result = ResampleService.resample_to(ds, 128.0)
        ds = result.dataset

        assert ds is not None
        assert ds.sfreq == 128.0

    def test_processing_history_recorded(self):
        ds = make_test_dataset(n_samples=9000)  # 同上：长于 0.1Hz 高通 auto 滤波器长度
        original_history_len = len(ds.processing_history)

        result = FilterService.standard_preprocessing(ds)
        ds = result.dataset
        assert len(ds.processing_history) == original_history_len + 1
        assert ds.processing_history[-1]["step"] == "filter"

        result = ReferenceService.average(ds)
        ds = result.dataset
        assert len(ds.processing_history) == original_history_len + 2
        assert ds.processing_history[-1]["step"] == "reference"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])