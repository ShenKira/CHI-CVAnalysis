# -*- coding: utf-8 -*-
"""Small, consistent Qt stylesheet for the v2 workspace."""

from __future__ import annotations


BASE_FONT_SIZE = 11.0


def application_stylesheet(scale: float = 1.0) -> str:
    scale = max(0.8, min(1.6, float(scale)))
    font_size = BASE_FONT_SIZE * scale
    control_height = max(22, int(24 * scale))
    button_padding = max(4, int(6 * scale))
    button_padding_x = max(8, int(12 * scale))
    tab_padding = max(5, int(7 * scale))
    css = """
    QMainWindow, QDialog {
        background: #f4f6f8;
    }
    QWidget {
        font-family: "Microsoft YaHei", "Segoe UI", "Arial";
        font-size: __FONT_SIZE__pt;
        color: #263238;
    }
    QMenuBar {
        background: #ffffff;
        border-bottom: 1px solid #d9e0e6;
    }
    QMenuBar::item {
        padding: 5px 10px;
        background: transparent;
    }
    QMenuBar::item:selected {
        background: #e8f1fb;
        border-radius: 4px;
    }
    QMenu {
        background: #ffffff;
        border: 1px solid #d9e0e6;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 24px 6px 20px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background: #e8f1fb;
    }
    QToolBar {
        background: #ffffff;
        border-bottom: 1px solid #d9e0e6;
        spacing: 6px;
        padding: 4px;
    }
    QToolButton {
        padding: 5px 10px;
        border-radius: 5px;
        background: transparent;
    }
    QToolButton:hover {
        background: #e8f1fb;
    }
    QPushButton {
        background: #1976d2;
        color: white;
        border: none;
        border-radius: 5px;
        padding: __BUTTON_PADDING__px __BUTTON_PADDING_X__px;
        font-weight: 600;
        min-height: __CONTROL_HEIGHT__px;
    }
    QPushButton:hover {
        background: #1565c0;
    }
    QPushButton:pressed {
        background: #0d47a1;
    }
    QPushButton:disabled {
        background: #b0bec5;
        color: #eceff1;
    }
    QPushButton[secondary="true"] {
        background: #eceff1;
        color: #37474f;
    }
    QPushButton[secondary="true"]:hover {
        background: #dfe6ea;
    }
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
        background: #ffffff;
        border: 1px solid #cfd8dc;
        border-radius: 4px;
        padding: 4px 6px;
        min-height: __CONTROL_HEIGHT__px;
    }
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
        border: 1px solid #1976d2;
    }
    QGroupBox {
        border: 1px solid #d9e0e6;
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 8px;
        background: #ffffff;
        font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #37474f;
    }
    QTreeView, QTableView {
        background: #ffffff;
        alternate-background-color: #f7f9fb;
        border: 1px solid #d9e0e6;
        border-radius: 4px;
        gridline-color: #eceff1;
        selection-background-color: #d8ebff;
        selection-color: #1a237e;
    }
    QHeaderView::section {
        background: #f0f4f7;
        padding: 5px;
        border: none;
        border-right: 1px solid #e0e6ea;
        border-bottom: 1px solid #d9e0e6;
        font-weight: 600;
    }
    QSplitter::handle {
        background: #dfe6ea;
    }
    QSplitter::handle:vertical {
        height: 6px;
    }
    QSplitter::handle:horizontal {
        width: 6px;
    }
    QSplitter::handle:hover {
        background: #90caf9;
    }
    QTabWidget::pane {
        border: 1px solid #d9e0e6;
        background: #ffffff;
        border-radius: 4px;
    }
    QTabBar::tab {
        background: #eef2f5;
        padding: __TAB_PADDING__px 14px;
        margin-right: 2px;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
    }
    QTabBar::tab:selected {
        background: #ffffff;
        color: #1565c0;
        font-weight: 600;
    }
    QMainWindow::separator {
        background: #dfe6ea;
        width: 6px;
        height: 6px;
    }
    QMainWindow::separator:hover {
        background: #90caf9;
    }
    QDockWidget {
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
        font-weight: 600;
    }
    QDockWidget::title {
        background: #eef2f5;
        padding: 6px;
        border-bottom: 1px solid #d9e0e6;
    }
    QStatusBar {
        background: #ffffff;
        border-top: 1px solid #d9e0e6;
    }
    QPlainTextEdit {
        background: #ffffff;
        border: 1px solid #d9e0e6;
        border-radius: 4px;
    }
    """
    return (
        css.replace("__FONT_SIZE__", f"{font_size:.1f}")
        .replace("__CONTROL_HEIGHT__", str(control_height))
        .replace("__BUTTON_PADDING__", str(button_padding))
        .replace("__BUTTON_PADDING_X__", str(button_padding_x))
        .replace("__TAB_PADDING__", str(tab_padding))
    )
