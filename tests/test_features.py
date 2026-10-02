"""特征提取模块单元测试"""
import numpy as np
import pytest

from eeg_workbench.models.features import (
    BandPowerParams, TimeFrequencyParams, ConnectivityParams, NonlinearParams,
    SpectralMethod, TimeFrequencyMethod, ConnectivityMethod, NonlinearMeasure,
    STANDARD_BANDS, create_band_power_params
)
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
from eeg_workbench.services.features import (
    SpectralService, TimeFrequencyService, ConnectivityService, NonlinearService
)


# ---- 测试辅助 ----
def make_test_dataset(n_ch=8, n_samples=5000, sfreq=250.0) -> EEGDataset:
    """创建测试用数据集"""
    data = np.random.randn(n_ch, n_samples) * 10  # µV
    # 添加一些频率成分
    t = np.arange(n_samples) / sfreq
    data[0] += 5 * np.sin(2 * np.pi * 10 * t)  # Alpha
    data[1] += 3 * np.sin(2 * np.pi * 20 * t)  # Beta
    ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
    )


def make_epochs_data(n_epochs=20, n_ch=8, n_samples=500, sfreq=250.0) -> np.ndarray:
    """创建测试用 Epochs 数据"""
    data = np.random.randn(n_epochs, n_ch, n_samples) * 10
    t = np.arange(n_samples) / sfreq
    # 添加诱发响应
    data[:, 0, :] += 2 * np.sin(2 * np.pi * 10 * t)  # Alpha
    return data


# ---- Models 测试 ----
class TestBandPowerParams:
    def test_standard_bands(self):
        params = BandPowerParams()
        errors = params.validate(250.0)
        assert len(errors) == 0
        assert "Alpha" in params.bands
        assert params.bands["Alpha"] == (8, 13)

    def test_custom_bands(self):
        params = BandPowerParams(bands={"Custom": (10, 20)})
        errors = params.validate(250.0)
        assert len(errors) == 0

    def test_invalid_band(self):
        params = BandPowerParams(bands={"Bad": (20, 10)})
        errors = params.validate(250.0)
        assert len(errors) > 0

    def test_band_exceeds_nyquist(self):
        params = BandPowerParams(bands={"High": (100, 200)})
        errors = params.validate(250.0)  # Nyquist = 125
        assert len(errors) > 0

    def test_create_from_preset(self):
        params = create_band_power_params("standard")
        assert "Delta" in params.bands
        params = create_band_power_params("erp")
        assert "Theta" in params.bands
        params = create_band_power_params("micro")
        assert "Alpha1" in params.bands


class TestTimeFrequencyParams:
    def test_default_validation(self):
        params = TimeFrequencyParams()
        errors = params.validate(250.0, 5000)
        assert len(errors) == 0

    def test_morlet_params(self):
        params = TimeFrequencyParams(method=TimeFrequencyMethod.MORLET, n_cycles=7.0)
        errors = params.validate(250.0, 5000)
        assert len(errors) == 0

    def test_custom_freqs(self):
        params = TimeFrequencyParams(freqs=np.array([4, 8, 12, 30]))
        assert params.freqs is not None
        assert len(params.freqs) == 4


class TestConnectivityParams:
    def test_coherence_validation(self):
        params = ConnectivityParams(method=ConnectivityMethod.COHERENCE)
        errors = params.validate(250.0, 32)
        assert len(errors) == 0

    def test_plv_validation(self):
        params = ConnectivityParams(method=ConnectivityMethod.PLV)
        errors = params.validate(250.0, 32)
        assert len(errors) == 0

    def test_gca_validation(self):
        params = ConnectivityParams(method=ConnectivityMethod.GCA, gca_order=10)
        errors = params.validate(250.0, 32)
        assert len(errors) == 0

    def test_gca_invalid_order(self):
        params = ConnectivityParams(method=ConnectivityMethod.GCA, gca_order=0)
        errors = params.validate(250.0, 32)
        assert len(errors) > 0


class TestNonlinearParams:
    def test_default_validation(self):
        params = NonlinearParams()
        errors = params.validate(5000)
        assert len(errors) == 0

    def test_sample_entropy_params(self):
        params = NonlinearParams(
            measures=[NonlinearMeasure.SAMPLE_ENTROPY],
            sample_entropy_m=2,
            sample_entropy_r=0.2
        )
        errors = params.validate(5000)
        assert len(errors) == 0

    def test_insufficient_samples(self):
        params = NonlinearParams(
            measures=[NonlinearMeasure.SAMPLE_ENTROPY],
            sample_entropy_m=5  # 需要更多样本
        )
        errors = params.validate(100)  # 样本太少
        assert len(errors) > 0


# ---- Services 测试 ----
class TestSpectralService:
    def test_welch_band_power(self):
        ds = make_test_dataset()
        params = BandPowerParams(method=SpectralMethod.WELCH)
        result = SpectralService.compute(ds, params)
        assert result.feature_result is not None
        assert result.feature_result.band_power is not None
        assert "Alpha" in result.feature_result.band_power
        assert result.feature_result.band_power["Alpha"].shape == (8,)

    def test_welch_band_power_short_signal(self):
        data = np.random.randn(8, 31) * 10
        ds = EEGDataset(
            name="ShortSignal",
            data=data.astype(np.float64),
            sfreq=250.0,
            ch_names=[f"Ch{i}" for i in range(8)],
            channel_info={ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in [f"Ch{i}" for i in range(8)]},
        )
        params = BandPowerParams(method=SpectralMethod.WELCH)
        result = SpectralService.compute(ds, params)
        assert result.feature_result is not None
        assert result.feature_result.band_power is not None
        assert "Alpha" in result.feature_result.band_power
        assert result.feature_result.band_power["Alpha"].shape == (8,)

    def test_multitaper_band_power(self):
        ds = make_test_dataset()
        params = BandPowerParams(method=SpectralMethod.MULTITAPER)
        result = SpectralService.compute(ds, params)
        assert result.feature_result is not None

    def test_fft_band_power(self):
        ds = make_test_dataset()
        params = BandPowerParams(method=SpectralMethod.FFT)
        result = SpectralService.compute(ds, params)
        assert result.feature_result is not None

    def test_relative_power(self):
        ds = make_test_dataset()
        params = BandPowerParams(relative=True)
        result = SpectralService.compute(ds, params)
        # 相对功率总和应接近 1
        total = sum(v.sum() for v in result.feature_result.band_power.values())
        assert abs(total - 1.0) < 0.5  # 允许一定误差

    def test_log_transform(self):
        ds = make_test_dataset()
        params = BandPowerParams(log_transform=True)
        result = SpectralService.compute(ds, params)
        # 对数变换后应为负值
        for v in result.feature_result.band_power.values():
            assert np.all(v <= 0)

    def test_epochs_input(self):
        ds = make_test_dataset()
        epochs = make_epochs_data()
        params = BandPowerParams()
        result = SpectralService.compute(ds, params, epochs_data=epochs)
        assert result.feature_result.band_power["Alpha"].shape == (20, 8)


class TestTimeFrequencyService:
    def test_morlet_tfr(self):
        ds = make_test_dataset(n_samples=2000)
        params = TimeFrequencyParams(
            method=TimeFrequencyMethod.MORLET,
            fmin=4, fmax=40, n_freqs=20,
            n_cycles=7.0
        )
        result = TimeFrequencyService.compute(ds, params)
        assert result.feature_result is not None
        assert result.feature_result.time_frequency is not None
        assert result.feature_result.time_frequency.shape[1] == 20  # n_freqs

    def test_stft_tfr(self):
        ds = make_test_dataset(n_samples=2000)
        params = TimeFrequencyParams(
            method=TimeFrequencyMethod.STFT,
            fmin=4, fmax=40, n_fft=128
        )
        result = TimeFrequencyService.compute(ds, params)
        assert result.feature_result is not None

    def test_multitaper_tfr(self):
        ds = make_test_dataset(n_samples=2000)
        params = TimeFrequencyParams(
            method=TimeFrequencyMethod.MULTITAPER,
            fmin=4, fmax=40, n_freqs=10
        )
        result = TimeFrequencyService.compute(ds, params)
        assert result.feature_result is not None

    def test_baseline_correction(self):
        ds = make_test_dataset(n_samples=2000)
        params = TimeFrequencyParams(
            method=TimeFrequencyMethod.MORLET,
            fmin=4, fmax=40, n_freqs=10,
            baseline=(-0.5, -0.1),
            baseline_mode="logratio"
        )
        result = TimeFrequencyService.compute(ds, params)
        assert result.feature_result is not None

    def test_epochs_average(self):
        ds = make_test_dataset(n_samples=2000)
        epochs = make_epochs_data(n_epochs=10, n_samples=500)
        params = TimeFrequencyParams(
            method=TimeFrequencyMethod.MORLET,
            fmin=4, fmax=40, n_freqs=10,
            average=True
        )
        result = TimeFrequencyService.compute(ds, params, epochs_data=epochs)
        assert result.feature_result.time_frequency.shape[0] == 1  # 平均后只剩 1 epoch


class TestConnectivityService:
    def test_coherence(self):
        ds = make_test_dataset(n_ch=8, n_samples=2000)
        params = ConnectivityParams(
            method=ConnectivityMethod.COHERENCE,
            fmin=4, fmax=40, n_freqs=10
        )
        result = ConnectivityService.compute(ds, params)
        assert result.feature_result is not None
        assert result.feature_result.connectivity is not None
        # (n_freqs, n_ch, n_ch)
        assert result.feature_result.connectivity.shape == (10, 8, 8)

    def test_plv(self):
        ds = make_test_dataset(n_ch=8, n_samples=2000)
        params = ConnectivityParams(
            method=ConnectivityMethod.PLV,
            fmin=4, fmax=40, n_freqs=5
        )
        result = ConnectivityService.compute(ds, params)
        assert result.feature_result is not None

    def test_imag_coherence(self):
        ds = make_test_dataset(n_ch=8, n_samples=2000)
        params = ConnectivityParams(
            method=ConnectivityMethod.IMAG_COHERENCE,
            fmin=4, fmax=40, n_freqs=5
        )
        result = ConnectivityService.compute(ds, params)
        assert result.feature_result is not None

    def test_specific_indices(self):
        ds = make_test_dataset(n_ch=8, n_samples=2000)
        # 只计算 Ch0 到其他通道
        indices = (np.array([0, 0, 0]), np.array([1, 2, 3]))
        params = ConnectivityParams(
            method=ConnectivityMethod.COHERENCE,
            fmin=4, fmax=40, n_freqs=5,
            indices=indices
        )
        result = ConnectivityService.compute(ds, params)
        assert result.feature_result is not None

    def test_epochs_connectivity(self):
        ds = make_test_dataset(n_ch=8, n_samples=2000)
        epochs = make_epochs_data(n_epochs=10, n_ch=8, n_samples=500)
        params = ConnectivityParams(
            method=ConnectivityMethod.COHERENCE,
            fmin=4, fmax=40, n_freqs=5
        )
        result = ConnectivityService.compute(ds, params, epochs_data=epochs)
        # (n_epochs, n_freqs, n_ch, n_ch)
        assert result.feature_result.connectivity.shape[0] == 10


class TestNonlinearService:
    def test_sample_entropy(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        params = NonlinearParams(
            measures=[NonlinearMeasure.SAMPLE_ENTROPY],
            sample_entropy_m=2,
            sample_entropy_r=0.2
        )
        result = NonlinearService.compute(ds, params)
        assert result.feature_result is not None
        assert "sample_entropy" in result.feature_result.nonlinear
        se = result.feature_result.nonlinear["sample_entropy"]
        assert se.shape == (8,)  # 8 通道

    def test_permutation_entropy(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        params = NonlinearParams(
            measures=[NonlinearMeasure.PERMUTATION_ENTROPY],
            perm_entropy_order=3,
            perm_entropy_delay=1
        )
        result = NonlinearService.compute(ds, params)
        assert "perm_entropy" in result.feature_result.nonlinear

    def test_hurst_exponent(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        params = NonlinearParams(
            measures=[NonlinearMeasure.HURST_EXPONENT]
        )
        result = NonlinearService.compute(ds, params)
        assert "hurst" in result.feature_result.nonlinear
        hurst = result.feature_result.nonlinear["hurst"]
        # Hurst 指数通常在 0-1 之间
        assert np.all(hurst >= 0) and np.all(hurst <= 1.5)

    def test_dfa(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        params = NonlinearParams(
            measures=[NonlinearMeasure.DETRENDED_FA]
        )
        result = NonlinearService.compute(ds, params)
        assert "dfa" in result.feature_result.nonlinear

    def test_entropy_suite(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        result = NonlinearService.entropy_suite(ds)
        assert "sample_entropy" in result.feature_result.nonlinear
        assert "perm_entropy" in result.feature_result.nonlinear
        assert "approx_entropy" in result.feature_result.nonlinear

    def test_fractal_suite(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        result = NonlinearService.fractal_suite(ds)
        assert "hurst" in result.feature_result.nonlinear
        assert "dfa" in result.feature_result.nonlinear

    def test_epochs_nonlinear(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)
        epochs = make_epochs_data(n_epochs=5, n_ch=8, n_samples=500)
        params = NonlinearParams(
            measures=[NonlinearMeasure.SAMPLE_ENTROPY, NonlinearMeasure.PERMUTATION_ENTROPY]
        )
        result = NonlinearService.compute(ds, params, epochs_data=epochs)
        assert result.feature_result.nonlinear["sample_entropy"].shape == (5, 8)


# ---- 集成测试 ----
class TestFeaturesPipeline:
    def test_full_pipeline(self):
        ds = make_test_dataset(n_ch=8, n_samples=5000)

        # 1. 频段功率
        bp = SpectralService.compute(ds, BandPowerParams())
        assert bp.feature_result.band_power is not None

        # 2. 时频
        tfr = TimeFrequencyService.compute(ds, TimeFrequencyParams(n_freqs=10))
        assert tfr.feature_result.time_frequency is not None

        # 3. 连通性
        conn = ConnectivityService.compute(ds, ConnectivityParams(n_freqs=5))
        assert conn.feature_result.connectivity is not None

        # 4. 非线性
        nl = NonlinearService.compute(ds, NonlinearParams(
            measures=[NonlinearMeasure.SAMPLE_ENTROPY, NonlinearMeasure.HURST_EXPONENT]
        ))
        assert nl.feature_result.nonlinear is not None

        # 5. Epochs 分析
        epochs = make_epochs_data(n_epochs=10, n_ch=8, n_samples=500)
        bp_epochs = SpectralService.compute(ds, BandPowerParams(), epochs_data=epochs)
        assert bp_epochs.feature_result.band_power["Alpha"].shape == (10, 8)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])