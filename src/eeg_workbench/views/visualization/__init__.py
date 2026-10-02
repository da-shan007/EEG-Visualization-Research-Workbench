"""可视化模块 Views 导出"""
from .visualization_main_widget import VisualizationMainWidget
from .waveform_widget import WaveformWidget
from .spectral_widget import SpectralWidget
from .tfr_widget import TFRWidget
from .connectivity_widget import ConnectivityWidget
from .statistical_widget import StatisticalWidget
from .source_widget import SourceVisualizationWidget
from .report_widget import ReportWidget

__all__ = [
    "VisualizationMainWidget",
    "WaveformWidget",
    "SpectralWidget",
    "TFRWidget",
    "ConnectivityWidget",
    "StatisticalWidget",
    "SourceVisualizationWidget",
    "ReportWidget",
]