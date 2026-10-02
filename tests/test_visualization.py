"""可视化模块单元测试"""
from pathlib import Path

import numpy as np
import pytest

from eeg_workbench.models.visualization import (
    PlotConfig, WaveformPlotConfig, SpectralPlotConfig, TFRPlotConfig,
    ConnectivityPlotConfig, StatisticalPlotConfig, SourcePlotConfig,
    ReportConfig, PlotType, PlotBackend, ExportFormat,
    WAVEFORM_PRESET, SPECTRAL_PRESET, TFR_PRESET,
    CONNECTIVITY_PRESET, STATISTICAL_PRESET, SOURCE_PRESET,
    REPORT_PRESET, create_plot_config
)
from eeg_workbench.models.dataset import EEGDataset, ChannelInfo, ChannelType
from eeg_workbench.services.visualization import (
    PlottingService, ReportGenerator, ExportService
)


# ---- 测试辅助 ----
def make_test_dataset(n_ch=8, n_samples=1000, sfreq=250.0) -> EEGDataset:
    """创建测试用数据集"""
    data = np.random.randn(n_ch, n_samples) * 10
    ch_names = [f"Ch{i}" for i in range(n_ch)]
    ch_info = {ch: ChannelInfo(name=ch, type=ChannelType.EEG) for ch in ch_names}
    return EEGDataset(
        name="TestDataset",
        data=data.astype(np.float64),
        sfreq=sfreq,
        ch_names=ch_names,
        channel_info=ch_info,
    )


# ---- Models 测试 ----
class TestPlotConfigs:
    def test_waveform_preset(self):
        config = WAVEFORM_PRESET
        assert isinstance(config, WaveformPlotConfig)
        assert config.n_channels_per_plot == 20
        assert config.line_width == 0.8

    def test_spectral_preset(self):
        config = SPECTRAL_PRESET
        assert isinstance(config, SpectralPlotConfig)
        assert config.method == "welch"
        assert config.fmin == 0
        assert config.fmax == 100

    def test_tfr_preset(self):
        config = TFR_PRESET
        assert isinstance(config, TFRPlotConfig)
        assert config.method == "morlet"
        assert config.n_cycles == 7.0

    def test_connectivity_preset(self):
        config = CONNECTIVITY_PRESET
        assert isinstance(config, ConnectivityPlotConfig)
        assert config.matrix_cmap == "RdBu_r"
        assert config.matrix_vmin == -1
        assert config.matrix_vmax == 1

    def test_statistical_preset(self):
        config = STATISTICAL_PRESET
        assert isinstance(config, StatisticalPlotConfig)
        assert config.plot_type == "bar"
        assert config.effect_size_type == "cohen_d"

    def test_source_preset(self):
        config = SOURCE_PRESET
        assert isinstance(config, SourcePlotConfig)
        assert config.surface == "inflated"
        assert config.hemi == "both"

    def test_report_preset(self):
        config = REPORT_PRESET
        assert isinstance(config, ReportConfig)
        assert config.title == "EEG 分析报告"
        assert config.output_format == ExportFormat.PDF

    def test_create_plot_config(self):
        config = create_plot_config(PlotType.RAW_WAVEFORM, figsize=(10, 8))
        assert config.figsize == (10, 8)
        assert config.n_channels_per_plot == 20

        config = create_plot_config(PlotType.PSD, fmin=1, fmax=50)
        assert config.fmin == 1
        assert config.fmax == 50


class TestReportConfig:
    def test_default_values(self):
        config = ReportConfig()
        assert config.title == "EEG 分析报告"
        assert config.output_format == ExportFormat.PDF
        assert config.include_toc is True
        assert config.figure_dpi == 300
        assert config.figure_width_cm == 16
        assert "overview" in config.sections

    def test_custom_sections(self):
        config = ReportConfig(sections=["overview", "erp", "statistics"])
        assert config.sections == ["overview", "erp", "statistics"]


# ---- Services 测试 ----
class TestPlottingService:
    def test_plot_waveform(self):
        ds = make_test_dataset()
        service = PlottingService()
        config = WaveformPlotConfig()
        
        # 这里主要测试不抛出异常
        try:
            result = service.plot_waveform(ds, config)
            assert result is not None
        except ImportError:
            # matplotlib 未安装时跳过
            pytest.skip("matplotlib 未安装")

    def test_plot_spectral(self):
        ds = make_test_dataset()
        service = PlottingService()
        config = SpectralPlotConfig()
        
        try:
            result = service.plot_spectral(ds, config)
            assert result is not None
        except ImportError:
            pytest.skip("matplotlib 未安装")


class TestReportGenerator:
    def test_pdf_fallback(self):
        config = ReportConfig()
        generator = ReportGenerator()
        
        try:
            result = generator._generate_pdf_fallback(config)
            assert result.output_path.endswith(".pdf")
        except ImportError:
            pytest.skip("reportlab 未安装")

    def test_html_generation(self):
        config = ReportConfig()
        config.output_format = ExportFormat.HTML
        generator = ReportGenerator()
        
        result = generator._generate_html(None, config, None)
        assert result.format == ExportFormat.HTML
        assert result.output_path.endswith(".html")


class TestExportService:
    def test_export_csv(self):
        data = np.random.randn(10, 5)
        service = ExportService()
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
            result = service.export_data(data, tmp.name, ExportFormat.CSV)
            assert result.format == ExportFormat.CSV
            assert Path(tmp.name).exists()
        # 文件句柄关闭后再清理（Windows 下句柄未关会 WinError 32）
        Path(tmp.name).unlink()

    def test_export_json(self):
        data = {"key": "value", "array": [1, 2, 3]}
        service = ExportService()
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            result = service.export_data(data, tmp.name, ExportFormat.JSON)
            assert result.format == ExportFormat.JSON
            assert Path(tmp.name).exists()
        Path(tmp.name).unlink()

    def test_export_npz(self):
        data = np.random.randn(10, 5)
        service = ExportService()
        
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.npz', delete=False) as tmp:
            result = service.export_data(data, tmp.name, ExportFormat.NPZ)
            assert result.format == ExportFormat.NPZ
            assert Path(tmp.name).exists()
        Path(tmp.name).unlink()


# ---- 集成测试 ----
class TestVisualizationIntegration:
    def test_full_pipeline_waveform(self):
        """完整流程：数据 -> 波形图 -> 导出"""
        ds = make_test_dataset()
        
        # 1. 绘制波形
        service = PlottingService()
        config = WaveformPlotConfig()
        result = service.plot_waveform(ds, config)
        
        # 2. 导出
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            export_service = ExportService()
            result = export_service.export_figure(result.figure, tmp.name)
            assert result.format == ExportFormat.PNG
        # 句柄关闭后再清理（Windows 下 WinError 32）
        Path(tmp.name).unlink()

    def test_report_generation_pipeline(self):
        """报告生成完整流程"""
        ds = make_test_dataset()
        
        config = ReportConfig(
            title="测试报告",
            author="Test",
            sections=["overview", "methods", "results"]
        )
        
        generator = ReportGenerator()
        result = generator._generate_pdf_fallback(config)
        assert result.output_path.endswith(".pdf")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])