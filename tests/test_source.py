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

    def test_validate_rejects_str_model_type(self):
        # UI 曾直接传下拉框字符串导致构建报“不支持的类型”；validate 应提前拦截
        params = HeadModelParams(model_type="bem")
        errors = params.validate()
        assert any("HeadModelType" in e for e in errors)


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


class TestCJKFont:
    def test_ensure_cjk_font_idempotent(self):
        from eeg_workbench.utils.fonts import ensure_cjk_font
        first = ensure_cjk_font()
        second = ensure_cjk_font()
        assert first == second
        if first is not None:
            import matplotlib
            assert first in matplotlib.rcParams["font.sans-serif"]


class TestPreviewPlots:
    """在线预览绘图测试（全离线：合成几何 + 真 sphere/fwd，不下载数据）"""

    def test_supported_types_exclude_unsupportable(self):
        assert HeadModelType.SPHERICAL in HeadModelService.SUPPORTED_MODEL_TYPES
        assert HeadModelType.BEM in HeadModelService.SUPPORTED_MODEL_TYPES
        assert HeadModelType.FEM not in HeadModelService.SUPPORTED_MODEL_TYPES
        assert HeadModelType.MULTI_LAYER not in HeadModelService.SUPPORTED_MODEL_TYPES

    def _synthetic_bem(self):
        rng = np.random.default_rng(0)
        surfs = []
        for i, r in enumerate([0.06, 0.075, 0.09]):
            u = rng.normal(size=(120, 3))
            u /= np.linalg.norm(u, axis=1, keepdims=True)
            surfs.append({
                "rr": u * r,
                "tris": np.array([[a, a + 1, a + 2] for a in range(0, 117, 3)]),
                "sigma": (1.0, 0.0125, 1.0)[i],
                "id": (4, 3, 2)[i],
            })
        return {"surfs": surfs}

    def test_fig_bem_geometry(self):
        import matplotlib
        matplotlib.use("Agg")
        from eeg_workbench.services.source.preview_plots import fig_bem_geometry
        fig = fig_bem_geometry(self._synthetic_bem())
        assert len(fig.axes) == 1

    def test_fig_sphere_geometry_real_model(self):
        import matplotlib
        matplotlib.use("Agg")
        import mne
        from eeg_workbench.services.source.preview_plots import fig_sphere_geometry
        sphere = mne.make_sphere_model(r0=(0.0, 0.0, 0.04), head_radius=0.095, verbose=False)
        fig = fig_sphere_geometry(sphere)
        assert len(fig.axes) == 1

    def test_fig_dipoles_all_views(self):
        import matplotlib
        matplotlib.use("Agg")
        from eeg_workbench.services.source.preview_plots import (
            fig_dipoles_2d, DIPOLE_VIEW_PLANES,
        )
        dips = [{"pos": np.array([0.01, -0.02, 0.06]),
                 "ori": np.array([0.3, 0.1, 0.9]),
                 "amplitude": 20e-9, "gof": 0.95}]
        assert set(DIPOLE_VIEW_PLANES) == {
            "lateral", "medial", "rostral", "caudal", "dorsal", "ventral"}
        for view in DIPOLE_VIEW_PLANES:
            assert len(fig_dipoles_2d(dips, view=view).axes) == 1

    def test_fig_sensors_and_src_cloud(self):
        import matplotlib
        matplotlib.use("Agg")
        from eeg_workbench.services.source.preview_plots import (
            fig_sensors_2d, fig_src_cloud,
        )
        rng = np.random.default_rng(1)
        pos = rng.uniform(-0.09, 0.09, (8, 3))
        fig = fig_sensors_2d(pos, [f"Ch{i}" for i in range(8)])
        assert len(fig.axes) == 1
        src = [{"rr": rng.uniform(-0.07, 0.07, (50, 3))}]
        assert len(fig_src_cloud(src).axes) == 1

    def test_fig_sensitivity_real_fwd(self):
        import matplotlib
        matplotlib.use("Agg")
        import mne
        from matplotlib.figure import Figure
        sphere = mne.make_sphere_model(verbose=False)
        info = mne.create_info(["Cz", "Pz", "Oz", "Fz"], 256.0, "eeg")
        from eeg_workbench.utils.montage import make_standard_montage_compat
        info.set_montage(make_standard_montage_compat("standard_1020"))
        src = mne.setup_volume_source_space(sphere=sphere, pos=30.0, verbose=False)
        fwd = mne.make_forward_solution(info, trans=None, src=src, bem=sphere,
                                        eeg=True, meg=False, verbose=False)
        fig = ForwardModelService.plot_sensitivity(fwd)
        assert isinstance(fig, Figure)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])