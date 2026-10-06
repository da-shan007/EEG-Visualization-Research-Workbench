"""ERD/ERS 事件相关去同步/同步分析服务"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import time
import numpy as np

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.erp import ERDSParams, EpochParams, ERDSResult, BaselineMode
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class ERDSAnalysisResult:
    """ERD/ERS 分析结果"""
    result: ERDSResult
    processing_time_ms: float
    params_used: ERDSParams


class ERDSService:
    """ERD/ERS 分析服务"""

    @staticmethod
    def analyze(
        dataset: EEGDataset,
        params: ERDSParams,
        *,
        verbose: bool = False
    ) -> ERDSAnalysisResult:
        """执行 ERD/ERS 分析"""
        start_time = time.perf_counter()

        try:
            import mne
            from mne.time_frequency import tfr_morlet, tfr_multitaper, tfr_stockwell
        except ImportError:
            raise RuntimeError("ERD/ERS 分析需要 MNE: pip install mne")

        raw = dataset.to_mne_raw()
        epochs_dict = {}
        tfrs = {}

        # 1. 提取每个条件的 Epochs
        for cond_name, ep_params in params.conditions.items():
            events, event_id = ERDSService._find_events(raw, ep_params)
            if len(events) == 0:
                print(f"警告: 条件 {cond_name} 未找到匹配事件")
                continue

            epochs = mne.Epochs(
                raw, events, event_id=event_id,
                tmin=ep_params.tmin, tmax=ep_params.tmax,
                baseline=ep_params.baseline if ep_params.baseline else None,
                reject=ep_params.reject,
                preload=True,
                verbose=False
            )
            epochs_dict[cond_name] = epochs

        if not epochs_dict:
            raise ValueError("未提取到任何 Epochs")

        # 2. 计算时频图
        freq_list: list[float] = []
        for fmin, fmax in params.bands.values():
            band_freqs = np.linspace(fmin, fmax, max(5, int((fmax - fmin) / 2)))
            freq_list.extend(float(f) for f in band_freqs)
        freqs = np.unique(freq_list)

        for cond_name, epochs in epochs_dict.items():
            if params.tf_method == "morlet":
                n_cycles = params.n_cycles
                if isinstance(n_cycles, (int, float)):
                    n_cycles = freqs / freqs[0] * n_cycles
                tfr = tfr_morlet(
                    epochs, freqs=freqs, n_cycles=n_cycles,
                    return_itc=False, average=False, verbose=False
                )
            elif params.tf_method == "multitaper":
                tfr = tfr_multitaper(
                    epochs, freqs=freqs, time_bandwidth=4.0,
                    return_itc=False, average=False, verbose=False
                )
            else:
                raise ValueError(f"不支持的时频方法: {params.tf_method}")

            # 基线校正
            if params.baseline:
                tfr.apply_baseline(
                    baseline=params.baseline,
                    mode=params.baseline_mode.value,
                    verbose=False
                )

            tfrs[cond_name] = tfr

        # 3. 计算平均 TFR
        avg_tfrs = {cond: tfr.average() for cond, tfr in tfrs.items()}

        # 3. 计算差分 TFR
        contrast_tfrs = {}
        cond_names = list(tfrs.keys())
        for i, cond_a in enumerate(cond_names):
            for cond_b in cond_names[i+1:]:
                contrast = avg_tfrs[cond_a].copy().subtract(avg_tfrs[cond_b])
                contrast_tfrs[f"{cond_a}-{cond_b}"] = contrast

        # 4. 频段平均 ERD/ERS
        band_erds = ERDSService._compute_band_erds(avg_tfrs, params.bands)

        # 5. 统计检验
        stats = {}
        if params.stats_test != "none" and len(tfrs) >= 2:
            stats = ERDSService._statistical_test(tfrs, params)

        # 构建结果
        result = ERDSResult(
            tfrs=tfrs,
            avg_tfrs=avg_tfrs,
            contrast_tfrs=contrast_tfrs,
            stats=stats,
            band_erds=band_erds,
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=dataset.id,
                step="erds_analysis",
                params={"bands": list(params.bands.keys()), "conditions": list(tfrs.keys())}
            ),
            source="ERDSService"
        )

        return ERDSAnalysisResult(
            result=result,
            processing_time_ms=elapsed,
            params_used=params
        )

    @staticmethod
    def _find_events(raw: Any, ep_params: EpochParams) -> tuple[np.ndarray, dict[str, Any]]:
        import mne
        events, event_id = mne.events_from_annotations(raw)
        
        if ep_params.event_descriptions:
            matched_events = []
            matched_ids = {}
            for desc, code in event_id.items():
                for target in ep_params.event_descriptions:
                    if target in desc or desc in target:
                        matched_ids[desc] = code
                        matched_events.append(events[events[:, 2] == code])
            if matched_events:
                events = np.vstack(matched_events)
                event_id = matched_ids
        
        return events, event_id

    @staticmethod
    def _compute_band_erds(
        avg_tfrs: dict[str, Any], bands: dict[str, tuple[float, float]]
    ) -> dict[str, dict[str, np.ndarray]]:
        """计算各频段的平均 ERD/ERS"""
        band_erds: dict[str, dict[str, np.ndarray]] = {}
        
        for cond_name, tfr in avg_tfrs.items():
            band_erds[cond_name] = {}
            tfr_data = tfr.data  # (n_channels, n_freqs, n_times)
            tfr_freqs = tfr.freqs
            tfr_times = tfr.times
            
            for band_name, (fmin, fmax) in bands.items():
                freq_mask = (tfr_freqs >= fmin) & (tfr_freqs <= fmax)
                if not np.any(freq_mask):
                    continue
                
                # 频段内平均
                band_data = tfr_data[:, freq_mask, :]
                band_avg = np.mean(band_data, axis=1)  # (n_channels, n_times)
                band_erds[cond_name][band_name] = band_avg
        
        return band_erds

    @staticmethod
    def _statistical_test(tfrs: dict[str, Any], params: ERDSParams) -> dict[str, Any]:
        """统计检验"""
        stats: dict[str, Any] = {}
        
        if params.stats_test == "permutation":
            try:
                from mne.stats import permutation_cluster_test
                # 简化：只做两条件对比
                cond_names = list(tfrs.keys())
                if len(cond_names) >= 2:
                    # 这里需要 (n_subjects, n_channels, n_freqs, n_times) 格式
                    # 简化处理
                    pass
            except ImportError:
                pass
        
        return stats


def run_erds_analysis(
    dataset: EEGDataset,
    params: ERDSParams,
    **kwargs: Any
) -> ERDSAnalysisResult:
    return ERDSService.analyze(dataset, params, **kwargs)