"""Views 包导出"""
from .data_management.dataset_loader_widget import DatasetLoaderWidget
from .data_management.metadata_editor import MetadataEditorWidget
from .data_management.event_editor_widget import EventEditorWidget
from .data_management.segmentation_widget import SegmentationWidget

from .preprocessing import (
    FilterWidget, ReferenceWidget, ResampleWidget,
    ICAWidget, InterpolationWidget, PreprocessingMainWidget
)

from .features import (
    BandPowerWidget, TimeFrequencyWidget, ConnectivityWidget as FeaturesConnectivityWidget,
    NonlinearWidget, FeaturesMainWidget
)

from .erp import (
    ERPConditionWidget, ERPPeakWidget, ERDSWidget, ERPMainWidget
)

from .source import (
    HeadModelWidget, ForwardModelWidget, InverseSolutionWidget,
    DipoleFitWidget, Visualization3DWidget, SourceMainWidget
)

from .statistics import (
    TTestWidget, ANOVAWidget, NonparametricWidget, PermutationWidget,
    CorrelationWidget, CorrectionWidget, EffectSizeWidget, StatisticsMainWidget
)

from .visualization import (
    WaveformWidget, SpectralWidget, TFRWidget, ConnectivityWidget,
    StatisticalWidget, SourceVisualizationWidget, ReportWidget, VisualizationMainWidget
)

__all__ = [
    "DatasetLoaderWidget",
    "MetadataEditorWidget",
    "EventEditorWidget",
    "SegmentationWidget",
    "FilterWidget",
    "ReferenceWidget",
    "ResampleWidget",
    "ICAWidget",
    "InterpolationWidget",
    "PreprocessingMainWidget",
    "BandPowerWidget",
    "TimeFrequencyWidget",
    "FeaturesConnectivityWidget",
    "NonlinearWidget",
    "FeaturesMainWidget",
    "ERPConditionWidget", "ERPPeakWidget", "ERDSWidget", "ERPMainWidget",
    "HeadModelWidget", "ForwardModelWidget", "InverseSolutionWidget",
    "DipoleFitWidget", "Visualization3DWidget", "SourceMainWidget",
    "TTestWidget", "ANOVAWidget", "NonparametricWidget", "PermutationWidget",
    "CorrelationWidget", "CorrectionWidget", "EffectSizeWidget", "StatisticsMainWidget",
    "WaveformWidget", "SpectralWidget", "TFRWidget", "ConnectivityWidget",
    "StatisticalWidget", "SourceVisualizationWidget", "ReportWidget", "VisualizationMainWidget",
]