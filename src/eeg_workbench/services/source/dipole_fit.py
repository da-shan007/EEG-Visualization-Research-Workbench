"""偶极子拟合服务：等效电流偶极子拟合 (ECD)"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np
from scipy.optimize import minimize, differential_evolution

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.source import DipoleFitParams
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class DipoleFitResult:
    dipoles: list[dict[str, Any]]
    processing_time_ms: float
    params_used: DipoleFitParams


class DipoleFitService:
    @staticmethod
    def fit(
        dataset: EEGDataset,
        params: DipoleFitParams,
        *,
        verbose: bool = False
    ) -> DipoleFitResult:
        start_time = time.perf_counter()

        try:
            import mne
        except ImportError:
            raise RuntimeError("偶极子拟合需要 MNE: pip install mne")

        raw = dataset.to_mne_raw()
        tmin = params.tmin if params.tmin is not None else 0
        tmax = params.tmax if params.tmax is not None else raw.times[-1]
        raw_crop = raw.copy().crop(tmin, tmax)

        if params.initial_pos is not None:
            initial_pos = params.initial_pos
        else:
            initial_pos = DipoleFitService._auto_initial_guess(raw_crop)

        if params.method == "differential_evolution":
            dipoles = DipoleFitService._fit_differential_evolution(raw_crop, params, initial_pos, verbose)
        elif params.method == "nelder_mead":
            dipoles = DipoleFitService._fit_nelder_mead(raw_crop, params, initial_pos, verbose)
        else:
            dipoles = DipoleFitService._fit_least_squares(raw_crop, params, initial_pos, verbose)

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="dipole_fit",
                params={"n_dipoles": len(dipoles), "method": params.method}
            ),
            source="DipoleFitService"
        )

        return DipoleFitResult(dipoles=dipoles, processing_time_ms=elapsed, params_used=params)

    @staticmethod
    def _auto_initial_guess(raw: Any) -> np.ndarray:
        try:
            import mne
            guess = mne.fit_dipole._initial_guess(raw.info)
            return np.asarray(guess, dtype=float)
        except:
            return np.array([0.0, 0.0, 0.04])

    @staticmethod
    def _fit_least_squares(raw: Any, params: DipoleFitParams, initial_pos: np.ndarray, verbose: bool) -> list[dict[str, Any]]:
        import mne
        dipoles, _ = mne.fit_dipole(raw, covariance=None, bem=None, trans=None, verbose=verbose)
        return DipoleFitService._convert_mne_dipoles(dipoles)

    @staticmethod
    def _fit_nelder_mead(raw: Any, params: DipoleFitParams, initial_pos: np.ndarray, verbose: bool) -> list[dict[str, Any]]:
        from scipy.optimize import minimize
        
        def objective(x: np.ndarray) -> Any:
            pos = x[:3]
            ori = x[3:6] / (np.linalg.norm(x[3:6]) + 1e-12)
            amp = x[6]
            predicted = DipoleFitService._dipole_field(pos, ori, amp, raw.info)
            data = raw.get_data()
            return np.sum((data - predicted) ** 2)
        
        x0 = np.concatenate([initial_pos, [1, 0, 0], [10e-9]])
        bounds = params.pos_bounds or [
            (-0.1, 0.1), (-0.1, 0.1), (0, 0.15),
            (-1, 1), (-1, 1), (-1, 1),
            (0, 100e-9)
        ]
        
        result = minimize(objective, x0, method="Nelder-Mead", bounds=bounds, options={"maxiter": 1000})
        return DipoleFitService._extract_dipoles_from_result(result, raw.times, raw)

    @staticmethod
    def _fit_differential_evolution(raw: Any, params: DipoleFitParams, initial_pos: np.ndarray, verbose: bool) -> list[dict[str, Any]]:
        from scipy.optimize import differential_evolution
        
        def objective(x: np.ndarray) -> Any:
            pos = x[:3]
            ori = x[3:6] / (np.linalg.norm(x[3:6]) + 1e-12)
            amp = x[6]
            predicted = DipoleFitService._dipole_field(pos, ori, amp, raw.info)
            data = raw.get_data()
            return np.sum((data - predicted) ** 2)
        
        bounds = params.pos_bounds or [
            (-0.1, 0.1), (-0.1, 0.1), (0, 0.15),
            (-1, 1), (-1, 1), (-1, 1),
            (0, 100e-9)
        ]
        
        result = differential_evolution(objective, bounds, maxiter=100, popsize=15, atol=1e-6, seed=42)
        return DipoleFitService._extract_dipoles_from_result(result, raw.times, raw)

    @staticmethod
    def _dipole_field(pos: np.ndarray, ori: np.ndarray, amp: float, info: Any) -> np.ndarray:
        # 简化实现，实际应使用 MNE forward 模块
        return np.zeros((len(info["ch_names"]), 100))

    @staticmethod
    def _convert_mne_dipoles(mne_dipoles: Any) -> list[dict[str, Any]]:
        dipoles = []
        for dip in mne_dipoles:
            dipoles.append({
                "pos": dip.pos, "ori": dip.ori, "amplitude": dip.amplitude,
                "gof": dip.gof, "time": dip.times[dip.gof.argmax()] if hasattr(dip, 'times') else 0,
            })
        return dipoles

    @staticmethod
    def _extract_dipoles_from_result(result: Any, times: Any, raw: Any = None) -> list[dict[str, Any]]:
        x = result.x
        if raw is not None:
            # 残差相对信号方差 -> goodness-of-fit (0~1，越接近 1 越好)
            var = float(np.var(raw.get_data()))
            gof = float(1.0 - result.fun / var) if var > 0 else 0.0
        else:
            gof = 0.0
        return [{
            "pos": x[:3],
            "ori": x[3:6] / (np.linalg.norm(x[3:6]) + 1e-12),
            "amplitude": x[6],
            "gof": gof,
            "time": times[len(times)//2],
            "success": result.success,
            "message": result.message
        }]


def fit_dipoles(dataset: EEGDataset, params: DipoleFitParams, **kwargs: Any) -> DipoleFitResult:
    return DipoleFitService.fit(dataset, params, **kwargs)