"""源定位模块单元测试"""
import numpy as np
import pytest

from eeg_workbench.models.source import (
    HeadModelParams, ForwardModelParams, InverseParams, DipoleFitParams,
    HeadModelType, SourceSpaceType, InverseMethod,
    STANDARD_HEAD_MODELS, create_head_model_params
)
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
from eeg_workbench.services.source import HeadModelService, ForwardModelService, InverseService, DipoleFitService


# ---- 测试辅助 ----
def make_test_dataset(n_ch=8, n_samples=1000, sfreq=250.0) -> EEGDataset:
    data = np.random.randn(n_ch, n_samples) * 10
    ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
    )


# ---- Models 测试 ----
class TestHeadModelParams:
    def test_spherical_validation(self):
        params = HeadModelParams(model_type=HeadModelType.SPHERICAL, sphere_radius=0.1)
        errors = params.validate()
        assert len(errors) == 0

    def test_spherical_missing_radius(self):
        params = HeadModelParams(model_type=HeadModelType.SPHERICAL)
        errors = params.validate()
        assert any("半径" in e for e in errors)

    def test_bem_validation(self):
        params = HeadModelParams(model_type=HeadModelType.BEM, conductivity=(0.3, 0.006, 0.3))
        errors = params.validate()
        assert len(errors) == 0

    def test_bem_invalid_conductivity(self):
        params = HeadModelParams(model_type=HeadModelType.BEM, conductivity=(0.3,))
        errors = params.validate()
        assert any("1 层或 3 层" in e for e in errors)

    def test_create_from_preset(self):
        for preset in ["fsaverage_bem", "single_sphere", "three_layer_bem"]:
            params = create_head_model_params(preset)
            assert isinstance(params, HeadModelParams)


class TestForwardModelParams:
    def test_default_values(self):
        params = ForwardModelParams()
        assert params.source_space_type == SourceSpaceType.SURFACE
        assert params.spacing == "oct6"
        assert params.eeg is True


class TestInverseParams:
    def test_default_validation(self):
        params = InverseParams()
        assert params.method == InverseMethod.MNE

    def test_beamformer_requires_freq(self):
        params = InverseParams(method=InverseMethod.LCMV)
        errors = params.validate(InverseMethod.LCMV)
        assert any("频带" in e for e in errors)

    def test_dics_requires_freq(self):
        params = InverseParams(method=InverseMethod.DICS)
        errors = params.validate(InverseMethod.DICS)
        assert any("频带" in e for e in errors)


class TestDipoleFitParams:
    def test_default_values(self):
        params = DipoleFitParams()
        assert params.method == "least_squares"
        assert params.max_dipoles == 1
        assert params.goodness_of_fit_threshold == 0.9


# ---- Services 测试 (需要 MNE) ----
class TestSourceServices:
    def test_head_model_service_import(self):
        # 验证服务可以导入
        assert HeadModelService is not None
        assert ForwardModelService is not None
        assert InverseService is not None
        assert DipoleFitService is not None

    def test_interpolate_to_surface_methods(self):
        from eeg_workbench.services.source.visualization_3d import SourceVisualization3D
        rng = np.random.default_rng(4)
        src = rng.uniform(-1, 1, (40, 3))
        data = src[:, 0] + 2 * src[:, 1]
        tgt = rng.uniform(-0.8, 0.8, (15, 3))
        for method in ("nearest", "linear"):
            out = SourceVisualization3D.interpolate_to_surface(data, src, tgt, None, method=method)
            assert out.shape == (15,)
            assert not np.isnan(out).any()
        with pytest.raises(ValueError):
            SourceVisualization3D.interpolate_to_surface(data, src, tgt, None, method="spline")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])