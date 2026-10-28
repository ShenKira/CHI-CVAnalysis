# -*- coding: utf-8 -*-
"""Color swatches for the current plot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.plotting.colors import detect_figure_colors

if TYPE_CHECKING:
    from cvanalysis.ui.widgets.plot_tab import PlotTab


class PlotColorPanel(QWidget):
    """Show used colors and change them for the current plot only."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab: PlotTab | None = None
        self._swatches_layout: QHBoxLayout | None = None
        self.setMinimumHeight(80)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        header = QHBoxLayout()
        title = QLabel("绘图颜色")
        title.setStyleSheet("font-weight: 600; color: #263238;")
        header.addWidget(title)
        self.info = QLabel("当前没有图")
        self.info.setStyleSheet("color: #607d8b;")
        self.info.setWordWrap(True)
        self.info.setMinimumWidth(0)
        header.addWidget(self.info, 1)
        self.reset_button = QPushButton("恢复默认颜色")
        self.reset_button.setProperty("secondary", True)
        self.reset_button.setToolTip("清除本图的颜色覆盖，恢复预设颜色")
        self.reset_button.clicked.connect(self._reset_colors)
        header.addWidget(self.reset_button)
        layout.addLayout(header)

        self.swatches = QWidget()
        self._swatches_layout = QHBoxLayout(self.swatches)
        self._swatches_layout.setContentsMargins(0, 0, 0, 0)
        self._swatches_layout.setSpacing(5)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(38)
        scroll.setWidget(self.swatches)
        layout.addWidget(scroll)
        layout.addStretch(1)
        self.bind(None)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_swatches(self) -> None:
        if self._swatches_layout is None:
            return
        self._clear_layout(self._swatches_layout)
        if self.tab is None:
            self.info.setText("当前没有图")
            self.reset_button.setEnabled(False)
            return
        colors = detect_figure_colors(self.tab.figure)
        self.reset_button.setEnabled(bool(self.tab.spec.analysis_options.get("color_overrides")))
        if not colors:
            self.info.setText("未检测到颜色")
            return
        self.info.setText("点击色块修改当前图颜色（文字颜色在最后）")
        for color in colors:
            button = QPushButton()
            button.setFixedSize(26, 26)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"{color}；点击修改")
            button.setStyleSheet(
                "QPushButton {"
                f"background: {color};"
                "border: 1px solid #607d8b;"
                "border-radius: 4px;"
                "}"
            )
            button.clicked.connect(lambda checked=False, value=color: self._choose_color(value))
            self._swatches_layout.addWidget(button)
        self._swatches_layout.addStretch(1)

    def bind(self, tab: PlotTab | None) -> None:
        self.tab = tab
        self._refresh_swatches()

    def refresh_colors(self) -> None:
        self._refresh_swatches()

    def _choose_color(self, old_color: str) -> None:
        if self.tab is None:
            return
        selected = QColorDialog.getColor(QColor(old_color), self, "选择颜色")
        if not selected.isValid():
            return
        new_color = selected.name(QColor.HexRgb)
        if new_color.lower() == old_color.lower():
            return
        options = self.tab.spec.analysis_options
        overrides = dict(options.get("color_overrides") or {})
        for key, value in list(overrides.items()):
            if str(value).lower() == old_color.lower():
                overrides.pop(key)
        overrides[old_color] = new_color
        options["color_overrides"] = overrides
        self.tab.redraw()
        self.refresh_colors()
        self.changed.emit()

    def _reset_colors(self) -> None:
        if self.tab is None:
            return
        if self.tab.spec.analysis_options.pop("color_overrides", None) is None:
            return
        self.tab.redraw()
        self.refresh_colors()
        self.changed.emit()
