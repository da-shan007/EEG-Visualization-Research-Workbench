"""预处理模块 Views 导出"""
from .filter_widget import FilterWidget
from .reference_widget import ReferenceWidget
from .resample_widget import ResampleWidget
from .ica_widget import ICAWidget
from .interpolation_widget import InterpolationWidget
from .preprocessing_main_widget import PreprocessingMainWidget

__all__ = [
    "FilterWidget",
    "ReferenceWidget",
    "ResampleWidget",
    "ICAWidget",
    "InterpolationWidget",
    "PreprocessingMainWidget",
]