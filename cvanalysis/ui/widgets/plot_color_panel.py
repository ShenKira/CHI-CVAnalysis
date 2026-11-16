# -*- coding: utf-8 -*-
"""Independent graphics and text color editing for the current plot."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from cvanalysis.plotting.colors import detect_figure_color_groups
from cvanalysis.ui.theme import apply_theme_role, theme_color
from cvanalysis.ui.widgets.inline_color_picker import InlineColorPicker

if TYPE_CHECKING:
    from cvanalysis.ui.widgets.plot_tab import PlotTab


class PlotColorPanel(QWidget):
    """Select a used color by role, then choose its replacement in place."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab: PlotTab | None = None
        self._selected: tuple[str, str] | None = None
        self._buttons: dict[tuple[str, str], QPushButton] = {}
        self._build_ui()
        self.bind(None)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("绘图颜色")
        apply_theme_role(title, "title")
        header.addWidget(title)
        self.info = QLabel("选择图形或文字色块，再在右侧选色。")
        self.info.setWordWrap(True)
        apply_theme_role(self.info, "hint")
        header.addWidget(self.info, 1)
        self.reset_button = QPushButton("恢复默认颜色")
        self.reset_button.setProperty("secondary", True)
        self.reset_button.setToolTip("清除本图的颜色覆盖，恢复预设颜色")
        self.reset_button.clicked.connect(self._reset_colors)
        header.addWidget(self.reset_button)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(12)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(175)
        scroll.setMaximumWidth(240)
        swatches = QWidget()
        swatch_layout = QVBoxLayout(swatches)
        swatch_layout.setContentsMargins(0, 0, 0, 0)
        swatch_layout.setSpacing(7)
        self._layouts = {}
        for role, label in (("graphics", "图形颜色"), ("text", "文字颜色")):
            heading = QLabel(label)
            apply_theme_role(heading, "title")
            swatch_layout.addWidget(heading)
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self._layouts[role] = grid
            swatch_layout.addWidget(container)
        swatch_layout.addStretch(1)
        scroll.setWidget(swatches)
        body.addWidget(scroll)

        palette_column = QVBoxLayout()
        self.selection_label = QLabel("请先选择左侧色块")
        apply_theme_role(self.selection_label, "hint")
        palette_column.addWidget(self.selection_label)
        self.palette = InlineColorPicker(self)
        self.palette.currentColorChanged.connect(self._update_apply_button)
        palette_column.addWidget(self.palette, 1)
        self.apply_button = QPushButton("应用颜色到当前图")
        self.apply_button.setProperty("primary", True)
        self.apply_button.clicked.connect(self._apply_selected_color)
        palette_column.addWidget(self.apply_button, 0, Qt.AlignRight)
        body.addLayout(palette_column, 1)
        outer.addLayout(body, 1)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _refresh_swatches(self):
        for grid in self._layouts.values():
            self._clear_layout(grid)
        self._buttons.clear()
        if self.tab is None:
            self.info.setText("当前没有图")
            self.reset_button.setEnabled(False)
            self._selected = None
            self.selection_label.setText("请先选择左侧色块")
            self.palette.setEnabled(False)
            self._update_apply_button()
            return
        self.palette.setEnabled(True)
        options = self.tab.spec.analysis_options
        self.reset_button.setEnabled(bool(options.get("color_overrides") or options.get("color_overrides_by_role")))
        groups = detect_figure_color_groups(self.tab.figure)
        self.info.setText("选择图形或文字色块，再在右侧选色。")
        for role, colors in groups.items():
            grid = self._layouts[role]
            if not colors:
                grid.addWidget(QLabel("无"), 0, 0)
            for index, color in enumerate(colors):
                button = QPushButton()
                button.setFixedSize(27, 27)
                button.setCursor(Qt.PointingHandCursor)
                button.setCheckable(True)
                button.setChecked(self._selected == (role, color))
                button.setAccessibleName(("图形颜色 " if role == "graphics" else "文字颜色 ") + color)
                button.setToolTip(button.accessibleName())
                apply_theme_role(button, "color-swatch")
                button.setStyleSheet(
                    f"QPushButton {{ background: {color}; border: 1px solid {theme_color('border_control')}; "
                    f"border-radius: 6px; padding: 0; min-width: 0; min-height: 0; }} "
                    f"QPushButton:checked {{ border: 3px solid {theme_color('primary')}; }}"
                )
                button.clicked.connect(lambda checked=False, r=role, c=color: self._select_color(r, c))
                grid.addWidget(button, index // 5, index % 5)
                self._buttons[(role, color)] = button
        if self._selected not in self._buttons:
            self._selected = None
            self.selection_label.setText("请先选择左侧色块")
        self._update_apply_button()

    def bind(self, tab: PlotTab | None):
        if tab is not self.tab:
            self._selected = None
        self.tab = tab
        self._refresh_swatches()

    def refresh_colors(self):
        self._refresh_swatches()

    def _select_color(self, role, color):
        self._selected = (role, color)
        for key, button in self._buttons.items():
            button.setChecked(key == self._selected)
        self.selection_label.setText(("图形颜色：" if role == "graphics" else "文字颜色：") + color)
        self.palette.setCurrentColor(QColor(color))
        self._update_apply_button()

    def _update_apply_button(self, *_):
        valid = self.tab is not None and self._selected is not None and self.palette.currentColor().isValid()
        if valid:
            valid = self.palette.currentColor().name(QColor.HexRgb).lower() != self._selected[1].lower()
        self.apply_button.setEnabled(bool(valid))

    def _apply_selected_color(self):
        if self.tab is None or self._selected is None:
            return
        role, old = self._selected
        color = self.palette.currentColor()
        if not color.isValid():
            return
        new = color.name(QColor.HexRgb)
        if new.lower() == old.lower():
            return
        options = self.tab.spec.analysis_options
        raw = options.get("color_overrides_by_role")
        by_role = dict(raw) if isinstance(raw, dict) else {}
        role_map = dict(by_role.get(role)) if isinstance(by_role.get(role), dict) else {}
        # Existing maps refer to colors before this role's remap. Compose them
        # so repeated edits survive redraws while retaining the legacy mapping.
        for source, target in list(role_map.items()):
            if str(target).lower() == old.lower():
                role_map[source] = new
        role_map[old] = new
        by_role[role] = role_map
        options["color_overrides_by_role"] = by_role
        self._selected = (role, new)
        self.tab.redraw()
        self._refresh_swatches()
        self.changed.emit()

    def _reset_colors(self):
        if self.tab is None:
            return
        options = self.tab.spec.analysis_options
        changed = options.pop("color_overrides", None) is not None
        roles = options.get("color_overrides_by_role")
        if isinstance(roles, dict):
            remaining = {key: value for key, value in roles.items() if key not in ("graphics", "text")}
            changed = changed or len(remaining) != len(roles)
            if remaining:
                options["color_overrides_by_role"] = remaining
            else:
                options.pop("color_overrides_by_role", None)
        if not changed:
            return
        self._selected = None
        self.tab.redraw()
        self._refresh_swatches()
        self.changed.emit()
