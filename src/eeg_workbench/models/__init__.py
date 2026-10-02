"""领域模型包：纯数据结构 + 业务规则，无 UI/IO 依赖。"""
from .dataset import EEGDataset, ChannelInfo, Event, Montage, EpochData
from .metadata import SubjectInfo, ExperimentCondition, DatasetMetadata
from .preprocessing import (
    FilterParams, ReferenceParams, ResampleParams, ICAParams,
    BadChannelInterpolationParams,
    FilterType, ReferenceType, ResampleMethod, ICAComponentType, InterpolationMethod,
    FILTER_PRESETS, REFERENCE_PRESETS,
    create_filter_params, create_reference_params
)
from .features import (
    BandPowerParams, TimeFrequencyParams, ConnectivityParams, NonlinearParams,
    SpectralMethod, TimeFrequencyMethod, ConnectivityMethod, NonlinearMeasure,
    FeatureExtractionResult, STANDARD_BANDS, create_band_power_params
)
from .erp import (
    ERPAnalysisParams, ERDSParams, EpochParams, ERPResult, ERDSResult,
    ERPComponent, BaselineMode, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY,
    create_erp_params, create_erds_params
)
from .source import (
    HeadModelParams, ForwardModelParams, InverseParams, DipoleFitParams,
    HeadModelType, SourceSpaceType, InverseMethod,
    HeadModelResult, ForwardModelResult, InverseSolutionResult,
    STANDARD_HEAD_MODELS,
    create_head_model_params, create_inverse_params, create_forward_params
)
from .statistics import (
    StatisticsParams, TTestParams, ANOVAParams, NonparametricParams,
    PermutationParams, CorrelationParams,
    StatisticalTest, MultipleComparisonCorrection, EffectSize,
    ComparisonResult, CorrelationResult, StatisticsResult,
    create_statistics_params
)
from .visualization import (
    PlotConfig, WaveformPlotConfig, SpectralPlotConfig, TFRPlotConfig,
    ConnectivityPlotConfig, StatisticalPlotConfig, SourcePlotConfig,
    ReportConfig, PlotType, PlotBackend, ExportFormat, TFRParams,
    WAVEFORM_PRESET, SPECTRAL_PRESET, TFR_PRESET,
    CONNECTIVITY_PRESET, STATISTICAL_PRESET, SOURCE_PRESET,
    REPORT_PRESET, create_plot_config
)

__all__ = [
    "EEGDataset",
    "ChannelInfo",
    "Event",
    "Montage",
    "EpochData",
    "SubjectInfo",
    "ExperimentCondition",
    "DatasetMetadata",
    "FilterParams", "ReferenceParams", "ResampleParams", "ICAParams",
    "BadChannelInterpolationParams",
    "FilterType", "ReferenceType", "ResampleMethod", "ICAComponentType", "InterpolationMethod",
    "FILTER_PRESETS", "REFERENCE_PRESETS",
    "create_filter_params", "create_reference_params",
    "BandPowerParams", "TimeFrequencyParams", "ConnectivityParams", "NonlinearParams",
    "SpectralMethod", "TimeFrequencyMethod", "ConnectivityMethod", "NonlinearMeasure",
    "FeatureExtractionResult", "STANDARD_BANDS", "create_band_power_params",
    "ERPAnalysisParams", "ERDSParams", "EpochParams", "ERPResult", "ERDSResult",
    "ERPComponent", "BaselineMode", "DEFAULT_ERP_PEAK_WINDOWS", "DEFAULT_ERP_POLARITY",
    "create_erp_params", "create_erds_params",
    "HeadModelParams", "ForwardModelParams", "InverseParams", "DipoleFitParams",
    "HeadModelType", "SourceSpaceType", "InverseMethod",
    "HeadModelResult", "ForwardModelResult", "InverseSolutionResult",
    "STANDARD_HEAD_MODELS",
    "create_head_model_params", "create_inverse_params", "create_forward_params",
    "StatisticsParams", "TTestParams", "ANOVAParams", "NonparametricParams",
    "PermutationParams", "CorrelationParams",
    "StatisticalTest", "MultipleComparisonCorrection", "EffectSize",
    "ComparisonResult", "CorrelationResult", "StatisticsResult",
    "create_statistics_params",
    "PlotConfig", "WaveformPlotConfig", "SpectralPlotConfig", "TFRPlotConfig",
    "ConnectivityPlotConfig", "StatisticalPlotConfig", "SourcePlotConfig",
    "TFRParams",
    "ReportConfig", "PlotType", "PlotBackend", "ExportFormat",
    "WAVEFORM_PRESET", "SPECTRAL_PRESET", "TFR_PRESET",
    "CONNECTIVITY_PRESET", "STATISTICAL_PRESET", "SOURCE_PRESET",
    "REPORT_PRESET", "create_plot_config",
]