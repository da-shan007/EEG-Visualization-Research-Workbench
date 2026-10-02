"""CSV / Excel / TXT 通用表格格式读取器

约定：
- 第一行表头：通道名
- 第一列可选：时间戳 或 样本索引
- 支持多 Sheet (Excel)，默认读第一个
- 元数据可通过同名 .json/.yaml 伴随文件提供
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

from eeg_workbench.services.io import BaseReader, LoadResult
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType, Montage
from eeg_workbench.models.metadata import DatasetMetadata


class TableReader(BaseReader):
    EXTENSIONS = (".csv", ".txt", ".tsv", ".xlsx", ".xls", ".ods")
    FORMAT_NAME = "Table (CSV/Excel/TXT)"

    def read(self, file_path: str, **kwargs) -> LoadResult:
        path = Path(file_path)
        ext = path.suffix.lower()

        # 读取参数
        delimiter = kwargs.get("delimiter", None)  # None -> 自动推断
        header_row = kwargs.get("header", 0)
        time_column = kwargs.get("time_column", None)  # 时间列名或索引
        sfreq = kwargs.get("sfreq", None)              # 采样率 (Hz)，必填
        unit = kwargs.get("unit", "uV")                # 数据单位：uV, mV, V
        ch_types = kwargs.get("ch_types", None)        # dict: ch_name -> type
        montage_name = kwargs.get("montage", "standard_1020")

        if sfreq is None:
            raise ValueError("表格格式必须指定采样率 sfreq (Hz)")

        # 读取数据
        if ext in (".xlsx", ".xls", ".ods"):
            sheet_name = kwargs.get("sheet_name", 0)
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, engine="openpyxl")
        else:
            if delimiter is None:
                delimiter = "\t" if ext == ".tsv" else ","
            df = pd.read_csv(file_path, delimiter=delimiter, header=header_row)

        # 处理时间列
        if time_column is not None:
            if isinstance(time_column, str):
                time_data = df[time_column].values
                df = df.drop(columns=[time_column])
            else:
                time_data = df.iloc[:, time_column].values
                df = df.drop(df.columns[time_column], axis=1)
            # 验证时间列单调递增
            if not np.all(np.diff(time_data) > 0):
                raise ValueError("时间列必须单调递增")
        else:
            # 无时间列，按采样率生成
            time_data = np.arange(len(df)) / sfreq

        ch_names = df.columns.tolist()
        data = df.values.T  # (n_ch, n_samples)

        # 单位换算 -> µV
        unit = unit.lower()
        if unit in ("mv", "millivolt"):
            data *= 1000
        elif unit in ("v", "volt"):
            data *= 1_000_000
        elif unit in ("uv", "µv", "microvolt"):
            pass
        else:
            raise ValueError(f"不支持的单位: {unit}")

        # 构建 ChannelInfo
        channel_info = {}
        for ch in ch_names:
            ctype = ChannelType.EEG
            if ch_types and ch in ch_types:
                ctype = ChannelType(ch_types[ch].lower())
            channel_info[ch] = ChannelInfo(name=ch, type=ctype)

        # 尝试加载标准蒙版（跨 MNE 版本兼容）
        montage = None
        try:
            from eeg_workbench.utils.montage import make_standard_montage_compat
            std_montage = make_standard_montage_compat(montage_name)
            montage = Montage.from_mne_montage(std_montage, name=montage_name)
        except Exception:
            pass

        # 构建 EEGDataset
        ds = EEGDataset(
            id=Path(file_path).stem,
            name=kwargs.get("name", path.stem),
            file_path=file_path,
            data=data.astype(np.float64),
            sfreq=float(sfreq),
            ch_names=ch_names,
            channel_info=channel_info,
            montage=montage,
        )

        # 伴随元数据
        meta = self._load_sidecar_metadata(file_path)
        if meta:
            ds.metadata = meta
            # 同步元数据中的采样率等
            if meta.sampling_frequency and not sfreq:
                ds.sfreq = meta.sampling_frequency

        # 发布事件
        from eeg_workbench.core.events import get_event_bus, EventType, DatasetLoadedPayload
        get_event_bus().publish(
            EventType.DATASET_LOADED,
            DatasetLoadedPayload(
                dataset_id=ds.id,
                file_path=file_path,
                n_channels=ds.n_channels,
                duration=ds.duration,
                sfreq=ds.sfreq
            ),
            source=self.FORMAT_NAME
        )

        return LoadResult(dataset=ds, metadata={"source_format": "table"})


# 便捷函数：从 DataFrame 直接创建
def create_dataset_from_dataframe(
    df: pd.DataFrame,
    sfreq: float,
    ch_names: list[str] | None = None,
    time_column: str | int | None = None,
    unit: str = "uV",
    name: str = "DataFrame Import"
) -> EEGDataset:
    """直接从 pandas DataFrame 创建 EEGDataset（用于插件/脚本）"""
    from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
    import numpy as np

    if time_column is not None:
        if isinstance(time_column, str):
            time_data = df[time_column].values
            df = df.drop(columns=[time_column])
        else:
            time_data = df.iloc[:, time_column].values
            df = df.drop(df.columns[time_column], axis=1)
    else:
        time_data = np.arange(len(df)) / sfreq

    # 注意：ch_names 必须在移除时间列之后推导，否则默认通道列表会包含已删除的
    # time 列，df[ch_names] 在 pandas 下抛 KeyError: "['time'] not in index"
    if ch_names is None:
        ch_names = df.columns.tolist()

    data = df[ch_names].values.T
    unit = unit.lower()
    if unit in ("mv", "millivolt"):
        data *= 1000
    elif unit in ("v", "volt"):
        data *= 1_000_000

    channel_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}

    ds = EEGDataset(
        id=name.lower().replace(" ", "_"),
        name=name,
        file_path="",
        data=data.astype(np.float64),
        sfreq=float(sfreq),
        ch_names=ch_names,
        channel_info=channel_info,
    )
    return ds