from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .core import load_eeg_csv

try:
    import mne
except ImportError:  # Optional until advanced scientific dependencies are installed.
    mne = None

try:
    from scipy import signal as scipy_signal
    from scipy.stats import f_oneway, pearsonr, ttest_ind
except ImportError:  # Optional for lightweight deployments.
    scipy_signal = None
    f_oneway = pearsonr = ttest_ind = None


STANDARD_BANDS: dict[str, tuple[float, float]] = {
    'delta': (1.0, 4.0),
    'theta': (4.0, 8.0),
    'alpha': (8.0, 13.0),
    'beta': (13.0, 30.0),
    'gamma': (30.0, 45.0),
}


@dataclass
class EEGRecording:
    """Portable recording container shared by import, analysis and export workflows."""

    data: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    source_path: str | None = None

    @property
    def channels(self) -> list[str]:
        return [column for column in self.data.columns if column != 'time']

    @property
    def sample_rate(self) -> float:
        if len(self.data) < 2:
            return 250.0
        differences = np.diff(self.data['time'].to_numpy(dtype=float))
        differences = differences[np.isfinite(differences) & (differences > 0)]
        return float(1.0 / np.median(differences)) if len(differences) else 250.0


def _require_mne() -> Any:
    if mne is None:
        raise RuntimeError('该格式需要安装 MNE-Python：python -m pip install mne')
    return mne


def load_event_file(path: str | Path) -> list[dict[str, Any]]:
    """Load BrainVision .vmrk or tabular TSV event markers."""
    path = Path(path)
    if path.suffix.lower() == '.vmrk':
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding='utf-8-sig', errors='ignore').splitlines():
            match = re.match(r'Mk\d+=([^,]+),(\d+),(\d+)(?:,(\d+))?', line.strip())
            if not match:
                continue
            label, position, _, duration = match.groups()
            events.append({
                'time': (int(position) - 1) / 250.0,
                'label': label.strip(),
                'sample': int(position),
                'duration': int(duration or 1),
            })
        return events

    table = pd.read_csv(path, sep='\t' if path.suffix.lower() in {'.tsv', '.txt'} else None, engine='python')
    time_column = next((column for column in table.columns if str(column).lower() in {'time', 'onset', 'latency'}), table.columns[0])
    label_column = next((column for column in table.columns if str(column).lower() in {'label', 'event', 'type', 'condition', 'marker'}), table.columns[-1])
    return [{'time': float(row[time_column]), 'label': str(row[label_column])} for _, row in table.iterrows()]


def load_recording(path: str | Path, metadata: dict[str, Any] | None = None) -> EEGRecording:
    """Load table and common MNE-supported EEG formats into one recording model."""
    path = Path(path)
    suffix = path.suffix.lower()
    metadata = dict(metadata or {})
    if suffix in {'.csv', '.tsv', '.txt', '.xls', '.xlsx', '.edf'}:
        data = load_eeg_csv(path)
        return EEGRecording(data=data, metadata=metadata, source_path=str(path))

    mne_module = _require_mne()
    if suffix in {'.bdf', '.vhdr', '.set'}:
        if suffix == '.bdf':
            raw = mne_module.io.read_raw_bdf(path, preload=True, verbose='ERROR')
        elif suffix == '.vhdr':
            raw = mne_module.io.read_raw_brainvision(path, preload=True, verbose='ERROR')
        else:
            raw = mne_module.io.read_raw_eeglab(path, preload=True, verbose='ERROR')
        values = raw.get_data()
        time = raw.times
        data = pd.DataFrame(values.T, columns=raw.ch_names)
        data.insert(0, 'time', time)
        events = [
            {'time': float(annotation['onset']), 'label': str(annotation['description'])}
            for annotation in raw.annotations
        ]
        return EEGRecording(data=data, metadata={**metadata, 'sfreq': float(raw.info['sfreq']), 'ch_names': raw.ch_names}, events=events, source_path=str(path))

    raise ValueError(f'不支持的 EEG 文件格式：{suffix}')


def edit_metadata(recording: EEGRecording, **values: Any) -> EEGRecording:
    recording.metadata.update({key: value for key, value in values.items() if value is not None})
    return recording


def crop_recording(recording: EEGRecording, start: float, end: float) -> EEGRecording:
    if start > end:
        start, end = end, start
    mask = (recording.data['time'] >= start) & (recording.data['time'] <= end)
    data = recording.data.loc[mask].copy().reset_index(drop=True)
    events = [event for event in recording.events if start <= float(event.get('time', 0)) <= end]
    return EEGRecording(data=data, metadata=dict(recording.metadata), events=events, source_path=recording.source_path)


def concatenate_recordings(recordings: Iterable[EEGRecording]) -> EEGRecording:
    recordings = list(recordings)
    if not recordings:
        raise ValueError('至少需要一个 EEG session。')
    channels = recordings[0].channels
    if any(recording.channels != channels for recording in recordings):
        raise ValueError('拼接 session 的通道集合必须一致。')
    frames = []
    events = []
    offset = 0.0
    for recording in recordings:
        frame = recording.data.copy()
        frame['time'] += offset
        frames.append(frame)
        events.extend([{**event, 'time': float(event.get('time', 0)) + offset} for event in recording.events])
        offset = float(frame['time'].iloc[-1] + 1.0 / recording.sample_rate)
    return EEGRecording(pd.concat(frames, ignore_index=True), dict(recordings[0].metadata), events)


def preprocess_recording(
    recording: EEGRecording,
    low_cut: float | None = 0.1,
    high_cut: float | None = 40.0,
    notch: float | None = 50.0,
    reference: str = 'average',
    resample_hz: float | None = None,
) -> EEGRecording:
    """Apply band/low/high filtering, notch, re-reference and optional resampling."""
    data = recording.data.copy()
    channels = recording.channels
    sample_rate = recording.sample_rate
    if scipy_signal is None:
        raise RuntimeError('预处理需要安装 SciPy：python -m pip install scipy')
    for channel in channels:
        values = data[channel].to_numpy(dtype=float)
        if low_cut is not None and high_cut is not None:
            values = scipy_signal.sosfiltfilt(scipy_signal.butter(4, [low_cut, high_cut], btype='bandpass', fs=sample_rate, output='sos'), values)
        elif low_cut is not None:
            values = scipy_signal.sosfiltfilt(scipy_signal.butter(4, low_cut, btype='highpass', fs=sample_rate, output='sos'), values)
        elif high_cut is not None:
            values = scipy_signal.sosfiltfilt(scipy_signal.butter(4, high_cut, btype='lowpass', fs=sample_rate, output='sos'), values)
        if notch is not None and 0 < notch < sample_rate / 2:
            values = scipy_signal.sosfiltfilt(scipy_signal.butter(2, [notch - 1, notch + 1], btype='bandstop', fs=sample_rate, output='sos'), values)
        data[channel] = values

    if reference == 'average':
        data[channels] = data[channels].sub(data[channels].mean(axis=1), axis=0)
    elif reference in data.columns:
        data[channels] = data[channels].sub(data[reference], axis=0)
    elif reference not in {'none', ''}:
        raise ValueError(f'参考通道不存在：{reference}')

    if resample_hz is not None and resample_hz > 0 and abs(resample_hz - sample_rate) > 1e-6:
        count = max(2, int(round(len(data) * resample_hz / sample_rate)))
        new_time = np.arange(count, dtype=float) / resample_hz
        resampled = {'time': new_time}
        for channel in channels:
            resampled[channel] = np.interp(new_time, data['time'].to_numpy(), data[channel].to_numpy())
        data = pd.DataFrame(resampled)
    return EEGRecording(data, dict(recording.metadata), list(recording.events), recording.source_path)


def compute_band_features(recording: EEGRecording, bands: dict[str, tuple[float, float]] | None = None) -> pd.DataFrame:
    """Return absolute, relative and log power for Delta through Gamma bands."""
    bands = bands or STANDARD_BANDS
    sample_rate = recording.sample_rate
    rows = []
    for channel in recording.channels:
        values = recording.data[channel].to_numpy(dtype=float)
        frequencies, power = scipy_signal.periodogram(values, fs=sample_rate) if scipy_signal else (np.fft.rfftfreq(len(values), 1 / sample_rate), np.abs(np.fft.rfft(values)) ** 2)
        total = float(np.trapezoid(power[(frequencies >= 1) & (frequencies <= 45)], frequencies[(frequencies >= 1) & (frequencies <= 45)])) or 1.0
        for name, (low, high) in bands.items():
            mask = (frequencies >= low) & (frequencies < high)
            absolute = float(np.trapezoid(power[mask], frequencies[mask])) if np.any(mask) else 0.0
            rows.append({'channel': channel, 'band': name, 'absolute_power': absolute, 'relative_power': absolute / total, 'log_power': float(np.log10(absolute + np.finfo(float).eps))})
    return pd.DataFrame(rows)


def compute_stft(recording: EEGRecording, channel: str, nperseg: int = 256) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if scipy_signal is None:
        raise RuntimeError('时频分析需要安装 SciPy。')
    if channel not in recording.channels:
        raise ValueError(f'通道不存在：{channel}')
    return scipy_signal.stft(recording.data[channel].to_numpy(dtype=float), fs=recording.sample_rate, nperseg=min(nperseg, len(recording.data)))


def compute_erp(recording: EEGRecording, event_label: str, tmin: float = -0.2, tmax: float = 0.8) -> pd.DataFrame:
    sample_rate = recording.sample_rate
    window = np.arange(int(round((tmax - tmin) * sample_rate)) + 1) / sample_rate + tmin
    epochs = []
    time_values = recording.data['time'].to_numpy(dtype=float)
    for event in recording.events:
        if str(event.get('label')) != event_label:
            continue
        center = float(event['time'])
        indices = np.searchsorted(time_values, center + window)
        if indices[-1] >= len(recording.data) or indices[0] < 0:
            continue
        epochs.append(recording.data.iloc[indices][recording.channels].to_numpy())
    if not epochs:
        return pd.DataFrame(columns=['time', *recording.channels])
    average = np.mean(np.stack(epochs), axis=0)
    result = pd.DataFrame(average, columns=recording.channels)
    result.insert(0, 'time', window)
    return result


def compare_groups(groups: dict[str, Iterable[float]], method: str = 'ttest') -> dict[str, float | str]:
    arrays = [np.asarray(list(values), dtype=float) for values in groups.values()]
    if len(arrays) < 2:
        raise ValueError('组间比较至少需要两组数据。')
    if ttest_ind is None:
        raise RuntimeError('统计检验需要安装 SciPy。')
    if method == 'anova':
        statistic, p_value = f_oneway(*arrays)
    else:
        statistic, p_value = ttest_ind(arrays[0], arrays[1], equal_var=False, nan_policy='omit')
    return {'method': method, 'statistic': float(statistic), 'p_value': float(p_value)}


def export_recording(recording: EEGRecording, path: str | Path) -> None:
    path = Path(path)
    if path.suffix.lower() == '.json':
        payload = {'metadata': recording.metadata, 'events': recording.events, 'data': recording.data.to_dict(orient='records')}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    elif path.suffix.lower() == '.tsv':
        recording.data.to_csv(path, sep='\t', index=False, encoding='utf-8-sig')
    elif path.suffix.lower() == '.xlsx':
        recording.data.to_excel(path, index=False, engine='openpyxl')
    else:
        recording.data.to_csv(path, index=False, encoding='utf-8-sig')


def edit_events(
    recording: EEGRecording,
    add: Iterable[dict[str, Any]] = (),
    remove_times: Iterable[float] = (),
    updates: dict[float, dict[str, Any]] | None = None,
) -> EEGRecording:
    """Add, remove and update event markers without changing signal samples."""
    remove_times = list(remove_times)
    updates = updates or {}
    events = []
    for event in recording.events:
        event_time = float(event.get('time', 0.0))
        if any(abs(event_time - target) < 1e-9 for target in remove_times):
            continue
        updated = dict(event)
        updated.update(updates.get(event_time, {}))
        events.append(updated)
    events.extend(dict(event) for event in add)
    events.sort(key=lambda event: float(event.get('time', 0.0)))
    return EEGRecording(recording.data.copy(), dict(recording.metadata), events, recording.source_path)


def remove_bad_segments(recording: EEGRecording, segments: Iterable[tuple[float, float]]) -> EEGRecording:
    """Replace manually marked bad time segments with per-channel interpolation."""
    data = recording.data.copy()
    invalid = np.zeros(len(data), dtype=bool)
    time = data['time'].to_numpy(dtype=float)
    for start, end in segments:
        left, right = sorted((float(start), float(end)))
        invalid |= (time >= left) & (time <= right)
    for channel in recording.channels:
        values = data[channel].to_numpy(dtype=float)
        valid = ~invalid & np.isfinite(values)
        if valid.sum() >= 2:
            values[invalid] = np.interp(time[invalid], time[valid], values[valid])
        data[channel] = values
    return EEGRecording(data, dict(recording.metadata), list(recording.events), recording.source_path)


def interpolate_bad_channels(recording: EEGRecording, bad_channels: Iterable[str], method: str = 'average') -> EEGRecording:
    """Repair bad channels using the remaining channels or a declared neighbor map."""
    data = recording.data.copy()
    bad_channels = list(dict.fromkeys(bad_channels))
    good_channels = [channel for channel in recording.channels if channel not in bad_channels]
    if not good_channels:
        raise ValueError('至少需要一个正常通道才能插值。')
    for channel in bad_channels:
        if channel not in data.columns:
            raise ValueError(f'坏通道不存在：{channel}')
        data[channel] = data[good_channels].mean(axis=1).to_numpy()
    return EEGRecording(data, dict(recording.metadata), list(recording.events), recording.source_path)


def run_ica_artifact_removal(
    recording: EEGRecording,
    n_components: int | float = 0.99,
    eog_channels: Iterable[str] = (),
    random_state: int = 42,
) -> tuple[EEGRecording, list[int]]:
    """Fit MNE ICA and exclude components correlated with supplied EOG channels."""
    mne_module = _require_mne()
    channels = recording.channels
    info = mne_module.create_info(channels, recording.sample_rate, ch_types='eeg')
    raw = mne_module.io.RawArray(recording.data[channels].to_numpy(dtype=float).T, info, verbose='ERROR')
    ica = mne_module.preprocessing.ICA(n_components=n_components, random_state=random_state, max_iter='auto')
    ica.fit(raw, verbose='ERROR')
    excluded: list[int] = []
    for channel in eog_channels:
        if channel in channels:
            found, _ = ica.find_bads_eog(raw, ch_name=channel, verbose='ERROR')
            excluded.extend(found)
    ica.exclude = sorted(set(excluded))
    cleaned = raw.copy()
    ica.apply(cleaned, verbose='ERROR')
    values = cleaned.get_data().T
    data = recording.data.copy()
    data[channels] = values
    return EEGRecording(data, dict(recording.metadata), list(recording.events), recording.source_path), ica.exclude


def compute_connectivity(recording: EEGRecording, method: str = 'coherence') -> pd.DataFrame:
    """Compute a channel connectivity matrix using coherence or phase locking value."""
    if scipy_signal is None:
        raise RuntimeError('连通性分析需要安装 SciPy。')
    channels = recording.channels
    values = recording.data[channels].to_numpy(dtype=float).T
    matrix = np.eye(len(channels), dtype=float)
    for first in range(len(channels)):
        for second in range(first + 1, len(channels)):
            if method == 'plv':
                phase_first = np.angle(scipy_signal.hilbert(values[first]))
                phase_second = np.angle(scipy_signal.hilbert(values[second]))
                score = float(np.abs(np.mean(np.exp(1j * (phase_first - phase_second)))))
            else:
                frequencies, coherence = scipy_signal.coherence(values[first], values[second], fs=recording.sample_rate)
                mask = (frequencies >= 1) & (frequencies <= 45)
                score = float(np.mean(coherence[mask])) if np.any(mask) else 0.0
            matrix[first, second] = matrix[second, first] = score
    return pd.DataFrame(matrix, index=channels, columns=channels)


def compute_entropy_features(recording: EEGRecording) -> pd.DataFrame:
    """Return spectral entropy and amplitude statistics for each channel."""
    rows = []
    for channel in recording.channels:
        values = recording.data[channel].to_numpy(dtype=float)
        power = np.abs(np.fft.rfft(values - np.mean(values))) ** 2
        distribution = power / max(float(np.sum(power)), np.finfo(float).eps)
        spectral_entropy = float(-np.sum(distribution * np.log2(distribution + np.finfo(float).eps)))
        rows.append({
            'channel': channel,
            'spectral_entropy': spectral_entropy,
            'mean': float(np.mean(values)),
            'std': float(np.std(values)),
            'rms': float(np.sqrt(np.mean(values ** 2))),
        })
    return pd.DataFrame(rows)
