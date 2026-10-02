"""IO 服务测试 (使用模拟数据)"""
import tempfile
from pathlib import Path
import numpy as np
import pytest

from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, Event, ChannelType
from eeg_workbench.services.io import ReaderFactory


class TestReaderFactory:
    def test_supported_extensions(self):
        exts = ReaderFactory.supported_extensions()
        assert ".edf" in exts
        assert ".bdf" in exts
        assert ".vhdr" in exts
        assert ".set" in exts
        assert ".csv" in exts
        assert ".tsv" in exts
        assert ".xlsx" in exts

    def test_unsupported_format(self):
        with pytest.raises(ValueError):
            ReaderFactory.get_reader("test.xyz")


class TestTableReader:
    """测试 CSV/Excel 表格读取器"""

    def test_create_from_dataframe(self):
        from eeg_workbench.services.io.csv_excel import create_dataset_from_dataframe
        import pandas as pd

        # 创建测试 DataFrame
        n_ch, n_samples = 3, 1000
        sfreq = 250.0
        ch_names = ["Fp1", "Fp2", "Cz"]
        data = np.random.randn(n_samples, n_ch) * 10
        df = pd.DataFrame(data, columns=ch_names)
        df["time"] = np.arange(n_samples) / sfreq

        ds = create_dataset_from_dataframe(
            df, sfreq=sfreq, time_column="time", unit="uV", name="TestDF"
        )

        assert ds.n_channels == 3
        assert ds.ch_names == ch_names
        assert ds.sfreq == sfreq
        assert abs(ds.duration - 4.0) < 0.01
        assert ds.data.shape == (n_ch, n_samples)

    def test_csv_roundtrip(self):
        """测试 CSV 写入再读取"""
        from eeg_workbench.services.io.csv_excel import create_dataset_from_dataframe
        import pandas as pd

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"

            # 创建原始数据集
            n_ch, n_samples = 2, 500
            sfreq = 100.0
            ch_names = ["Ch1", "Ch2"]
            data = np.random.randn(n_ch, n_samples) * 5
            df = pd.DataFrame(data.T, columns=ch_names)
            df.insert(0, "time", np.arange(n_samples) / sfreq)

            ds1 = create_dataset_from_dataframe(df, sfreq=sfreq, time_column="time", name="Roundtrip")

            # 导出为 CSV（mne 1.13 的 Raw.export 不支持 fmt="csv"，改用 pandas 写出）
            df.to_csv(csv_path, index=False)

            # 重新加载
            result = ReaderFactory.load_dataset(str(csv_path), sfreq=sfreq, time_column="time")
            ds2 = result.dataset

            # 验证
            assert ds2.n_channels == n_ch
            assert ds2.sfreq == sfreq
            assert np.allclose(ds2.data, ds1.data, atol=1e-6)


class TestEventImporters:
    """测试事件导入导出"""

    def test_vmrk_export_import(self):
        from eeg_workbench.services.events import export_vmrk, import_vmrk

        ds = EEGDataset(
            name="Test",
            data=np.random.randn(2, 1000),
            sfreq=250.0,
            ch_names=["Ch1", "Ch2"],
            channel_info={c: ChannelInfo(name=c) for c in ["Ch1", "Ch2"]},
            events=[
                Event(onset=0.5, duration=0, description="Stimulus/S1", value=1, sample=125),
                Event(onset=1.0, duration=0.1, description="Response/Left", value=2, sample=250),
                Event(onset=2.0, duration=0, description="BAD_segment", value=-1),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            vmrk_path = Path(tmpdir) / "test.vmrk"
            export_vmrk(ds, str(vmrk_path))

            # 读回
            ds2 = import_vmrk(str(vmrk_path), ds)
            assert len(ds2.events) >= 3

    def test_tsv_export_import(self):
        from eeg_workbench.services.events import export_tsv, import_tsv

        ds = EEGDataset(
            name="Test",
            data=np.random.randn(2, 1000),
            sfreq=250.0,
            ch_names=["Ch1", "Ch2"],
            channel_info={c: ChannelInfo(name=c) for c in ["Ch1", "Ch2"]},
            events=[
                Event(onset=0.5, duration=0, description="Stimulus/S1", value=1),
                Event(onset=1.0, duration=0.1, description="Response/Left", value=2),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tsv_path = Path(tmpdir) / "events.tsv"
            export_tsv(ds, str(tsv_path))

            # 读回
            ds2 = import_tsv(str(tsv_path), ds)
            assert len(ds2.events) >= 2
            # 验证关键字段
            for ev in ds2.events:
                assert ev.onset in [0.5, 1.0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])