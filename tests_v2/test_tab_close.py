# -*- coding: utf-8 -*-
"""Regression tests for closing the active plot tab."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.main_window import MainWindow


def _make_window(tmp_path, synthetic_cv_runs, *, tabs: int = 1):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    for _ in range(max(0, tabs - 1)):
        window._add_plot_tab(
            PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
        )
    app.processEvents()
    return app, window


def test_close_tab_action_shortcut_and_menu(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    assert not window.close_tab_action.isEnabled()
    assert window.close_tab_action.shortcut() == QKeySequence("Ctrl+W")
    assert window.close_tab_action.shortcutContext() == Qt.WindowShortcut
    assert window.close_tab_action.text() == "关闭当前标签页"

    view_menu = next(
        menu for menu in window.findChildren(QMenu) if menu.title().startswith("视图")
    )
    assert window.close_tab_action in view_menu.actions()

    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    assert window.close_tab_action.isEnabled()
    window.close()
    app.processEvents()


def test_project_and_tab_shortcuts_do_not_conflict(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    shortcuts = [
        action.shortcut().toString()
        for action in window.findChildren(QAction)
        if not action.shortcut().isEmpty()
    ]
    assert len(shortcuts) == len(set(shortcuts))
    assert window.close_tab_action.shortcut() == QKeySequence("Ctrl+W")
    assert window.close_project_action.shortcut() == QKeySequence("Ctrl+Shift+W")
    window.close()
    app.processEvents()


def test_close_current_tab_keeps_project_data(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs, tabs=2)
    assert window.tabs.count() == 2
    assert window.close_tab_action.isEnabled()
    run_ids = {run.run_id for run in synthetic_cv_runs}

    window.close_tab_action.trigger()
    app.processEvents()

    assert window.tabs.count() == 1
    assert not window.dataset.is_empty
    assert {run.run_id for run in window.dataset.cv_runs} == run_ids
    assert window._dirty
    window.close()
    app.processEvents()


def test_close_last_tab_disables_action_but_keeps_project(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs, tabs=1)
    window.close_tab_action.trigger()
    app.processEvents()
    assert window.tabs.count() == 0
    assert not window.close_tab_action.isEnabled()
    assert not window.close_plots_action.isEnabled()
    assert not window.dataset.is_empty
    window.close()
    app.processEvents()


def test_ctrl_w_closes_canvas_tab_without_closing_window(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs, tabs=2)
    window.show()
    window.activateWindow()
    canvas = window.tabs.currentWidget().canvas
    canvas.setFocus()
    app.processEvents()

    QTest.keyClick(canvas, Qt.Key_W, Qt.ControlModifier)
    app.processEvents()

    assert window.tabs.count() == 1
    assert window.isVisible()
    assert not window.dataset.is_empty
    window.close()
    app.processEvents()


def test_close_tab_when_no_tabs_is_a_noop(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs, tabs=1)
    window._close_all_tabs_silent()
    app.processEvents()
    assert window.tabs.count() == 0
    window._close_current_tab()
    app.processEvents()
    assert window.tabs.count() == 0
    window.close()
    app.processEvents()
