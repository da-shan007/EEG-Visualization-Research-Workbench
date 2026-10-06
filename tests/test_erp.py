"""ERP/ERD/ERS 分析模块单元测试"""
import numpy as np
import pytest

from eeg_workbench.models.erp import (
    ERPAnalysisParams, ERDSParams, EpochParams,
    ERPComponent, BaselineMode, DEFAULT_ERP_PEAK_WINDOWS,
    DEFAULT_ERP_POLARITY,
    create_erp_params, create_erds_params
)
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
from eeg_workbench.services.erp import (
    ERPService, ERDSService, PeakDetector, TopomapService,
    ERPAnalysisResult, ERDSAnalysisResult
)


# ---- 测试辅助 ----
def make_test_dataset(n_ch=8, n_samples=5000, sfreq=250.0) -> EEGDataset:
    """创建测试用数据集"""
    data = np.random.randn(n_ch, n_samples) * 10  # µV
    # 添加一些 ERP 样式信号
    t = np.arange(n_samples) / sfreq
    # 模拟 P300: 300ms 处正峰
    p300_idx = int(0.3 * sfreq)
    if p300_idx < n_samples:
        data[0, p300_idx:p300_idx+50] += 10 * np.hanning(50)
    # 模拟 N100: 100ms 处负峰
    n100_idx = int(0.1 * sfreq)
    if n100_idx < n_samples:
        data[1, n100_idx:n100_idx+30] -= 8 * np.hanning(30)

    ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    # 添加一些事件
    from eeg_workbench.models.dataset import Event
    events = [
        Event(onset=0.5, description="Stimulus/Target", value=1),
        Event(onset=1.5, description="Stimulus/NonTarget", value=2),
        Event(onset=2.5, description="Stimulus/Target", value=1),
        Event(onset=3.5, description="Stimulus/NonTarget", value=2),
    ]
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
        events=events,
    )


def make_epochs_data(n_epochs=20, n_ch=8, n_samples=500, sfreq=250.0) -> np.ndarray:
    """创建测试用 Epochs 数据 (n_epochs, n_ch, n_times)"""
    data = np.random.randn(n_epochs, n_ch, n_samples) * 10
    t = np.arange(n_samples) / sfreq
    # 添加诱发响应
    # P300 在 300ms
    p300_idx = int(0.3 * sfreq)
    if p300_idx < n_samples:
        data[:, 0, p300_idx:p300_idx+50] += 10 * np.hanning(50)
    # N100 在 100ms
    n100_idx = int(0.1 * sfreq)
    if n100_idx < n_samples:
        data[:, 1, n100_idx:n100_idx+30] -= 8 * np.hanning(30)
    return data


# ---- Models 测试 ----
class TestERPParams:
    def test_epoch_params_validation(self):
        params = EpochParams(
            event_descriptions=["Stimulus/Target"],
            tmin=-0.2, tmax=0.8,
            baseline=(-0.2, 0.0)
        )
        errors = params.validate(250.0)
        assert len(errors) == 0

    def test_invalid_time_window(self):
        params = EpochParams(tmin=0.5, tmax=0.2)
        errors = params.validate(250.0)
        assert any("tmin 必须小于 tmax" in e for e in errors)

    def test_baseline_outside_epoch(self):
        params = EpochParams(tmin=-0.2, tmax=0.8, baseline=(-0.5, 0.0))
        errors = params.validate(250.0)
        assert any("基线窗必须在 epoch 窗内" in e for e in errors)

    def test_create_erp_params(self):
        params = create_erp_params(
            event_descriptions=["Stimulus/Target", "Stimulus/NonTarget"],
            tmin=-0.2, tmax=0.8
        )
        assert isinstance(params, ERPAnalysisParams)
        assert len(params.conditions) == 1

    def test_create_erds_params(self):
        params = create_erds_params(
            event_descriptions=["Stimulus/Target"],
            bands={"Alpha": (8, 13), "Beta": (13, 30)},
            tmin=-1.0, tmax=2.0
        )
        assert isinstance(params, ERDSParams)
        assert params.bands["Alpha"] == (8, 13)
        assert params.tmin == -1.0


class TestERPComponent:
    def test_default_peak_windows(self):
        assert ERPComponent.P1 in DEFAULT_ERP_PEAK_WINDOWS
        assert ERPComponent.N1 in DEFAULT_ERP_PEAK_WINDOWS
        assert ERPComponent.P3 in DEFAULT_ERP_PEAK_WINDOWS
        assert DEFAULT_ERP_PEAK_WINDOWS[ERPComponent.P3] == (0.25, 0.5)

    def test_default_polarity(self):
        assert DEFAULT_ERP_POLARITY[ERPComponent.P1] == "pos"
        assert DEFAULT_ERP_POLARITY[ERPComponent.N1] == "neg"
        assert DEFAULT_ERP_POLARITY[ERPComponent.P3] == "pos"


# ---- Services 测试 ----
class TestPeakDetector:
    def test_detect_known_peaks(self):
        """测试峰值检测器能否检测到已知信号"""
        import mne
        ds = make_test_dataset()
        
        # 创建 MNE Raw 并提取 Epochs
        raw = ds.to_mne_raw()
        events, event_id = mne.events_from_annotations(raw)
        
        epochs = mne.Epochs(
            raw, events, event_id=event_id,
            tmin=-0.2, tmax=0.8, baseline=(-0.2, 0.0),
            preload=True, verbose=False
        )
        
        evoked = epochs.average()
        
        # 检测峰值
        detector = PeakDetector()
        peaks = detector.detect(evoked)
        
        # 应该能检测到一些峰值
        assert len(peaks) > 0
        for comp, peak in peaks.items():
            assert isinstance(peak.latency, float)
            assert isinstance(peak.amplitude, float)
            assert peak.channel in evoked.ch_names

    def test_custom_peak_detection(self):
        import mne
        ds = make_test_dataset()
        raw = ds.to_mne_raw()
        events, event_id = mne.events_from_annotations(raw)
        
        epochs = mne.Epochs(
            raw, events, event_id=event_id,
            tmin=-0.2, tmax=0.8, baseline=(-0.2, 0.0),
            preload=True, verbose=False
        )
        evoked = epochs.average()
        
        detector = PeakDetector()
        # 自定义检测 200-400ms 间的正峰
        result = detector.detect_custom(evoked, (0.2, 0.4), "pos")
        if result:
            assert 0.2 <= result.latency <= 0.4
            assert result.polarity == "positive"


class TestTopomapService:
    def test_compute_topomap_data(self):
        import mne
        ds = make_test_dataset()
        raw = ds.to_mne_raw()
        events, event_id = mne.events_from_annotations(raw)
        
        epochs = mne.Epochs(
            raw, events, event_id=event_id,
            tmin=-0.2, tmax=0.8, baseline=(-0.2, 0.0),
            preload=True, verbose=False
        )
        evoked = epochs.average()
        
        topomap_data = TopomapService.compute_topomap_data(evoked, 0.3)
        assert topomap_data.data.shape == (evoked.info["nchan"],)
        assert len(topomap_data.ch_names) == evoked.info["nchan"]

    def test_compute_from_array(self):
        ds = make_test_dataset(n_ch=8)
        montage = ds.montage
        topomap_data = TopomapService.compute_topomap_from_array(
            ds.data.mean(axis=1), ds.ch_names, montage
        )
        assert topomap_data.data.shape == (8,)


# ---- 集成测试 (需要完整 MNE 环境) ----
@pytest.mark.integration
class TestERPIntegration:
    def test_erp_analysis_pipeline(self):
        """完整 ERP 分析流程测试"""
        ds = make_test_dataset()
        
        params = create_erp_params(
            event_descriptions=["Stimulus/Target", "Stimulus/NonTarget"],
            tmin=-0.2, tmax=0.8,
            baseline=(-0.2, 0.0)
        )
        # 添加对比
        params.contrast_pairs = [("Condition", "Condition")]  # 简化
        
        result = ERPService.analyze(ds, params)
        assert isinstance(result, ERPAnalysisResult)
        assert result.result.evokeds is not None

    def test_erds_analysis_pipeline(self):
        """ERD/ERS 分析流程测试"""
        ds = make_test_dataset(n_ch=8, n_samples=10000)  # 更长数据用于 ERD/ERS
        
        params = create_erds_params(
            event_descriptions=["Stimulus/Target"],
            bands={"Alpha": (8, 13), "Beta": (13, 30)},
            tmin=-1.0, tmax=2.0,
            baseline=(-1.0, -0.5)
        )
        
        result = ERDSService.analyze(ds, params)
        assert isinstance(result, ERDSAnalysisResult)
        assert result.result.tfrs is not None


class TestPeakNormalization:
    """峰值表示归一化回归测试。

    ERPService._detect_peaks 给纯 dict，PeakDetector.batch_detect 给
    PeakResult 对象（不支持下标访问）。_serialize_peaks/_peak_to_dict
    必须两种都接受——以前 PeakResult 路径走 _emit_peaks 会 TypeError。
    """

    def _peak_obj(self):
        from eeg_workbench.models.erp import PeakResult
        return PeakResult(
            component=ERPComponent.P3,
            latency=0.3, amplitude=5.0, channel="Ch0",
            polarity="positive", time_window=(0.2, 0.5),
        )

    def test_peak_to_dict_accepts_peak_result(self):
        from eeg_workbench.viewmodels.erp_vm import ERPViewModel
        d = ERPViewModel._peak_to_dict(self._peak_obj())
        assert d == {"latency": 0.3, "amplitude": 5.0,
                     "channel": "Ch0", "polarity": "positive"}

    def test_peak_to_dict_accepts_plain_dict(self):
        from eeg_workbench.viewmodels.erp_vm import ERPViewModel
        d = ERPViewModel._peak_to_dict(
            {"latency": 0.3, "amplitude": 5.0,
             "channel": "Ch0", "polarity": "positive"})
        assert d["latency"] == 0.3

    def test_peak_to_dict_none_and_empty(self):
        from eeg_workbench.viewmodels.erp_vm import ERPViewModel
        assert ERPViewModel._peak_to_dict(None) is None
        assert ERPViewModel._peak_to_dict({}) is None

    def test_serialize_peaks_with_peak_result_objects(self):
        from eeg_workbench.viewmodels.erp_vm import ERPViewModel
        out = ERPViewModel._serialize_peaks(
            {"Cond": {ERPComponent.P3: self._peak_obj()}})
        assert out["Cond"]["P3"]["latency"] == 0.3

    def test_serialize_peaks_with_plain_dicts(self):
        from eeg_workbench.viewmodels.erp_vm import ERPViewModel
        out = ERPViewModel._serialize_peaks(
            {"Cond": {ERPComponent.P3: {
                "latency": 0.3, "amplitude": 5.0,
                "channel": "Ch0", "polarity": "positive"}}})
        assert out["Cond"]["P3"]["channel"] == "Ch0"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])