"""3D 源可视化服务：脑表面、源估计、地形图、连通性"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import numpy as np

from eeg_workbench.models.source import SourceAnalysisResult
from eeg_workbench.models.dataset import EEGDataset, Montage


@dataclass
class BrainPlotData:
    """大脑绘图数据"""
    # 脑表面
    vertices: np.ndarray  # (n_verts, 3) 米
    faces: np.ndarray     # (n_faces, 3) 三角形索引
    
    # 激活数据
    values: np.ndarray | None = None  # (n_verts,) 或 (n_verts, n_times)
    times: np.ndarray | None = None   # (n_times,)
    
    # 颜色映射
    vlim: tuple[float, float] | None = None
    cmap: str = "RdBu_r"
    clim: str = "auto"  # 'auto', 'symmetric', 'percentile'
    
    # 显示选项
    hemi: str = "both"  # 'lh', 'rh', 'both', 'split'
    views: list[str] = None  # ['lateral', 'medial', 'rostral', 'caudal', 'dorsal', 'ventral']
    background: str = "white"
    cortex: str = "classic"  # 'classic', 'bone', 'low_contrast', 'high_contrast'
    size: tuple[int, int] = (800, 600)
    
    # 交互
    interactive: bool = True
    title: str | None = None


class SourceVisualization3D:
    """3D 源可视化服务"""

    def __init__(self):
        self._brain = None
        self._fig = None

    def plot_source_estimate(
        self,
        stc,
        subject: str = "fsaverage",
        subjects_dir: str | None = None,
        **kwargs
    ) -> BrainPlotData:
        """绘制源估计 (使用 MNE/PyVista)"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("3D 可视化需要 MNE: pip install mne")

        # 如果是 VectorSourceEstimate，取模长
        if hasattr(stc, 'data') and stc.data.ndim == 3:
            # Vector STC: 取模长
            data = np.linalg.norm(stc.data, axis=1)
        else:
            data = stc.data

        # 形变到 fsaverage
        if subject != "fsaverage":
            stc_fs = stc.morph_to("fsaverage", subject_from=subject)
            data = stc_fs.data
            subject = "fsaverage"

        brain = mne.viz.Brain(
            subject, hemi="both", surf="inflated",
            subjects_dir=kwargs.get("subjects_dir"),
            background="white", cortex="classic",
            size=(800, 600), **kwargs
        )

        # 添加数据
        brain.add_data(
            data, vertices=stc.vertices,
            time_idx=kwargs.get("time_idx", 0),
            hemi="both", colormap="RdBu_r",
            **kwargs
        )

        # 设置视角
        if "views" in kwargs:
            for view in kwargs["views"]:
                brain.show_view(view)

        return BrainPlotData(
            vertices=stc.vertices[0] if isinstance(stc.vertices, list) else stc.vertices,
            faces=np.array([]),  # 需要从 surface 获取
            values=data,
            times=stc.times,
            **kwargs
        )

    def plot_topomap_3d(
        self,
        evoked,
        time_point: float,
        **kwargs
    ) -> dict:
        """绘制 3D 地形图"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("需要 MNE")

        idx = np.argmin(np.abs(evoked.times - time_point))
        data = evoked.data[:, idx] * 1e6  # V -> µV

        brain = mne.viz.Brain("fsaverage", hemi="both", surf="inflated", **kwargs)
        brain.add_topomap(
            data, evoked.info, time_point,
            **kwargs
        )

        return {"data": data, "time": time_point}

    def plot_connectivity_3d(
        self,
        con,
        stc_vertices,
        stc_faces,
        threshold: float = 0.5,
        **kwargs
    ) -> dict:
        """绘制 3D 连通性 (节点+边)"""
        # con: (n_nodes, n_nodes) 连通性矩阵
        # 只显示大于阈值的连接
        mask = np.abs(con) > threshold
        edges = np.where(mask)
        
        return {
            "vertices": stc_vertices,
            "faces": stc_faces,
            "edges": edges,
            "weights": con[edges],
        }

    def plot_dipoles_3d(
        self,
        dipoles: list[dict],
        subject: str = "fsaverage",
        **kwargs
    ) -> dict:
        """绘制 3D 偶极子位置和朝向"""
        try:
            import mne
        except ImportError:
            raise RuntimeError("需要 MNE")

        brain = mne.viz.Brain("fsaverage", hemi="both", surf="inflated", **kwargs)

        for dip in dipoles:
            pos = dip.get("pos", [0, 0, 0.04])
            ori = dip.get("ori", [0, 0, 1])
            amp = dip.get("amplitude", 10e-9)
            gof = dip.get("gof", 1.0)

            # 添加偶极子
            brain.add_dipole(
                pos=pos, ori=ori,
                amplitude=amp,
                scale=10,  # 缩放因子
                color="red" if dip.get("gof", 0) > 0.9 else "orange",
                **kwargs
            )

        return {"dipoles": dipoles}

    def export_scene(self, filepath: str, format: str = "html"):
        """导出 3D 场景"""
        if hasattr(self, '_brain') and self._brain:
            if format == "html":
                self._brain.save_imageset(filepath)
            elif format == "png":
                self._brain.save_image(filepath)
            elif format == "stl":
                self._brain.export_stl(filepath)

    @staticmethod
    def interpolate_to_surface(
        data: np.ndarray,
        src_vertices: np.ndarray,
        target_vertices: np.ndarray,
        target_faces: np.ndarray,
        method: str = "nearest"
    ) -> np.ndarray:
        """将源估计插值到目标表面

        data: 源顶点上的标量值，形状 (n_src,)。
        src_vertices: 源顶点 3D 坐标，形状 (n_src, 3)。
        target_vertices: 目标顶点 3D 坐标，形状 (n_target, 3)。
        method: 'nearest' 最近邻；'linear'/'cubic' 用三维 griddata 插值，
            凸包外的点回退为最近邻，保证无 NaN。
        """
        from scipy.spatial import cKDTree

        data = np.asarray(data, dtype=float)
        src_vertices = np.asarray(src_vertices, dtype=float)
        target_vertices = np.asarray(target_vertices, dtype=float)
        if data.ndim != 1 or src_vertices.shape != (data.shape[0], 3):
            raise ValueError(
                "data 须为 (n_src,)，src_vertices 须为 (n_src, 3)"
            )
        if target_vertices.ndim != 2 or target_vertices.shape[1] != 3:
            raise ValueError("target_vertices 须为 (n_target, 3)")

        if method == "nearest":
            tree = cKDTree(src_vertices)
            _, idx = tree.query(target_vertices)
            return data[idx]
        elif method in ("linear", "cubic"):
            from scipy.interpolate import griddata

            values = griddata(src_vertices, data, target_vertices, method=method)
            nan_mask = np.isnan(values)
            if np.any(nan_mask):
                tree = cKDTree(src_vertices)
                _, idx = tree.query(target_vertices[nan_mask])
                values[nan_mask] = data[idx]
            return values
        else:
            raise ValueError(
                f"不支持的插值方法: {method}（支持 nearest / linear / cubic）"
            )

    @staticmethod
    def create_montage_visualization(
        montage: Montage,
        **kwargs
    ) -> dict:
        """创建电极蒙版 3D 可视化"""
        positions = np.array(list(montage.positions.values()))
        ch_names = list(montage.positions.keys())
        
        return {
            "positions": positions,
            "names": ch_names,
            "nasion": montage.nasion,
            "lpa": montage.lpa,
            "rpa": montage.rpa,
        }


def plot_source_estimate(
    stc, subject: str = "fsaverage", **kwargs
) -> BrainPlotData:
    """函数式接口"""
    viz = SourceVisualization3D()
    return viz.plot_source_estimate(stc, subject, **kwargs)