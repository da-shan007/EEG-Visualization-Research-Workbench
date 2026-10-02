import numpy as np
import pandas as pd

from eeg_workbench_legacy.research import (
    EEGRecording,
    compare_groups,
    compute_band_features,
    compute_erp,
    concatenate_recordings,
    crop_recording,
    load_event_file,
    load_recording,
)


def make_recording(offset=0.0):
    time = np.arange(500, dtype=float) / 250.0 + offset
    return EEGRecording(
        pd.DataFrame({
            'time': time,
            'Fp1': np.sin(2 * np.pi * 10 * time),
            'C3': np.cos(2 * np.pi * 6 * time),
        }),
        metadata={'subject': 'S01'},
        events=[{'time': offset + 0.5, 'label': 'Cue'}],
    )


def test_recording_crop_and_concatenate():
    recording = make_recording()
    cropped = crop_recording(recording, 0.2, 0.8)
    combined = concatenate_recordings([cropped, cropped])

    assert cropped.data['time'].iloc[0] >= 0.2
    assert len(combined.data) == len(cropped.data) * 2
    assert combined.data['time'].is_monotonic_increasing


def test_band_features_include_absolute_relative_and_log_power():
    features = compute_band_features(make_recording())

    assert {'delta', 'theta', 'alpha', 'beta', 'gamma'}.issubset(set(features['band']))
    assert {'absolute_power', 'relative_power', 'log_power'}.issubset(features.columns)
    assert np.isfinite(features[['absolute_power', 'relative_power', 'log_power']].to_numpy()).all()


def test_erp_averages_matching_events():
    erp = compute_erp(make_recording(), 'Cue', tmin=-0.1, tmax=0.2)

    assert list(erp.columns) == ['time', 'Fp1', 'C3']
    assert len(erp) > 0


def test_event_file_and_csv_recording_import(tmp_path):
    data_path = tmp_path / 'sample.csv'
    event_path = tmp_path / 'events.tsv'
    make_recording().data.to_csv(data_path, index=False)
    pd.DataFrame({'time': [0.5], 'label': ['Cue']}).to_csv(event_path, sep='\t', index=False)

    recording = load_recording(data_path)
    events = load_event_file(event_path)

    assert recording.channels == ['Fp1', 'C3']
    assert events == [{'time': 0.5, 'label': 'Cue'}]


def test_group_comparison_returns_statistics():
    result = compare_groups({'control': [1, 2, 3, 4], 'patient': [4, 5, 6, 7]})

    assert result['method'] == 'ttest'
    assert 0 <= result['p_value'] <= 1
