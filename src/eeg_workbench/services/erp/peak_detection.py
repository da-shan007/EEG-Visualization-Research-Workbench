"""ERP 峰值检测服务"""
from __future__ import annotations
from typing import Any, Optional
import numpy as np
from scipy.signal import find_peaks

from eeg_workbench.models.erp import (
    ERPComponent, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY,
    PeakPolarity, PeakResult,
)


class PeakDetector:
    """ERP 峰值检测器"""

    def __init__(
        self,
        peak_windows: dict[ERPComponent, tuple[float, float]] | None = None,
        polarities: dict[ERPComponent, PeakPolarity] | None = None,
        min_peak_distance: float = 0.02  # 秒
    ) -> None:
        self.peak_windows = peak_windows or DEFAULT_ERP_PEAK_WINDOWS
        self.polarities = polarities or DEFAULT_ERP_POLARITY
        self.min_peak_distance = min_peak_distance

    def detect(
        self,
        evoked: Any,
        components: list[ERPComponent] | None = None
    ) -> dict[ERPComponent, PeakResult]:
        """检测 ERP 峰值

        Args:
            evoked: MNE Evoked 对象
            components: 要检测的成分列表，None 表示检测所有
        """
        if components is None:
            components = list(self.peak_windows.keys())

        results = {}
        data = evoked.data * 1e6  # V -> µV
        times = evoked.times
        ch_names = evoked.ch_names
        sfreq = evoked.info["sfreq"]
        min_dist_samples = int(self.min_peak_distance * sfreq)

        for component in components:
            result = self._detect_component(evoked, data, times, ch_names, component, min_dist_samples)
            if result:
                results[component] = result

        return results

    def _detect_component(
        self,
        evoked: Any,
        data: np.ndarray,  # (n_ch, n_times) µV
        times: np.ndarray,
        ch_names: list[str],
        component: ERPComponent,
        min_dist_samples: int
    ) -> Optional[PeakResult]:
        tmin, tmax = self.peak_windows.get(component, (0, 1))
        polarity = self.polarities.get(component, "both")

        time_mask = (times >= tmin) & (times <= tmax)
        if not np.any(time_mask):
            return None

        window_data = data[:, time_mask]
        window_times = times[time_mask]

        all_candidates = []
        best_peak = None
        best_value = -np.inf if polarity in ("pos", "both") else np.inf

        for ch_idx, ch_name in enumerate(ch_names):
            ch_data = window_data[ch_idx]

            if polarity in ("pos", "both"):
                # 正峰
                peaks_idx, props = find_peaks(
                    ch_data, distance=min_dist_samples, prominence=0.5
                )
                for p_idx in peaks_idx:
                    candidate = {
                        "latency": float(window_times[p_idx]),
                        "amplitude": float(ch_data[p_idx]),
                        "channel": ch_name,
                        "polarity": "positive",
                        "prominence": props.get("prominences", [0])[0] if "prominences" in props else 0
                    }
                    all_candidates.append(candidate)
                    if ch_data[p_idx] > best_value:
                        best_value = ch_data[p_idx]
                        best_peak = PeakResult(
                            component=component,
                            latency=float(candidate["latency"]),
                            amplitude=float(candidate["amplitude"]),
                            channel=str(candidate["channel"]),
                            polarity="positive",
                            time_window=(tmin, tmax),
                            all_candidates=all_candidates
                        )

            if polarity in ("neg", "both"):
                # 负峰
                peaks_idx, props = find_peaks(
                    -ch_data, distance=min_dist_samples, prominence=0.5
                )
                for p_idx in peaks_idx:
                    candidate = {
                        "latency": float(window_times[p_idx]),
                        "amplitude": float(ch_data[p_idx]),
                        "channel": ch_name,
                        "polarity": "negative",
                        "prominence": props.get("prominences", [0])[0] if "prominences" in props else 0
                    }
                    all_candidates.append(candidate)
                    if ch_data[p_idx] < best_value:
                        best_value = ch_data[p_idx]
                        best_peak = PeakResult(
                            component=component,
                            latency=float(candidate["latency"]),
                            amplitude=float(candidate["amplitude"]),
                            channel=str(candidate["channel"]),
                            polarity="negative",
                            time_window=(tmin, tmax),
                            all_candidates=all_candidates
                        )

        return best_peak

    def detect_custom(
        self,
        evoked: Any,
        time_window: tuple[float, float],
        polarity: PeakPolarity = "both",
        component_name: str = "custom"
    ) -> Optional[PeakResult]:
        """自定义时间窗口峰值检测"""
        from eeg_workbench.models.erp import ERPComponent
        custom_comp = ERPComponent.CUSTOM
        original_window = self.peak_windows.get(custom_comp)
        original_polarity = self.polarities.get(custom_comp)

        self.peak_windows[custom_comp] = time_window
        self.polarities[custom_comp] = polarity

        result = self._detect_component(
            evoked,
            evoked.data * 1e6,
            evoked.times,
            evoked.ch_names,
            custom_comp,
            int(0.02 * evoked.info["sfreq"])
        )

        # 恢复
        if original_window:
            self.peak_windows[custom_comp] = original_window
        else:
            del self.peak_windows[custom_comp]
        if original_polarity:
            self.polarities[custom_comp] = original_polarity
        else:
            del self.polarities[custom_comp]

        if result:
            result.component = ERPComponent.CUSTOM
        return result

    def batch_detect(
        self,
        evokeds: dict[str, Any],
        components: list[ERPComponent] | None = None
    ) -> dict[str, dict[ERPComponent, PeakResult]]:
        """批量检测多条件"""
        results = {}
        for cond_name, evoked in evokeds.items():
            results[cond_name] = self.detect(evoked, components)
        return results


def detect_erp_peaks(
    evoked: Any,
    components: list[ERPComponent] | None = None,
    **kwargs: Any
) -> dict[ERPComponent, PeakResult]:
    """函数式接口"""
    detector = PeakDetector(**kwargs)
    return detector.detect(evoked, components)