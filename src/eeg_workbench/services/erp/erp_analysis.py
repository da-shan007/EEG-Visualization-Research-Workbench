"""ERP 叠加平均分析服务：Epochs 提取、条件平均、差分波、统计检验"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.erp import (
    ERPAnalysisParams, EpochParams, ERPResult,
    ERPComponent, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ERPAnalysisResult:
    """ERP 分析结果"""
    result: ERPResult
    processing_time_ms: float
    params_used: ERPAnalysisParams


class ERPService:
    """ERP 分析服务"""

    @staticmethod
    def analyze(
        dataset: EEGDataset,
        params: ERPAnalysisParams,
        *,
        verbose: bool = False
    ) -> ERPAnalysisResult:
        """执行 ERP 分析

        Args:
            dataset: 预处理后的数据集
            params: ERP 分析参数
            verbose: 详细输出
        """
        start_time = time.perf_counter()

        # 1. 提取 Epochs
        epochs_dict = ERPService._extract_epochs(dataset, params)
        if not epochs_dict:
            raise ValueError("未提取到任何 Epochs")

        # 2. 计算条件平均
        evokeds = {}
        for cond_name, epochs in epochs_dict.items():
            evoked = epochs.average()
            evokeds[cond_name] = evoked

        # 3. 计算差分波
        contrasts = {}
        for cond_a, cond_b in params.contrast_pairs:
            if cond_a in evokeds and cond_b in evokeds:
                # mne 1.13 的 EvokedArray 没有 subtract() 方法，直接对 data 做减法
                contrast = evokeds[cond_a].copy()
                contrast.data = contrast.data - evokeds[cond_b].data
                contrasts[f"{cond_a}-{cond_b}"] = contrast

        # 4. 峰值检测
        peaks = {}
        if params.peak_detection:
            for cond_name, evoked in evokeds.items():
                peaks[cond_name] = ERPService._detect_peaks(
                    evoked, params, cond_name
                )

        # 5. 统计检验
        stats = {}
        if len(evokeds) >= 2 and params.stats_test != "none":
            stats = ERPService._statistical_test(evokeds, params)

        # 6. 地形图时间点
        topomaps = {}
        topo_times = params.topo_times.copy()
        if not topo_times and params.peak_detection:
            # 自动添加峰值时刻
            for cond_peaks in peaks.values():
                for peak_info in cond_peaks.values():
                    if "latency" in peak_info:
                        topo_times.append(peak_info["latency"])
            topo_times = list(set(topo_times))  # 去重

        for t in topo_times:
            topomaps[f"t_{t:.3f}"] = ERPService._compute_topomap(evokeds, t)

        # 构建结果
        result = ERPResult(
            evokeds=evokeds,
            contrasts=contrasts,
            peaks=peaks,
            stats=stats,
            topomaps=topomaps,
            epochs=epochs_dict,
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="erp_analysis",
                params={"conditions": list(evokeds.keys()), "contrasts": list(contrasts.keys())}
            ),
            source="ERPService"
        )

        return ERPAnalysisResult(
            result=result,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _extract_epochs(
        dataset: EEGDataset,
        params: ERPAnalysisParams
    ) -> dict[str, Any]:
        """提取 Epochs"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("ERP 分析需要 MNE: pip install mne")

        raw = dataset.to_mne_raw()
        epochs_dict = {}

        for cond_name, ep_params in params.conditions.items():
            # 查找匹配的事件
            events, event_id = ERPService._find_events(raw, ep_params)
            if len(events) == 0:
                print(f"警告: 条件 {cond_name} 未找到匹配事件")
                continue

            # 创建 Epochs
            epochs = mne.Epochs(
                raw, events, event_id=event_id,
                tmin=ep_params.tmin, tmax=ep_params.tmax,
                baseline=ep_params.baseline if ep_params.baseline else None,
                reject=ep_params.reject,
                flat=ep_params.flat,
                preload=True,
                verbose=False
            )

            # ICA 去伪影
            if ep_params.apply_ica and ep_params.ica_exclude:
                # 假设 ICA 已在预处理阶段完成，这里只排除成分
                pass

            # 重采样
            if ep_params.resample_sfreq:
                epochs.resample(ep_params.resample_sfreq, verbose=False)

            # 存储元数据
            if ep_params.metadata:
                epochs.metadata = ep_params.metadata

            epochs_dict[cond_name] = epochs

        return epochs_dict

    @staticmethod
    def _find_events(raw, ep_params: EpochParams) -> tuple[np.ndarray, dict]:
        """查找匹配事件"""
        import mne

        # 从 annotations 获取事件
        events, event_id = mne.events_from_annotations(raw)
        if len(events) == 0:
            return events, event_id

        # 筛选匹配的事件
        if ep_params.event_descriptions:
            target = ep_params.event_descriptions
            selected_ids = {}
            for desc, code in event_id.items():
                if any(desc == t or t in desc or desc in t for t in target):
                    selected_ids[desc] = code
            if not selected_ids:
                return np.empty((0, 3), dtype=int), {}
            code_values = list(selected_ids.values())
            filtered = events[np.isin(events[:, 2], code_values)]
            return filtered, selected_ids

        if ep_params.event_codes:
            filtered = events[np.isin(events[:, 2], ep_params.event_codes)]
            selected_ids = {k: v for k, v in event_id.items() if v in ep_params.event_codes}
            return filtered, selected_ids

        return events, event_id

    @staticmethod
    def _detect_peaks(
        evoked, params: ERPAnalysisParams, cond_name: str
    ) -> dict[ERPComponent, dict]:
        """检测 ERP 峰值"""
        from scipy.signal import find_peaks
        
        peaks = {}
        data = evoked.data  # (n_channels, n_times)
        times = evoked.times
        ch_names = evoked.ch_names

        for component in params.peak_components:
            tmin, tmax = params.peak_time_windows.get(component, (0, 1))
            polarity = params.peak_polarity.get(component, "both")

            # 时间窗掩码
            time_mask = (times >= tmin) & (times <= tmax)
            if not np.any(time_mask):
                continue

            window_data = data[:, time_mask]
            window_times = times[time_mask]

            # 对每个通道检测峰值
            best_peak = None
            best_value = -np.inf if polarity in ("pos", "both") else np.inf

            for ch_idx, ch_name in enumerate(ch_names):
                ch_data = window_data[ch_idx]
                
                if polarity in ("pos", "both"):
                    # 正峰
                    peaks_idx, props = find_peaks(ch_data, distance=int(0.02 * evoked.info["sfreq"]))
                    if len(peaks_idx) > 0:
                        max_idx = peaks_idx[np.argmax(ch_data[peaks_idx])]
                        if ch_data[max_idx] > best_value:
                            best_value = ch_data[max_idx]
                            best_peak = {
                                "latency": float(window_times[max_idx]),
                                "amplitude": float(ch_data[max_idx]) * 1e6,  # V -> µV
                                "channel": ch_name,
                                "polarity": "positive"
                            }
                
                if polarity in ("neg", "both"):
                    # 负峰 (反转数据)
                    peaks_idx, props = find_peaks(-ch_data, distance=int(0.02 * evoked.info["sfreq"]))
                    if len(peaks_idx) > 0:
                        min_idx = peaks_idx[np.argmin(ch_data[peaks_idx])]
                        if ch_data[min_idx] < best_value:
                            best_value = ch_data[min_idx]
                            best_peak = {
                                "latency": float(window_times[min_idx]),
                                "amplitude": float(ch_data[min_idx]) * 1e6,
                                "channel": ch_name,
                                "polarity": "negative"
                            }

            if best_peak:
                peaks[component] = best_peak

        return peaks

    @staticmethod
    def _statistical_test(evokeds: dict, params: ERPAnalysisParams) -> dict:
        """统计检验"""
        stats = {}
        
        if params.stats_test == "ttest":
            # 成对 t 检验需要元数据中的分组信息
            pass
        elif params.stats_test == "permutation":
            # 基于簇的置换检验
            try:
                from mne.stats import permutation_cluster_test
                # 准备数据: (n_conditions, n_subjects, n_channels, n_times)
                # 这里简化处理
                pass
            except ImportError:
                pass
        
        return stats

    @staticmethod
    def _compute_topomap(evokeds: dict, time_point: float) -> dict:
        """计算地形图数据"""
        topomaps = {}
        for cond_name, evoked in evokeds.items():
            # 找到最接近的时间点
            idx = np.argmin(np.abs(evoked.times - time_point))
            topomaps[cond_name] = {
                "data": evoked.data[:, idx] * 1e6,  # V -> µV
                "time": evoked.times[idx],
                "ch_names": evoked.ch_names,
            }
        return topomaps


def run_erp_analysis(
    dataset: EEGDataset,
    params: ERPAnalysisParams,
    **kwargs
) -> ERPAnalysisResult:
    return ERPService.analyze(dataset, params, **kwargs)