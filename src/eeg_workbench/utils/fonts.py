"""matplotlib 中文字体配置：解决图形中文显示为方框的问题。

背景：matplotlib 默认字体 DejaVu Sans 不含 CJK 字形，图形标题/标签里的
中文会显示成 □□□（实测日志：Glyph ... missing from font(s) DejaVu Sans）。
本模块在应用启动时挑选系统已有的中文字体并写入 rcParams，全局生效。
"""
from __future__ import annotations


#: 按优先级排列的候选中文字体（Windows / macOS / Linux）
CANDIDATE_CJK_FONTS = (
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Noto Sans SC",
)


def ensure_cjk_font() -> str | None:
    """挑选系统已有中文字体并配置给 matplotlib，返回选中的字体名。

    无可用中文字体时返回 None（图形中文仍为方框，调用方可据此提示用户）。
    多次调用安全（幂等）。
    """
    try:
        import matplotlib
        from matplotlib import font_manager
    except ImportError:
        return None

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((f for f in CANDIDATE_CJK_FONTS if f in available), None)
    if chosen is None:
        return None
    matplotlib.rcParams["font.sans-serif"] = [
        chosen, *matplotlib.rcParams.get("font.sans-serif", []),
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return chosen
