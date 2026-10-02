"""源定位与脑区分析参数模型"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from enum import Enum
import numpy as np


class HeadModelType(Enum):
    """头模型类型"""
    SPHERICAL = "spherical"           # 球形模型
    BEM = "bem"                       # 边界元模型
    FEM = "fem"                       # 有限元模型
    MULTI_LAYER = "multi_layer"       # 多层球模型


class SourceSpaceType(Enum):
    """源空间类型"""
    SURFACE = "surface"               # 皮层面源空间
    VOLUME = "volume"                 # 体积源空间
    MIXED = "mixed"                   # 混合源空间
    DISCRETE = "discrete"             # 离散源空间 (用于偶极子拟合)


class InverseMethod(Enum):
    """逆向求解方法"""
    # 偶极子拟合
    DIPOLE_FIT = "dipole_fit"         # 等效电流偶极子拟合
    # 分布式源模型
    MNE = "mne"                       # 最小范数估计
    dSPM = "dspm"                     # 动态统计参数映射
    sLORETA = "sloreta"               # 标准化 LORETA
    eLORETA = "eloreta"               # 精确 LORETA
    LCMV = "lcmv"                     # 线性约束最小方差波束成形
    DICS = "dics"                     # 动态成像相干波束成形
    # 稀疏贝叶斯
    MCE = "mce"                       # 最大熵 / 稀疏贝叶斯
    GAMMA_MAP = "gamma_map"           # Gamma MAP
    # 其他
    SAM = "sam"                       # 合成孔径磁强计
    MUSIC = "music"                   # 多信号分类


class CoordinateFrame(Enum):
    """坐标系"""
    HEAD = "head"                     # 头部坐标系
    MRI = "mri"                       # MRI 体素坐标
    FS_TAL = "fs_tal"                 # FreeSurfer Talairach
    MNI_TAL = "mni_tal"               # MNI Talairach
    MNI = "mni"                       # MNI 标准空间


@dataclass
class HeadModelParams:
    """头模型构建参数"""
    model_type: HeadModelType = HeadModelType.BEM
    
    # 主体标识 (用于 fsaverage 等标准模型)
    subject: str = "fsaverage"
    subjects_dir: str | None = None
    
    # BEM 参数
    conductivity: tuple[float, ...] = (0.3, 0.006, 0.3)  # (头皮, 颅骨, 脑)
    bem_surfaces: list[str] | None = None  # ['inner_skull', 'outer_skull', 'outer_skin']
    
    # 球形模型参数
    sphere_radius: float | None = None  # 单位 m
    sphere_center: tuple[float, float, float] | None = None
    
    # MRI 体素参数
    mri_resolution: float = 0.005  # 5mm 体素
    
    # 标准模型文件路径
    trans_file: str | None = None  # 头部-MRI 变换文件
    
    def validate(self) -> list[str]:
        errors = []
        if self.model_type == HeadModelType.BEM:
            n_layers = len(self.conductivity)
            if n_layers not in (1, 3):
                errors.append("BEM 导电率必须是 1 层或 3 层")
            elif n_layers == 1 and self.bem_surfaces is None:
                # 单层 BEM 没有默认表面可用，必须显式给出表面列表
                errors.append(
                    "BEM 单层导电率必须显式指定 bem_surfaces"
                    "（导电率必须是 1 层或 3 层，单层时需配合表面配置）"
                )
        if self.model_type == HeadModelType.SPHERICAL and self.sphere_radius is None:
            errors.append("球形模型需要指定半径")
        return errors


@dataclass
class ForwardModelParams:
    """前向模型 (导场矩阵) 参数"""
    # 源空间
    source_space_type: SourceSpaceType = SourceSpaceType.SURFACE
    spacing: str | float = "oct6"  # 皮层面间距: 'oct6', 'oct5', 'ico5', 或体积间距 mm
    add_dist: bool = True  # 计算源点到传感器距离
    
    # 导场计算
    meg: bool = False
    eeg: bool = True
    mindist: float = 5e-3  # 最小源-传感器距离 (m)
    
    # 并行计算
    n_jobs: int = -1
    
    # 固定朝向
    fixed: bool = True  # 固定法向朝向 (皮层面)
    use_cps: bool = True  # 皮层面补偿


@dataclass
class InverseParams:
    """逆向求解参数"""
    method: InverseMethod = InverseMethod.MNE
    
    # 正则化参数
    lambda2: float = 1.0 / 9.0  # SNR=3 对应的 lambda2
    snr: float = 3.0
    
    # 方法特定参数
    # MNE/dSPM/sLORETA
    depth: float | None = 0.8  # 深度加权
    loose: float = 0.2  # 松散方向约束
    
    # LCMV/DICS
    reg: float = 0.05  # 正则化
    weight_norm: bool = True
    
    # Beamformer
    rank: dict | None = None
    reduce_rank: bool = True
    
    # 时间窗
    tmin: float | None = None
    tmax: float | None = None
    
    # 频带 (DICS)
    fmin: float | None = None
    fmax: float | None = None
    csd_method: str = "multitaper"  # 'multitaper', 'morlet', 'fourier'
    
    # 输出选项
    pick_ori: Literal["normal", "max-power", "vector"] = "normal"

    def validate(self, method: InverseMethod) -> list[str]:
        errors = []
        if method in (InverseMethod.LCMV, InverseMethod.DICS):
            if self.fmin is None or self.fmax is None:
                errors.append("波束成形需要指定频带 fmin/fmax")
        return errors


@dataclass
class DipoleFitParams:
    """偶极子拟合参数"""
    # 拟合策略
    method: Literal["least_squares", "nelder_mead", "differential_evolution"] = "least_squares"
    
    # 初始猜测
    initial_pos: np.ndarray | None = None  # (3,) 米
    initial_ori: np.ndarray | None = None  # (3,) 单位向量
    
    # 约束
    head_center: np.ndarray | None = None
    head_radius: float | None = None
    
    # 搜索范围
    pos_bounds: tuple[tuple[float, float], ...] | None = None
    
    # 评价
    goodness_of_fit_threshold: float = 0.9
    max_dipoles: int = 1
    
    # 时间窗
    tmin: float | None = None
    tmax: float | None = None


@dataclass
class SourceAnalysisResult:
    """源分析结果容器"""
    # 源估计
    stc: Any | None = None  # mne.SourceEstimate
    
    # 源空间
    src: Any | None = None  # mne.SourceSpaces
    
    # 前向模型
    fwd: Any | None = None  # mne.ForwardSolution
    
    # 逆向算子
    inv: Any | None = None  # mne.InverseOperator
    
    # 偶极子拟合结果
    dipoles: list[dict] | None = None
    
    # 元信息
    method: str = ""
    params: Any = None
    processing_time_ms: float = 0.0
    
    # 3D 可视化数据
    vertices: np.ndarray | None = None
    faces: np.ndarray | None = None
    values: np.ndarray | None = None


@dataclass
class BrainRegionParams:
    """脑区标签与激活提取参数"""
    # 图谱选择
    atlas: Literal["aparc", "aparc.a2009s", "aparc.DKTatlas", "HCPMMP1", "BA"] = "aparc"
    hemi: Literal["lh", "rh", "both"] = "both"
    
    # 提取方式
    extract_mode: Literal["mean", "max", "sum", "pca"] = "mean"
    
    # 时间窗
    tmin: float | None = None
    tmax: float | None = None
    
    # 阈值
    threshold: float | None = None  # 统计阈值
    p_threshold: float = 0.05
    
    # 统计检验
    statistical_test: Literal["ttest", "permutation", "cluster"] = "cluster"
    n_permutations: int = 1000


@dataclass
class ConnectivitySourceParams:
    """源空间连通性参数"""
    method: Literal["coh", "plv", "pli", "wpli", "gc"] = "coh"
    fmin: float = 8.0
    fmax: float = 13.0
    tmin: float | None = None
    tmax: float | None = None
    mode: Literal["multitaper", "fourier", "cwt_morlet"] = "multitaper"


# ---- 常用预设 ----
STANDARD_HEAD_MODELS = {
    "fsaverage_bem": HeadModelParams(
        model_type=HeadModelType.BEM,
        subject="fsaverage",
        conductivity=(0.3, 0.006, 0.3)
    ),
    "single_sphere": HeadModelParams(
        model_type=HeadModelType.SPHERICAL,
        sphere_radius=0.1,  # 10cm
        sphere_center=(0.0, 0.0, 0.04)
    ),
    "three_layer_bem": HeadModelParams(
        model_type=HeadModelType.BEM,
        conductivity=(0.33, 0.0042, 0.33)
    ),
}


def create_head_model_params(preset: str = "fsaverage_bem", **overrides) -> HeadModelParams:
    if preset not in STANDARD_HEAD_MODELS:
        raise ValueError(f"未知预设: {preset}")
    params = STANDARD_HEAD_MODELS[preset]
    for k, v in overrides.items():
        if hasattr(params, k):
            setattr(params, k, v)
    return params


def create_inverse_params(method: InverseMethod, **overrides) -> InverseParams:
    params = InverseParams(method=method)
    for k, v in overrides.items():
        if hasattr(params, k):
            setattr(params, k, v)
    return params


def create_forward_params(**overrides) -> ForwardModelParams:
    params = ForwardModelParams()
    for k, v in overrides.items():
        if hasattr(params, k):
            setattr(params, k, v)
    return params


@dataclass
class HeadModelResult:
    """头模型构建结果"""
    model: Any  # mne.HeadModel / mne.bem.ConductorModel
    subject: str
    model_type: HeadModelType
    processing_time_ms: float
    params_used: HeadModelParams


@dataclass
class ForwardModelResult:
    """前向模型结果"""
    fwd: Any  # mne.ForwardSolution
    src: Any  # mne.SourceSpaces
    processing_time_ms: float
    params_used: ForwardModelParams
    leadfield_info: dict


@dataclass
class InverseSolutionResult:
    """逆向求解结果"""
    stc: Any  # mne.SourceEstimate
    inv: Any  # mne.InverseOperator
    processing_time_ms: float
    params_used: InverseParams
    method: str


@dataclass
class DipoleFitResult:
    """偶极子拟合结果"""
    dipoles: list[dict]
    processing_time_ms: float
    params_used: DipoleFitParams