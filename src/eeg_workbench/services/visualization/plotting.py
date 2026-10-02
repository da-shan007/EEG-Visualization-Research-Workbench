"""绘图服务：波形、频谱、时频、连通性、统计、源定位绘图"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Literal
import numpy as np
from pathlib import Path

from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.models.visualization import (
    PlotConfig, WaveformPlotConfig, SpectralPlotConfig,
    TFRPlotConfig, ConnectivityPlotConfig,
    StatisticalPlotConfig, SourcePlotConfig,
    PlotType, PlotBackend, ExportFormat
)
from eeg_workbench.core.events import get_event_bus, EventType, PreprocessingPayload


@dataclass
class FigureResult:
    """绘图结果"""
    figure: Any  # matplotlib.figure.Figure 或 pyqtgraph.PlotWidget
    axes: Any | None = None
    config: PlotConfig | None = None
    data_info: dict = field(default_factory=dict)


class PlottingService:
    """绘图服务主入口"""

    def __init__(self):
        self._backend = PlotBackend.MATPLOTLIB
        self._figures: list = []

    def set_backend(self, backend: PlotBackend):
        """设置绘图后端"""
        self._backend = backend

    def plot(
        self,
        dataset: EEGDataset,
        plot_type: PlotType,
        config: PlotConfig | None = None,
        **kwargs
    ) -> FigureResult:
        """统一绘图入口"""
        
        # 根据类型分发
        if plot_type in (PlotType.RAW_WAVEFORM, PlotType.ERP_WAVEFORM, PlotType.EPOCH_WAVEFORM):
            return self.plot_waveform(dataset, config or WaveformPlotConfig(), **kwargs)
        elif plot_type == PlotType.PSD:
            return self.plot_spectral(dataset, config or SpectralPlotConfig(), **kwargs)
        elif plot_type == PlotType.TFR:
            return self.plot_tfr(dataset, config or TFRPlotConfig(), **kwargs)
        elif plot_type in (PlotType.CONNECTIVITY_MATRIX, PlotType.CONNECTIVITY_GRAPH, PlotType.CONNECTIVITY_3D):
            return self.plot_connectivity(dataset, config or ConnectivityPlotConfig(), **kwargs)
        elif plot_type in (PlotType.STAT_BAR, PlotType.STAT_VIOLIN, PlotType.STAT_BOX, 
                          PlotType.STAT_RAINCLOUD, PlotType.STAT_EFFECT_SIZE):
            return self.plot_statistical(dataset, config or StatisticalPlotConfig(), **kwargs)
        elif plot_type in (PlotType.SOURCE_ESTIMATE, PlotType.SOURCE_3D, PlotType.DIPOLE_3D):
            return self.plot_source(dataset, config or SourcePlotConfig(), **kwargs)
        elif plot_type == PlotType.TOPOMAP:
            return self.plot_topomap(dataset, config or PlotConfig(), **kwargs)
        else:
            raise ValueError(f"不支持的绘图类型: {plot_type}")

    # ---- 波形图 ----
    def plot_waveform(
        self,
        dataset: EEGDataset,
        config: WaveformPlotConfig,
        events: list = None,
        **kwargs
    ) -> FigureResult:
        """绘制波形图"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
        except ImportError:
            raise RuntimeError("波形绘图需要 matplotlib: pip install matplotlib")

        # 选择通道
        picks = self._resolve_picks(dataset, config.picks)
        data = dataset.data[picks]
        ch_names = [dataset.ch_names[i] for i in picks]
        times = dataset.times
        
        # 时间范围
        if config.tmin is not None or config.tmax is not None:
            tmin = config.tmin if config.tmin is not None else times[0]
            tmax = config.tmax if config.tmax is not None else times[-1]
            time_mask = (times >= tmin) & (times <= tmax)
            times = times[time_mask]
            data = data[:, time_mask]

        # 单位转换
        unit_scale = config.scalings.get("eeg", 1.0)
        data = data * unit_scale * 1e6  # V -> µV

        # 创建图形
        n_ch = len(picks)
        n_plots = int(np.ceil(n_ch / config.n_channels_per_plot))
        
        fig, axes = plt.subplots(
            n_plots, 1, 
            figsize=config.figsize,
            dpi=config.dpi,
            facecolor=config.facecolor,
            squeeze=False
        )
        axes = axes.flatten()

        for plot_idx in range(n_plots):
            ax = axes[plot_idx]
            start_ch = plot_idx * config.n_channels_per_plot
            end_ch = min(start_ch + config.n_channels_per_plot, n_ch)
            
            # 偏移
            offset_step = config.offset_step * np.std(data[start_ch:end_ch])
            
            for i, ch_idx in enumerate(range(start_ch, end_ch)):
                offset = i * offset_step
                color = config.color_cycle[ch_idx % len(config.color_cycle)]
                
                ax.plot(
                    times, data[ch_idx] + offset,
                    color=color, linewidth=config.line_width, alpha=config.alpha
                )
                
                # 通道名
                if config.show_channel_names:
                    ax.text(
                        0.01, offset + np.mean(data[ch_idx]),
                        ch_names[ch_idx],
                        transform=ax.get_yaxis_transform(),
                        fontsize=config.tick_size,
                        verticalalignment='center'
                    )

            # 网格
            if config.show_grid:
                ax.grid(True, alpha=config.grid_alpha)

            # 事件标记
            if events and config.show_events:
                for ev in events:
                    if config.tmin is not None and ev.onset < config.tmin:
                        continue
                    if config.tmax is not None and ev.onset > config.tmax:
                        continue
                    color = config.event_colors.get(ev.description, 'red')
                    marker = config.event_markers.get(ev.description, '|')
                    ax.axvline(ev.onset, color=color, linestyle='--', alpha=0.7, linewidth=1)

            ax.set_xlim(times[0], times[-1])
            ax.set_ylabel(config.unit, fontsize=config.label_size)

        axes[-1].set_xlabel(f'Time ({config.time_unit})', fontsize=config.label_size)
        
        # 标题
        fig.suptitle(f'Waveform - {n_ch} channels', fontsize=config.title_size)
        
        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(figure=fig, axes=axes, config=config, 
                          data_info={"n_channels": n_ch, "duration": times[-1] - times[0]})

    def _resolve_picks(self, dataset: EEGDataset, picks) -> list[int]:
        """解析通道选择"""
        if picks == "all":
            return list(range(dataset.n_channels))
        elif picks == "eeg":
            return [i for i, ch in enumerate(dataset.ch_names) 
                   if dataset.channel_info.get(ch, {}).type.value == "eeg"]
        elif picks == "eog":
            return [i for i, ch in enumerate(dataset.ch_names) 
                   if dataset.channel_info.get(ch, {}).type.value == "eog"]
        elif picks == "ecg":
            return [i for i, ch in enumerate(dataset.ch_names) 
                   if dataset.channel_info.get(ch, {}).type.value == "ecg"]
        elif isinstance(picks, list):
            if all(isinstance(p, str) for p in picks):
                return [dataset.ch_names.index(p) for p in picks if p in dataset.ch_names]
            else:
                return picks
        return list(range(dataset.n_channels))

    # ---- 频谱图 ----
    def plot_spectral(
        self,
        dataset: EEGDataset,
        config: SpectralPlotConfig,
        **kwargs
    ) -> FigureResult:
        """绘制功率谱密度"""
        try:
            import matplotlib.pyplot as plt
            from scipy.signal import welch, periodogram
        except ImportError:
            raise RuntimeError("频谱绘图需要 matplotlib 和 scipy")

        picks = self._resolve_picks(dataset, kwargs.get("picks", "eeg"))
        data = dataset.data[picks]
        sfreq = dataset.sfreq
        ch_names = [dataset.ch_names[i] for i in picks]

        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi, facecolor=config.facecolor)

        for i, ch_idx in enumerate(picks):
            if config.method == "welch":
                f, psd = welch(
                    dataset.data[ch_idx], fs=sfreq,
                    nperseg=config.n_fft, noverlap=config.n_overlap
                )
            elif config.method == "periodogram":
                f, psd = periodogram(dataset.data[ch_idx], fs=sfreq)
            else:
                # FFT
                n = len(dataset.data[ch_idx])
                psd = np.abs(np.fft.rfft(dataset.data[ch_idx])) ** 2
                f = np.fft.rfftfreq(n, 1/sfreq)

            # 频率范围
            mask = (f >= config.fmin) & (f <= config.fmax)
            f, psd = f[mask], psd[mask]

            color = config.color_cycle[i % len(config.color_cycle)]
            ax.plot(f, 10 * np.log10(psd), color=color, label=ch_names[i], 
                   linewidth=1, alpha=0.8)

        ax.set_xlabel('Frequency (Hz)', fontsize=config.label_size)
        ax.set_ylabel('Power (dB)', fontsize=config.label_size)
        ax.set_xscale(config.xscale)
        ax.set_xlim(config.fmin, config.fmax)
        ax.legend(fontsize=config.legend_size, loc='upper right')
        ax.grid(True, alpha=0.3)

        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(figure=fig, axes=ax, config=config)

    # ---- 时频图 ----
    def plot_tfr(
        self,
        dataset: EEGDataset,
        config: TFRPlotConfig,
        epochs_data: np.ndarray = None,
        **kwargs
    ) -> FigureResult:
        """绘制时频图（Morlet/Multitaper 时频分解 + 基线校正）

        通道维度取平均绘制单张时频图；epochs_data 提供时先对 epoch 平均。
        """
        try:
            import matplotlib.pyplot as plt
            import mne
        except ImportError:
            raise RuntimeError("时频绘图需要 matplotlib 和 mne")

        # ---- 数据准备 (n_epochs, n_ch, n_times) ----
        data = epochs_data if epochs_data is not None else dataset.data
        data = np.atleast_3d(np.asarray(data, dtype=float))
        if data.ndim == 2:                      # (n_ch, n_times)
            data = data[np.newaxis]
        if data.shape[1] != dataset.n_channels and data.shape[-1] == dataset.n_channels:
            data = np.swapaxes(data, 1, -1)     # 兼容 (n_ep, n_times, n_ch)
        sfreq = dataset.sfreq
        n_times = data.shape[-1]
        picks = self._resolve_picks(dataset, kwargs.get("picks", "eeg"))
        data = data[:, picks, :]
        n_ep, n_ch = data.shape[0], data.shape[1]

        # ---- 频率轴 ----
        n_freqs = int(kwargs.get("n_freqs", 30))
        fmin = max(float(config.fmin), 0.5)
        fmax = min(float(config.fmax), sfreq / 2)
        freqs = np.logspace(np.log10(fmin), np.log10(fmax), n_freqs)
        # 标量 n_cycles 按频率缩放（与 features/time_frequency.py 保持一致的低频增强）
        n_cycles = config.n_cycles * freqs / fmin
        # clamp：mne 小波长度约 2*ceil(5*sigma*sfreq)-1，sigma=n_cycles/(2*pi*f)，不得超过信号长
        max_half = (n_times + 1) // 2 - 1
        max_sigma_t = max(max_half, 1) / (5.0 * sfreq)
        n_cycles = np.minimum(n_cycles, 2 * np.pi * freqs * max_sigma_t)

        # ---- 时频分解 ----
        method = getattr(config, "method", "morlet") or "morlet"
        if method == "multitaper":
            power = mne.time_frequency.tfr_array_multitaper(
                data, sfreq, freqs, n_cycles=n_cycles, time_bandwidth=4.0,
                output="power", verbose=False)
        else:  # morlet / stockwell(回落 morlet)
            power = mne.time_frequency.tfr_array_morlet(
                data, sfreq, freqs, n_cycles=n_cycles,
                output="power", verbose=False)
        power = power.mean(axis=(0, 1))         # (freqs, times) 通道与 epoch 平均

        times = np.arange(n_times) / sfreq      # 与 features 层时间定义一致（0 起）

        # ---- 时间窗裁剪 ----
        t_mask = np.ones(n_times, dtype=bool)
        if config.tmin is not None:
            t_mask &= times >= float(config.tmin)
        if config.tmax is not None:
            t_mask &= times <= float(config.tmax)
        if not t_mask.any():
            t_mask = np.ones(n_times, dtype=bool)
        plot_times, plot_power = times[t_mask], power[:, t_mask]

        # ---- 基线校正 ----
        baseline_note = ""
        bl = getattr(config, "baseline", None)
        if bl is not None:
            bl_start, bl_end = max(float(bl[0]), times[0]), min(float(bl[1]), times[-1])
            bl_mask = (times >= bl_start) & (times <= bl_end)
            if np.any(bl_mask):
                bl_power = power[:, bl_mask]
                mode = getattr(config, "baseline_mode", "logratio")
                with np.errstate(divide="ignore", invalid="ignore"):
                    if mode == "mean":
                        plot_power = plot_power - bl_power.mean(axis=1, keepdims=True)
                    elif mode == "ratio":
                        plot_power = plot_power / (bl_power.mean(axis=1, keepdims=True) + 1e-30)
                    elif mode == "logratio":
                        plot_power = 10 * np.log10(
                            (plot_power + 1e-30) / (bl_power.mean(axis=1, keepdims=True) + 1e-30))
                    elif mode == "zscore":
                        mu = bl_power.mean(axis=1, keepdims=True)
                        sd = bl_power.std(axis=1, keepdims=True) + 1e-30
                        plot_power = (plot_power - mu) / sd
                    elif mode == "percent":
                        mu = bl_power.mean(axis=1, keepdims=True)
                        plot_power = (plot_power - mu) / (mu + 1e-30) * 100.0
            else:
                baseline_note = f"（baseline {bl} 超出数据时间范围 {times[0]:.2f}~{times[-1]:.2f}s，已跳过）"

        # ---- 绘图 ----
        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi, facecolor=config.facecolor)
        im = ax.pcolormesh(
            plot_times, freqs, plot_power,
            shading="auto", cmap=config.cmap,
            vmin=config.vmin, vmax=config.vmax,
        )
        fig.colorbar(im, ax=ax, label=f"Power ({method}"
                     + (f", {getattr(config, 'baseline_mode', '')} baseline)"
                        if bl else ")"))
        ax.set_xlabel("Time (s)", fontsize=config.label_size)
        ax.set_ylabel("Frequency (Hz)", fontsize=config.label_size)
        n_ch_total = len(dataset.ch_names)
        title = f"Time-Frequency ({method}) - {n_ch} / {n_ch_total} ch mean"
        if baseline_note:
            title += f" {baseline_note}"
        ax.set_title(title, fontsize=config.label_size)

        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(
            figure=fig, axes=ax, config=config,
            data_info={"method": method, "n_freqs": n_freqs,
                       "baseline": str(bl), "channels_avg": int(n_ch)},
        )

    # ---- 连通性 ----
    def plot_connectivity(
        self,
        dataset: EEGDataset,
        config: ConnectivityPlotConfig,
        connectivity_matrix: np.ndarray = None,
        **kwargs
    ) -> FigureResult:
        """绘制连通性矩阵/图"""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise RuntimeError("连通性绘图需要 matplotlib")

        if connectivity_matrix is None:
            raise ValueError("需要提供连通性矩阵")

        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi, facecolor=config.facecolor)

        if config.show_matrix:
            im = ax.imshow(
                connectivity_matrix,
                cmap=config.matrix_cmap,
                vmin=config.matrix_vmin,
                vmax=config.matrix_vmax,
                aspect='auto'
            )
            plt.colorbar(im, ax=ax, label='Connectivity')
            ax.set_xlabel('Channels', fontsize=config.label_size)
            ax.set_ylabel('Channels', fontsize=config.label_size)

        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(figure=fig, axes=ax, config=config)

    # ---- 统计图 ----
    def plot_statistical(
        self,
        dataset: EEGDataset,
        config: StatisticalPlotConfig,
        data: dict = None,
        **kwargs
    ) -> FigureResult:
        """绘制统计图"""
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
        except ImportError:
            raise RuntimeError("统计绘图需要 matplotlib 和 seaborn")

        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi, facecolor=config.facecolor)

        # 数据源：外部统计数据（dict）优先，否则退化为各通道分布的描述统计
        values: dict[str, np.ndarray] = {}
        subtitle = ""
        if data is None:
            picks = self._resolve_picks(dataset, kwargs.get("picks", "eeg"))
            values = {
                dataset.ch_names[i]: np.asarray(dataset.data[i], dtype=float)
                for i in picks
            }
            subtitle = "通道数据分布（描述统计）"
        elif isinstance(data, dict):
            raw = data.get("groups", data)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, (list, tuple, np.ndarray)):
                        arr = np.asarray(v, dtype=float).ravel()
                        if arr.size:
                            values[str(k)] = arr
            subtitle = str(data.get("title", "统计数据"))

        if not values:
            ax.text(0.5, 0.5, "无可绘制的统计数据",
                    ha="center", va="center", transform=ax.transAxes, fontsize=14)
        else:
            self._draw_stats(ax, values, config, subtitle)

        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(figure=fig, axes=ax, config=config,
                            data_info={"n_groups": len(values), "plot_type": config.plot_type})

    @staticmethod
    def _draw_stats(ax, values: dict, config, subtitle: str) -> None:
        """按 config.plot_type 绘制分组统计图（bar/box/violin/raincloud/forest）。"""
        from scipy import stats as sps

        labels = list(values.keys())
        arrays = [values[k] for k in labels]
        ptype = getattr(config, "plot_type", "bar")
        rng = np.random.default_rng(0)

        def _scatter(x_pos, arr):
            if not config.show_individual_points:
                return
            jitter = rng.uniform(-config.point_jitter, config.point_jitter, size=arr.size) \
                if config.point_jitter else np.zeros(arr.size)
            ax.scatter(x_pos + jitter, arr, s=12, alpha=config.point_alpha,
                       color="black", zorder=3)

        if ptype in ("bar", "effect_size", "forest"):
            means = np.array([np.mean(a) for a in arrays])
            errs = np.zeros(len(arrays))
            if config.show_confidence:
                for i, a in enumerate(arrays):
                    if a.size > 1:
                        se = sps.sem(a)
                        tcrit = sps.t.ppf((1 + config.confidence_level) / 2, df=a.size - 1)
                        errs[i] = tcrit * se
            x = np.arange(len(labels))
            ax.bar(x, means, yerr=errs, capsize=4, alpha=0.7,
                   edgecolor="black", color="#4C72B0")
            for xi, a in zip(x, arrays):
                _scatter(xi, a)
            if ptype in ("forest", "effect_size"):
                ax.axhline(0, color="red", linewidth=0.8, linestyle="--")
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.grid(axis="y", alpha=0.3)
        elif ptype == "box":
            ax.boxplot(arrays, showfliers=True)
            ax.set_xticks(range(1, len(labels) + 1))
            ax.set_xticklabels(labels, rotation=45, ha="right")
            for i, a in enumerate(arrays, start=1):
                _scatter(np.full(a.size, i), a)
            ax.grid(axis="y", alpha=0.3)
        elif ptype in ("violin", "raincloud"):
            vparts = ax.violinplot(arrays, showmeans=True, showextrema=False)
            for pc in vparts["bodies"]:
                pc.set_alpha(0.6)
                pc.set_facecolor("#4C72B0")
            for i, a in enumerate(arrays, start=1):
                _scatter(np.full(a.size, float(i)), a)
            ax.set_xticks(range(1, len(labels) + 1))
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.grid(axis="y", alpha=0.3)
        else:  # 未知类型回落 bar
            means = [np.mean(a) for a in arrays]
            x = np.arange(len(labels))
            ax.bar(x, means, alpha=0.7, edgecolor="black", color="#4C72B0")
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha="right")

        ax.set_title(f"Statistical Plot ({ptype}) - {subtitle}",
                     fontsize=config.label_size)
        ax.set_ylabel("Value", fontsize=config.label_size)

    # ---- 源定位 ----
    def plot_source(
        self,
        dataset: EEGDataset,
        config: SourcePlotConfig,
        stc = None,
        **kwargs
    ) -> FigureResult:
        """绘制源定位"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("源定位可视化需要 MNE")

        if stc is None:
            raise ValueError("需要提供 SourceEstimate 对象")

        # 使用 MNE 绘图
        brain = mne.viz.Brain(
            subject=stc.subject,
            hemi=config.hemi,
            surf=config.surface,
            views=config.views,
            background=config.facecolor,
            cortex=config.colormap,
            size=config.figsize[::-1],  # (width, height) -> (height, width)
        )

        brain.add_data(
            stc.data, vertices=stc.vertices,
            time_idx=kwargs.get("time_idx", 0),
            hemi=config.hemi,
            colormap=config.colormap,
            clim=config.clim if config.clim != "auto" else None,
            transparent=config.transparent
        )

        if config.show_dipoles and kwargs.get("dipoles"):
            for dip in kwargs["dipoles"]:
                brain.add_dipole(
                    dip["pos"], dip["ori"], 
                    amplitude=dip.get("amplitude", 10e-9),
                    scale=config.dipole_scale,
                    color=config.dipole_color
                )

        return FigureResult(figure=brain, config=config, 
                          data_info={"subject": stc.subject, "n_vertices": len(stc.vertices[0])})

    # ---- 地形图 ----
    def plot_topomap(
        self,
        dataset: EEGDataset,
        config: PlotConfig,
        data: np.ndarray = None,
        times: np.ndarray = None,
        **kwargs
    ) -> FigureResult:
        """绘制地形图"""
        try:
            import mne
            import matplotlib.pyplot as plt
        except ImportError:
            raise RuntimeError("地形图需要 MNE 和 matplotlib")

        if data is None:
            raise ValueError("需要提供地形图数据")

        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi, facecolor=config.facecolor)
        
        info = dataset.to_mne_raw().info
        im, cn = mne.viz.plot_topomap(
            data, info,
            axes=ax,
            cmap=config.cmap,
            vlim=config.vlim if hasattr(config, 'vlim') else None,
            sensors=config.show_grid if hasattr(config, 'show_grid') else True,
            contours=6,
            outlines='head',
            show=False
        )

        if config.tight_layout:
            plt.tight_layout()

        return FigureResult(figure=fig, axes=ax, config=config)


# ---- 便捷函数 ----
def create_figure(plot_type: PlotType, **kwargs) -> FigureResult:
    """创建图形的便捷函数"""
    service = PlottingService()
    return service.plot(None, plot_type, **kwargs)


def plot_waveform(dataset: EEGDataset, config: WaveformPlotConfig = None, **kwargs) -> FigureResult:
    """绘制波形图"""
    service = PlottingService()
    return service.plot_waveform(dataset, config or WaveformPlotConfig(), **kwargs)


def plot_spectral(dataset: EEGDataset, config: SpectralPlotConfig = None, **kwargs) -> FigureResult:
    """绘制频谱"""
    service = PlottingService()
    return service.plot_spectral(dataset, config or SpectralPlotConfig(), **kwargs)


def plot_tfr(dataset: EEGDataset, config: TFRPlotConfig = None, **kwargs) -> FigureResult:
    """绘制时频图"""
    service = PlottingService()
    return service.plot_tfr(dataset, config or TFRPlotConfig(), **kwargs)