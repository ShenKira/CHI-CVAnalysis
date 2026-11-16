# -*- coding: utf-8 -*-
"""Qt stylesheet builder driven by JSON theme definitions and UI tokens."""

from __future__ import annotations

from cvanalysis.appearance import (
    ThemeDefinition,
    get_theme,
    load_themes,
    normalize_theme,
)
from cvanalysis.ui.tokens import (
    BASE_FONT_SIZE,
    FONT_FAMILIES,
    UiTokens,
)

_CURRENT_THEME: ThemeDefinition | None = None

_QSS_TEMPLATE = """
QMainWindow, QDialog {
    background: __BACKGROUND__;
}
QWidget {
    font-family: __FONT_FAMILY__;
    font-size: __FONT_SIZE__pt;
    color: __TEXT__;
}
QMenuBar {
    background: __SURFACE__;
    border-bottom: 1px solid __BORDER_LIGHT__;
    padding: 2px;
}
QMenuBar::item {
    padding: 6px 10px;
    background: transparent;
    border-radius: __RADIUS_MD__px;
}
QMenuBar::item:selected {
    background: __MENU_HOVER__;
}
QMenu {
    background: __SURFACE__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_LG__px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 26px 7px 18px;
    border-radius: __RADIUS_MD__px;
}
QMenu::item:selected {
    background: __MENU_HOVER__;
}
QMenu::item:disabled {
    color: __TEXT_TERTIARY__;
}
QMenu::separator {
    height: 1px;
    background: __MENU_SEPARATOR__;
    margin: 4px 8px;
}
QToolBar {
    background: __SURFACE__;
    border: none;
    border-bottom: 1px solid __BORDER_LIGHT__;
    spacing: __SPACE_XS__px;
    padding: 6px 8px;
}
QToolButton {
    padding: __BUTTON_PADDING__px __BUTTON_PADDING_X__px;
    min-height: __CONTROL_HEIGHT__px;
    border-radius: __RADIUS_MD__px;
    background: transparent;
}
QToolButton:hover {
    background: __SURFACE_ALT__;
}
QToolButton:pressed {
    background: __SURFACE_SUNKEN__;
}
QToolButton:checked {
    background: __SELECTION_BG__;
    color: __SELECTION_TEXT__;
}
QToolButton:focus {
    background: __SELECTION_BG__;
}
QPushButton {
    background: __SURFACE__;
    color: __TEXT__;
    border: 1px solid __BORDER_CONTROL__;
    border-radius: __RADIUS_MD__px;
    padding: __BUTTON_PADDING__px __BUTTON_PADDING_X__px;
    font-weight: 600;
    min-height: __CONTROL_HEIGHT__px;
}
QPushButton[secondary="true"] {
    background: __SURFACE__;
    color: __TEXT__;
    border-color: __BORDER_CONTROL__;
}
QPushButton:hover {
    background: __SURFACE_ALT__;
    border-color: __PRIMARY__;
}
QPushButton:pressed {
    background: __SURFACE_SUNKEN__;
}
QPushButton:focus {
    border: 2px solid __FOCUS__;
    padding: __BUTTON_FOCUS_PADDING__px __BUTTON_FOCUS_PADDING_X__px;
}
QPushButton[primary="true"] {
    background: __PRIMARY__;
    color: __PRIMARY_TEXT__;
    border: 1px solid __PRIMARY__;
}
QPushButton[primary="true"]:hover {
    background: __PRIMARY_HOVER__;
    border-color: __PRIMARY_HOVER__;
}
QPushButton[primary="true"]:pressed {
    background: __PRIMARY_PRESSED__;
    border-color: __PRIMARY_PRESSED__;
}
QPushButton[primary="true"]:focus {
    border: 2px solid __FOCUS__;
    padding: __BUTTON_FOCUS_PADDING__px __BUTTON_FOCUS_PADDING_X__px;
}
QPushButton[pill="true"] {
    border-radius: __RADIUS_PILL__px;
    padding-left: __PILL_PADDING_X__px;
    padding-right: __PILL_PADDING_X__px;
}
QPushButton[danger="true"] {
    background: __ERROR_BG__;
    color: __ERROR__;
    border-color: __ERROR__;
}
QPushButton[danger="true"]:hover {
    background: __SURFACE_SUNKEN__;
    border-color: __ERROR__;
}
QPushButton:disabled {
    background: __SURFACE_SUNKEN__;
    color: __TEXT_DISABLED__;
    border-color: __BORDER_LIGHT__;
}
QPushButton[themeRole="color-swatch"] {
    border: 1px solid __BORDER_CONTROL__;
    border-radius: __RADIUS_SM__px;
    padding: 2px;
    min-width: 0;
    min-height: 0;
}
QPushButton[themeRole="color-swatch"]:focus {
    border: 2px solid __FOCUS__;
    padding: 1px;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: __SURFACE__;
    border: 1px solid __BORDER_CONTROL__;
    border-radius: __RADIUS_SM__px;
    padding: 5px 8px;
    min-height: __CONTROL_HEIGHT__px;
    selection-background-color: __SELECTION_BG__;
    selection-color: __SELECTION_TEXT__;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 2px solid __FOCUS__;
    padding: 4px 7px;
}
QLineEdit:read-only {
    background: __SURFACE_SUNKEN__;
    color: __TEXT_SECONDARY__;
}
QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {
    background: __SURFACE_SUNKEN__;
    color: __TEXT_DISABLED__;
    border-color: __BORDER_LIGHT__;
}
QComboBox QAbstractItemView {
    background: __SURFACE__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_MD__px;
    selection-background-color: __SELECTION_BG__;
    selection-color: __SELECTION_TEXT__;
    padding: 4px;
}
QCheckBox, QRadioButton {
    spacing: __SPACE_SM__px;
}
QGroupBox {
    background: __SURFACE_ALT__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_LG__px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: __TEXT_SECONDARY__;
    background: __SURFACE_ALT__;
}
QTreeView, QTableView {
    background: __SURFACE__;
    alternate-background-color: __TABLE_ALT__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_LG__px;
    gridline-color: __GRIDLINE__;
    selection-background-color: __SELECTION_BG__;
    selection-color: __SELECTION_TEXT__;
    outline: none;
}
QTreeView::item, QTableView::item {
    padding: 3px 6px;
    min-height: __ROW_HEIGHT__px;
}
QTreeView::item:selected, QTableView::item:selected {
    background: __SELECTION_BG__;
    color: __SELECTION_TEXT__;
}
QTreeView::item:selected:!active, QTableView::item:selected:!active {
    background: __SELECTION_INACTIVE_BG__;
}
QTreeView:focus, QTableView:focus {
    border: 2px solid __FOCUS__;
}
QHeaderView::section {
    background: __HEADER_BG__;
    color: __HEADER_TEXT__;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid __HEADER_BORDER__;
    border-bottom: 1px solid __HEADER_BORDER__;
    font-weight: 600;
}
QTableCornerButton::section {
    background: __HEADER_BG__;
    border: none;
    border-bottom: 1px solid __HEADER_BORDER__;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: __SCROLLBAR__;
    border-radius: __RADIUS_SM__px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: __SCROLLBAR_HOVER__;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: __SCROLLBAR__;
    border-radius: __RADIUS_SM__px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: __SCROLLBAR_HOVER__;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QSplitter::handle {
    background: __SURFACE_ALT__;
}
QSplitter::handle:vertical {
    height: 8px;
}
QSplitter::handle:horizontal {
    width: 8px;
}
QSplitter::handle:hover {
    background: __SPLITTER_HOVER__;
}
QMainWindow::separator {
    background: __SURFACE_ALT__;
    width: 8px;
    height: 8px;
}
QMainWindow::separator:hover {
    background: __SPLITTER_HOVER__;
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QWidget[themeRole="canvas-host"] {
    background: __SURFACE_ALT__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: 0px;
}
QTreeView[structuralView="true"] { border-radius: 0px; }
QTabBar::tab {
    background: __TAB_BG__;
    padding: __TAB_PADDING__px 14px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-top-left-radius: __RADIUS_MD__px;
    border-top-right-radius: __RADIUS_MD__px;
}
QTabBar::tab:hover {
    background: __SURFACE_ALT__;
}
QTabBar::tab:selected {
    background: __TAB_SELECTED_BG__;
    color: __TAB_SELECTED_TEXT__;
    border: 1px solid __BORDER_LIGHT__;
    border-bottom: 2px solid __PRIMARY__;
    font-weight: 600;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    font-weight: 600;
}
QDockWidget::title {
    background: __SURFACE_ALT__;
    padding: 8px 10px;
    border-bottom: 1px solid __BORDER_LIGHT__;
}
QStatusBar {
    background: __SURFACE__;
    border-top: 1px solid __BORDER_LIGHT__;
}
QPlainTextEdit {
    background: __SURFACE__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_LG__px;
    selection-background-color: __SELECTION_BG__;
    selection-color: __SELECTION_TEXT__;
}
QPlainTextEdit[structuralView="true"] { border-radius: 0px; }
QToolTip {
    background: __TOOLTIP_BG__;
    color: __TOOLTIP_TEXT__;
    border: 1px solid __TOOLTIP_BORDER__;
    border-radius: __RADIUS_MD__px;
    padding: 6px 8px;
}
QProgressBar {
    background: __SURFACE_SUNKEN__;
    border: 1px solid __BORDER_LIGHT__;
    border-radius: __RADIUS_MD__px;
    text-align: center;
    min-height: 10px;
}
QProgressBar::chunk {
    background: __PRIMARY__;
    border-radius: __RADIUS_SM__px;
}
QDialogButtonBox QPushButton {
    min-width: 84px;
}
QLabel[themeRole="hint"] {
    color: __TEXT_TERTIARY__;
    font-size: __SMALL_FONT_SIZE__pt;
}
QLabel[themeRole="muted"] {
    color: __TEXT_SECONDARY__;
}
QLabel[themeRole="title"] {
    color: __TEXT__;
    font-size: __TITLE_FONT_SIZE__pt;
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
    padding: 7px 8px;
    border-bottom: 1px solid __BORDER_LIGHT__;
    font-weight: 600;
}
"""


def apply_theme_role(widget, role: str) -> None:
    """Assign a semantic QSS role and refresh the widget style."""
    if widget is None:
        return
    widget.setProperty("themeRole", role)
    _repolish(widget)


def apply_button_role(button, role: str = "secondary", *, pill: bool = False) -> None:
    """Set the visual hierarchy of a button without duplicating QSS rules.

    ``primary`` is reserved for the one action that commits the current
    context.  ``danger`` is reserved for destructive actions.  Large primary
    actions may opt into the pill shape; compact toolbar buttons should not.
    """
    if button is None:
        return
    role = str(role or "secondary").lower()
    button.setProperty("primary", role == "primary")
    button.setProperty("danger", role == "danger")
    button.setProperty("secondary", role not in {"primary", "danger"})
    button.setProperty("pill", bool(pill))
    _repolish(button)


def _repolish(widget) -> None:
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
    tokens = UiTokens.from_scale(scale)
    themes = load_themes(themes_path)
    default_theme = get_theme("default", themes)
    if isinstance(theme, ThemeDefinition):
        selected = theme
    else:
        selected = get_theme(normalize_theme(theme, [item.id for item in themes]), themes)
    set_current_theme(selected)

    css = _QSS_TEMPLATE
    for role in default_theme.colors:
        css = css.replace(
            "__" + role.upper() + "__",
            _role_color(selected, default_theme, role),
        )
    replacements = {
        "__FONT_FAMILY__": ", ".join(f'"{family}"' for family in FONT_FAMILIES),
        "__FONT_SIZE__": f"{tokens.font_size_pt:.1f}",
        "__SMALL_FONT_SIZE__": f"{tokens.small_font_pt:.1f}",
        "__TITLE_FONT_SIZE__": f"{tokens.title_font_pt:.1f}",
        "__CONTROL_HEIGHT__": str(tokens.control_height),
        "__ROW_HEIGHT__": str(tokens.row_height),
        "__BUTTON_PADDING__": str(tokens.button_padding_y),
        "__BUTTON_PADDING_X__": str(tokens.button_padding_x),
        "__BUTTON_FOCUS_PADDING__": str(max(3, tokens.button_padding_y - 1)),
        "__BUTTON_FOCUS_PADDING_X__": str(max(9, tokens.button_padding_x - 1)),
        "__PILL_PADDING_X__": str(tokens.button_padding_x + 8),
        "__TAB_PADDING__": str(tokens.tab_padding_y),
        "__RADIUS_SM__": str(tokens.radius_sm),
        "__RADIUS_MD__": str(tokens.radius_md),
        "__RADIUS_LG__": str(tokens.radius_lg),
        "__RADIUS_PILL__": str(
            max(14, (tokens.control_height + 2 * tokens.button_padding_y) // 2 + 1)
        ),
        "__SPACE_XS__": str(tokens.space_xs),
        "__SPACE_SM__": str(tokens.space_sm),
    }
    for key, value in replacements.items():
        css = css.replace(key, value)
    return css
