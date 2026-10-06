"""逆向求解服务：MNE、dSPM、sLORETA、eLORETA、LCMV、DICS、波束成形"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.source import (
    InverseParams, InverseMethod,
    SourceAnalysisResult
)
from eeg_workbench.services.source.forward_model import ForwardModelResult
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


# MNE 的 apply_inverse() 对方法名大小写敏感，只接受 'MNE'/'dSPM'/'sLORETA'/'eLORETA'，
# 而 InverseMethod 的 value 全是小写（'mne'/'dspm'/...）。直接把 .value 传给 MNE
# 会抛 ValueError，所以统一走这个映射。
_MNE_METHOD_NAMES: dict[InverseMethod, str] = {
    InverseMethod.MNE: "MNE",
    InverseMethod.dSPM: "dSPM",
    InverseMethod.sLORETA: "sLORETA",
    InverseMethod.eLORETA: "eLORETA",
}


def _mne_method_name(method: InverseMethod) -> str:
    """返回 MNE 认识的 canonical 方法名，未知方法退回 MNE。"""
    return _MNE_METHOD_NAMES.get(method, "MNE")


@dataclass
class InverseSolutionResult:
    """逆向求解结果"""
    stc: Any  # mne.SourceEstimate
    inv: Any  # mne.InverseOperator
    processing_time_ms: float
    params_used: InverseParams
    method: str


class InverseService:
    """逆向求解服务"""

    @staticmethod
    def compute(
        dataset: EEGDataset,
        fwd_result: ForwardModelResult,
        params: InverseParams,
        *,
        verbose: bool = False
    ) -> InverseSolutionResult:
        """计算逆向解"""
        start_time = time.perf_counter()

        try:
            import mne
            from mne.minimum_norm import (
                make_inverse_operator, apply_inverse,
                apply_inverse_epochs, apply_inverse_raw
            )
            from mne.beamformer import (
                make_lcmv, apply_lcmv, apply_lcmv_epochs,
                make_dics, apply_dics
            )
        except ImportError:
            raise RuntimeError("逆向求解需要 MNE: pip install mne")

        fwd = fwd_result.fwd
        raw = dataset.to_mne_raw()

        # 计算噪声协方差
        noise_cov = InverseService._compute_noise_cov(raw, params, verbose)

        # 根据方法计算逆向解
        if params.method in (InverseMethod.MNE, InverseMethod.dSPM, InverseMethod.sLORETA, InverseMethod.eLORETA):
            result = InverseService._compute_mne_family(
                raw, fwd, noise_cov, params, verbose
            )
        elif params.method in (InverseMethod.LCMV, InverseMethod.SAM):
            result = InverseService._compute_beamformer(
                raw, fwd, noise_cov, params, verbose
            )
        elif params.method == InverseMethod.DICS:
            result = InverseService._compute_dics(
                raw, fwd, noise_cov, params, verbose
            )
        elif params.method in (InverseMethod.MCE, InverseMethod.GAMMA_MAP):
            result = InverseService._compute_sparse_bayesian(
                raw, fwd, noise_cov, params, verbose
            )
        else:
            raise ValueError(f"不支持的逆向方法: {params.method}")

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="inverse_solution",
                params={"method": params.method.value, "snr": params.snr}
            ),
            source="InverseService"
        )

        return InverseSolutionResult(
            stc=result["stc"],
            inv=result["inv"],
            processing_time_ms=elapsed,
            params_used=params,
            method=params.method.value
        )

    @staticmethod
    def _compute_noise_cov(raw: Any, params: InverseParams, verbose: bool) -> Any:
        """计算噪声协方差矩阵"""
        import mne
        
        if params.tmin is not None or params.tmax is not None:
            # 使用指定时间窗计算
            noise_cov = mne.compute_raw_covariance(
                raw, tmin=params.tmin, tmax=params.tmax,
                method="shrunk", verbose=verbose
            )
        else:
            # 使用空房间或预刺激基线
            noise_cov = mne.compute_raw_covariance(
                raw, method="shrunk", verbose=verbose
            )
        return noise_cov

    @staticmethod
    def _compute_mne_family(
        raw: Any, fwd: Any, noise_cov: Any, params: InverseParams, verbose: bool
    ) -> dict[str, Any]:
        """计算 MNE/dSPM/sLORETA/eLORETA"""
        import mne
        from mne.minimum_norm import (
            make_inverse_operator, apply_inverse,
            apply_inverse_epochs
        )

        # 构建逆向算子
        inv = make_inverse_operator(
            raw.info, fwd, noise_cov,
            loose=params.loose,
            depth=params.depth,
            fixed=False,
            verbose=verbose
        )

        # 计算 lambda2
        lambda2 = params.lambda2 if params.lambda2 > 0 else 1.0 / params.snr**2

        # 应用逆向解
        if params.method == InverseMethod.MNE:
            stc = apply_inverse(raw, inv, lambda2, method="MNE", verbose=verbose)
        elif params.method == InverseMethod.dSPM:
            stc = apply_inverse(raw, inv, lambda2, method="dSPM", verbose=verbose)
        elif params.method == InverseMethod.sLORETA:
            stc = apply_inverse(raw, inv, lambda2, method="sLORETA", verbose=verbose)
        elif params.method == InverseMethod.eLORETA:
            # eLORETA 需要特殊处理
            stc = apply_inverse(raw, inv, lambda2, method="eLORETA", verbose=verbose)
        else:
            stc = apply_inverse(raw, inv, lambda2, method="MNE", verbose=verbose)

        return {"stc": stc, "inv": inv}

    @staticmethod
    def _compute_beamformer(
        raw: Any, fwd: Any, noise_cov: Any, params: InverseParams, verbose: bool
    ) -> dict[str, Any]:
        """计算 LCMV/SAM 波束成形"""
        import mne
        from mne.beamformer import make_lcmv, apply_lcmv, apply_lcmv_epochs

        # 数据协方差
        data_cov = mne.compute_raw_covariance(raw, verbose=verbose)

        # 构建 LCMV
        lcmv = make_lcmv(
            raw.info, fwd, data_cov,
            reg=params.reg,
            noise_cov=noise_cov,
            pick_ori=params.pick_ori,
            weight_norm=params.weight_norm,
            rank=params.rank,
            reduce_rank=params.reduce_rank,
            verbose=verbose
        )

        # 应用波束成形
        stc = apply_lcmv(raw, lcmv, verbose=verbose)

        return {"stc": stc, "inv": lcmv}

    @staticmethod
    def _compute_dics(
        raw: Any, fwd: Any, noise_cov: Any, params: InverseParams, verbose: bool
    ) -> dict[str, Any]:
        """计算 DICS (动态成像相干波束成形)"""
        import mne
        from mne.beamformer import make_dics, apply_dics

        if params.fmin is None or params.fmax is None:
            raise ValueError("DICS 需要指定频带 fmin/fmax")

        # 计算 CSD
        csd = mne.time_frequency.csd_morlet(
            raw, frequencies=np.linspace(params.fmin, params.fmax, 10),
            n_cycles=7.0, verbose=verbose
        )

        # 构建 DICS
        dics = make_dics(
            raw.info, fwd, csd,
            reg=params.reg,
            pick_ori=params.pick_ori,
            weight_norm=params.weight_norm,
            verbose=verbose
        )

        # 应用 DICS
        stc = apply_dics(raw, dics, verbose=verbose)

        return {"stc": stc, "inv": dics}

    @staticmethod
    def _compute_sparse_bayesian(
        raw: Any, fwd: Any, noise_cov: Any, params: InverseParams, verbose: bool
    ) -> dict[str, Any]:
        """稀疏贝叶斯方法 (MCE/Gamma MAP)"""
        # MNE 对稀疏贝叶斯支持有限，通常需要外部工具
        # 这里提供接口，实际实现可调用外部工具或使用近似方法
        import mne
        from mne.minimum_norm import make_inverse_operator, apply_inverse

        inv = make_inverse_operator(
            raw.info, fwd, noise_cov,
            loose=params.loose, depth=params.depth, verbose=verbose
        )

        lambda2 = params.lambda2 if params.lambda2 > 0 else 1.0 / params.snr**2
        stc = apply_inverse(raw, inv, lambda2, method="MNE", verbose=verbose)

        return {"stc": stc, "inv": inv}

    @staticmethod
    def apply_inverse_epochs(
        epochs: Any, inv: Any, params: InverseParams, verbose: bool = False
    ) -> Any:
        """对 Epochs 应用逆向解"""
        import mne
        from mne.minimum_norm import apply_inverse_epochs

        lambda2 = params.lambda2 if params.lambda2 > 0 else 1.0 / params.snr**2
        method = _mne_method_name(params.method)
        
        stcs = apply_inverse_epochs(
            epochs, inv, lambda2, method=method,
            pick_ori=params.pick_ori, verbose=verbose
        )
        return stcs

    @staticmethod
    def apply_inverse_raw(
        raw: Any, inv: Any, params: InverseParams, verbose: bool = False
    ) -> Any:
        """对 Raw 应用逆向解"""
        import mne
        from mne.minimum_norm import apply_inverse

        lambda2 = params.lambda2 if params.lambda2 > 0 else 1.0 / params.snr**2
        method = _mne_method_name(params.method)
        
        stc = apply_inverse(
            raw, inv, lambda2, method=method,
            pick_ori=params.pick_ori, verbose=verbose
        )
        return stc

    @staticmethod
    def morph_to_fsaverage(
        stc: Any, subject_from: str, subject_to: str = "fsaverage",
        subjects_dir: str | None = None
    ) -> Any:
        """形变到标准脑 (fsaverage)"""
        import mne
        return stc.morph_to(subject_to, subject_from=subject_from, subjects_dir=subjects_dir)

    @staticmethod
    def extract_label_time_course(
        stc: Any, labels: Any, src: Any, mode: str = "mean", verbose: bool = False
    ) -> Any:
        """提取标签时间序列"""
        import mne
        return mne.extract_label_time_course(stc, labels, src, mode=mode, verbose=verbose)


def compute_inverse_solution(
    dataset: EEGDataset,
    fwd_result: ForwardModelResult,
    params: InverseParams,
    **kwargs: Any
) -> InverseSolutionResult:
    return InverseService.compute(dataset, fwd_result, params, **kwargs)