from pathlib import Path

import numpy as np
import pandas as pd

from eeg_workbench_legacy.core import (
    apply_preprocessing,
    compare_channel_features,
    compute_band_power_metrics,
    compute_channel_band_summary,
    compute_brain_region_activity,
    compute_event_epoch_summary,
    compute_topography_values,
    describe_eeg_dataset,
    detect_eeg_columns,
    extract_event_markers,
    generate_synthetic_dataset,
    get_standard_eeg_montage_positions,
    load_eeg_csv,
    remove_artifacts,
)


def test_generate_synthetic_dataset_shapes():
    df = generate_synthetic_dataset(num_channels=8, samples=1000, sample_rate=250)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns[:2]) == ['time', 'Fp1']
    assert df.shape[0] == 1000
    assert df.shape[1] == 9


def test_compute_band_power_metrics_returns_expected_keys():
    df = generate_synthetic_dataset(num_channels=4, samples=512, sample_rate=250)
    metrics = compute_band_power_metrics(df)
    expected = {'alpha', 'beta', 'theta', 'gamma'}
    assert expected.issubset(metrics.keys())
    for key in expected:
        assert isinstance(metrics[key], float)


def test_load_eeg_csv_reads_data_and_time_column(tmp_path):
    path = tmp_path / 'sample.csv'
    pd.DataFrame({
        'time': [0.0, 0.1, 0.2],
        'Fp1': [1.0, 1.5, 1.2],
        'C3': [0.5, 0.8, 0.7],
    }).to_csv(path, index=False)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert df.shape == (3, 3)


def test_load_eeg_csv_supports_realistic_eeg_headers(tmp_path):
    path = tmp_path / 'real_eeg.csv'
    pd.DataFrame({
        'Time(s)': [0.0, 0.1, 0.2],
        'EEG Fp1': [1.0, 1.5, 1.3],
        'EEG-C3': [0.5, 0.7, 0.6],
        'Marker': [10, 11, 12],
    }).to_csv(path, index=False)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert df.shape == (3, 3)


def test_load_eeg_csv_supports_tsv_and_txt_delimited_files(tmp_path):
    path = tmp_path / 'real_eeg.tsv'
    pd.DataFrame({
        'Time(s)': [0.0, 0.1, 0.2],
        'EEG Fp1': [1.0, 1.5, 1.3],
        'EEG-C3': [0.5, 0.7, 0.6],
    }).to_csv(path, index=False, sep='\t')

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert df.shape == (3, 3)


def _write_test_edf(path, channel_names, samples_per_channel, sample_rate=250.0):
    n_channels = len(channel_names)
    physical_min = -1.0
    physical_max = 1.0
    digital_min = -32768
    digital_max = 32767
    data = np.zeros((n_channels, samples_per_channel), dtype=np.float64)
    time = np.arange(samples_per_channel) / sample_rate
    data[0] = np.sin(2 * np.pi * 10 * time)
    data[1] = np.cos(2 * np.pi * 8 * time)

    header = bytearray(256)
    header[0:8] = b'0       '
    header[236:244] = b'1       '
    header[244:252] = b'0.040000'
    header[252:256] = b'0002'

    signal_headers = []
    for idx, name in enumerate(channel_names):
        block = bytearray(256)
        block[0:16] = name.encode('ascii').ljust(16, b' ')
        block[80:88] = b'uV      '
        block[88:96] = f'{physical_min:>8.3f}'.encode('ascii')
        block[96:104] = f'{physical_max:>8.3f}'.encode('ascii')
        block[104:112] = f'{digital_min:>8d}'.encode('ascii')
        block[112:120] = f'{digital_max:>8d}'.encode('ascii')
        block[252:256] = f'{samples_per_channel:>4d}'.encode('ascii')
        signal_headers.append(bytes(block))

    payload = []
    for idx in range(samples_per_channel):
        for ch in range(n_channels):
            scaled = np.clip(np.rint((data[ch, idx] - physical_min) / (physical_max - physical_min) * (digital_max - digital_min) + digital_min), digital_min, digital_max)
            payload.append(np.int16(scaled).tobytes())

    path.write_bytes(header + b''.join(signal_headers) + b''.join(payload))


def test_load_eeg_file_supports_edf(tmp_path):
    path = tmp_path / 'sample.edf'
    _write_test_edf(path, ['Fp1', 'C3'], samples_per_channel=20, sample_rate=250.0)

    df = load_eeg_csv(path)
    assert 'time' in df.columns
    assert {'Fp1', 'C3'}.issubset(df.columns)
    assert len(df) == 20


def test_load_eeg_file_supports_standard_edf_signal_headers(tmp_path):
    path = tmp_path / 'standard.edf'
    channel_names = ['Fp1', 'C3']
    samples_per_channel = 4
    n_channels = len(channel_names)
    header = bytearray(256 + n_channels * 256)
    header[236:244] = b'1       '
    header[244:252] = b'1       '
    header[252:256] = f'{n_channels:>4d}'.encode('ascii')

    signal_header = memoryview(header)[256:]

    def write_field(offset, width, values):
        for idx, value in enumerate(values):
            start = offset + idx * width
            signal_header[start:start + width] = str(value).ljust(width)[:width].encode('ascii')

    write_field(0, 16, channel_names)
    write_field(104 * n_channels, 8, ['-1', '-1'])
    write_field(112 * n_channels, 8, ['1', '1'])
    write_field(120 * n_channels, 8, ['-32768', '-32768'])
    write_field(128 * n_channels, 8, ['32767', '32767'])
    write_field(216 * n_channels, 8, [str(samples_per_channel)] * n_channels)

    payload = b''.join(np.int16(value).tobytes() for value in [0, 100, 200, 300, 400, 500, 600, 700])
    path.write_bytes(header + payload)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert len(df) == samples_per_channel
    assert np.isfinite(df[['Fp1', 'C3']].to_numpy()).all()


def test_load_eeg_file_aligns_channels_with_different_sample_rates(tmp_path):
    path = tmp_path / 'different_rates.edf'
    channel_names = ['Fp1', 'C3']
    sample_counts = [4, 2]
    n_channels = len(channel_names)
    header = bytearray(256 + n_channels * 256)
    header[236:244] = b'1       '
    header[244:252] = b'1       '
    header[252:256] = f'{n_channels:>4d}'.encode('ascii')
    signal_header = memoryview(header)[256:]

    def write_field(offset, width, values):
        for idx, value in enumerate(values):
            start = offset + idx * width
            signal_header[start:start + width] = str(value).ljust(width)[:width].encode('ascii')

    write_field(0, 16, channel_names)
    write_field(104 * n_channels, 8, ['-1', '-1'])
    write_field(112 * n_channels, 8, ['1', '1'])
    write_field(120 * n_channels, 8, ['-32768', '-32768'])
    write_field(128 * n_channels, 8, ['32767', '32767'])
    write_field(216 * n_channels, 8, [str(value) for value in sample_counts])

    payload = b''.join(np.int16(value).tobytes() for value in [0, 100, 200, 300, 400, 500])
    path.write_bytes(header + payload)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert len(df) == 4
    assert np.isfinite(df[['Fp1', 'C3']].to_numpy()).all()


def test_load_eeg_file_reads_available_records_when_payload_is_shorter(tmp_path):
    path = tmp_path / 'short_payload.edf'
    channel_names = ['Fp1', 'C3']
    samples_per_record = 2
    n_channels = len(channel_names)
    header = bytearray(256 + n_channels * 256)
    header[236:244] = b'3       '
    header[244:252] = b'1       '
    header[252:256] = f'{n_channels:>4d}'.encode('ascii')
    signal_header = memoryview(header)[256:]

    def write_field(offset, width, values):
        for idx, value in enumerate(values):
            start = offset + idx * width
            signal_header[start:start + width] = str(value).ljust(width)[:width].encode('ascii')

    write_field(0, 16, channel_names)
    write_field(104 * n_channels, 8, ['-1', '-1'])
    write_field(112 * n_channels, 8, ['1', '1'])
    write_field(120 * n_channels, 8, ['-32768', '-32768'])
    write_field(128 * n_channels, 8, ['32767', '32767'])
    write_field(216 * n_channels, 8, [str(samples_per_record)] * n_channels)

    payload = b''.join(np.int16(value).tobytes() for value in [0, 100, 200, 300])
    path.write_bytes(header + payload)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert len(df) == samples_per_record


def test_load_eeg_csv_handles_nan_and_metadata_columns(tmp_path):
    path = tmp_path / 'nan_eeg.csv'
    pd.DataFrame({
        'Time(s)': [0.0, 0.1, 0.2],
        'EEG Fp1': [1.0, np.nan, 1.4],
        'EEG-C3': [0.6, 0.8, np.nan],
        'Marker': [1, np.nan, 3],
        'Notes': ['a', '', 'b'],
    }).to_csv(path, index=False)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert df.shape[0] == 3
    assert np.isfinite(df[['Fp1', 'C3']].to_numpy()).all()


def test_load_eeg_csv_ignores_malformed_numeric_tokens_in_channel_values(tmp_path):
    path = tmp_path / 'malformed_channel.csv'
    pd.DataFrame({
        'Time(s)': [0.0, 0.1, 0.2, 0.3],
        'Fp1': [1.0, 2.0, 'Fc.', 4.0],
        'C3': [0.5, 0.7, 0.9, 1.1],
        'Trigger': ['None', 'Fc.', 'Cue', 'None'],
    }).to_csv(path, index=False)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1', 'C3']
    assert df['Fp1'].notna().all()
    assert np.isfinite(df[['Fp1', 'C3']].to_numpy()).all()


def test_load_eeg_csv_ignores_malformed_tokens_in_time_and_metadata(tmp_path):
    path = tmp_path / 'malformed_time.csv'
    pd.DataFrame({
        'time': [0.0, 'Fc.', 0.2, 0.3],
        'Fp1': [1.0, 1.1, 'Fc.', 1.3],
        'Trigger': ['None', 'Fc.', 'Cue', 'None'],
    }).to_csv(path, index=False)

    df = load_eeg_csv(path)
    assert list(df.columns) == ['time', 'Fp1']
    assert np.isfinite(df[['time', 'Fp1']].to_numpy()).all()


def test_compute_topography_values_returns_realistic_channel_map():
    df = generate_synthetic_dataset(num_channels=8, samples=512, sample_rate=250)
    values = compute_topography_values(df)
    assert set(values.keys()).issuperset({'Fp1', 'Fp2', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2'})
    assert all(isinstance(v, float) for v in values.values())


def test_compute_topography_values_stays_finite_for_short_data():
    df = pd.DataFrame({'time': [0.0, 0.01], 'Fp1': [1.0, 1.1]})
    values = compute_topography_values(df)
    assert np.isfinite(list(values.values())).all()


def test_compute_brain_region_activity_returns_region_map():
    df = generate_synthetic_dataset(num_channels=8, samples=512, sample_rate=250)
    region_map = compute_brain_region_activity(df)
    assert set(region_map.keys()).issuperset({'frontal', 'central', 'parietal', 'occipital'})
    assert all(isinstance(v, float) for v in region_map.values())


def test_apply_preprocessing_returns_clean_dataset():
    df = generate_synthetic_dataset(num_channels=4, samples=256, sample_rate=250)
    cleaned = apply_preprocessing(df, low_cut=1.0, high_cut=40.0, notch=50.0, artifact_threshold=4.5)
    assert cleaned.shape == df.shape
    assert list(cleaned.columns) == list(df.columns)
    assert np.isfinite(cleaned.drop(columns=['time']).to_numpy()).all()


def test_remove_artifacts_replaces_spikes_and_preserves_shape():
    time = np.arange(100, dtype=float) / 250.0
    signal = np.sin(2 * np.pi * 10 * time)
    signal[50] = 100.0
    signal[51] = -100.0
    df = pd.DataFrame({'time': time, 'Fp1': signal})

    cleaned = remove_artifacts(df)

    assert cleaned.shape == df.shape
    assert abs(cleaned['Fp1'].iloc[50]) < 2.0
    assert abs(cleaned['Fp1'].iloc[51]) < 2.0
    assert np.isfinite(cleaned['Fp1'].to_numpy()).all()


def test_get_standard_eeg_montage_positions_has_realistic_layout():
    montage = get_standard_eeg_montage_positions()
    assert {'Fp1', 'Fp2', 'F3', 'Fz', 'F4', 'C3', 'Cz', 'C4', 'P3', 'Pz', 'P4', 'O1', 'O2'}.issubset(montage)
    assert all(len(pos) == 3 for pos in montage.values())


def test_extract_event_markers_returns_time_label_pairs():
    df = pd.DataFrame({
        'time': [0.0, 0.2, 0.4, 0.6],
        'Marker': [0, 1, 1, 0],
        'Trigger': ['None', 'Cue', 'Cue', 'None'],
    })
    events = extract_event_markers(df)
    assert events[0]['time'] == 0.2
    assert events[0]['label'] == 'Cue'
    assert len(events) == 2


def test_extract_event_markers_ignores_non_numeric_trigger_tokens():
    df = pd.DataFrame({
        'time': [0.0, 0.1, 0.2, 0.3],
        'Fp1': [1.0, 1.1, 1.2, 1.3],
        'Trigger': ['None', 'Fc.', 'Cue', 'None'],
    })
    events = extract_event_markers(df)
    assert events == [{'time': 0.2, 'label': 'Cue'}]


def test_detect_eeg_columns_identifies_time_and_channels():
    df = pd.DataFrame({
        'Time(s)': [0.0, 0.1, 0.2],
        'EEG Fp1': [1.0, 1.2, 1.5],
        'EEG C3': [0.4, 0.6, 0.8],
        'Marker': [0, 1, 0],
        'Notes': ['a', 'b', 'c'],
    })
    detection = detect_eeg_columns(df)
    assert detection['time_column'] == 'Time(s)'
    assert detection['channels'] == ['Fp1', 'C3']
    assert 'Marker' in detection['metadata_columns']


def test_compute_channel_band_summary_returns_per_channel_band_metrics():
    df = generate_synthetic_dataset(num_channels=4, samples=512, sample_rate=250)
    summary = compute_channel_band_summary(df)
    assert set(summary.keys()).issuperset({'Fp1', 'Fp2', 'C3', 'C4'})
    assert all(set(metric.keys()) == {'theta', 'alpha', 'beta', 'gamma'} for metric in summary.values())


def test_compute_event_epoch_summary_returns_window_metrics():
    df = generate_synthetic_dataset(num_channels=4, samples=512, sample_rate=250)
    events = [{'time': 0.5, 'label': 'Cue'}, {'time': 1.2, 'label': 'Stimulus'}]
    summary = compute_event_epoch_summary(df, events, window_sec=0.5)
    assert isinstance(summary, list)
    assert len(summary) == 2
    assert set(summary[0].keys()).issuperset({'time', 'label', 'alpha', 'beta'})


def test_compare_channel_features_returns_delta_metrics():
    df = generate_synthetic_dataset(num_channels=4, samples=512, sample_rate=250)
    summary = compare_channel_features(df, 'Fp1', 'C3')
    assert set(summary.keys()).issuperset({'reference', 'comparison', 'delta_alpha', 'delta_beta'})
    assert summary['reference'] == 'Fp1'
    assert summary['comparison'] == 'C3'


def test_describe_eeg_dataset_includes_channels_and_events():
    df = pd.DataFrame({
        'time': [0.0, 0.1, 0.2],
        'Fp1': [1.0, 2.0, 1.5],
        'C3': [0.5, 1.0, 0.7],
        'Marker': [0, 1, 0],
        'Label': ['None', 'Cue', 'None'],
    })
    summary = describe_eeg_dataset(df)
    assert summary['channel_count'] == 2
    assert 'Cue' in summary['event_labels']
    assert summary['sample_count'] == 3
