"""地形图绘制服务"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import numpy as np

from eeg_workbench.models.dataset import EEGDataset, Montage
from eeg_workbench.utils.montage import (
    make_standard_montage_compat as _compat_montage,
)


@dataclass
class TopomapData:
    """地形图数据"""
    data: np.ndarray              # (n_channels,) 每个通道的值
    ch_names: list[str]           # 通道名
    times: np.ndarray | None = None  # 如果是时变地形图
    vlim: tuple[float, float] | None = None  # 颜色范围
    cmap: str = "RdBu_r"          # 颜色映射
    sensors: bool = True          # 显示电极位置
    contours: int = 6             # 等高线数
    outlines: str = "head"        # 轮廓: 'head', 'skirt', None
    sphere: float | tuple[float, ...] | None = None  # 头模型半径


class TopomapService:
    """地形图服务"""

    @staticmethod
    def compute_topomap_data(
        evoked: Any,
        time_point: float,
        *,
        ch_type: str = "eeg",
        scale: float = 1e6  # V -> µV
    ) -> TopomapData:
        """从 Evoked 计算指定时间点的地形图数据"""
        idx = np.argmin(np.abs(evoked.times - time_point))
        data = evoked.data[:, idx] * scale
        return TopomapData(
            data=data,
            ch_names=evoked.ch_names,
            times=np.array([evoked.times[idx]]),
        )

    @staticmethod
    def compute_topomap_from_array(
        data: np.ndarray,
        ch_names: list[str],
        montage: Montage | None = None,
        *,
        scale: float = 1.0,
        **kwargs: Any
    ) -> TopomapData:
        """从数组计算地形图数据"""
        return TopomapData(
            data=data * scale,
            ch_names=ch_names,
            **kwargs
        )

    @staticmethod
    def plot_topomap(
        topomap_data: TopomapData,
        *,
        ax: Any = None,
        show: bool = True,
        **kwargs: Any
    ) -> Any:
        """绘制地形图 (需要 matplotlib/mne)"""
        try:
            import mne
            import matplotlib.pyplot as plt
        except ImportError:
            raise RuntimeError("绘制地形图需要 MNE 和 matplotlib")

        # 创建 Info 对象
        if hasattr(topomap_data, 'ch_names') and hasattr(topomap_data, 'data'):
            ch_names = topomap_data.ch_names
            data = topomap_data.data
        else:
            raise ValueError("无效的 TopomapData")

        info = mne.create_info(ch_names=ch_names, sfreq=1000, ch_types="eeg")
        
        # 设置蒙版
        if hasattr(topomap_data, 'montage') and topomap_data.montage:
            mne_montage = topomap_data.montage.to_mne_montage()
            info.set_montage(mne_montage, on_missing="warn")

        # 创建 Evoked 对象用于绘图
        evoked = mne.EvokedArray(data[np.newaxis, :], info, tmin=0)
        if hasattr(topomap_data, 'times') and topomap_data.times is not None:
            evoked.times = topomap_data.times

        # 绘制
        if ax is None:
            fig, ax = plt.subplots(figsize=kwargs.get("figsize", (6, 5)))

        im, cn = mne.viz.plot_topomap(
            data, evoked.info,
            times=topomap_data.times[0] if topomap_data.times is not None else 0,
            ch_type="eeg",
            sensors=topomap_data.sensors,
            contours=topomap_data.contours,
            outlines=topomap_data.outlines,
            sphere=topomap_data.sphere,
            vlim=topomap_data.vlim,
            cmap=topomap_data.cmap,
            axes=ax,
            show=show,
            **kwargs
        )

        return im, cn

    @staticmethod
    def plot_topomap_times(
        evoked: Any,
        times: list[float],
        *,
        ch_type: str = "eeg",
        n_cols: int = 4,
        scale: float = 1e6,
        **kwargs: Any
    ) -> None:
        """绘制多个时间点的地形图"""
        try:
            import mne
            import math
        except ImportError:
            raise RuntimeError("绘制地形图需要 MNE")

        times = [float(t) for t in (times or [])]
        if not times:
            # 无时间点（如无峰值）时取全通道绝对幅度最大处
            import numpy as np
            times = [float(evoked.times[int(np.argmax(np.abs(evoked.data).max(axis=0)))])]

        # 网格自适应：mne 要求 nrows*ncols >= len(times)（旧 bug：固定 1×4 放不下 5 个峰值）
        ncols = max(1, min(n_cols, len(times)))
        nrows = math.ceil(len(times) / ncols)

        evoked.plot_topomap(
            times=times,
            ch_type=ch_type,
            ncols=ncols,  # mne 1.13 起参数名为 ncols（旧名 n_cols 已移除）
            nrows=nrows,
            scalings=dict(eeg=scale),
            **kwargs
        )

    @staticmethod
    def plot_joint(
        evoked: Any,
        times: list[float] | str = "peaks",
        *,
        title: str | None = None,
        **kwargs: Any
    ) -> None:
        """绘制联合图 (波形 + 地形图)"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("绘制联合图需要 MNE")

        evoked.plot_joint(
            times=times,
            title=title,
            **kwargs
        )

    @staticmethod
    def interpolate_to_grid(
        topomap_data: TopomapData,
        grid_res: int = 64,
        *,
        montage: Montage | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """将地形图数据插值到规则网格 (用于自定义绘图)
        
        Returns:
            xi, yi: 网格坐标
            zi: 插值后的数据
        """
        try:
            from scipy.interpolate import griddata
            import mne
        except ImportError:
            raise RuntimeError("插值需要 scipy 和 MNE")

        ch_names = topomap_data.ch_names
        data = topomap_data.data

        # 获取通道位置
        info = mne.create_info(ch_names=ch_names, sfreq=1000, ch_types="eeg")
        if montage:
            mne_montage = montage.to_mne_montage()
            info.set_montage(mne_montage, on_missing="warn")
        else:
            info.set_montage(_compat_montage("standard_1020"), on_missing="warn")

        pos_2d = mne.channels.layout._find_topomap_coords(info, picks=range(len(ch_names)))

        # 创建网格
        x_min, x_max = pos_2d[:, 0].min(), pos_2d[:, 0].max()
        y_min, y_max = pos_2d[:, 1].min(), pos_2d[:, 1].max()
        margin = 0.05
        xi = np.linspace(x_min - margin, x_max + margin, grid_res)
        yi = np.linspace(y_min - margin, y_max + margin, grid_res)
        xi, yi = np.meshgrid(xi, yi)

        # 插值
        zi = griddata(pos_2d, data, (xi, yi), method='cubic', fill_value=np.nan)

        return xi, yi, zi


def plot_topomap(
    evoked: Any,
    time_point: float,
    **kwargs: Any
) -> Any:
    """函数式接口"""
    data = TopomapService.compute_topomap_data(evoked, time_point)
    return TopomapService.plot_topomap(data, **kwargs)