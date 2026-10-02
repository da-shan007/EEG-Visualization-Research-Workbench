"""EEG Workbench 主包"""
__version__ = "0.1.0"
__author__ = "Research Team"

from .core.config import get_config, get_config_manager
from .core.events import get_event_bus, EventBus, EventType, DomainEvent
from .core.base import ObservableModel, ViewModelBase, Command, async_slot

from .models.dataset import (
    EEGDataset, ChannelInfo, Event, Montage, EpochData,
    ChannelType, ReferenceType
)
from .models.metadata import (
    DatasetMetadata, SubjectInfo, ExperimentCondition,
    Sex, GroupType, Handedness
)
from .models.preprocessing import (
    FilterParams, ReferenceParams, ResampleParams, ICAParams,
    BadChannelInterpolationParams,
    FilterType, ReferenceType as PreprocReferenceType,
    ResampleMethod, ICAComponentType, InterpolationMethod,
    FILTER_PRESETS, REFERENCE_PRESETS,
    create_filter_params, create_reference_params
)
from .models.features import (
    BandPowerParams, TimeFrequencyParams, ConnectivityParams, NonlinearParams,
    SpectralMethod, TimeFrequencyMethod, ConnectivityMethod, NonlinearMeasure,
    FeatureExtractionResult, STANDARD_BANDS, create_band_power_params
)
from .models.erp import (
    ERPAnalysisParams, ERDSParams, EpochParams, ERPResult, ERDSResult,
    ERPComponent, BaselineMode, DEFAULT_ERP_PEAK_WINDOWS, DEFAULT_ERP_POLARITY,
    create_erp_params, create_erds_params
)
from .models.source import (
    HeadModelParams, ForwardModelParams, InverseParams, DipoleFitParams,
    HeadModelType, SourceSpaceType, InverseMethod,
    HeadModelResult, ForwardModelResult, InverseSolutionResult,
    STANDARD_HEAD_MODELS,
    create_head_model_params, create_inverse_params, create_forward_params
)
from .models.statistics import (
    StatisticsParams, TTestParams, ANOVAParams, NonparametricParams,
    PermutationParams, CorrelationParams,
    StatisticalTest, MultipleComparisonCorrection, EffectSize,
    ComparisonResult, CorrelationResult, StatisticsResult,
    create_statistics_params
)
from .models.visualization import (
    PlotConfig, WaveformPlotConfig, SpectralPlotConfig, TFRPlotConfig,
    ConnectivityPlotConfig, StatisticalPlotConfig, SourcePlotConfig,
    ReportConfig, PlotType, PlotBackend, ExportFormat,
    WAVEFORM_PRESET, SPECTRAL_PRESET, TFR_PRESET,
    CONNECTIVITY_PRESET, STATISTICAL_PRESET, SOURCE_PRESET,
    REPORT_PRESET, create_plot_config
)

from .services.io import ReaderFactory, LoadResult
from .services.events import EventEditor, import_vmrk, import_tsv, export_vmrk, export_tsv
from .services.segmentation import crop_dataset, concatenate_datasets, CropResult
from .services.preprocessing import (
    FilterService, ReferenceService, ResampleService, ICAService, InterpolationService,
    apply_filter, apply_reference, apply_resample, run_ica, apply_ica, interpolate_bads,
    FilterResult, ReferenceResult, ResampleResult, ICAResult, InterpolationResult
)
from .services.features import (
    SpectralService, TimeFrequencyService, ConnectivityService, NonlinearService,
    compute_band_power, compute_tfr, compute_connectivity, compute_nonlinear_features,
    BandPowerResult, TFRResult, ConnectivityResult, NonlinearResult
)
from .services.erp import (
    ERPService, ERDSService, PeakDetector, TopomapService,
    run_erp_analysis, run_erds_analysis, detect_erp_peaks, plot_topomap,
    ERPAnalysisResult, ERDSAnalysisResult, PeakResult
)
from .services.source import (
    HeadModelService, ForwardModelService, InverseService, DipoleFitService, SourceVisualization3D,
    build_head_model, compute_forward_solution, compute_inverse_solution, fit_dipoles,
    HeadModelResult, ForwardModelResult, InverseSolutionResult, DipoleFitResult
)
from .services.statistics import (
    StatisticalTestService, PermutationService, CorrelationService,
    MultipleComparisonService, EffectSizeService,
    run_ttest, run_anova, run_nonparametric,
    run_permutation_test, run_cluster_permutation,
    compute_correlation, compute_partial_correlation,
    correct_pvalues, cluster_correction,
    compute_effect_size,
    TTestResult, PermutationResult, CorrelationResultWrap,
    CorrectionResult, EffectSizeResult
)
from .services.visualization import (
    PlottingService, ReportGenerator, ExportService,
    create_figure, plot_waveform, plot_spectral, plot_tfr,
    generate_report, generate_html_report,
    export_figure, export_data, export_report
)

from .viewmodels.data_management_vm import DataManagementViewModel
from .viewmodels.preprocessing_vm import PreprocessingViewModel
from .viewmodels.features_vm import FeaturesViewModel
from .viewmodels.erp_vm import ERPViewModel
from .viewmodels.source_vm import SourceViewModel
from .viewmodels.statistics_vm import StatisticsViewModel
from .viewmodels.visualization_vm import VisualizationViewModel

from .views.data_management import (
    DatasetLoaderWidget, MetadataEditorWidget,
    EventEditorWidget, SegmentationWidget
)
from .views.preprocessing import (
    FilterWidget, ReferenceWidget, ResampleWidget,
    ICAWidget, InterpolationWidget, PreprocessingMainWidget
)
from .views.features import (
    BandPowerWidget, TimeFrequencyWidget, ConnectivityWidget,
    NonlinearWidget, FeaturesMainWidget
)
from .views.erp import (
    ERPConditionWidget, ERPPeakWidget, ERDSWidget, ERPMainWidget
)
from .views.source import (
    HeadModelWidget, ForwardModelWidget, InverseSolutionWidget,
    DipoleFitWidget, Visualization3DWidget, SourceMainWidget
)
from .views.statistics import (
    TTestWidget, ANOVAWidget, NonparametricWidget, PermutationWidget,
    CorrelationWidget, CorrectionWidget, EffectSizeWidget, StatisticsMainWidget
)
from .views.visualization import (
    WaveformWidget, SpectralWidget, TFRWidget, ConnectivityWidget,
    StatisticalWidget, SourceVisualizationWidget, ReportWidget, VisualizationMainWidget
)

from .utils import (
    standard_montage_names, load_elp, load_csd,
    validate_dataset_complete, ValidationResult
)

__all__ = [
    # Core
    "get_config", "get_config_manager",
    "get_event_bus", "EventBus", "EventType", "DomainEvent",
    "ObservableModel", "ViewModelBase", "Command", "async_slot",
    # Models
    "EEGDataset", "ChannelInfo", "Event", "Montage", "EpochData",
    "ChannelType", "ReferenceType",
    "DatasetMetadata", "SubjectInfo", "ExperimentCondition",
    "Sex", "GroupType", "Handedness",
    # Preprocessing Models
    "FilterParams", "ReferenceParams", "ResampleParams", "ICAParams",
    "BadChannelInterpolationParams",
    "FilterType", "PreprocReferenceType", "ResampleMethod", "ICAComponentType", "InterpolationMethod",
    "FILTER_PRESETS", "REFERENCE_PRESETS",
    "create_filter_params", "create_reference_params",
    # Features Models
    "BandPowerParams", "TimeFrequencyParams", "ConnectivityParams", "NonlinearParams",
    "SpectralMethod", "TimeFrequencyMethod", "ConnectivityMethod", "NonlinearMeasure",
    "FeatureExtractionResult", "STANDARD_BANDS", "create_band_power_params",
    # ERP Models
    "ERPAnalysisParams", "ERDSParams", "EpochParams", "ERPResult", "ERDSResult",
    "ERPComponent", "BaselineMode", "DEFAULT_ERP_PEAK_WINDOWS", "DEFAULT_ERP_POLARITY",
    "create_erp_params", "create_erds_params",
    # Source Models
    "HeadModelParams", "ForwardModelParams", "InverseParams", "DipoleFitParams",
    "HeadModelType", "SourceSpaceType", "InverseMethod",
    "HeadModelResult", "ForwardModelResult", "InverseSolutionResult",
    "STANDARD_HEAD_MODELS",
    "create_head_model_params", "create_inverse_params", "create_forward_params",
    # Statistics Models
    "StatisticsParams", "TTestParams", "ANOVAParams", "NonparametricParams",
    "PermutationParams", "CorrelationParams",
    "StatisticalTest", "MultipleComparisonCorrection", "EffectSize",
    "ComparisonResult", "CorrelationResult", "StatisticsResult",
    "create_statistics_params",
    # Visualization Models
    "PlotConfig", "WaveformPlotConfig", "SpectralPlotConfig", "TFRPlotConfig",
    "ConnectivityPlotConfig", "StatisticalPlotConfig", "SourcePlotConfig",
    "ReportConfig", "PlotType", "PlotBackend", "ExportFormat",
    "WAVEFORM_PRESET", "SPECTRAL_PRESET", "TFR_PRESET",
    "CONNECTIVITY_PRESET", "STATISTICAL_PRESET", "SOURCE_PRESET",
    "REPORT_PRESET", "create_plot_config",
    # Services
    "ReaderFactory", "LoadResult",
    "EventEditor", "import_vmrk", "import_tsv", "export_vmrk", "export_tsv",
    "crop_dataset", "concatenate_datasets", "CropResult",
    # Preprocessing Services
    "FilterService", "ReferenceService", "ResampleService", "ICAService", "InterpolationService",
    "apply_filter", "apply_reference", "apply_resample", "run_ica", "apply_ica", "interpolate_bads",
    "FilterResult", "ReferenceResult", "ResampleResult", "ICAResult", "InterpolationResult",
    # Features Services
    "SpectralService", "TimeFrequencyService", "ConnectivityService", "NonlinearService",
    "compute_band_power", "compute_tfr", "compute_connectivity", "compute_nonlinear_features",
    "BandPowerResult", "TFRResult", "ConnectivityResult", "NonlinearResult",
    # ERP Services
    "ERPService", "ERDSService", "PeakDetector", "TopomapService",
    "run_erp_analysis", "run_erds_analysis", "detect_erp_peaks", "plot_topomap",
    "ERPAnalysisResult", "ERDSAnalysisResult", "PeakResult",
    # Source Services
    "HeadModelService", "ForwardModelService", "InverseService", "DipoleFitService", "SourceVisualization3D",
    "build_head_model", "compute_forward_solution", "compute_inverse_solution", "fit_dipoles",
    "HeadModelResult", "ForwardModelResult", "InverseSolutionResult", "DipoleFitResult",
    # Statistics Services
    "StatisticalTestService", "PermutationService", "CorrelationService",
    "MultipleComparisonService", "EffectSizeService",
    "run_ttest", "run_anova", "run_nonparametric",
    "run_permutation_test", "run_cluster_permutation",
    "compute_correlation", "compute_partial_correlation",
    "correct_pvalues", "cluster_correction",
    "compute_effect_size",
    "TTestResult", "PermutationResult", "CorrelationResultWrap",
    "CorrectionResult", "EffectSizeResult",
    # Visualization Services
    "PlottingService", "ReportGenerator", "ExportService",
    "create_figure", "plot_waveform", "plot_spectral", "plot_tfr",
    "generate_report", "generate_html_report",
    "export_figure", "export_data", "export_report",
    # ViewModels
    "DataManagementViewModel", "PreprocessingViewModel", "FeaturesViewModel", "ERPViewModel", "SourceViewModel", "StatisticsViewModel", "VisualizationViewModel",
    # Views
    "DatasetLoaderWidget", "MetadataEditorWidget",
    "EventEditorWidget", "SegmentationWidget",
    "FilterWidget", "ReferenceWidget", "ResampleWidget",
    "ICAWidget", "InterpolationWidget", "PreprocessingMainWidget",
    "BandPowerWidget", "TimeFrequencyWidget", "ConnectivityWidget",
    "NonlinearWidget", "FeaturesMainWidget",
    "ERPConditionWidget", "ERPPeakWidget", "ERDSWidget", "ERPMainWidget",
    "HeadModelWidget", "ForwardModelWidget", "InverseSolutionWidget",
    "DipoleFitWidget", "Visualization3DWidget", "SourceMainWidget",
    "TTestWidget", "ANOVAWidget", "NonparametricWidget", "PermutationWidget",
    "CorrelationWidget", "CorrectionWidget", "EffectSizeWidget", "StatisticsMainWidget",
    "WaveformWidget", "SpectralWidget", "TFRWidget", "ConnectivityWidget",
    "StatisticalWidget", "SourceVisualizationWidget", "ReportWidget", "VisualizationMainWidget",
    # Utils
    "standard_montage_names", "load_elp", "load_csd",
    "validate_dataset_complete", "ValidationResult",
]