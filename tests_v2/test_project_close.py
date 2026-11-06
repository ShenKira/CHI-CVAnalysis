# -*- coding: utf-8 -*-
"""Regression tests for closing the current project."""

from __future__ import annotations

import os
import threading
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.main_window import BASE_WINDOW_TITLE, MainWindow
from cvanalysis.ui.widgets.plot_tab import PlotTab


def _make_window(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    return app, window


def test_close_project_action_shortcut_and_menu(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    assert not window.close_project_action.isEnabled()
    assert window.close_project_action.shortcut() == QKeySequence("Ctrl+Shift+W")
    assert window.close_project_action.shortcutContext() == Qt.WindowShortcut
    assert window.close_project_action.text() == "关闭当前项目"

    file_menu = next(
        menu for menu in window.findChildren(QMenu) if menu.title().startswith("文件")
    )
    assert window.close_project_action in file_menu.actions()
    window.close()
    app.processEvents()


def test_close_project_resets_workspace_and_keeps_app_state(
    tmp_path, synthetic_cv_runs
):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window._add_plot_tab(
        PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    )
    window._project_analysis = {"default_normalization": "mass"}
    window.dataset.path = tmp_path / "old.cvproj"
    window.results_panel.results_tabs.setCurrentIndex(2)
    window.settings_service.settings["app"]["last_directory"] = str(tmp_path)
    window.settings_service.settings["app"]["recent_projects"] = ["old.cvproj"]
    window._mark_dirty()

    assert window.close_project() is True
    app.processEvents()

    assert window.dataset.is_empty
    assert window.dataset.path is None
    assert window.dataset.name == "未命名数据集"
    assert window.tabs.count() == 0
    assert window.dataset_model.rowCount() == 0
    assert window.results_panel.cv_model.rowCount() == 0
    assert window.results_panel.eis_model.rowCount() == 0
    assert window.results_panel.cp_model.rowCount() == 0
    assert window.results_panel.results_tabs.currentIndex() == 0
    assert window.file_detail_label.text() == "未选择文件"
    assert window.analysis_panel.info_label.text() == "尚未导入数据"
    assert window.analysis_panel.normalization_combo.currentData() == "none"
    assert window.analysis_panel.fit_model_combo.currentData() == "auto"
    assert window.analysis_panel.target_spin.value() == 0.0
    assert window.analysis_panel.freq_low_edit.text() == ""
    assert window.analysis_panel.freq_high_edit.text() == ""
    assert window.analysis_panel.freq_low_edit.placeholderText() == "低频，如 0.01"
    assert window.analysis_panel.freq_high_edit.placeholderText() == "高频，如 1e6"
    assert window.analysis_panel.analysis_tabs.currentIndex() == 0
    assert window.options_panel.tab is None
    assert not window.options_panel.apply_button.isEnabled()
    assert window.fits == {}
    assert window.metrics == {}
    assert window._project_analysis is None
    assert window._pending_redraw_tabs == []
    assert not window._redraw_timer.isActive()
    assert window._dirty is False
    assert window.windowTitle() == BASE_WINDOW_TITLE
    assert not window.close_project_action.isEnabled()
    assert not window.close_tab_action.isEnabled()
    assert window.settings_service.settings["app"]["last_directory"] == str(tmp_path)
    assert window.settings_service.settings["app"]["recent_projects"] == ["old.cvproj"]
    assert "项目已关闭" in window.statusBar().currentMessage()
    window.close()
    app.processEvents()


def test_close_project_cancel_and_discard_branches(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    path = tmp_path / "cancel.cvproj"
    window.dataset.path = path
    window._mark_dirty()

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel) as prompt:
        assert window.close_project() is False
    assert prompt.called
    assert not window.dataset.is_empty
    assert window.tabs.count() > 0
    assert window.dataset.path == path
    assert window._dirty

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
        assert window.close_project() is True
    assert window.dataset.is_empty
    assert window.dataset.path is None
    assert not path.exists()
    assert window.tabs.count() == 0
    window.close()
    app.processEvents()


def test_close_project_save_success_then_resets_path(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    path = tmp_path / "saved.cvproj"
    window.dataset.path = path
    window._mark_dirty()

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Save):
        assert window.close_project() is True
    assert path.exists()
    assert window.dataset.is_empty
    assert window.dataset.path is None
    window.close()
    app.processEvents()


def test_close_project_save_as_success_then_resets(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window._mark_dirty()
    path = tmp_path / "save-as.cvproj"

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Save), patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(path), "CVAnalysis 项目 (*.cvproj)"),
    ) as dialog:
        assert window.close_project() is True
    assert dialog.called
    assert path.exists()
    assert window.dataset.is_empty
    assert window.dataset.path is None
    window.close()
    app.processEvents()


def test_close_project_save_as_cancel_and_failure_abort(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window._mark_dirty()

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Save), patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        assert window.close_project() is False
    assert not window.dataset.is_empty
    assert window.dataset.path is None
    assert window.tabs.count() > 0

    failing_path = tmp_path / "failing.cvproj"
    window.dataset.path = failing_path
    window._project_analysis = {"default_normalization": "mass"}
    tabs_before = window.tabs.count()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Save), patch(
        "cvanalysis.ui.main_window.save_project_file",
        side_effect=RuntimeError("disk full"),
    ), patch.object(QMessageBox, "critical") as critical:
        assert window.close_project() is False
    assert critical.called
    assert not window.dataset.is_empty
    assert window.dataset.path == failing_path
    assert window._dirty
    assert window.tabs.count() == tabs_before
    assert window.close_tab_action.isEnabled()
    assert window._project_analysis == {"default_normalization": "mass"}
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
        window.close()
    app.processEvents()


def test_close_project_empty_dirty_skips_save_prompt(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window.dataset.clear()
    window._mark_dirty()
    assert window.dataset.is_empty and window._dirty

    with patch.object(QMessageBox, "question") as prompt:
        assert window.close_project() is True
    assert not prompt.called
    assert window._dirty is False
    assert window.windowTitle() == BASE_WINDOW_TITLE
    window.close()
    app.processEvents()


def test_close_project_blocked_while_background_busy(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window._tasks.append(object())
    with patch.object(QMessageBox, "information") as information:
        assert window.close_project() is False
    assert information.called
    assert not window.dataset.is_empty
    assert window.tabs.count() > 0
    window._tasks.clear()

    class FakeImportThread:
        def isRunning(self):
            return True

    window.import_thread = FakeImportThread()
    with patch.object(QMessageBox, "information") as information:
        assert window.close_project() is False
    assert information.called
    window.import_thread = None
    window.close()
    app.processEvents()


def test_closing_project_does_not_redraw_hidden_dirty_tabs(
    tmp_path, synthetic_cv_runs, monkeypatch
):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    for _ in range(2):
        window._add_plot_tab(
            PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
        )
    window.tabs.setCurrentIndex(0)
    window._mark_all_tabs_dirty()

    calls = []
    original = PlotTab.redraw

    def counted(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(PlotTab, "redraw", counted)
    assert window.close_project() is True
    assert calls == []
    window.close()
    app.processEvents()


def test_background_task_keeps_ui_alive_and_close_waits(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window.show()
    gate = threading.Event()
    applied = []
    window._run_task(lambda: gate.wait(3), applied.append)
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    app.processEvents()
    assert ticks
    window.close()
    assert window.isVisible()
    gate.set()
    for _ in range(200):
        QTest.qWait(10)
        app.processEvents()
        if not window._tasks:
            break
    assert not window._tasks
    assert not window.isVisible()
    assert not applied


def test_ctrl_shift_w_closes_project_without_closing_window(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    window.show()
    window.activateWindow()
    canvas = window.tabs.currentWidget().canvas
    canvas.setFocus()
    app.processEvents()

    QTest.keyClick(canvas, Qt.Key_W, Qt.ControlModifier | Qt.ShiftModifier)
    app.processEvents()

    assert window.isVisible()
    assert window.dataset.is_empty
    assert window.tabs.count() == 0
    assert window.windowTitle() == BASE_WINDOW_TITLE
    window.close()
    app.processEvents()


def test_reimport_after_close_uses_save_as(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    old_path = tmp_path / "old-project.cvproj"
    window.dataset.path = old_path
    window._mark_dirty()
    assert window.close_project() is True

    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    new_path = tmp_path / "new-project.cvproj"
    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(new_path), "CVAnalysis 项目 (*.cvproj)"),
    ) as dialog:
        assert window.save_project() is True
    assert dialog.called
    assert new_path.exists()
    assert not old_path.exists()
    window.close()
    app.processEvents()
