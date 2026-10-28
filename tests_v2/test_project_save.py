# -*- coding: utf-8 -*-
from unittest.mock import patch

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar

from cvanalysis.domain.models import Dataset
from cvanalysis.ui.main_window import MainWindow


def _make_window(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    return app, window


def test_ctrl_s_saves_to_existing_project_without_dialog(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    path = tmp_path / "project.cvproj"
    window.dataset.path = path

    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        side_effect=AssertionError("Ctrl+S should not open Save As for an existing project"),
    ):
        assert window.save_project() is True
    assert path.exists()
    assert window.windowTitle().endswith(path.name)

    run = synthetic_cv_runs[0]
    run.legend_template = "{File_Name}"
    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        side_effect=AssertionError("second Ctrl+S should overwrite the same project"),
    ):
        assert window.save_project() is True
    assert "{File_Name}" in path.read_text(encoding="utf-8")
    window.close()
    app.processEvents()


def test_ctrl_s_without_project_path_prompts_once_then_saves_directly(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    path = tmp_path / "new-project.cvproj"

    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(path), "CVAnalysis 项目 (*.cvproj)"),
    ) as dialog:
        assert window.save_project() is True
    dialog.assert_called_once()
    assert window.dataset.path == path
    assert path.exists()

    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        side_effect=AssertionError("saved project should be reused"),
    ):
        assert window.save_project() is True
    window.close()
    app.processEvents()


def test_save_as_uses_new_path_and_has_its_own_shortcut(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    old_path = tmp_path / "old.cvproj"
    new_path = tmp_path / "new.cvproj"
    window.dataset.path = old_path

    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(new_path), "CVAnalysis 项目 (*.cvproj)"),
    ) as dialog:
        assert window.save_project_as() is True
    dialog.assert_called_once()
    assert window.dataset.path == new_path
    assert new_path.exists()

    assert window.save_project_action.shortcut() == QKeySequence(QKeySequence.Save)
    assert window.save_project_as_action.shortcut() == QKeySequence(QKeySequence.SaveAs)
    toolbar = window.findChild(QToolBar, "main_toolbar")
    assert window.save_project_action in toolbar.actions()
    assert window.save_project_action.text() == "保存"
    window.close()
    app.processEvents()


def test_save_cancel_and_failure_keep_current_path(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)

    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        assert window.save_project() is False
    assert window.dataset.path is None

    path = tmp_path / "existing.cvproj"
    window.dataset.path = path
    with patch(
        "cvanalysis.ui.main_window.save_project_file",
        side_effect=RuntimeError("disk full"),
    ), patch.object(QMessageBox, "critical") as critical:
        assert window.save_project() is False
    assert window.dataset.path == path
    critical.assert_called_once()
    window.close()
    app.processEvents()


def test_save_is_blocked_while_background_task_is_running(tmp_path, synthetic_cv_runs):
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    path = tmp_path / "busy.cvproj"
    window.dataset.path = path
    window._tasks.append(object())
    with patch.object(QMessageBox, "information") as information:
        assert window.save_project() is False
    assert information.called
    assert not path.exists()
    window._tasks.clear()
    window.close()
    app.processEvents()


def test_dirty_marker_and_close_prompt(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    assert window._dirty
    assert "*" in window.windowTitle()

    path = tmp_path / "dirty-project.cvproj"
    with patch(
        "cvanalysis.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(path), "CVAnalysis 项目 (*.cvproj)"),
    ):
        assert window.save_project() is True
    assert not window._dirty
    assert "*" not in window.windowTitle()

    window._mark_dirty()
    assert "*" in window.windowTitle()
    window.show()
    app.processEvents()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel) as prompt:
        window.close()
    assert prompt.called
    assert window.isVisible()

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
        window.close()
    app.processEvents()
    assert not window.isVisible()


def test_open_project_warns_before_discarding_changes(tmp_path, synthetic_cv_runs, monkeypatch):
    monkeypatch.delenv("CVANALYSIS_DISABLE_SAVE_PROMPTS", raising=False)
    app, window = _make_window(tmp_path, synthetic_cv_runs)
    assert window._dirty
    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.Cancel
    ) as prompt, patch(
        "cvanalysis.ui.main_window.QFileDialog.getOpenFileName"
    ) as dialog:
        window.open_project()
    assert prompt.called
    assert not dialog.called
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
        window.close()
    app.processEvents()
