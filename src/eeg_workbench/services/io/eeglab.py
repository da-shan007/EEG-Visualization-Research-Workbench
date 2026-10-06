"""EEGLAB 格式读取器 (.set, .fdt)"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from eeg_workbench.services.io import BaseReader, LoadResult


class EEGLABReader(BaseReader):
    EXTENSIONS = (".set",)
    FORMAT_NAME = "EEGLAB"

    def read(self, file_path: str, **kwargs: Any) -> LoadResult:
        import mne

        preload = kwargs.get("preload", True)
        # MNE 支持读取 .set (需要 scipy.io.loadmat)
        raw = mne.io.read_raw_eeglab(file_path, preload=preload, verbose=False)

        return LoadResult(dataset=self._create_dataset(raw, file_path, **kwargs))