# -*- coding: utf-8 -*-
"""Regression tests for lazy/current-tab plot redraws."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.widgets.plot_tab import PlotTab


def _window_with_two_tabs(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    window._add_plot_tab(
        PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    )
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    return app, window


def test_current_options_only_redraw_current_tab(tmp_path, synthetic_cv_runs, monkeypatch):
    app, window = _window_with_two_tabs(tmp_path, synthetic_cv_runs)
    tab0 = window.tabs.widget(0)
    tab1 = window.tabs.widget(1)
    assert isinstance(tab0, PlotTab) and isinstance(tab1, PlotTab)

    calls = []
    original = PlotTab.redraw

    def counted(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(PlotTab, "redraw", counted)
    calls.clear()

    window._on_options_changed()
    window._redraw_timer.stop()
    window._flush_pending_tabs()

    assert calls == [tab0]

    window.close()
    app.processEvents()


def test_hidden_dirty_tab_redraws_when_activated(tmp_path, synthetic_cv_runs, monkeypatch):
    app, window = _window_with_two_tabs(tmp_path, synthetic_cv_runs)
    tab0 = window.tabs.widget(0)
    tab1 = window.tabs.widget(1)

    calls = []
    original = PlotTab.redraw

    def counted(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(PlotTab, "redraw", counted)
    calls.clear()

    window._mark_all_tabs_dirty()
    window._flush_pending_tabs()
    assert calls == [tab0]

    calls.clear()
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    assert calls == [tab1]

    window.close()
    app.processEvents()
