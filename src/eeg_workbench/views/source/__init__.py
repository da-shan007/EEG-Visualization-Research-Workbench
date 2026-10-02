"""源定位模块 Views 导出"""
from .source_main_widget import SourceMainWidget
from .head_model_widget import HeadModelWidget
from .forward_widget import ForwardModelWidget
from .inverse_widget import InverseSolutionWidget
from .dipole_widget import DipoleFitWidget
from .visualization_3d_widget import Visualization3DWidget

__all__ = [
    "SourceMainWidget",
    "HeadModelWidget",
    "ForwardModelWidget",
    "InverseSolutionWidget",
    "DipoleFitWidget",
    "Visualization3DWidget",
]