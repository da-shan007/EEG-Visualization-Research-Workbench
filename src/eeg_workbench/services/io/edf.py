"""EDF/BDF 格式读取器（基于 pyedflib + MNE）"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np

from eeg_workbench.services.io import BaseReader, LoadResult
from eeg_workbench.models.dataset import ChannelType


class EDFReader(BaseReader):
    EXTENSIONS = (".edf", ".bdf")
    FORMAT_NAME = "EDF/BDF"

    def read(self, file_path: str, **kwargs) -> LoadResult:
        # 优先用 MNE 读取（自动处理标注、事件、通道类型）
        try:
            import mne
            preload = kwargs.get("preload", True)
            raw = mne.io.read_raw_edf(file_path, preload=preload, verbose=False)
        except Exception as e:
            # 回退到 pyedflib 纯读取
            raw = self._read_with_pyedflib(file_path, **kwargs)

        return LoadResult(dataset=self._create_dataset(raw, file_path, **kwargs))

    def _read_with_pyedflib(self, file_path: str, **kwargs) -> Any:
        """纯 pyedflib 读取，构造 MNE Raw 对象"""
        import pyedflib
        import mne

        f = pyedflib.EdfReader(file_path)
        n_ch = f.signals_in_file
        ch_names = f.getSignalLabels()
        sfreq = f.getSampleFrequency(0)

        # 读取所有信号
        data = np.zeros((n_ch, f.getNSamples()[0]), dtype=np.float64)
        for i in range(n_ch):
            data[i, :] = f.readSignal(i)

        # 通道类型推断
        ch_types = []
        for label in ch_names:
            lower = label.upper()
            if any(x in lower for x in ["EOG", "EOGL", "EOGR"]):
                ch_types.append("eog")
            elif "ECG" in lower or "EKG" in lower:
                ch_types.append("ecg")
            elif "EMG" in lower:
                ch_types.append("emg")
            elif "STIM" in lower or "TRIG" in lower or "STATUS" in lower:
                ch_types.append("stim")
            else:
                ch_types.append("eeg")

        info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types=ch_types)
        raw = mne.io.RawArray(data * 1e-6, info)  # µV -> V

        # 读取标注
        annotations = f.readAnnotations()
        if annotations[0].size > 0:
            from mne import Annotations
            raw.set_annotations(Annotations(*annotations))

        f.close()
        return raw


class BDFReader(EDFReader):
    """BDF 专用（继承 EDF，仅改名）"""
    FORMAT_NAME = "BDF"