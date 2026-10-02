"""前向模型 (导场矩阵) 计算服务"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.source import ForwardModelParams, HeadModelResult, SourceSpaceType
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ForwardModelResult:
    """前向模型结果"""
    fwd: Any  # mne.ForwardSolution
    src: Any  # mne.SourceSpaces
    processing_time_ms: float
    params_used: ForwardModelParams
    leadfield_info: dict


class ForwardModelService:
    """前向模型计算服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        head_model: HeadModelResult,
        params: ForwardModelParams,
        *,
        verbose: bool = False
    ) -> ForwardModelResult:
        """计算导场矩阵"""
        start_time = time.perf_counter()

        try:
            import mne
        except ImportError:
            raise RuntimeError("前向模型计算需要 MNE: pip install mne")

        # 区分球形头模型 vs BEM/FEM：球形模型返回 sphere dict
        is_spherical = head_model.model_type.value == 'spherical'
        bem_or_sphere = head_model.model

        # 1. 构建源空间
        src = ForwardModelService._setup_source_space(
            dataset, head_model, params, verbose, is_spherical, bem_or_sphere
        )

        # 2. 计算导场矩阵
        fwd = mne.make_forward_solution(
            info=dataset.to_mne_raw().info,
            trans=None,  # EEG 通常不需要 trans，除非有 MRI 对齐
            src=src,
            bem=bem_or_sphere,
            meg=params.meg,
            eeg=params.eeg,
            mindist=params.mindist,
            n_jobs=params.n_jobs,
            verbose=verbose
        )

        # 3. 固定朝向 (皮层面法向)
        if params.fixed and params.use_cps:
            fwd = mne.convert_forward_solution(
                fwd, surf_ori=True, force_fixed=True, verbose=verbose
            )

        elapsed = (time.perf_counter() - start_time) * 1000

        # 导场信息
        sol = fwd["sol"]
        if isinstance(sol, dict) and 'data' in sol:
            sol_arr = sol['data']
        else:
            sol_arr = sol
        leadfield_info = {
            "n_sources": fwd["source_nn"].shape[0],
            "n_channels": sol_arr.shape[0] if hasattr(sol_arr, 'shape') else int(sol.get('nrow', 0) if isinstance(sol, dict) else 0),
            "n_orient": fwd["source_nn"].shape[1] if fwd["source_nn"].ndim > 1 else 1,
            "src_type": params.source_space_type.value,
        }

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="forward_model",
                params=leadfield_info
            ),
            source="ForwardModelService"
        )

        return ForwardModelResult(
            fwd=fwd,
            src=src,
            processing_time_ms=elapsed,
            params_used=params,
            leadfield_info=leadfield_info
        )

    @staticmethod
    def _setup_source_space(
        dataset: EEGDataset,
        head_model: HeadModelResult,
        params: ForwardModelParams,
        verbose: bool,
        is_spherical: bool = False,
        sphere: dict | None = None
    ) -> Any:
        """设置源空间"""
        import mne
        
        subject = head_model.subject
        subjects_dir = None  # 可以从参数获取
        
        if is_spherical:
            # 球形头模型：用 sphere dict 创建体积源空间 (spacing 对 sphere 无效)
            src = mne.setup_volume_source_space(
                sphere=sphere,
                verbose=verbose
            )
            return src
        
        if params.source_space_type == SourceSpaceType.SURFACE:
            # 皮层面源空间
            src = mne.setup_source_space(
                subject=subject,
                subjects_dir=subjects_dir,
                spacing=params.spacing,
                add_dist=params.add_dist,
                verbose=verbose
            )
        elif params.source_space_type == SourceSpaceType.VOLUME:
            # 体积源空间
            src = mne.setup_volume_source_space(
                subject=subject,
                subjects_dir=subjects_dir,
                spacing=params.spacing,
                verbose=verbose
            )
        elif params.source_space_type == SourceSpaceType.MIXED:
            # 混合源空间
            surf_src = mne.setup_source_space(
                subject=subject,
                subjects_dir=subjects_dir,
                spacing=params.spacing,
                add_dist=params.add_dist,
                verbose=verbose
            )
            vol_src = mne.setup_volume_source_space(
                subject=subject,
                subjects_dir=subjects_dir,
                spacing=params.spacing,
                verbose=verbose
            )
            src = surf_src + vol_src
        else:
            # 离散源空间 (用于偶极子拟合)
            src = []
        
        return src

    @staticmethod
    def compute_leadfield(
        fwd,
        picks: list[int] | None = None
    ) -> np.ndarray:
        """提取导场矩阵"""
        if picks is not None:
            gain = fwd["sol"][picks]
        else:
            gain = fwd["sol"]
        return gain

    @staticmethod
    def compute_sensitivity(fwd) -> np.ndarray:
        """计算敏感度图"""
        import mne
        return mne.sensitivity_map(fwd, ch_type="eeg", mode="fixed")

    @staticmethod
    def plot_sensitivity(fwd, **kwargs):
        """绘制敏感度图"""
        import mne
        return mne.viz.plot_sensitivity_map(fwd, ch_type="eeg", **kwargs)


def compute_forward_solution(
    dataset: EEGDataset,
    head_model: HeadModelResult,
    params: ForwardModelParams,
    **kwargs
) -> ForwardModelResult:
    return ForwardModelService.compute(dataset, head_model, params, **kwargs)