"""导出服务：图形、数据、报告的多格式导出"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Literal
from pathlib import Path
import time
import numpy as np
import json

from eeg_workbench.models.visualization import (
    ExportFormat, PlotConfig
)
from eeg_workbench.services.visualization.plotting import FigureResult
from eeg_workbench.models.dataset import EEGDataset
from eeg_workbench.services.visualization.plotting import PlottingService
from eeg_workbench.services.visualization.report_generator import ReportGenerator


@dataclass
class ExportResult:
    """导出结果"""
    output_path: str
    format: ExportFormat
    file_size_bytes: int
    processing_time_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class ExportService:
    """导出服务：统一的多格式导出接口"""

    def __init__(self) -> None:
        self.plotting_service = PlottingService()
        self.report_generator = ReportGenerator()

    # ---- 图形导出 ----
    def export_figure(
        self,
        figure: Any,
        output_path: str,
        format: ExportFormat = ExportFormat.PNG,
        dpi: int = 300,
        bbox_inches: str = "tight",
        **kwargs: Any
    ) -> ExportResult:
        """导出图形为指定格式"""
        start_time = time.perf_counter()

        if format == ExportFormat.PNG:
            figure.savefig(output_path, dpi=300, bbox_inches=bbox_inches)
        elif format == ExportFormat.PDF:
            figure.savefig(output_path, format='pdf', bbox_inches=bbox_inches)
        elif format == ExportFormat.SVG:
            figure.savefig(output_path, format='svg', bbox_inches=bbox_inches)
        elif format == ExportFormat.EPS:
            figure.savefig(output_path, format='eps', bbox_inches=bbox_inches)
        elif format == ExportFormat.HTML:
            # 使用 mpld3 或 plotly 导出交互式 HTML
            try:
                import mpld3
                html_str = mpld3.fig_to_html(figure)
                Path(output_path).write_text(html_str)
            except ImportError:
                # 回退：静态 HTML + base64 图片
                self._export_html_fallback(figure, output_path)
        else:
            raise ValueError(f"不支持的图形导出格式: {format}")

        file_size = Path(output_path).stat().st_size
        elapsed = (time.perf_counter() - start_time) * 1000

        return ExportResult(
            output_path=output_path,
            format=format,
            file_size_bytes=file_size,
            processing_time_ms=elapsed,
            metadata={"dpi": 300}
        )

    def _export_html_fallback(self, figure: Any, output_path: str) -> None:
        """HTML 导出回退方案"""
        import base64
        from io import BytesIO
        
        buf = BytesIO()
        figure.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>EEG Figure Export</title>
    <style>
        body {{ margin: 0; padding: 20px; font-family: sans-serif; }}
        .container {{ max-width: 100%; text-align: center; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <img src="data:image/png;base64,{img_b64}" alt="Exported Figure">
    </div>
</body>
</html>
        """
        Path(output_path).write_text(html, encoding='utf-8')

    # ---- 数据导出 ----
    def export_data(
        self,
        data: Any,
        output_path: str,
        format: ExportFormat = ExportFormat.CSV,
        **kwargs: Any
    ) -> ExportResult:
        """导出数据"""
        start_time = time.perf_counter()

        if format == ExportFormat.CSV:
            self._export_csv(data, output_path, **kwargs)
        elif format == ExportFormat.JSON:
            self._export_json(data, output_path, **kwargs)
        elif format == ExportFormat.NPZ:
            self._export_npz(data, output_path, **kwargs)
        elif format == ExportFormat.EXCEL:
            self._export_excel(data, output_path, **kwargs)
        else:
            raise ValueError(f"不支持的数据导出格式: {format}")

        file_size = Path(output_path).stat().st_size
        elapsed = (time.perf_counter() - start_time) * 1000

        return ExportResult(
            output_path=output_path,
            format=format,
            file_size_bytes=file_size,
            processing_time_ms=elapsed,
            metadata={}
        )

    def _export_csv(self, data: Any, output_path: str, **kwargs: Any) -> None:
        """导出 CSV"""
        import pandas as pd
        
        if isinstance(data, np.ndarray):
            # 如果是多维数组，展平或仅导出第一个通道
            if data.ndim == 2:
                df = pd.DataFrame(data.T, columns=[f"Ch{i}" for i in range(data.shape[0])])
            elif data.ndim == 3:
                # (n_epochs, n_ch, n_times) -> 展平为长表格
                n_epochs, n_ch, n_times = data.shape
                records = []
                for ep in range(n_epochs):
                    for ch in range(data.shape[1]):
                        for t, val in enumerate(data[ep, ch]):
                            records.append({
                                'epoch': ep,
                                'channel': ch,
                                'time_point': t,
                                'value': val
                            })
                df = pd.DataFrame(records)
            else:
                df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame(data)
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame([data])
        
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

    def _export_json(self, data: Any, output_path: str, **kwargs: Any) -> None:
        """导出 JSON"""
        if isinstance(data, np.ndarray):
            data = data.tolist()
        elif hasattr(data, 'tolist'):
            data = data.tolist()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def _export_npz(self, data: Any, output_path: str, **kwargs: Any) -> None:
        """导出 NPZ (NumPy 压缩格式)"""
        if isinstance(data, dict):
            np.savez_compressed(output_path, **data)
        elif isinstance(data, np.ndarray):
            np.savez_compressed(output_path, data=data)
        else:
            np.savez_compressed(output_path, data=np.array(data))

    def _export_excel(self, data: Any, output_path: str, **kwargs: Any) -> None:
        """导出 Excel"""
        import pandas as pd
        
        if isinstance(data, dict):
            # 多 sheet
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                for sheet_name, sheet_data in data.items():
                    if isinstance(sheet_data, np.ndarray):
                        pd.DataFrame(sheet_data).to_excel(writer, sheet_name=sheet_name, index=False)
                    elif isinstance(sheet_data, pd.DataFrame):
                        sheet_data.to_excel(writer, sheet_name=sheet_name, index=False)
                    else:
                        pd.DataFrame(sheet_data).to_excel(writer, sheet_name=sheet_name, index=False)
        elif isinstance(data, np.ndarray):
            pd.DataFrame(data).to_excel(output_path, index=False)
        elif isinstance(data, pd.DataFrame):
            data.to_excel(output_path, index=False)
        else:
            pd.DataFrame([data]).to_excel(output_path, index=False)

    # ---- 报告导出 ----
    def export_report(
        self,
        dataset: EEGDataset,
        output_path: str,
        format: ExportFormat = ExportFormat.PDF,
        config: Optional[Any] = None,
        sections_data: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> ExportResult:
        """导出完整报告"""
        start_time = time.perf_counter()

        if format == ExportFormat.PDF:
            # 使用 report_generator
            from eeg_workbench.services.visualization.report_generator import generate_report
            from eeg_workbench.models.visualization import ReportConfig
            
            if config is None:
                config = ReportConfig()
            config.output_format = ExportFormat.PDF
            config.output_path = output_path
            
            generator = ReportGenerator()
            result = generator.generate(dataset, config, sections_data)
            
        elif format == ExportFormat.HTML:
            from eeg_workbench.services.visualization.report_generator import generate_html_report
            from eeg_workbench.models.visualization import ReportConfig
            
            if config is None:
                config = ReportConfig()
            config.output_format = ExportFormat.HTML
            config.output_path = output_path
            
            result = generate_html_report(dataset, config, sections_data)
            
        elif format == ExportFormat.DOCX:
            from eeg_workbench.models.visualization import ReportConfig

            if config is None:
                config = ReportConfig()
            config.output_format = ExportFormat.DOCX
            config.output_path = output_path

            generator = ReportGenerator()
            result = generator.generate(dataset, config, sections_data)
        elif format == ExportFormat.PPTX:
            from eeg_workbench.models.visualization import ReportConfig

            if config is None:
                config = ReportConfig()
            config.output_format = ExportFormat.PPTX
            config.output_path = output_path

            generator = ReportGenerator()
            result = generator.generate(dataset, config, sections_data)
        else:
            raise ValueError(f"不支持的报告导出格式: {format}")

        file_size = Path(output_path).stat().st_size
        elapsed = (time.perf_counter() - start_time) * 1000

        return ExportResult(
            output_path=output_path,
            format=format,
            file_size_bytes=file_size,
            processing_time_ms=elapsed,
            metadata={"sections": len(config.sections) if config else 0}
        )

    # ---- 批量导出 ----
    def export_batch(
        self,
        items: list[dict[str, Any]],  # 每项包含 type, data, path, format
        **kwargs: Any
    ) -> list[ExportResult]:
        """批量导出多个项目"""
        results: list[ExportResult] = []
        for item in items:
            try:
                if item.get('type') == 'figure':
                    result = self.export_figure(
                        item['data'], item['path'], item.get('format', ExportFormat.PNG)
                    )
                elif item.get('type') == 'data':
                    result = self.export_data(item['data'], item['path'], item.get('format', ExportFormat.CSV))
                elif item.get('type') == 'report':
                    result = self.export_report(item['data'], item['path'], item.get('format', ExportFormat.PDF))
                else:
                    raise ValueError(f"未知导出类型: {item.get('type')}")
                results.append(result)
            except Exception as e:
                results.append(ExportResult(
                    output_path=item['path'],
                    format=item.get('format', ExportFormat.CSV),
                    file_size_bytes=0,
                    processing_time_ms=0,
                    metadata={"error": str(e)}
                ))
        return results


def export_figure(
    figure: Any,
    output_path: str,
    format: ExportFormat = ExportFormat.PNG,
    **kwargs: Any
) -> ExportResult:
    """导出图形的便捷函数"""
    service = ExportService()
    return service.export_figure(figure, output_path, format, **kwargs)


def export_data(
    data: Any,
    output_path: str,
    format: ExportFormat = ExportFormat.CSV,
    **kwargs: Any
) -> ExportResult:
    """导出数据的便捷函数"""
    service = ExportService()
    return service.export_data(data, output_path, format, **kwargs)


def export_report(
    dataset: EEGDataset,
    output_path: str,
    format: ExportFormat = ExportFormat.PDF,
    **kwargs: Any
) -> ExportResult:
    """导出报告的便捷函数"""
    service = ExportService()
    return service.export_report(dataset, output_path, format, **kwargs)