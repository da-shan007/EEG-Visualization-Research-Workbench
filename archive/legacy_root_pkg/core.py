from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


def _normalize_eeg_column_name(column_name: object) -> str:
    """Normalize common EEG CSV headers to readable channel names."""
    text = str(column_name).strip().replace('\ufeff', '')
    if not text:
        return ''

    lowered = text.lower()
    if lowered in {'time', 'timestamp', 'time(s)', 'seconds', 'sec', 't'}:
        return 'time'
    if any(token in lowered for token in ['marker', 'trigger', 'event', 'label', 'status', 'condition', 'epoch', 'stimulus']):
        return ''

    cleaned = text
    cleaned = re.sub(r'(?i)^.*?\b(?:eeg|channel|ch)\b\s*[:\-_]?\s*', '', cleaned)
    cleaned = re.sub(r'(?i)\(.*?\)', '', cleaned)
    cleaned = cleaned.replace(' ', '').replace('-', '').replace('_', '').replace('.', '')
    cleaned = re.sub(r'[^A-Za-z0-9]', '', cleaned)
    if not cleaned:
        return ''

    if cleaned.lower() in {'time', 'timestamp', 'seconds', 'sec'}:
        return 'time'

    return cleaned[0].upper() + cleaned[1:] if cleaned and cleaned[0].isalpha() else cleaned


def _safe_float(value: object, default: float | None = None) -> float | None:
    """Coerce values like 'Fc.' or 'N/A' to float without crashing the import pipeline."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip()
    if text in {'', 'nan', 'NaN', 'None', 'none', 'N/A', 'n/a', 'null', 'NULL'}:
        return default
    normalized = text.replace(',', '')
    if normalized.startswith('(') and normalized.endswith(')'):
        normalized = f'-{normalized[1:-1]}'
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return default


def _coerce_numeric_series(series: pd.Series) -> pd.Series:
    """Convert EEG channel values to numeric while discarding malformed text tokens such as 'Fc.'."""
    converted = series.map(lambda value: _safe_float(value, np.nan))
    return pd.to_numeric(converted, errors='coerce')


def detect_eeg_columns(df: pd.DataFrame) -> Dict[str, object]:
    """Detect time, EEG channel, and metadata columns from a raw EEG dataframe."""
    if df.empty:
        return {'time_column': None, 'channels': [], 'metadata_columns': [], 'other_columns': []}

    original_columns = [str(col) for col in df.columns]
    normalized_columns = [_normalize_eeg_column_name(col) for col in original_columns]
    working = df.copy()
    working.columns = normalized_columns

    metadata_names = {'marker', 'trigger', 'event', 'label', 'status', 'notes', 'condition', 'epoch', 'stimulus'}
    time_candidates: List[str] = []
    channels: List[str] = []
    metadata_columns: List[str] = []
    other_columns: List[str] = []

    for idx, col in enumerate(normalized_columns):
        original_name = original_columns[idx]
        raw_lower = original_name.lower()
        lower = str(col).lower()

        if raw_lower in metadata_names or any(token in raw_lower for token in ['marker', 'trigger', 'event', 'label', 'status', 'notes']):
            metadata_columns.append(original_name)
            continue

        if lower in {'time', ''}:
            if any(token in raw_lower for token in ['time', 'timestamp', 'seconds', 'sec']):
                time_candidates.append(original_name)
            continue

        numeric_series = _coerce_numeric_series(df.iloc[:, idx])
        if numeric_series.notna().sum() == 0:
            other_columns.append(original_name)
            continue

        channels.append(col)

    if not time_candidates:
        for idx, col in enumerate(normalized_columns):
            lower = str(col).lower()
            if any(token in lower for token in ['timestamp', 'seconds', 'sec']):
                time_candidates.append(original_columns[idx])

    if not time_candidates:
        time_candidates = [original_columns[0]] if original_columns else [None]

    time_column = time_candidates[0] if time_candidates else 'time'
    return {
        'time_column': time_column,
        'channels': channels,
        'metadata_columns': metadata_columns,
        'other_columns': other_columns,
    }


def validate_eeg_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate structure and basic quality for EEG data. Returns a cleaned copy."""
    if df.empty:
        raise ValueError('EEG data is empty.')

    renamed = {old: _normalize_eeg_column_name(old) for old in df.columns}
    df = df.rename(columns=renamed)
    df = df.loc[:, [col for col in df.columns if str(col).strip() != '']].copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()

    if 'time' not in df.columns:
        df.insert(0, 'time', np.arange(len(df)) / 250.0)
    else:
        df['time'] = _coerce_numeric_series(df['time'])
        df = df.dropna(subset=['time']).reset_index(drop=True)

    metadata_names = {'marker', 'trigger', 'event', 'label', 'status', 'notes', 'condition', 'epoch', 'stimulus'}
    candidate_columns: List[str] = []
    for col in df.columns:
        if col == 'time' or not col:
            continue
        lower = str(col).lower()
        if lower in metadata_names or any(token in lower for token in ['marker', 'trigger', 'event', 'label', 'status', 'notes']):
            continue
        cleaned_series = _coerce_numeric_series(df[col])
        if cleaned_series.notna().sum() == 0:
            continue
        df[col] = cleaned_series
        candidate_columns.append(col)

    if not candidate_columns:
        raise ValueError('EEG file must contain at least one numeric data channel.')

    df = df[['time', *candidate_columns]].copy()
    if df.empty:
        raise ValueError('EEG file must contain at least one numeric data channel.')

    df = df.interpolate(method='linear', limit_direction='both')
    df = df.dropna(subset=[col for col in df.columns if col != 'time']).reset_index(drop=True)
    df = df.sort_values('time').reset_index(drop=True)
    if df['time'].nunique() < 2:
        raise ValueError('EEG signal must contain more than one time point.')

    return df


def _read_edf(path: str | Path) -> pd.DataFrame:
    """Load EEG data from a minimal EDF/EDF+ file and normalize it to the standard dataframe schema."""
    raw_data = Path(path).read_bytes()
    if len(raw_data) < 256:
        raise ValueError('EDF file is too small to contain a valid header.')

    n_channels = int((raw_data[252:256].decode('ascii', errors='ignore').strip() or '0'))
    if n_channels <= 0:
        raise ValueError('EDF file does not declare any channels.')

    header_size = 256 + n_channels * 256
    if len(raw_data) < header_size:
        raise ValueError('EDF file header is incomplete.')

    declared_records = int((raw_data[236:244].decode('ascii', errors='ignore').strip() or '1'))
    record_duration = float((raw_data[244:252].decode('ascii', errors='ignore').strip() or '0'))

    signal_header = raw_data[256:header_size]

    def field(offset: int, width: int, channel: int) -> str:
        start = offset + channel * width
        return signal_header[start:start + width].decode('ascii', errors='ignore').strip()

    signal_names = [field(0, 16, channel) for channel in range(n_channels)]
    sample_count_text = [field(216 * n_channels, 8, channel) for channel in range(n_channels)]
    physical_min_text = [field(104 * n_channels, 8, channel) for channel in range(n_channels)]
    physical_max_text = [field(112 * n_channels, 8, channel) for channel in range(n_channels)]
    digital_min_text = [field(120 * n_channels, 8, channel) for channel in range(n_channels)]
    digital_max_text = [field(128 * n_channels, 8, channel) for channel in range(n_channels)]

    standard_header_valid = bool(signal_names[0]) and all(text.lstrip('-').isdigit() for text in sample_count_text)
    if standard_header_valid:
        sample_counts = [int(text or '0') for text in sample_count_text]
        physical_min = [float(text or '0') for text in physical_min_text]
        physical_max = [float(text or '1') for text in physical_max_text]
        digital_min = [float(text or '-32768') for text in digital_min_text]
        digital_max = [float(text or '32767') for text in digital_max_text]
    else:
        signal_names = []
        sample_counts = []
        physical_min = []
        physical_max = []
        digital_min = []
        digital_max = []
        for ch_idx in range(n_channels):
            block = signal_header[ch_idx * 256:(ch_idx + 1) * 256]
            signal_names.append(block[:16].decode('ascii', errors='ignore').strip())
            sample_counts.append(int((block[252:256].decode('ascii', errors='ignore').strip() or '0')))
            physical_min.append(float((block[88:96].decode('ascii', errors='ignore').strip() or '0')))
            physical_max.append(float((block[96:104].decode('ascii', errors='ignore').strip() or '1')))
            digital_min.append(float((block[104:112].decode('ascii', errors='ignore').strip() or '-32768')))
            digital_max.append(float((block[112:120].decode('ascii', errors='ignore').strip() or '32767')))

    signal_names = [label or f'Channel{ch_idx + 1}' for ch_idx, label in enumerate(signal_names)]

    if not any(sample_counts):
        raise ValueError('EDF file does not include sample counts in its channel headers.')

    channel_arrays: List[np.ndarray] = []
    record_bytes = sum(count * 2 for count in sample_counts)
    if record_bytes <= 0:
        raise ValueError('EDF file does not contain a valid record layout.')
    payload_bytes = len(raw_data) - header_size
    if payload_bytes < 2:
        raise ValueError('EDF file does not contain readable signal records.')
    available_records = max(1, int(np.ceil(payload_bytes / record_bytes)))
    n_records = available_records if declared_records <= 0 else min(declared_records, available_records)
    for ch_idx, sample_count in enumerate(sample_counts):
        values: List[float] = []
        channel_offset = sum(sample_counts[:ch_idx]) * 2
        for record_idx in range(n_records):
            data_start = header_size + record_idx * record_bytes + channel_offset
            available_bytes = max(0, min(sample_count * 2, len(raw_data) - data_start))
            available_samples = available_bytes // 2
            if available_samples <= 0:
                continue
            raw_chunk = raw_data[data_start:data_start + available_samples * 2]
            int_values = np.frombuffer(raw_chunk, dtype='<i2', count=available_samples)
            if digital_max[ch_idx] == digital_min[ch_idx]:
                scaled = int_values.astype(float)
            else:
                scaled = ((int_values - digital_min[ch_idx]) / (digital_max[ch_idx] - digital_min[ch_idx])) * (physical_max[ch_idx] - physical_min[ch_idx]) + physical_min[ch_idx]
            values.extend(scaled.tolist())
        channel_arrays.append(np.asarray(values, dtype=float))

    if not channel_arrays or not any(len(values) for values in channel_arrays):
        raise ValueError('EDF file does not contain any samples.')

    valid_channels = [idx for idx, values in enumerate(channel_arrays) if len(values)]
    channel_arrays = [channel_arrays[idx] for idx in valid_channels]
    signal_names = [signal_names[idx] for idx in valid_channels]
    channel_rates = [sample_counts[idx] / max(record_duration, 1e-9) for idx in valid_channels] if record_duration > 0 else [250.0] * len(valid_channels)

    sample_rate = max(channel_rates) if channel_rates else 250.0
    duration_sec = min(n_records * record_duration, max(len(values) / max(rate, 1e-9) for values, rate in zip(channel_arrays, channel_rates))) if record_duration > 0 else max(len(values) / max(rate, 1e-9) for values, rate in zip(channel_arrays, channel_rates))
    total_samples = max(2, int(round(duration_sec * sample_rate)))
    time = np.arange(total_samples, dtype=float) / sample_rate
    data = {'time': time}
    seen_names: Dict[str, int] = {}
    for ch_idx, label in enumerate(signal_names):
        cleaned = _normalize_eeg_column_name(label)
        final_name = cleaned or f'Channel{ch_idx + 1}'
        suffix = 1
        while final_name in seen_names:
            suffix += 1
            final_name = f'{cleaned or f"Channel{ch_idx + 1}"}{suffix}'
        seen_names[final_name] = 1
        source = channel_arrays[ch_idx]
        source_time = np.arange(len(source), dtype=float) / max(channel_rates[ch_idx], 1e-9)
        data[final_name] = np.interp(time, source_time, source)

    df = pd.DataFrame(data)
    return validate_eeg_dataframe(df)


def load_eeg_csv(path: str | Path) -> pd.DataFrame:
    """Load EEG data from common EEG table formats and validate the resulting structure."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == '.edf':
        return _read_edf(path)
    if suffix in {'.xls', '.xlsx'}:
        df = pd.read_excel(path)
        return validate_eeg_dataframe(df)

    sep = ','
    if suffix in {'.tsv', '.txt'}:
        sep = '\t'

    try:
        df = pd.read_csv(path, sep=sep, engine='python')
    except Exception:
        df = pd.read_csv(path, sep=None, engine='python')
    return validate_eeg_dataframe(df)


def summarize_dataset(df: pd.DataFrame) -> Dict[str, float | int | str]:
    """Return a compact dataset summary suited for a research dashboard."""
    channels = [c for c in df.columns if c != 'time']
    sample_rate = 250.0
    if len(df) > 1:
        sample_rate = 1.0 / np.median(np.diff(df['time'].to_numpy()))
    return {
        'channels': int(len(channels)),
        'samples': int(len(df)),
        'duration_sec': float(df['time'].iloc[-1] - df['time'].iloc[0]),
        'sample_rate_hz': float(sample_rate),
        'mean_amplitude': float(np.mean(df[channels].to_numpy())),
        'std_amplitude': float(np.std(df[channels].to_numpy())),
    }


def apply_preprocessing(
    df: pd.DataFrame,
    low_cut: float | None = 1.0,
    high_cut: float | None = 40.0,
    notch: float | None = 50.0,
    artifact_threshold: float = 5.0,
) -> pd.DataFrame:
    """Apply a lightweight EEG preprocessing pipeline for real-world CSV signals."""
    cleaned = df.copy()
    channels = [c for c in cleaned.columns if c != 'time']
    if not channels:
        return cleaned

    sample_rate = 250.0
    if len(cleaned) > 1:
        sample_rate = 1.0 / np.median(np.diff(cleaned['time'].to_numpy()))

    time = cleaned['time'].to_numpy(dtype=float)
    for channel in channels:
        signal = cleaned[channel].to_numpy(dtype=float).copy()
        signal = signal - np.mean(signal)

        if sample_rate > 0:
            freq = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
            fft_vals = np.fft.rfft(signal)

            if low_cut is not None:
                fft_vals[freq < low_cut] = 0.0
            if high_cut is not None:
                fft_vals[freq > high_cut] = 0.0
            if notch is not None and notch > 0:
                notch_mask = np.abs(freq - notch) < 1.0
                fft_vals[notch_mask] = 0.0
            signal = np.fft.irfft(fft_vals, n=len(signal))

        signal = signal.astype(float)
        median = float(np.median(signal))
        std = float(np.std(signal))
        if std <= 0:
            std = 1.0
        threshold = max(artifact_threshold * std, 5.0 * np.finfo(float).eps)
        spikes = np.abs(signal - median) > threshold
        if np.any(spikes):
            signal[spikes] = median
        cleaned[channel] = signal

    return cleaned


def remove_artifacts(
    df: pd.DataFrame,
    z_threshold: float = 6.0,
    derivative_threshold: float = 8.0,
) -> pd.DataFrame:
    """Remove transient EEG artifacts with robust amplitude and slope detection."""
    cleaned = df.copy()
    channels = [c for c in cleaned.columns if c != 'time']
    for channel in channels:
        signal = cleaned[channel].to_numpy(dtype=float).copy()
        if len(signal) < 3:
            continue

        median = float(np.median(signal))
        deviation = np.abs(signal - median)
        mad = float(np.median(deviation))
        robust_scale = max(1.4826 * mad, float(np.std(signal)) * 0.1, np.finfo(float).eps)
        amplitude_mask = deviation > z_threshold * robust_scale

        differences = np.diff(signal, prepend=signal[0])
        diff_median = float(np.median(differences))
        diff_mad = float(np.median(np.abs(differences - diff_median)))
        diff_scale = max(1.4826 * diff_mad, float(np.std(differences)) * 0.1, np.finfo(float).eps)
        slope_mask = np.abs(differences - diff_median) > derivative_threshold * diff_scale

        artifact_mask = amplitude_mask | slope_mask | np.r_[slope_mask[1:], False]
        if not np.any(artifact_mask):
            continue

        sample_index = np.arange(len(signal))
        valid_index = sample_index[~artifact_mask]
        if len(valid_index) >= 2:
            signal[artifact_mask] = np.interp(sample_index[artifact_mask], valid_index, signal[valid_index])
        elif len(valid_index) == 1:
            signal[artifact_mask] = signal[valid_index[0]]
        else:
            signal[:] = median
        cleaned[channel] = signal

    return cleaned


def compute_topography_values(df: pd.DataFrame) -> Dict[str, float]:
    """Compute a per-channel topographic summary using band power on common EEG locations."""
    channels = [c for c in df.columns if c != 'time']
    topography: Dict[str, float] = {}
    for channel in channels:
        signal = df[channel].to_numpy()
        fs = 1.0 / np.median(np.diff(df['time'].to_numpy())) if len(df) > 1 else 250.0
        freq = np.fft.rfftfreq(len(signal), d=1 / fs)
        spectrum = np.abs(np.fft.rfft(signal - np.mean(signal)))
        alpha_mask = (freq >= 8) & (freq <= 13)
        beta_mask = (freq >= 13) & (freq <= 30)
        alpha_value = float(np.mean(spectrum[alpha_mask])) if np.any(alpha_mask) else 0.0
        beta_value = float(np.mean(spectrum[beta_mask])) if np.any(beta_mask) else 0.0
        topography[channel] = alpha_value + 0.4 * beta_value

    max_value = max(topography.values()) if topography else 1.0
    if max_value > 0:
        topography = {name: value / max_value for name, value in topography.items()}
    return topography


def get_standard_eeg_montage_positions() -> Dict[str, tuple[float, float, float]]:
    """Return a standard 10-20 EEG montage geometry for realistic head-map rendering."""
    return {
        'Fp1': (-1.00, -1.05, -0.35), 'Fp2': (1.00, -1.05, -0.35),
        'F7': (-1.35, -0.30, -0.15), 'F3': (-0.70, -0.20, 0.00), 'Fz': (0.00, -0.18, 0.10),
        'F4': (0.70, -0.20, 0.00), 'F8': (1.35, -0.30, -0.15),
        'T3': (-1.05, 0.35, -0.10), 'C3': (-0.60, 0.35, 0.00), 'Cz': (0.00, 0.35, 0.12),
        'C4': (0.60, 0.35, 0.00), 'T4': (1.05, 0.35, -0.10),
        'T5': (-1.00, 0.92, -0.10), 'P3': (-0.60, 0.95, 0.08), 'Pz': (0.00, 0.96, 0.15),
        'P4': (0.60, 0.95, 0.08), 'T6': (1.00, 0.92, -0.10),
        'O1': (-0.45, 1.55, 0.00), 'Oz': (0.00, 1.78, 0.00), 'O2': (0.45, 1.55, 0.00),
    }


def compute_brain_region_activity(
    df: pd.DataFrame,
    topography_values: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """Aggregate channel-level activity into canonical brain regions for 3D cortical mapping."""
    values = topography_values if topography_values is not None else compute_topography_values(df)
    region_groups = {
        'frontal': ['Fp1', 'Fp2', 'F7', 'F8', 'Fz'],
        'central': ['C3', 'C4', 'Cz'],
        'parietal': ['P3', 'P4', 'Pz'] if 'Pz' in df.columns else ['P3', 'P4'],
        'occipital': ['O1', 'O2'],
    }

    region_map: Dict[str, float] = {}
    for region, channels in region_groups.items():
        available = [ch for ch in channels if ch in values]
        if not available:
            region_map[region] = 0.0
        else:
            region_map[region] = float(np.mean([values[ch] for ch in available]))

    return region_map


def generate_synthetic_dataset(num_channels: int = 8, samples: int = 2000, sample_rate: int = 250) -> pd.DataFrame:
    """Generate a realistic synthetic EEG dataset with multiple channels and standard frequency components."""
    time = np.linspace(0, (samples - 1) / sample_rate, samples)
    channel_names = [
        'Fp1', 'Fp2', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2',
        'F7', 'F8', 'T3', 'T4', 'T5', 'T6', 'Fz', 'Cz'
    ][:num_channels]

    columns = ['time'] + channel_names
    data = {'time': time}

    for idx, name in enumerate(channel_names):
        alpha = 10 + idx * 0.2
        beta = 20 + idx * 0.35
        theta = 6 + idx * 0.18
        gamma = 35 + idx * 0.3

        alpha_wave = np.sin(2 * np.pi * alpha * time + idx * 0.7) * 3.0
        beta_wave = np.sin(2 * np.pi * beta * time + idx * 1.1) * 2.1
        theta_wave = np.sin(2 * np.pi * theta * time + idx * 0.5) * 2.6
        gamma_wave = np.sin(2 * np.pi * gamma * time + idx * 1.4) * 0.9
        drift = np.sin(0.7 * time + idx) * 0.8
        noise = np.random.default_rng(42 + idx).normal(0, 0.7, size=samples)
        data[name] = alpha_wave + beta_wave + theta_wave + gamma_wave + drift + noise

    return pd.DataFrame(data, columns=columns)


def compute_channel_band_summary(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Compute per-channel band-power features for EEG research review."""
    channels = [c for c in df.columns if c != 'time']
    if not channels:
        return {}

    time_values = df['time'].to_numpy()
    fs = 1.0 / np.median(np.diff(time_values)) if len(time_values) > 1 else 250.0
    summary: Dict[str, Dict[str, float]] = {}

    for channel in channels:
        signal = df[channel].to_numpy(dtype=float)
        signal = signal - np.mean(signal)
        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), d=1 / fs)
        power = np.abs(fft_vals) ** 2
        band_metrics: Dict[str, float] = {}
        for band_name, f_low, f_high in [
            ('theta', 4, 8),
            ('alpha', 8, 13),
            ('beta', 13, 30),
            ('gamma', 30, 45),
        ]:
            band_mask = (freqs >= f_low) & (freqs <= f_high)
            band_value = float(np.trapezoid(power[band_mask], freqs[band_mask])) if np.any(band_mask) else 0.0
            band_metrics[band_name] = band_value
        summary[channel] = band_metrics

    return summary


def _is_valid_event_label(value: object) -> bool:
    """Reject malformed metadata such as 'Fc.' or other punctuation-heavy junk while preserving real labels."""
    text = str(value).strip()
    if not text or text.lower() in {'', 'none', 'nan', 'n/a', 'na'}:
        return False
    if text.lower() in {'cue', 'stimulus', 'blink', 'response', 'target', 'event'}:
        return True
    if re.fullmatch(r'[A-Za-z0-9_\-\s]+', text) is None:
        return False
    return any(ch.isalpha() for ch in text)


def extract_event_markers(df: pd.DataFrame) -> List[Dict[str, float | str]]:
    """Extract event markers from trigger or label columns used by EEG datasets."""
    if df.empty:
        return []

    events: List[Dict[str, float | str]] = []
    trigger_columns = [c for c in df.columns if str(c).lower() in {'marker', 'trigger', 'event', 'status', 'stimulus'}]
    label_columns = [c for c in df.columns if str(c).lower() in {'label', 'eventlabel', 'annotation', 'condition', 'event_name'}]

    for idx, row in df.iterrows():
        time_val = _safe_float(row.get('time', idx), default=float(idx))
        if time_val is None:
            continue
        label_value = None
        for col in label_columns:
            value = row.get(col)
            if pd.notna(value):
                value_str = str(value).strip()
                if _is_valid_event_label(value_str):
                    label_value = value_str
                    break

        text_trigger_value = None
        numeric_trigger_value = None
        for col in trigger_columns:
            value = row.get(col)
            if pd.isna(value):
                continue
            value_str = str(value).strip()
            if value_str in {'', 'None', 'nan', 'NaN', 'N/A', 'n/a'}:
                continue
            try:
                candidate_numeric = float(value)
            except (TypeError, ValueError):
                candidate_numeric = None
            if candidate_numeric is None:
                if _is_valid_event_label(value_str):
                    text_trigger_value = value_str
                    break
                continue
            if numeric_trigger_value is None:
                numeric_trigger_value = value

        if label_value is not None:
            events.append({'time': time_val, 'label': label_value})
            continue

        chosen_value = text_trigger_value or numeric_trigger_value
        if chosen_value is not None:
            try:
                numeric = float(chosen_value)
            except (TypeError, ValueError):
                numeric = 0.0
            if numeric != 0 or text_trigger_value is not None:
                events.append({'time': time_val, 'label': str(chosen_value)})

    return events


def compute_event_epoch_summary(
    df: pd.DataFrame,
    events: List[Dict[str, float | str]],
    window_sec: float = 0.5,
    baseline_sec: float = 0.2,
) -> List[Dict[str, float | str]]:
    """Summarize spectral power in event-aligned time windows for EEG research analysis."""
    if df.empty or not events:
        return []

    summary: List[Dict[str, float | str]] = []
    for event in events:
        event_time = _safe_float(event.get('time', 0.0), default=0.0)
        if event_time is None:
            continue
        label = str(event.get('label', 'Event'))
        start = event_time - baseline_sec
        end = event_time + window_sec
        window_df = df[(df['time'] >= start) & (df['time'] <= end)].copy()
        if window_df.empty:
            continue

        band_metrics = compute_band_power_metrics(window_df)
        summary.append({
            'time': event_time,
            'label': label,
            'theta': float(band_metrics.get('theta', 0.0)),
            'alpha': float(band_metrics.get('alpha', 0.0)),
            'beta': float(band_metrics.get('beta', 0.0)),
            'gamma': float(band_metrics.get('gamma', 0.0)),
            'start': start,
            'end': end,
        })

    return summary


def describe_eeg_dataset(df: pd.DataFrame) -> Dict[str, object]:
    """Describe imported EEG data for UI preview and dataset review."""
    metadata_columns = {'marker', 'trigger', 'event', 'label', 'status', 'notes', 'condition', 'epoch', 'stimulus'}
    channels = [
        c for c in df.columns if c != 'time' and str(c).lower() not in metadata_columns
    ]
    for c in list(df.columns):
        if c == 'time':
            continue
        lower = str(c).lower()
        if lower in metadata_columns or any(token in lower for token in ['marker', 'trigger', 'event', 'label', 'status', 'notes']):
            if c in channels:
                channels.remove(c)

    event_labels = []
    for event in extract_event_markers(df):
        label = str(event.get('label', 'Event'))
        if label not in event_labels:
            event_labels.append(label)

    return {
        'sample_count': int(len(df)),
        'channel_count': int(len(channels)),
        'channels': channels,
        'event_labels': event_labels,
        'duration_sec': float(df['time'].iloc[-1] - df['time'].iloc[0]) if len(df) > 1 else 0.0,
    }


def compare_channel_features(df: pd.DataFrame, reference_channel: str, comparison_channel: str) -> Dict[str, float | str]:
    """Compare two EEG channels by their band-power features."""
    channels = [c for c in df.columns if c != 'time']
    if reference_channel not in channels or comparison_channel not in channels:
        raise ValueError('Both channels must be present in the dataset.')

    ref_summary = compute_channel_band_summary(df)[reference_channel]
    cmp_summary = compute_channel_band_summary(df)[comparison_channel]
    return {
        'reference': reference_channel,
        'comparison': comparison_channel,
        'delta_alpha': float(cmp_summary['alpha'] - ref_summary['alpha']),
        'delta_beta': float(cmp_summary['beta'] - ref_summary['beta']),
        'delta_theta': float(cmp_summary['theta'] - ref_summary['theta']),
        'delta_gamma': float(cmp_summary['gamma'] - ref_summary['gamma']),
    }


def compute_band_power_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """Compute approximate band power metrics for each channel and aggregate by band."""
    channels = [c for c in df.columns if c != 'time']
    time_values = df['time'].to_numpy()
    fs = 1.0 / np.median(np.diff(time_values)) if len(time_values) > 1 else 250.0
    metrics: Dict[str, float] = {}

    for band_name, f_low, f_high in [
        ('theta', 4, 8),
        ('alpha', 8, 13),
        ('beta', 13, 30),
        ('gamma', 30, 45),
    ]:
        values: List[float] = []
        for channel in channels:
            signal = df[channel].to_numpy()
            fft_vals = np.fft.rfft(signal - np.mean(signal))
            freqs = np.fft.rfftfreq(len(signal), d=1 / fs)
            power = np.abs(fft_vals) ** 2
            band_mask = (freqs >= f_low) & (freqs <= f_high)
            values.append(float(np.trapezoid(power[band_mask], freqs[band_mask])))
        metrics[band_name] = float(np.mean(values))

    return metrics
