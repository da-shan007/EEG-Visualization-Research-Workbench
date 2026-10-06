"""源定位在线预览绘图：全部基于 matplotlib，可嵌入 Qt 应用内显示。

设计约束（备忘 #16）：.venv 有 mne 1.13.2 但无 pyvista/pyvistaqt，
MNE Brain 3D 交互在此环境不可用；本模块只用 matplotlib（含 mplot3d）
和 mne.viz 中返回 Figure 的函数，保证离线可跑、可测、可嵌入。

约定：每个函数返回 matplotlib.figure.Figure，调用方负责嵌入
FigureCanvasQTAgg 并 close 旧图；函数内部不调用 plt.show()。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Sequence, cast
import numpy as np

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def _new_fig(w: float = 6.0, h: float = 4.2) -> Figure:
    from matplotlib.figure import Figure
    return Figure(figsize=(w, h), dpi=100)


def fig_bem_geometry(bem: Any, max_tri_per_surf: int = 1500) -> Figure:
    """BEM 三层表面几何（mplot3d 真实三角网格，MRI 坐标，单位 mm）。

    bem: make_bem_solution 返回的 ConductorModel（dict-like，含 'surfs'，
    每个 surf 含 'rr'(m)、'tris'、'sigma'、'id')。为显示速度做抽稀。
    注：传感器在头坐标系下、无 trans 时不叠加，避免坐标误导。
    """
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = _new_fig(6.4, 4.6)
    ax = fig.add_subplot(111, projection="3d")
    surfs = bem["surfs"] if isinstance(bem, dict) and "surfs" in bem else bem
    colors = ["#e74c3c", "#f39c12", "#3498db"]
    for i, surf in enumerate(surfs):
        rr = np.asarray(surf["rr"], dtype=float) * 1000.0  # m -> mm
        tris = np.asarray(surf["tris"], dtype=int)
        step = max(1, len(tris) // max_tri_per_surf)
        tris = tris[::step]
        verts = rr[tris]
        coll = Poly3DCollection(
            verts, facecolor=colors[i % len(colors)],
            edgecolor="none", alpha=0.35,
        )
        ax.add_collection3d(coll)
        sigma = surf.get("sigma", float("nan"))
        ax.text2D(
            0.02, 0.95 - 0.06 * i, f"层{i}: {surf.get('id', '?')} σ={sigma}",
            transform=ax.transAxes, fontsize=9,
        )
    all_pts = np.vstack([np.asarray(s["rr"]) * 1000.0 for s in surfs])
    mins, maxs = all_pts.min(axis=0), all_pts.max(axis=0)
    center = (mins + maxs) / 2
    radius = (maxs - mins).max() / 2
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("BEM 表面几何（抽稀显示）")
    fig.tight_layout()
    return fig


def fig_sphere_geometry(
    sphere: dict[str, Any],
    ch_pos: np.ndarray | None = None,
    ch_names: Sequence[str] | None = None,
) -> Figure:
    """球形头模型：头圆截面 + 传感器 XY 投影（单位 mm）。"""
    fig = _new_fig()
    ax = fig.add_subplot(111, aspect="equal")
    r0 = np.asarray(sphere.get("r0", [0.0, 0.0, 0.0]), dtype=float) * 1000.0
    # make_sphere_model 返回 layers=[{rad, sigma, ...}]，半径取最外层
    layers = sphere.get("layers") or []
    radius = float(max((lyr.get("rad", 0.0) for lyr in layers), default=0.095)) * 1000.0
    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(r0[0] + radius * np.cos(theta), r0[1] + radius * np.sin(theta),
            color="#2c3e50", lw=1.5, label="球模型边界")
    if ch_pos is not None and len(ch_pos):
        p = np.asarray(ch_pos, dtype=float) * 1000.0
        ax.scatter(p[:, 0], p[:, 1], s=18, c="#e74c3c", zorder=3, label="传感器")
        if ch_names is not None:
            for xy, name in zip(p[:, :2], ch_names):
                ax.annotate(name, xy, fontsize=6)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title(f"球形头模型 R={radius:.1f} mm 中心=({r0[0]:.1f},{r0[1]:.1f})")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    return fig


def fig_sensitivity(fwd: Any) -> Figure:
    """导场敏感度图：mne.sensitivity_map 真实计算 + 源位置散点投影。

    注：mne 1.13 无 mne.viz.plot_sensitivity_map，且 VolSourceEstimate
    没有 plot_topomap；统一用源点 XY 投影着色，体/面源空间通用。
    """
    import mne
    sens = mne.sensitivity_map(fwd, ch_type="eeg", mode="fixed")
    data = np.asarray(sens.data)
    if data.ndim == 3:  # VectorSourceEstimate 取模长
        data = np.linalg.norm(data, axis=1)
    values = data[:, 0] if data.ndim == 2 else data
    pos = np.asarray(fwd["source_rr"], dtype=float) * 1000.0  # m -> mm
    fig = _new_fig()
    ax = fig.add_subplot(111, aspect="equal")
    sc = ax.scatter(pos[:, 0], pos[:, 1], s=8, c=values, cmap="hot", alpha=0.8)
    fig.colorbar(sc, ax=ax, label="sensitivity")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title(
        f"导场敏感度（{len(values)} 源） max={values.max():.3g} mean={values.mean():.3g}"
    )
    fig.tight_layout()
    return fig


def fig_stc_topomap(stc: Any, time_idx: int = 0) -> Figure:
    """源估计头皮地形投影（stc.plot_topomap，matplotlib 后端可嵌入）。"""
    t = float(stc.times[time_idx]) if len(stc.times) > time_idx else float(stc.times[0])
    fig = cast(Figure, stc.plot_topomap(t, show=False))
    return fig


#: 视图按钮 → 偶极子 2D 投影平面：(横轴, 纵轴, 标题)
DIPOLE_VIEW_PLANES = {
    "lateral": (1, 2, "侧视 (Y-Z)"),
    "medial": (1, 2, "内侧视 (Y-Z 翻转)"),
    "rostral": (0, 2, "正视 (X-Z)"),
    "caudal": (0, 2, "后视 (X-Z 翻转)"),
    "dorsal": (0, 1, "俯视 (X-Y)"),
    "ventral": (0, 1, "仰视 (X-Y 翻转)"),
}
_FLIP_VIEWS = {"medial", "caudal", "ventral"}


def fig_dipoles_2d(
    dipoles: list[dict[str, Any]],
    view: str = "dorsal",
    head_radius_m: float = 0.095,
) -> Figure:
    """偶极子位置+朝向 2D 投影示意（箭头=朝向×幅度，圆=头边界，单位 mm）。

    这是无 pyvista 时的降级示意，非 Brain 渲染；标题与坐标轴如实标注平面。
    """
    ax_idx, ay_idx, title = DIPOLE_VIEW_PLANES.get(view, DIPOLE_VIEW_PLANES["dorsal"])
    flip = -1.0 if view in _FLIP_VIEWS else 1.0
    fig = _new_fig()
    ax = fig.add_subplot(111, aspect="equal")
    r_mm = head_radius_m * 1000.0
    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(r_mm * np.cos(theta), r_mm * np.sin(theta), color="#2c3e50", lw=1.2)
    for i, dip in enumerate(dipoles):
        pos = np.asarray(dip.get("pos", [0, 0, 0.04]), dtype=float) * 1000.0
        ori = np.asarray(dip.get("ori", [0, 0, 1]), dtype=float)
        amp = float(dip.get("amplitude", 10e-9))
        gof = float(dip.get("gof", 1.0))
        x, y = pos[ax_idx], flip * pos[ay_idx]
        u, v = ori[ax_idx], flip * ori[ay_idx]
        norm = float(np.linalg.norm([u, v])) or 1.0
        scale = 12.0 * (amp / 10e-9) ** (1.0 / 3.0)
        color = "#e74c3c" if gof > 0.9 else "#e67e22"
        ax.arrow(x, y, u / norm * scale, v / norm * scale,
                 head_width=3, head_length=4, fc=color, ec=color,
                 label=f"偶极子{i} gof={gof:.2f}" if len(dipoles) <= 5 else None)
        ax.plot(x, y, "o", color=color, ms=4)
    ax.set_xlabel(f"轴{ax_idx} (mm)")
    ax.set_ylabel(f"轴{ay_idx} (mm)")
    ax.set_title(f"偶极子 {title}（2D 投影示意，非 3D 渲染）")
    if len(dipoles) <= 5:
        ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    return fig


def fig_sensors_2d(ch_pos: np.ndarray, ch_names: Sequence[str]) -> Figure:
    """传感器 2D 分布（头坐标 XY 投影，无需 montage）。"""
    fig = _new_fig()
    ax = fig.add_subplot(111, aspect="equal")
    p = np.asarray(ch_pos, dtype=float) * 1000.0
    ax.scatter(p[:, 0], p[:, 1], s=22, c="#2980b9", zorder=3)
    for xy, name in zip(p[:, :2], ch_names):
        ax.annotate(name, xy, fontsize=6)
    for r in (50, 95):
        theta = np.linspace(0, 2 * np.pi, 200)
        ax.plot(r * np.cos(theta), r * np.sin(theta), color="#95a5a6",
                lw=0.8, ls="--")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title(f"传感器分布（{len(ch_names)} 通道，头坐标投影）")
    fig.tight_layout()
    return fig


def fig_src_cloud(src: Any) -> Figure:
    """源空间点云 2D 投影（XY）+ 各子空间点数；连通性矩阵未计算时的诚实底图。"""
    fig = _new_fig()
    ax = fig.add_subplot(111, aspect="equal")
    total = 0
    srcs = src if isinstance(src, (list, tuple)) else [src]
    for i, s in enumerate(srcs):
        rr = np.asarray(s["rr"], dtype=float) * 1000.0
        ax.scatter(rr[:, 0], rr[:, 1], s=2, alpha=0.5, label=f"源空间{i}: {len(rr)} 点")
        total += len(rr)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title(f"源点分布（共 {total} 源；连通性矩阵需先计算）")
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    return fig


def extract_sensor_xy(info: Any) -> tuple[np.ndarray, list[str]]:
    """从 mne Info 提取 EEG 通道位置（头坐标，单位 m）与名称。"""
    pos, names = [], []
    for ch in info["chs"]:
        if ch["kind"] == 2:  # FIFFV_EEG_CH
            loc = np.asarray(ch["loc"][:3], dtype=float)
            if np.any(loc):
                pos.append(loc)
                names.append(ch["ch_name"])
    return np.asarray(pos), names
