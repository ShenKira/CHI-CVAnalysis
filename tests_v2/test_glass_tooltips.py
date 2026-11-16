# -*- coding: utf-8 -*-
"""Liquid Glass tooltip behavior for the right-side analysis panel."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from cvanalysis.ui.glass.tooltips import LiquidTooltipFilter


class _Manager:
    def __init__(self, mode: str = "balanced"):
        self.mode = mode
        self.animations = False


def _send_tooltip_event(widget: QWidget) -> bool:
    position = QPoint(5, 5)
    event = QHelpEvent(
        QEvent.ToolTip, position, widget.mapToGlobal(position)
    )
    return bool(QApplication.sendEvent(widget, event))


def test_filter_shows_and_hides_glass_tooltip():
    app = QApplication.instance() or QApplication([])
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("hover")
    button.setToolTip("第一行提示\n第二行提示")
    layout.addWidget(button)
    root.show()
    app.processEvents()
    tooltip_filter = LiquidTooltipFilter(root, _Manager())
    try:
        assert _send_tooltip_event(button)
        app.processEvents()
        tooltip = tooltip_filter.tooltip
        assert tooltip.isVisible()
        assert tooltip.label.text() == "第一行提示\n第二行提示"
        assert tooltip.glass_mode == "balanced"
        assert tooltip.width() > 0 and tooltip.height() > 0

        QApplication.sendEvent(button, QEvent(QEvent.Leave))
        app.processEvents()
        assert not tooltip.isVisible()
    finally:
        tooltip_filter.tooltip.deleteLater()
        root.deleteLater()
        app.processEvents()


def test_empty_tooltip_does_not_show_and_solid_mode_falls_back():
    app = QApplication.instance() or QApplication([])
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("hover")
    button.setToolTip("")
    layout.addWidget(button)
    root.show()
    app.processEvents()
    tooltip_filter = LiquidTooltipFilter(root, _Manager("solid"))
    try:
        _send_tooltip_event(button)
        assert not tooltip_filter.tooltip.isVisible()

        button.setToolTip("solid fallback")
        _send_tooltip_event(button)
        app.processEvents()
        assert tooltip_filter.tooltip.isVisible()
        assert tooltip_filter.tooltip.glass_mode == "solid"
    finally:
        tooltip_filter.tooltip.deleteLater()
        root.deleteLater()
        app.processEvents()


def test_children_added_after_install_are_watched():
    app = QApplication.instance() or QApplication([])
    root = QWidget()
    layout = QVBoxLayout(root)
    root.show()
    app.processEvents()
    tooltip_filter = LiquidTooltipFilter(root, _Manager())
    try:
        button = QPushButton("late child")
        button.setToolTip("late tooltip")
        layout.addWidget(button)
        app.processEvents()
        assert _send_tooltip_event(button)
        app.processEvents()
        assert tooltip_filter.tooltip.isVisible()
        assert tooltip_filter.tooltip.label.text() == "late tooltip"
    finally:
        tooltip_filter.tooltip.deleteLater()
        root.deleteLater()
        app.processEvents()


def test_main_window_installs_filter_on_analysis_panel(tmp_path):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "tooltip_settings.json")
    try:
        window.show()
        app.processEvents()
        tooltip_filter = window.analysis_tooltip_filter
        assert isinstance(tooltip_filter, LiquidTooltipFilter)
        assert tooltip_filter.root is window.analysis_panel
        assert tooltip_filter.manager is window.glass_manager
        window.analysis_panel.info_label.setToolTip("analysis panel tooltip")
        assert _send_tooltip_event(window.analysis_panel.info_label)
        app.processEvents()
        assert tooltip_filter.tooltip.isVisible()
        assert tooltip_filter.tooltip.label.text() == "analysis panel tooltip"
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()


def test_analysis_tab_and_combo_item_tooltips_use_glass(tmp_path):
    from PySide6.QtCore import Qt

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "tooltip_tabs.json")
    try:
        window.show()
        app.processEvents()
        tooltip = window.analysis_tooltip_filter.tooltip
        tabs = window.analysis_panel.analysis_tabs
        tab_bar = tabs.tabBar()
        tab_position = tab_bar.tabRect(0).center()
        tab_event = QHelpEvent(
            QEvent.ToolTip,
            tab_position,
            tab_bar.mapToGlobal(tab_position),
        )
        QApplication.sendEvent(tab_bar, tab_event)
        app.processEvents()
        assert tooltip.isVisible()
        assert tooltip.label.text() == tab_bar.tabToolTip(0)

        tooltip.hide_tooltip()
        combo = window.analysis_panel.fit_model_combo
        combo.showPopup()
        app.processEvents()
        view = combo.view()
        index = view.model().index(1, 0)
        assert index.data(Qt.ToolTipRole)
        item_position = view.visualRect(index).center()
        item_event = QHelpEvent(
            QEvent.ToolTip,
            item_position,
            view.mapToGlobal(item_position),
        )
        QApplication.sendEvent(view, item_event)
        app.processEvents()
        assert tooltip.isVisible()
        assert tooltip.label.text() == index.data(Qt.ToolTipRole)
        combo.hidePopup()
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()
