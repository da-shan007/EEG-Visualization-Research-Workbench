"""头模型构建服务：球形模型、BEM、FEM、MRI 导入"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.source import (
    HeadModelParams, HeadModelType,
    SourceAnalysisResult, STANDARD_HEAD_MODELS
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class HeadModelResult:
    """头模型构建结果"""
    model: Any  # mne.HeadModel / mne.bem.ConductorModel
    subject: str
    model_type: HeadModelType
    processing_time_ms: float
    params_used: HeadModelParams


class HeadModelService:
    """头模型构建服务"""

    #: 本机可构建的模型类型（FEM/多层模型需外部求解器，后端显式拒绝，
    #: UI 下拉框只列出此处类型，避免可选但必失败）
    SUPPORTED_MODEL_TYPES = (HeadModelType.SPHERICAL, HeadModelType.BEM)

    @staticmethod
    def build(
        dataset: EEGDataset,
        params: HeadModelParams,
        *,
        verbose: bool = False
    ) -> HeadModelResult:
        """构建头模型"""
        start_time = time.perf_counter()

        try:
            import mne
        except ImportError:
            raise RuntimeError("头模型构建需要 MNE: pip install mne")

        # 根据模型类型构建
        if params.model_type == HeadModelType.SPHERICAL:
            model = HeadModelService._build_spherical(params, verbose)
        elif params.model_type == HeadModelType.BEM:
            model = HeadModelService._build_bem(params, verbose)
        elif params.model_type == HeadModelType.FEM:
            model = HeadModelService._build_fem(params, verbose)
        elif params.model_type == HeadModelType.MULTI_LAYER:
            model = HeadModelService._build_multi_layer(params, verbose)
        else:
            raise ValueError(f"不支持的头模型类型: {params.model_type}")

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="head_model",
                params={"type": params.model_type.value, "subject": params.subject}
            ),
            source="HeadModelService"
        )

        return HeadModelResult(
            model=model,
            subject=params.subject,
            model_type=params.model_type,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _build_spherical(params: HeadModelParams, verbose: bool) -> Any:
        """构建球形头模型 (返回供 EEG 前向计算的 sphere 模型 dict)"""
        import mne
        
        if params.sphere_radius is not None and params.sphere_center is not None:
            sphere = mne.make_sphere_model(
                r0=params.sphere_center,
                head_radius=params.sphere_radius,
                verbose=verbose
            )
        else:
            # 自动拟合球模型
            sphere = mne.make_sphere_model(verbose=verbose)
        
        return sphere

    @staticmethod
    def _build_bem(params: HeadModelParams, verbose: bool) -> Any:
        """构建 BEM 模型"""
        import mne
        
        subject = params.subject
        subjects_dir = params.subjects_dir
        
        if subjects_dir is None:
            import os
            subjects_dir = os.environ.get("SUBJECTS_DIR", mne.get_config("SUBJECTS_DIR"))
        
        if subject == "fsaverage" and subjects_dir is None:
            # 使用 MNE 内置 fsaverage
            subjects_dir = mne.datasets.fetch_fsaverage(verbose=True)
            subject = "fsaverage"
        
        # 检查 BEM 文件是否存在
        bem_path = mne.bem.make_bem_model(
            subject=subject,
            subjects_dir=subjects_dir,
            conductivity=params.conductivity,
            verbose=verbose
        )
        
        bem = mne.bem.make_bem_solution(bem_path, verbose=verbose)
        return bem

    @staticmethod
    def _build_fem(params: HeadModelParams, verbose: bool) -> Any:
        """构建 FEM 模型 (需要 SimNIBS 或其他 FEM 工具)"""
        # MNE 对 FEM 支持有限，通常需要外部工具生成
        raise RuntimeError(
            "FEM 头模型暂不支持直接构建：请先用 SimNIBS/charm 等工具由个体 MRI 生成 "
            ".msh 网格，再通过 HeadModelService.load_bem_from_file 导入已生成的模型"
        )

    @staticmethod
    def _build_multi_layer(params: HeadModelParams, verbose: bool) -> Any:
        """构建多层球模型"""
        # MNE 未提供多层同心球 EEG 头模型；多层球主要用于 MEG。
        # EEG 请使用 BEM（推荐，需个体 MRI 或 fsaverage 模板）或 SPHERICAL 单球模型。
        raise RuntimeError(
            "多层球模型暂不支持：EEG 源定位请改用 BEM（fsaverage 模板可用）或 SPHERICAL 单球模型"
        )

    @staticmethod
    def load_bem_from_file(bem_path: str, verbose: bool = False) -> Any:
        """从文件加载 BEM"""
        import mne
        return mne.read_bem_solution(bem_path, verbose=verbose)

    @staticmethod
    def create_scalp_surface(
        dataset: EEGDataset,
        params: HeadModelParams,
        verbose: bool = False
    ) -> Any:
        """创建头皮表面 (用于 3D 可视化)"""
        import mne
        
        # 从蒙版位置创建头皮表面
        if dataset.montage:
            dig_montage = dataset.montage.to_mne_montage()
            if dig_montage:
                return mne.make_scalp_surfaces(
                    subject=params.subject,
                    subjects_dir=params.subjects_dir,
                    verbose=verbose
                )
        return None


def build_head_model(
    dataset: EEGDataset,
    params: HeadModelParams,
    **kwargs: Any
) -> HeadModelResult:
    return HeadModelService.build(dataset, params, **kwargs)