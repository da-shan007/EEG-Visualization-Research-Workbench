"""ICA 服务：独立成分分析、自动伪影识别、成分排除"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Optional
import time
import numpy as np
from copy import deepcopy

from eeg_workbench.models.dataset import EEGDataset, Event
from eeg_workbench.models.preprocessing import ICAParams, ICAComponentType
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload, ProgressPayload


@dataclass
class ICAResult:
    """ICA 结果"""
    dataset: EEGDataset                    # 已应用 ICA 的数据集
    ica: Any                               # MNE ICA 对象
    params_used: ICAParams
    processing_time_ms: float
    components_excluded: list[int] = field(default_factory=list)
    component_labels: dict[int, str] = field(default_factory=dict)  # 成分 -> 标签
    component_properties: dict[int, dict[str, Any]] = field(default_factory=dict)  # 成分属性


class ICAService:
    """ICA 服务：拟合、自动识别、应用"""

    def __init__(self) -> None:
        self._ica: Any = None
        self._labels: dict[int, str] = {}
        self._properties: dict[int, dict[str, Any]] = {}

    def fit(
        self,
        dataset: EEGDataset,
        params: ICAParams,
        *,
        picks: list[int] | str | None = None,
        verbose: bool = False
    ) -> ICAResult:
        """拟合 ICA"""
        start_time = time.perf_counter()

        raw = dataset.to_mne_raw(copy=True)

        # 选择通道
        if picks is None:
            picks = "eeg"

        # 创建 ICA 对象
        from mne.preprocessing import ICA
        # mne 1.13 的 ICA.__init__ 没有 tol 参数；fastica 的收敛容差经 fit_params 传入
        fit_params = {"tol": params.tol} if params.method == "fastica" else None
        ica = ICA(
            n_components=params.n_components,
            method=params.method,
            random_state=params.random_state,
            max_iter=params.max_iter,
            fit_params=fit_params,
            verbose=verbose
        )

        # 发布进度
        get_event_bus().publish(
            EventType.PROGRESS_UPDATE,
            ProgressPayload(task="ICA拟合", current=0, total=100, message="正在拟合 ICA..."),
            source="ICAService"
        )

        # 拟合 (可选降采样加速)
        if params.decim > 1:
            ica.fit(raw, picks=picks, decim=params.decim, reject=params.reject, verbose=verbose)
        else:
            ica.fit(raw, picks=picks, reject=params.reject, verbose=verbose)

        get_event_bus().publish(
            EventType.PROGRESS_UPDATE,
            ProgressPayload(task="ICA拟合", current=50, total=100, message="ICA 拟合完成，正在识别伪影..."),
            source="ICAService"
        )

        # 自动识别伪影成分
        excluded: list[int] = []
        labels: dict[int, str] = {}
        properties: dict[int, dict[str, Any]] = {}

        if params.auto_find:
            excluded, labels, properties = self._auto_identify_artifacts(
                ica, raw, params, picks, verbose
            )

        get_event_bus().publish(
            EventType.PROGRESS_UPDATE,
            ProgressPayload(task="ICA拟合", current=100, total=100, message="ICA 完成"),
            source="ICAService"
        )

        self._ica = ica
        self._labels = labels
        self._properties = properties

        elapsed = (time.perf_counter() - start_time) * 1000

        # 注意：fit 只返回 ICA 对象和识别结果，不修改数据
        # 实际应用由 apply 方法完成
        return ICAResult(
            dataset=dataset,  # 未修改
            ica=ica,
            params_used=params,
            processing_time_ms=elapsed,
            components_excluded=excluded,
            component_labels=labels,
            component_properties=properties
        )

    def apply(
        self,
        dataset: EEGDataset,
        ica_result: ICAResult,
        *,
        exclude: list[int] | None = None,
        copy: bool = True,
        verbose: bool = False
    ) -> ICAResult:
        """应用 ICA (排除指定成分)"""
        start_time = time.perf_counter()

        if ica_result.ica is None:
            raise ValueError("ICAResult 中没有 ICA 对象，请先调用 fit()")

        raw = dataset.to_mne_raw(copy=copy)
        ica = ica_result.ica

        # 确定要排除的成分
        if exclude is None:
            exclude = ica_result.components_excluded

        # 应用 ICA
        ica.apply(raw, exclude=exclude, verbose=verbose)

        # 转回 EEGDataset
        new_dataset = EEGDataset.from_mne_raw(
            raw,
            name=f"{dataset.name}_ica_cleaned",
            file_path=dataset.file_path
        )

        new_dataset = replace(
            new_dataset,
            id=dataset.id,
            metadata=dataset.metadata,
            events=dataset.events,
            annotations=dataset.annotations,
            montage=dataset.montage,
            processing_history=dataset.processing_history + [{
                "step": "ica_apply",
                "params": {
                    "exclude": exclude,
                    "n_components": ica_result.ica.n_components_,
                    "method": ica_result.ica.method,
                },
                "duration_ms": (time.perf_counter() - start_time) * 1000,
                "input_shape": (dataset.n_channels, dataset.n_samples),
                "output_shape": (new_dataset.n_channels, new_dataset.n_samples),
            }]
        )

        elapsed = (time.perf_counter() - start_time) * 1000

        get_event_bus().publish(
            EventType.PREPROCESSING_FINISHED,
            PreprocessingPayload(
                dataset_id=new_dataset.id,
                step="ica",
                params={"exclude": exclude, "n_components": ica_result.ica.n_components_}
            ),
            source="ICAService"
        )

        return ICAResult(
            dataset=new_dataset,
            ica=ica,
            params_used=ica_result.params_used,
            processing_time_ms=elapsed,
            components_excluded=exclude,
            component_labels=ica_result.component_labels,
            component_properties=ica_result.component_properties
        )

    def fit_apply(
        self,
        dataset: EEGDataset,
        params: ICAParams,
        **kwargs: Any
    ) -> ICAResult:
        """一步完成：拟合 + 应用"""
        result = self.fit(dataset, params, **kwargs)
        return self.apply(dataset, result, **kwargs)

    def _auto_identify_artifacts(
        self,
        ica: Any,
        raw: Any,
        params: ICAParams,
        picks: list[int] | str | None,
        verbose: bool
    ) -> tuple[list[int], dict[int, str], dict[int, dict[str, Any]]]:
        """自动识别伪影成分"""
        excluded = []
        labels = {}
        properties = {}

        # 获取成分时间序列（一次计算，供全部成分复用；mne 1.13:
        # get_sources(inst, add_channels, start, stop)，无 picks 参数；
        # 成分所用通道在 ica.fit(picks=...) 时已确定）
        sources = ica.get_sources(raw)
        source_data = sources.get_data()  # (n_components, n_times)

        # 参考信号一次加载（EOG/ECG），避免逐成分重复 get_data
        eog_ref = self._load_ref_signal(raw, params.eog_channels) if params.eog_channels else None
        ecg_ref = self._load_ref_signal(raw, params.ecg_channels) if params.ecg_channels else None
        # 全部成分与参考信号的相关系数，一次向量化算完
        eog_corrs = self._corr_all_with_ref(source_data, eog_ref) if eog_ref is not None else None
        ecg_corrs = self._corr_all_with_ref(source_data, ecg_ref) if ecg_ref is not None else None

        # 频率特征分析
        from scipy import signal
        sfreq = raw.info["sfreq"]
        n_components = ica.n_components_

        # 计算每个成分的频谱特征
        freqs, psd = signal.welch(source_data, sfreq, nperseg=min(256, source_data.shape[1]//4))

        for comp_idx in range(n_components):
            comp_label = ICAComponentType.UNKNOWN
            comp_props = {"psd": psd[comp_idx].tolist(), "freqs": freqs.tolist()}

            # 1. EOG 相关性检测（查表：已向量化预计算）
            if eog_corrs is not None:
                eog_corr = float(eog_corrs[comp_idx])
                comp_props["eog_correlation"] = eog_corr
                if abs(eog_corr) > params.eog_threshold:
                    comp_label = ICAComponentType.EYE_BLINK if eog_corr > 0 else ICAComponentType.EYE_MOVEMENT
                    excluded.append(comp_idx)

            # 2. ECG 相关性检测（查表：已向量化预计算）
            if ecg_corrs is not None:
                ecg_corr = float(ecg_corrs[comp_idx])
                comp_props["ecg_correlation"] = ecg_corr
                if abs(ecg_corr) > params.ecg_threshold and comp_label == ICAComponentType.UNKNOWN:
                    comp_label = ICAComponentType.HEARTBEAT
                    excluded.append(comp_idx)

            # 3. 肌肉成分检测 (高频功率 > 阈值)
            high_freq_power = np.mean(psd[comp_idx][freqs > 30])
            total_power = np.mean(psd[comp_idx])
            muscle_ratio = high_freq_power / total_power if total_power > 0 else 0
            comp_props["muscle_ratio"] = muscle_ratio
            if muscle_ratio > params.muscle_threshold and comp_label == ICAComponentType.UNKNOWN:
                comp_label = ICAComponentType.MUSCLE
                excluded.append(comp_idx)

            # 4. 工频干扰检测
            line_freq = 50.0  # 假设 50Hz
            line_idx = np.argmin(np.abs(freqs - line_freq))
            line_power = psd[comp_idx][line_idx]
            comp_props["line_power"] = float(line_power)
            if line_power > np.percentile(psd[comp_idx], 99) and comp_label == ICAComponentType.UNKNOWN:
                comp_label = ICAComponentType.LINE_NOISE
                excluded.append(comp_idx)

            labels[comp_idx] = comp_label.value
            properties[comp_idx] = comp_props

        return excluded, labels, properties

    @staticmethod
    def _load_ref_signal(raw: Any, channels: list[str]) -> np.ndarray | None:
        """一次加载参考通道并平均，找不到有效通道返回 None。"""
        try:
            present = [ch for ch in channels if ch in raw.ch_names]
            if not present:
                return None
            data = raw.get_data(picks=present)
            combined = np.mean(data, axis=0)
            if not np.all(np.isfinite(combined)) or np.std(combined) == 0:
                return None
            return combined
        except Exception:
            return None

    @staticmethod
    def _corr_all_with_ref(source_data: np.ndarray, ref: np.ndarray) -> np.ndarray:
        """全部成分与参考信号的 Pearson 相关系数（一次向量化计算）。

        等价于对每个成分逐一 np.corrcoef，但只做一次矩阵乘法；
        常数/NaN 通道对应位置返回 0.0。
        """
        X = np.vstack([np.asarray(source_data, dtype=float), np.asarray(ref, dtype=float)[None, :]])
        X = X - X.mean(axis=1, keepdims=True)
        denom = np.sqrt((X ** 2).sum(axis=1))
        denom[denom == 0] = np.nan
        with np.errstate(invalid="ignore"):
            corrs = (X[:-1] @ X[-1]) / (denom[:-1] * denom[-1])
        return np.where(np.isnan(corrs), 0.0, corrs)

    def _compute_eog_correlation(self, ica: Any, raw: Any, comp_idx: int, eog_channels: list[str]) -> float:
        """计算成分与 EOG 通道的相关性（保留单成分接口，内部复用向量化实现）。"""
        try:
            source_data = ica.get_sources(raw).get_data()
            ref = self._load_ref_signal(raw, eog_channels)
            if ref is None:
                return 0.0
            return float(self._corr_all_with_ref(source_data, ref)[comp_idx])
        except Exception:
            return 0.0

    def _compute_ecg_correlation(self, ica: Any, raw: Any, comp_idx: int, ecg_channels: list[str]) -> float:
        """计算成分与 ECG 通道的相关性（保留单成分接口，内部复用向量化实现）。"""
        try:
            source_data = ica.get_sources(raw).get_data()
            ref = self._load_ref_signal(raw, ecg_channels)
            if ref is None:
                return 0.0
            return float(self._corr_all_with_ref(source_data, ref)[comp_idx])
        except Exception:
            return 0.0

    def get_ica_object(self) -> Any:
        """获取 MNE ICA 对象 (用于可视化)"""
        return self._ica

    def get_component_labels(self) -> dict[int, str]:
        return self._labels.copy()

    def get_component_properties(self) -> dict[int, dict[str, Any]]:
        return self._properties.copy()

    def plot_components(self, ica_result: ICAResult, **kwargs: Any) -> None:
        """绘制 ICA 成分 (调用 MNE 绘图)"""
        if ica_result.ica:
            ica_result.ica.plot_components(**kwargs)

    def plot_sources(self, ica_result: ICAResult, dataset: EEGDataset, **kwargs: Any) -> None:
        """绘制 ICA 成分时间序列"""
        if ica_result.ica:
            raw = dataset.to_mne_raw()
            ica_result.ica.plot_sources(raw, **kwargs)

    def plot_properties(self, ica_result: ICAResult, dataset: EEGDataset, picks: list[int], **kwargs: Any) -> None:
        """绘制指定成分的属性"""
        if ica_result.ica:
            raw = dataset.to_mne_raw()
            ica_result.ica.plot_properties(raw, picks=picks, **kwargs)


# ---- 函数式接口 ----
def run_ica(
    dataset: EEGDataset,
    params: ICAParams,
    **kwargs: Any
) -> ICAResult:
    """运行 ICA 拟合"""
    service = ICAService()
    return service.fit(dataset, params, **kwargs)


def apply_ica(
    dataset: EEGDataset,
    ica_result: ICAResult,
    **kwargs: Any
) -> ICAResult:
    """应用 ICA"""
    service = ICAService()
    return service.apply(dataset, ica_result, **kwargs)