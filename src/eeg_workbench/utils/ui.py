"""UI 布局辅助：统一表单标签/输入框比例。

问题背景：QFormLayout 默认让字段列占据标签列之外的全部宽度，
导致只需显示 4 位数字的 QSpinBox 横向拉满数百像素，
标签与输入框比例失衡（实测约 1:4.3）。

本模块提供 :func:`balance_form`，一次性修正：
- 标签右对齐，紧贴输入框（消除短标签与字段之间的大段空白）
- 数值型输入（QSpinBox/QDoubleSpinBox）限宽
- 下拉框（QComboBox）限宽（枚举文本不需要整行）
- 文本框/列表等保持字段列全宽

所有使用 QFormLayout 的面板统一调用，保证全应用表单比例一致。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QWidget,
)

#: 数值型输入框最大宽度（像素）
DEFAULT_SPIN_MAX_WIDTH = 140
#: 下拉框最大宽度（像素）
DEFAULT_COMBO_MAX_WIDTH = 240


def balance_form(
    form: QFormLayout,
    spin_max_width: int = DEFAULT_SPIN_MAX_WIDTH,
    combo_max_width: int = DEFAULT_COMBO_MAX_WIDTH,
) -> None:
    """平衡一个表单的标签/输入框比例。

    参数：
        form: 要修正的 QFormLayout。
        spin_max_width: QSpinBox/QDoubleSpinBox 的最大宽度。
        combo_max_width: QComboBox 的最大宽度。

    用法::

        form = QFormLayout(group)
        form.addRow("采样率:", spin)
        balance_form(form)
    """
    form.setLabelAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    )
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
        if item is None:
            continue
        widget = item.widget()
        if widget is None:
            continue  # 布局行（如 HBox），跳过
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setMaximumWidth(spin_max_width)
        elif isinstance(widget, QComboBox):
            widget.setMaximumWidth(combo_max_width)


def wrap_scroll(widget: QWidget) -> QScrollArea:
    """把高内容面板装进滚动区：空间不足时出滚动条，不压缩内部控件。

    背景：参数面板自然高度约 700–850px，主窗口默认尺寸下标签页只能分到
    约 300–400px；直接放入会导致 GroupBox 被纵向挤压。用滚动区包裹后，
    面板保持完整高度，多余部分滚动查看。

    用法::

        self._tabs.addTab(wrap_scroll(self._filter_widget), "滤波")
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


def embed_figure(container_layout: Any, fig: Any, old_canvas_attr: str = "_fig_canvas") -> Any:
    """把 matplotlib Figure 嵌入 Qt 布局（替换旧画布并释放资源）。

    参数：
        container_layout: 要放入画布的 QLayout。
        fig: matplotlib Figure；为 None 时只清空旧画布。
        old_canvas_attr: 调用方保存旧画布的属性名（为 None 则不记旧画布，
            每次调用前调用方需自行清理）。

    返回新画布（或 None）。调用方需持有返回值防止 GC，例如::

        self._fig_canvas = embed_figure(self._preview_layout, fig,
                                        old_canvas_attr=None)
    """
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    import matplotlib.pyplot as plt

    parent = container_layout.parentWidget() if hasattr(container_layout, "parentWidget") else None
    old = getattr(parent, old_canvas_attr, None) if parent is not None and old_canvas_attr else None
    if old is not None:
        try:
            plt.close(old.figure)
        except Exception:
            pass
        container_layout.removeWidget(old)
        old.deleteLater()
        setattr(parent, old_canvas_attr, None)
    if fig is None:
        return None
    canvas = FigureCanvasQTAgg(fig)  # type: ignore[no-untyped-call]
    container_layout.addWidget(canvas)
    canvas.draw_idle()  # type: ignore[no-untyped-call]
    if parent is not None and old_canvas_attr:
        setattr(parent, old_canvas_attr, canvas)
    return canvas


def require_table_item(table: QTableWidget, row: int, col: int) -> QTableWidgetItem:
    """取表格单元；缺失时抛错而非返回 None。

    背景：QTableWidget.item() 的类型是 ``QTableWidgetItem | None``，
    各面板对自建行反复写 ``if item is None`` 是噪音。行由调用方自己
    insertRow/setItem 建好时单元必存在，缺失即程序错误，大声失败。
    调用方只需 ``require_table_item(tbl, r, c).text()`` 一行。
    """
    item = table.item(row, col)
    if item is None:
        raise RuntimeError(f"表格单元缺失: row={row}, col={col}")
    return item


def relay_status(panels: Iterable[Any], target: Any) -> None:
    """把一组子面板的 ``status_message`` 信号接到父面板的同名信号。

    各主面板都写过 ``for w in [子面板...]: w.status_message.connect(...)`` 这种循环，
    但列表元素的静态公共基类是 ``QWidget``（它没有 ``status_message``），
    于是 mypy 会误报 ``attr-defined``。契约集中在这里表达一次，
    调用方只需给出面板清单；运行时行为与原循环完全一致。

    参数：
        panels: 拥有 ``status_message = Signal(str)`` 的子面板。
        target: 父面板上的 ``status_message`` 信号（注意传信号本身，不是 .emit）。
    """
    for panel in panels:
        panel.status_message.connect(target.emit)
