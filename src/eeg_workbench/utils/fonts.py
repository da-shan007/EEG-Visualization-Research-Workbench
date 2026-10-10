"""中文字体配置：解决图形/界面中文显示为方框的问题。

背景：matplotlib 默认字体 DejaVu Sans 不含 CJK 字形，图形标题/标签里的
中文会显示成 □□□（实测日志：Glyph ... missing from font(s) DejaVu Sans）；
Qt 界面同理，系统没装中文字体时整个 UI 的中文都是方框——而本项目界面
几乎全是中文。Windows 上有微软雅黑/黑体兜底，**Linux 最小化安装常常一个
中文字体都没有**，因此这里对 Qt 和 matplotlib 分别探测候选字体。

两者的字体查找机制不同，必须分开探测：
  * matplotlib —— ``font_manager.fontManager.ttflist``（扫描系统字体目录）
  * Qt        —— ``QFontDatabase.families()``（由 Qt 平台插件自行枚举）

本模块在应用启动时挑选系统已有的中文字体并写入对应配置，全局生效。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from PySide6.QtWidgets import QApplication

#: 按优先级排列的候选中文字体（Windows / macOS / Linux）
#: Linux 常见来源：fonts-noto-cjk（Noto Sans CJK SC）、fonts-wqy-microhei、
#: fonts-wqy-zenhei、fonts-arphic-uming、fonts-droid-fallback
CANDIDATE_CJK_FONTS = (
    # Windows
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    # macOS
    "PingFang SC",
    "Heiti SC",
    "Hiragino Sans GB",
    "STHeiti",
    # Linux
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans CJK TC",
    "Source Han Sans SC",
    "Noto Serif CJK SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Noto Sans SC",
    "Droid Sans Fallback",
    "AR PL UMing CN",
    "AR PL UKai CN",
)


def _available_candidates(available: set[str]) -> Optional[str]:
    """从已安装字体集合中按优先级挑第一个候选中文字体。"""
    return next((f for f in CANDIDATE_CJK_FONTS if f in available), None)


def ensure_cjk_font() -> Optional[str]:
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
    chosen = _available_candidates(available)
    if chosen is None:
        return None
    matplotlib.rcParams["font.sans-serif"] = [
        chosen, *matplotlib.rcParams.get("font.sans-serif", []),
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return chosen


def ensure_qt_cjk_font(app: "QApplication") -> Optional[str]:
    """把 Qt 界面字体设为系统已有的中文字体，返回选中的字体名。

    必须**在 QApplication 构造之后**调用（字体数据库随 app 初始化）。
    无可用中文字体时返回 None 且不改动现有字体，界面中文仍为方框。
    多次调用安全（幂等）。
    """
    try:
        from PySide6.QtGui import QFont, QFontDatabase
    except ImportError:
        return None

    chosen = _available_candidates(set(QFontDatabase.families()))
    if chosen is None:
        return None
    font = QFont(chosen)
    font.setPointSize(app.font().pointSize())
    app.setFont(font)
    return chosen


def missing_cjk_font_hint() -> Optional[str]:
    """两端都没装中文字体时返回给用户看的安装提示，否则返回 None。"""
    matplotlib_font = ensure_cjk_font()
    try:
        from PySide6.QtGui import QFontDatabase

        qt_available = set(QFontDatabase.families())
    except ImportError:
        qt_available = set()
    if matplotlib_font is not None or _available_candidates(qt_available) is not None:
        return None
    return (
        "未检测到中文字体，界面与图形中的中文会显示为方框。"
        "Debian/Ubuntu: sudo apt install fonts-noto-cjk fonts-wqy-microhei ; "
        "Fedora: sudo dnf install google-noto-sans-cjk-fonts ; "
        "Arch: sudo pacman -S noto-fonts-cjk wqy-microhei"
    )