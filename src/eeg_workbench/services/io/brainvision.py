"""BrainVision 格式读取器 (.vhdr, .vmrk, .eeg)"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from eeg_workbench.services.io import BaseReader, LoadResult


class BrainVisionReader(BaseReader):
    EXTENSIONS = (".vhdr", ".vmrk", ".eeg")
    FORMAT_NAME = "BrainVision"

    def read(self, file_path: str, **kwargs: Any) -> LoadResult:
        import mne

        # BrainVision 以 .vhdr 为主入口
        path = Path(file_path)
        if path.suffix.lower() != ".vhdr":
            # 尝试找同名 .vhdr
            vhdr_path = path.with_suffix(".vhdr")
            if vhdr_path.exists():
                file_path = str(vhdr_path)
            else:
                raise ValueError(f"BrainVision 格式需要 .vhdr 文件: {file_path}")

        preload = kwargs.get("preload", True)
        raw = mne.io.read_raw_brainvision(file_path, preload=preload, verbose=False)

        return LoadResult(dataset=self._create_dataset(raw, file_path, **kwargs))