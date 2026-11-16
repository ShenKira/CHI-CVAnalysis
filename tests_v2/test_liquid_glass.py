"""Main-window glass integration and native control behaviour."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QMenu, QPushButton, QStatusBar, QToolButton, QWidgetAction
from shiboken6 import isValid

from cvanalysis.domain.models import Dataset
from cvanalysis.ui.dialogs.settings_dialog import SettingsDialog
from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.glass.controls import LiquidComboView
from cvanalysis.ui.glass.material import GlassMaterial, GlassRenderer, _cached_kernel
from cvanalysis.ui.glass.menubar import LiquidMenuBar
from cvanalysis.ui.glass.popups import LayeredMenu, wrap_menu
from cvanalysis.ui.glass.plot_toolbar import CompactNavigationToolbar, _format_coordinate
from cvanalysis.ui.main_window import MainWindow


@pytest.fixture
def window(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    widget = MainWindow(settings_path=tmp_path / "config.json")
    widget.show()
    app.processEvents()
    widget._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    QTest.qWait(80)
    yield widget
    widget._mark_clean()
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_application_popups_including_menu_bar_are_modern(window):
    assert isinstance(window.statusBar(), QStatusBar)
    def assert_glass_tree(menu):
        assert isinstance(menu, LayeredMenu)
        for action in menu.actions():
            if action.menu():
                assert_glass_tree(action.menu())

    assert isinstance(window.menuBar(), LiquidMenuBar)
    for action in window.menuBar().actions():
        if action.menu():
            assert_glass_tree(action.menu())
    assert all(isinstance(button.menu(), LayeredMenu)
               for button in window.quick_analysis_buttons.values())
    assert isinstance(window.preset_combo.view(), LiquidComboView)
    dialog = SettingsDialog(window.settings_service.settings, window,
                            themes=window.settings_service.available_themes())
    dialog.show()
    QTest.qWait(80)
    assert all(isinstance(combo.view(), LiquidComboView) for combo in dialog.findChildren(QComboBox))
    dialog.close()
    dialog.deleteLater()


def test_menu_bar_keeps_actions_shortcuts_and_material_switch(window):
    bar = window.menuBar()
    file_menu = bar.actions()[0].menu()
    analysis = bar.actions()[1].menu()
    assert window.open_action in file_menu.actions()
    assert window.save_project_action in file_menu.actions()
    assert window.close_tab_action in bar.actions()[2].menu().actions()
    cv_menu = analysis.actions()[0].menu()
    assert window.cv_overlay_action in cv_menu.actions()
    assert window.cv_overlay_action in window.quick_analysis_buttons["CV 分析"].menu().actions()
    assert window.close_tab_action.shortcut().toString() == "Ctrl+W"
    before_effects = [QApplication.isEffectEnabled(effect) for effect in
                      (Qt.UI_AnimateMenu, Qt.UI_FadeMenu, Qt.UI_AnimateCombo)]
    window.settings_service.ui_state["material"] = "solid"
    window._refresh_glass_settings()
    file_menu.popup(bar.mapToGlobal(QPoint(0, bar.height())))
    QTest.qWait(40)
    assert not file_menu._glass_enabled
    file_menu.hide()
    window.settings_service.ui_state["material"] = "liquid_glass"
    window._refresh_glass_settings()
    file_menu.popup(bar.mapToGlobal(QPoint(0, bar.height())))
    QTest.qWait(40)
    assert file_menu._glass_enabled
    file_menu.hide()
    assert before_effects == [QApplication.isEffectEnabled(effect) for effect in
                              (Qt.UI_AnimateMenu, Qt.UI_FadeMenu, Qt.UI_AnimateCombo)]


def test_menu_bar_can_switch_to_glass_after_solid_start(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "solid-start.json"
    settings = SettingsService(path)
    settings.settings["ui"]["material"] = "solid"
    settings.save()
    widget = MainWindow(settings_path=path)
    widget.show()
    app.processEvents()
    menu = widget.menuBar().actions()[0].menu()
    assert isinstance(menu, LayeredMenu)
    widget.settings_service.ui_state["material"] = "liquid_glass"
    widget._refresh_glass_settings()
    menu.popup(widget.menuBar().mapToGlobal(QPoint(0, widget.menuBar().height())))
    QTest.qWait(40)
    assert menu._glass_enabled
    menu.hide()
    widget.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_menu_bar_mouse_and_keyboard_trigger_shared_action(window):
    bar = window.menuBar()
    top_action = bar.actions()[1]
    menu = top_action.menu()
    QTest.mouseClick(bar, Qt.LeftButton, pos=bar.actionGeometry(top_action).center())
    QTest.qWait(30)
    assert menu.isVisible()
    cv_action = menu.actions()[0]
    menu.setActiveAction(cv_action)
    QTest.keyClick(menu, Qt.Key_Right)
    QTest.qWait(30)
    submenu = cv_action.menu()
    assert submenu.isVisible()
    spy = QSignalSpy(window.cv_overlay_action.triggered)
    submenu.setActiveAction(window.cv_overlay_action)
    QTest.keyClick(submenu, Qt.Key_Return)
    assert spy.count() == 1
    assert window._active_plot_tab().spec.kind == "cv_overlay"


def test_menu_labels_fit_alongside_shortcuts_and_icons(window):
    def inspect(menu):
        assert isinstance(menu, LayeredMenu)
        menu.ensurePolished()
        menu.resize(menu.sizeHint())
        actions = [action for action in menu.actions()
                   if action.isVisible() and not action.isSeparator()]
        has_checks = any(action.isCheckable() for action in actions)
        has_icons = any(not action.icon().isNull() for action in actions)
        for action in actions:
            item = menu.actionGeometry(action)
            left = item.left() + menu.tokens.scaled(10)
            left += menu.tokens.scaled(19) if has_checks else 0
            left += menu.tokens.scaled(25) if has_icons else 0
            right = item.right() - menu.tokens.scaled(18 if action.menu() else 12)
            if not action.shortcut().isEmpty():
                right -= menu.fontMetrics().horizontalAdvance(action.shortcut().toString())
                right -= menu.tokens.scaled(8)
            assert right - left >= menu.fontMetrics().size(Qt.TextShowMnemonic, action.text()).width()
            if action.menu():
                inspect(action.menu())

    for action in window.menuBar().actions():
        if action.menu():
            inspect(action.menu())
    for button in window.quick_analysis_buttons.values():
        inspect(button.menu())


def test_complex_popup_keeps_widget_action_and_modern_solid_fallback(window):
    source = QMenu(window)
    widget_action = QWidgetAction(source)
    label = QLabel("Custom control")
    widget_action.setDefaultWidget(label)
    source.addAction(widget_action)
    ordinary = source.addAction("Ordinary action")
    result = wrap_menu(source, window, window.glass_manager)
    assert result is source
    assert result.actions() == [widget_action, ordinary]
    assert widget_action.defaultWidget() is label
    assert "QMenu::item:selected" in result.styleSheet()


def test_analysis_and_dynamic_options_combos_have_closed_glass_surface(window):
    combos = (window.analysis_panel.findChildren(QComboBox)
              + window.options_panel.findChildren(QComboBox))
    assert combos
    for combo in combos:
        assert isinstance(combo.view(), LiquidComboView), (
            combo.objectName(), combo.currentText(), type(combo.parentWidget()).__name__, combo.isVisible()
        )
        if not combo.property("liquidGroupMember"):
            assert combo.property("liquidControl") is True
            assert combo in window.pointer_lights.overlays
    assert 'QComboBox[liquidControl="true"]' in window.styleSheet()


def test_rebinding_options_releases_obsolete_combo_overlays(window):
    app = QApplication.instance()
    tab = window._active_plot_tab()
    for _ in range(2):
        window.options_panel.bind(tab)
        QTest.qWait(20)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    baseline = len(window.pointer_lights.overlays)
    for _ in range(5):
        window.options_panel.bind(tab)
        QTest.qWait(20)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    assert len(window.pointer_lights.overlays) <= baseline


def test_open_menu_and_other_button_hover_are_independent(window):
    buttons = list(window.quick_analysis_buttons.values())
    first, second = buttons[:2]
    group = next(group for group in window.button_groups._groups if first in group.members)
    menu = first.menu()
    menu.popup(first.mapToGlobal(QPoint(0, first.height())))
    QTest.qWait(100)
    assert window.button_groups.popup_is_open(first)
    point = second.mapToGlobal(second.rect().center())
    event = QMouseEvent(QEvent.MouseMove, QPointF(menu.mapFromGlobal(point)), QPointF(point),
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(menu, event)
    QTest.qWait(30)
    assert group.hovered is second and group.target_light == 1
    assert window.button_groups.popup_is_open(first)
    menu.hide()
    QTest.qWait(20)
    assert not window.button_groups.popup_is_open(first)


def test_keyboard_focus_is_visible_on_grouped_button(window):
    first = next(iter(window.quick_analysis_buttons.values()))
    group = next(group for group in window.button_groups._groups if first in group.members)
    first.clearFocus()
    QApplication.processEvents()
    before = group.grab().toImage()
    first.setFocus(Qt.TabFocusReason)
    QApplication.processEvents()
    assert first.hasFocus()
    assert group.grab().toImage() != before


def test_floating_toolbar_preserves_native_navigation(window):
    tab = window._active_plot_tab()
    floating = tab.liquid_toolbar
    assert floating.parentWidget() is tab.canvas_host
    assert not floating.expanded and floating.width() <= 42 and floating.height() <= 24
    QTest.mouseClick(floating.toggle, Qt.LeftButton)
    assert floating.expanded and tab.toolbar.isVisible()
    pan = tab.toolbar._actions["pan"]
    pan.trigger()
    assert pan.isChecked() and "pan" in str(tab.toolbar.mode).lower()
    pan.trigger()
    QTest.mouseClick(floating.toggle, Qt.LeftButton)
    assert not floating.expanded and not tab.toolbar.isVisible()


@pytest.mark.parametrize(("x", "y", "expected"), [
    (0.0578912, 38.45123, "0.05789, 38.45"),
    (-0.000000123456, 123456789, "-1.235e-7, 1.235e8"),
    (1.0, 100000.0, "1.000, 1.000e5"),
    (0.01, -12.0, "0.01000, -12.00"),
    (-0.0, 0.0, "0, 0"),
    (1.7976931348623157e308, -5e-324, "1.798e308, -4.941e-324"),
])
def test_toolbar_coordinate_format_has_four_significant_digits(x, y, expected):
    axes = SimpleNamespace(get_navigate=lambda: True)
    event = SimpleNamespace(inaxes=axes, xdata=x, ydata=y)
    assert CompactNavigationToolbar._mouse_event_to_message(event) == expected
    event.inaxes = None
    assert CompactNavigationToolbar._mouse_event_to_message(event) == ""


def test_floating_toolbar_shows_complete_coordinates(window):
    tab = window._active_plot_tab()
    floating = tab.liquid_toolbar
    QTest.mouseClick(floating.toggle, Qt.LeftButton)
    QApplication.processEvents()
    axes = tab.figure.axes[0]
    x, y = axes.transAxes.transform((0.4, 0.6))
    event = MouseEvent("motion_notify_event", tab.canvas, x, y)
    assert event.inaxes is axes
    tab.canvas.callbacks.process("motion_notify_event", event)
    QApplication.processEvents()
    label = tab.toolbar.locLabel
    assert label.parentWidget() is floating and label.isVisible()
    assert label.text() == f"{_format_coordinate(event.xdata)}, {_format_coordinate(event.ydata)}"
    assert label.fontMetrics().horizontalAdvance(label.text()) + 8 <= label.width()
    assert label.geometry().right() < floating.toggle.geometry().left()
    assert tab.toolbar._actions["home"].isEnabled()
    if tab.toolbar.width() < floating._natural_width:
        overflow = tab.toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        assert overflow is not None and overflow.isVisible()
    longest = "-1.798e308, -4.941e-324"
    tab.toolbar.set_message(longest)
    assert label.text() == longest and label.toolTip() == longest
    assert label.fontMetrics().horizontalAdvance(longest) + 8 <= label.width()
    QTest.mouseClick(floating.toggle, Qt.LeftButton)
    assert not label.isVisible()


def test_workspace_columns_follow_docks_and_bottom_splitter(window):
    import time
    def edges():
        left = window.dataset_dock.mapTo(window, QPoint(window.dataset_dock.width(), 0)).x()
        lower_left = window.results_panel.mapTo(window, QPoint(window.results_panel.width(), 0)).x()
        right = window.analysis_dock.mapTo(window, QPoint()).x()
        lower_right = window.options_panel.mapTo(window, QPoint()).x()
        return left, lower_left, right, lower_right

    def wait_aligned():
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            a, b, c, d = edges()
            if abs(a - b) <= 1 and abs(c - d) <= 1 and not window.column_alignment._timer.isActive():
                return
            QTest.qWait(20)
        pytest.fail(f"workspace columns did not align: {edges()}")

    wait_aligned()
    window.bottom_splitter.moveSplitter(window.bottom_splitter.sizes()[0] + 20, 1)
    wait_aligned()


def test_three_segmented_tabs_fill_available_row(window):
    for tabs in (window.results_panel.results_tabs, window.analysis_panel.analysis_tabs, window.options_panel.pages):
        bar = tabs.tabBar()
        assert bar.expanding()
        corner = tabs.cornerWidget()
        right = corner.mapTo(tabs, QPoint()).x() - 4 if corner and corner.isVisible() else tabs.width()
        assert abs(bar.geometry().right() + 1 - right) <= 2
        assert sum(bar.tabRect(i).width() for i in range(bar.count())) >= bar.width() - 2


@pytest.mark.parametrize("start,end", [(0, 2), (2, 0), (0, 1), (1, 2)])
def test_result_tab_lens_moves_without_overshoot(window, start, end):
    tabs = window.liquid_tab_bars[0]
    bar = window.results_panel.results_tabs.tabBar()
    tabs.manager.animations = True
    bar.setCurrentIndex(start)
    tabs.reset()
    first = QRectF(tabs.current)
    bar.setCurrentIndex(end)
    target = tabs._rect(end)
    centers = []
    for elapsed in (0, 30, 60, 100, 150, 180, 210, 235, 259):
        tabs.animation.setCurrentTime(elapsed)
        rect = QRectF(tabs.current)
        centers.append(rect.center().x())
        assert min(first.left(), target.left()) - .01 <= rect.left() <= max(first.left(), target.left()) + .01
        assert min(first.right(), target.right()) - .01 <= rect.right() <= max(first.right(), target.right()) + .01
        assert rect.left() >= 0 and rect.right() <= bar.width()
    if start < end:
        assert centers == sorted(centers)
    else:
        assert centers == sorted(centers, reverse=True)
    tabs.animation.setCurrentTime(tabs.animation.duration())
    assert tabs.current == target


def test_result_tab_lens_handles_rapid_switch_and_resize(window):
    tabs = window.liquid_tab_bars[0]
    bar = window.results_panel.results_tabs.tabBar()
    tabs.manager.animations = True
    bar.setCurrentIndex(0)
    tabs.reset()
    bar.setCurrentIndex(2)
    tabs.animation.setCurrentTime(80)
    visible = QRectF(tabs.current)
    bar.setCurrentIndex(1)
    assert tabs.animation.startValue() == visible
    assert tabs.current == visible
    tabs.animation.setCurrentTime(80)
    visible = QRectF(tabs.current)
    bar.resize(bar.width() + 60, bar.height())
    QCoreApplication.processEvents()
    assert abs(tabs.current.center().x() - visible.center().x()) < 10
    # Qt schedules final tab geometry on a zero-delay timer; a single
    # processEvents call does not guarantee that timer has run on Windows.
    for _ in range(100):
        if not tabs._geometry_timer.isActive() and tabs.animation.endValue() == tabs._rect(1):
            break
        QTest.qWait(10)
    assert tabs.animation.endValue() == tabs._rect(1)
    tabs.animation.setCurrentTime(tabs.animation.duration())
    assert tabs.current == tabs._rect(1)
    tabs.manager.animations = False
    bar.setCurrentIndex(2)
    assert tabs.current == tabs._rect(2)
    assert tabs.animation.state() != QVariantAnimation.Running


def test_eis_frequency_reset_stays_inside_its_row(window):
    window.analysis_panel.analysis_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    page = window.analysis_panel.analysis_tabs.widget(1)
    row = page.layout().itemAt(0).layout()
    reset = next(button for button in page.findChildren(QPushButton) if button.text() == "重置")
    assert reset.geometry().right() <= row.geometry().right()


def test_appearance_only_settings_do_not_reanalyze_data(window, monkeypatch):
    import cvanalysis.ui.main_window as main_window

    real_dialog = SettingsDialog(window.settings_service.settings, window,
                                 themes=window.settings_service.available_themes())
    values = real_dialog.values()
    real_dialog.deleteLater()
    values["ui"].update(material="solid", animations=False)
    original = window._active_plot_tab().spec.to_dict()

    class AcceptedSettings:
        def __init__(self, *args, **kwargs):
            pass
        def exec(self):
            return QDialog.Accepted
        def values(self):
            return values

    monkeypatch.setattr(main_window, "SettingsDialog", AcceptedSettings)
    monkeypatch.setattr(main_window, "refresh_analysis", lambda *args, **kwargs: pytest.fail("unexpected reanalysis"))
    window.open_settings()
    assert window.glass_manager.mode == "solid"
    assert window.glass_manager.animations is False
    assert window._active_plot_tab().spec.to_dict() == original


def test_closed_workspace_releases_widget_tree(tmp_path):
    app = QApplication.instance() or QApplication([])
    baseline = len(app.allWidgets())
    workspace = MainWindow(settings_path=tmp_path / "close.json")
    workspace.show()
    QApplication.processEvents()
    workspace.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(workspace)
    assert len(app.allWidgets()) <= baseline


def test_optical_buffer_rejects_unbounded_surfaces():
    assert _cached_kernel.cache_info().maxsize == 4
    with pytest.raises(ValueError):
        GlassRenderer(2000, 2000, 12, 1.0, GlassMaterial())
