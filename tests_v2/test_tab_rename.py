"""Regression coverage for inline plot-tab names."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu
import pytest

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.theme import application_stylesheet


@pytest.fixture
def rename_window(tmp_path, test_application, synthetic_cv_runs):
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    window._add_plot_tab(PlotSpec(
        "cv_overlay", [synthetic_cv_runs[0].run_id], title="Figure title"
    ))
    if window._plot_warning_box:
        window._plot_warning_box.close()
    window.dataset_dock.hide()
    window.analysis_dock.hide()
    window.show()
    test_application.processEvents()
    window._mark_clean()
    return window


def double_click_tab(window, index, app):
    bar = window.tabs.tabBar()
    QTest.mouseDClick(bar, Qt.LeftButton, pos=bar.tabRect(index).center())
    app.processEvents()
    editor = window._tab_renamer.editor
    assert editor is not None and editor.isVisible()
    return editor


@pytest.mark.parametrize("theme", ["default", "kon"])
def test_inline_double_click_targets_tab_and_survives_data_changes(
    rename_window, test_application, synthetic_cv_runs, theme,
):
    window, app = rename_window, test_application
    app.setStyleSheet(application_stylesheet(1.0, theme))
    first, second = window.tabs.widget(0), window.tabs.widget(1)
    assert window.tabs.currentWidget() is second
    original_title = first.spec.title
    original_data = list(first.spec.run_ids)
    editor = double_click_tab(window, 0, app)
    assert window._tab_renamer.plot is first
    assert editor.selectedText() == window._plot_tab_title(first.spec)
    editor.setText("循环稳定性")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert first.spec.tab_name == "循环稳定性"
    assert second.spec.tab_name == ""
    assert first.spec.title == original_title
    assert first.spec.run_ids == original_data
    assert window.tabs.tabText(window.tabs.indexOf(first)) == "循环稳定性"
    tooltip = window.tabs.tabToolTip(window.tabs.indexOf(first))
    assert "循环稳定性" in tooltip and first.spec.label in tooltip
    assert synthetic_cv_runs[0].display_name in tooltip
    assert window._dirty

    first.spec.run_ids = [synthetic_cv_runs[-1].run_id]
    window._plot_data_changed(first)
    app.processEvents()
    assert window.tabs.tabText(window.tabs.indexOf(first)) == "循环稳定性"
    assert synthetic_cv_runs[-1].display_name in window.tabs.tabToolTip(window.tabs.indexOf(first))


def test_escape_empty_and_focus_out_keep_independent_names(rename_window, test_application):
    window, app = rename_window, test_application
    first, second = window.tabs.widget(0), window.tabs.widget(1)
    window.tabs.setCurrentWidget(second)
    app.processEvents()
    window.options_panel.fraction.setText("0.333")
    pending = window.options_panel.fraction.text()
    editor = double_click_tab(window, window.tabs.indexOf(second), app)
    editor.setText("实验名称")
    QTest.keyClick(editor, Qt.Key_Escape)
    app.processEvents()
    assert second.spec.tab_name == ""
    assert not window._dirty
    assert window.options_panel.fraction.text() == pending

    editor = double_click_tab(window, window.tabs.indexOf(second), app)
    editor.setText("实验名称")
    window.tree.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    assert second.spec.tab_name == "实验名称"
    assert window.options_panel.fraction.text() == pending

    editor = double_click_tab(window, window.tabs.indexOf(first), app)
    editor.setText("实验名称")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert first.spec.tab_name == second.spec.tab_name == "实验名称"

    editor = double_click_tab(window, window.tabs.indexOf(first), app)
    editor.clear()
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert first.spec.tab_name == ""
    assert window.tabs.tabText(window.tabs.indexOf(first)) == window._plot_tab_title(first.spec)
    assert second.spec.tab_name == "实验名称"


def test_move_and_close_do_not_rename_another_plot(rename_window, test_application):
    window, app = rename_window, test_application
    first, second = window.tabs.widget(0), window.tabs.widget(1)
    editor = double_click_tab(window, 0, app)
    editor.setText("移动后的标签")
    window.tabs.tabBar().moveTab(0, 1)
    app.processEvents()
    if window._tab_renamer.editor is not None:
        QTest.keyClick(window._tab_renamer.editor, Qt.Key_Return)
    app.processEvents()
    assert first.spec.tab_name == "移动后的标签"
    assert second.spec.tab_name == ""

    editor = double_click_tab(window, window.tabs.indexOf(first), app)
    editor.setText("不会提交")
    window._close_tab(window.tabs.indexOf(first))
    app.processEvents()
    assert window._tab_renamer.editor is None
    assert second.spec.tab_name == ""
    assert window.tabs.count() == 1


def test_tab_menu_reset_and_empty_area(rename_window, test_application):
    window, app = rename_window, test_application
    tab = window.tabs.currentWidget()
    tab.spec.tab_name = "手动名称"
    window._update_plot_tab_label(tab)
    window._mark_clean()
    invoked = []

    def invoke_reset():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            return
        actions = {action.text(): action for action in menu.actions()}
        invoked.append((actions["重命名"].isEnabled(), actions["恢复自动名称"].isEnabled()))
        actions["恢复自动名称"].trigger()
        menu.close()

    bar = window.tabs.tabBar()
    position = bar.tabRect(window.tabs.currentIndex()).center()
    QTimer.singleShot(100, invoke_reset)
    bar.customContextMenuRequested.emit(position)
    app.processEvents()
    assert invoked == [(True, True)] and tab.spec.tab_name == ""
    assert window._dirty
    assert window._tab_renamer.editor is None

    window.tabs.tabBarDoubleClicked.emit(-1)
    bar.customContextMenuRequested.emit(QPoint(-1, -1))
    app.processEvents()
    assert len(invoked) == 1
    assert window._tab_renamer.editor is None


def test_tab_menu_rename_transfers_focus_after_menu_closes(rename_window, test_application):
    window, app = rename_window, test_application
    tab = window.tabs.currentWidget()
    bar = window.tabs.tabBar()
    observed = []

    def choose_rename():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            return
        rename = next(action for action in menu.actions() if action.text() == "重命名")
        observed.append(rename.isEnabled())
        rename.trigger()
        menu.close()

    QTimer.singleShot(100, choose_rename)
    bar.customContextMenuRequested.emit(bar.tabRect(window.tabs.currentIndex()).center())
    app.processEvents()
    editor = window._tab_renamer.editor
    assert observed == [True]
    assert editor is not None and editor.isVisible() and editor.hasFocus()
    editor.setText("菜单标签")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert tab.spec.tab_name == "菜单标签"


def test_rename_does_not_redraw_or_apply_pending_options(
    rename_window, test_application, monkeypatch,
):
    window, app = rename_window, test_application
    tab = window.tabs.currentWidget()
    window.options_panel.fraction.setText("0.375")
    calls = []
    monkeypatch.setattr(tab, "redraw", lambda: calls.append(True))
    before = dict(tab.spec.paper_layout)
    editor = double_click_tab(window, window.tabs.currentIndex(), app)
    editor.setText("纯标签修改")
    QTest.keyClick(editor, Qt.Key_Return)
    app.processEvents()
    assert calls == []
    assert window.options_panel.fraction.text() == "0.375"
    assert tab.spec.paper_layout == before
    assert tab.spec.tab_name == "纯标签修改"
