# -*- coding: utf-8 -*-
"""Qt stylesheet builder driven by JSON theme definitions."""

from __future__ import annotations

from cvanalysis.appearance import (
    ThemeDefinition,
    get_theme,
    load_themes,
    normalize_theme,
)

BASE_FONT_SIZE = 11.0

_CURRENT_THEME: ThemeDefinition | None = None

_QSS_TEMPLATE = """
QMainWindow, QDialog {
    background: __BACKGROUND__;
}
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", "Arial";
    font-size: __FONT_SIZE__pt;
    color: __TEXT__;
}
QMenuBar {
    background: __SURFACE__;
    border-bottom: 1px solid __BORDER__;
}
QMenuBar::item {
    padding: 5px 10px;
    background: transparent;
}
QMenuBar::item:selected {
    background: __MENU_HOVER__;
    border-radius: 4px;
}
QMenu {
    background: __SURFACE__;
    border: 1px solid __BORDER__;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 20px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: __MENU_HOVER__;
}
QToolBar {
    background: __SURFACE__;
    border-bottom: 1px solid __BORDER__;
    spacing: 6px;
    padding: 4px;
}
QToolButton {
    padding: 5px 10px;
    border-radius: 5px;
    background: transparent;
}
QToolButton:hover {
    background: __MENU_HOVER__;
}
QPushButton {
    background: __PRIMARY__;
    color: __PRIMARY_TEXT__;
    border: none;
    border-radius: 5px;
    padding: __BUTTON_PADDING__px __BUTTON_PADDING_X__px;
    font-weight: 600;
    min-height: __CONTROL_HEIGHT__px;
}
QPushButton:hover {
    background: __PRIMARY_HOVER__;
}
QPushButton:pressed {
    background: __PRIMARY_PRESSED__;
}
QPushButton:disabled {
    background: __PRIMARY_DISABLED__;
    color: __PRIMARY_DISABLED_TEXT__;
}
QPushButton[secondary="true"] {
    background: __SECONDARY__;
    color: __SECONDARY_TEXT__;
}
QPushButton[secondary="true"]:hover {
    background: __SECONDARY_HOVER__;
}
QPushButton[themeRole="color-swatch"] {
    border: 1px solid __BORDER__;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: __SURFACE__;
    border: 1px solid __BORDER__;
    border-radius: 4px;
    padding: 4px 6px;
    min-height: __CONTROL_HEIGHT__px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid __FOCUS__;
}
QGroupBox {
    border: 1px solid __BORDER__;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    background: __SURFACE__;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: __SECONDARY_TEXT__;
}
QTreeView, QTableView {
    background: __SURFACE__;
    alternate-background-color: __TABLE_ALT__;
    border: 1px solid __BORDER__;
    border-radius: 4px;
    gridline-color: __GRIDLINE__;
    selection-background-color: __SELECTION_BG__;
    selection-color: __SELECTION_TEXT__;
}
QHeaderView::section {
    background: __HEADER_BG__;
    color: __HEADER_TEXT__;
    padding: 5px;
    border: none;
    border-right: 1px solid __HEADER_BORDER__;
    border-bottom: 1px solid __BORDER__;
    font-weight: 600;
}
QSplitter::handle {
    background: __SPLITTER__;
}
QSplitter::handle:vertical {
    height: 6px;
}
QSplitter::handle:horizontal {
    width: 6px;
}
QSplitter::handle:hover {
    background: __SPLITTER_HOVER__;
}
QTabWidget::pane {
    border: 1px solid __BORDER__;
    background: __SURFACE__;
    border-radius: 4px;
}
QTabBar::tab {
    background: __TAB_BG__;
    padding: __TAB_PADDING__px 14px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabBar::tab:hover {
    background: __SURFACE_ALT__;
}
QTabBar::tab:selected {
    background: __TAB_SELECTED_BG__;
    color: __TAB_SELECTED_TEXT__;
    font-weight: 600;
}
QMainWindow::separator {
    background: __SPLITTER__;
    width: 6px;
    height: 6px;
}
QMainWindow::separator:hover {
    background: __SPLITTER_HOVER__;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    font-weight: 600;
}
QDockWidget::title {
    background: __LOG_TITLE_BG__;
    padding: 6px;
    border-bottom: 1px solid __BORDER__;
}
QStatusBar {
    background: __SURFACE__;
    border-top: 1px solid __BORDER__;
}
QPlainTextEdit {
    background: __SURFACE__;
    border: 1px solid __BORDER__;
    border-radius: 4px;
}
QToolTip {
    background: __TOOLTIP_BG__;
    color: __TOOLTIP_TEXT__;
    border: 1px solid __TOOLTIP_BORDER__;
}
QLabel[themeRole="hint"] {
    color: __MUTED__;
}
QLabel[themeRole="muted"] {
    color: __MUTED_STRONG__;
}
QLabel[themeRole="title"] {
    color: __TEXT__;
    font-weight: 600;
}
QLabel[themeRole="error"] {
    color: __ERROR__;
}
QLabel[themeRole="success"] {
    color: __SUCCESS__;
}
QLabel[themeRole="warning"] {
    color: __WARNING__;
}
QLabel[themeRole="log-title"] {
    background: __LOG_TITLE_BG__;
    padding: 6px;
    border-bottom: 1px solid __BORDER__;
    font-weight: 600;
}
"""


def apply_theme_role(widget, role: str) -> None:
    """Assign a semantic QSS role and refresh the widget style."""
    if widget is None:
        return
    widget.setProperty("themeRole", role)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def set_current_theme(theme: ThemeDefinition) -> None:
    global _CURRENT_THEME
    _CURRENT_THEME = theme


def current_theme() -> ThemeDefinition:
    global _CURRENT_THEME
    if _CURRENT_THEME is None:
        _CURRENT_THEME = get_theme("default", load_themes())
    return _CURRENT_THEME


def theme_color(role: str) -> str:
    """Return a semantic UI color from the active JSON theme."""
    return current_theme().color(role)


def _role_color(theme: ThemeDefinition, fallback: ThemeDefinition, role: str) -> str:
    return theme.colors.get(role) or fallback.colors.get(role, "")


def application_stylesheet(
    scale: float = 1.0,
    theme: str | ThemeDefinition = "default",
    themes_path=None,
) -> str:
    scale = max(0.8, min(1.6, float(scale)))
    themes = load_themes(themes_path)
    default_theme = get_theme("default", themes)
    if isinstance(theme, ThemeDefinition):
        selected = theme
    else:
        selected = get_theme(normalize_theme(theme, [item.id for item in themes]), themes)
    set_current_theme(selected)

    font_size = BASE_FONT_SIZE * scale
    control_height = max(22, int(24 * scale))
    button_padding = max(4, int(6 * scale))
    button_padding_x = max(8, int(12 * scale))
    tab_padding = max(5, int(7 * scale))
    css = _QSS_TEMPLATE
    for role in default_theme.colors:
        css = css.replace(
            "__" + role.upper() + "__",
            _role_color(selected, default_theme, role),
        )
    return (
        css.replace("__FONT_SIZE__", f"{font_size:.1f}")
        .replace("__CONTROL_HEIGHT__", str(control_height))
        .replace("__BUTTON_PADDING__", str(button_padding))
        .replace("__BUTTON_PADDING_X__", str(button_padding_x))
        .replace("__TAB_PADDING__", str(tab_padding))
    )
