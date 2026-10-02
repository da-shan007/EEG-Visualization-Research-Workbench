__all__ = [
    "generate_synthetic_dataset",
    "compute_band_power_metrics",
    "compute_topography_values",
    "compute_brain_region_activity",
    "apply_preprocessing",
    "remove_artifacts",
    "EEGRecording",
    "load_recording",
    "load_event_file",
    "crop_recording",
    "concatenate_recordings",
    "preprocess_recording",
    "compute_band_features",
    "compute_stft",
    "compute_erp",
    "compare_groups",
    "export_recording",
    "EEGWorkbenchApp",
]

from .core import (
    apply_preprocessing,
    remove_artifacts,
    compute_band_power_metrics,
    compute_brain_region_activity,
    compute_topography_values,
    generate_synthetic_dataset,
)
from .research import (
    EEGRecording,
    compare_groups,
    compute_band_features,
    compute_erp,
    compute_stft,
    concatenate_recordings,
    crop_recording,
    export_recording,
    load_event_file,
    load_recording,
    preprocess_recording,
)


def __getattr__(name):
    if name == "EEGWorkbenchApp":
        from .app import EEGWorkbenchApp
        return EEGWorkbenchApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
