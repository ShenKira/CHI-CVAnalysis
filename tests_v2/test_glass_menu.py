"""Behaviour of the production plot context menu and its safe fallbacks."""

from __future__ import annotations

import re
import sys
from types import SimpleNamespace
import matplotlib as mpl
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QActionGroup, QColor, QKeySequence, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QWidget, QWidgetAction
from shiboken6 import delete, isValid

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.export import render_svg_bytes
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.theme import application_stylesheet
from cvanalysis.ui.tokens import UiTokens
from cvanalysis.ui.widgets import glass_menu
from cvanalysis.ui.glass import popups
from cvanalysis.ui.widgets.plot_tab import PlotTab


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(app, synthetic_cv_runs, monkeypatch):
    app.setStyleSheet(application_stylesheet(1.0, "default"))
    monkeypatch.setattr(glass_menu, "_glass_available", lambda: True)
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    widget = PlotTab(PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs]),
                     BUILTIN_PRESETS["daily"], dataset)
    widget.resize(700, 560)
    widget.show()
    app.processEvents()
    yield widget
    if isValid(widget):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def _action(menu, text):
    return next(action for action in menu.actions() if action.text() == text)


def test_real_actions_check_and_ratio_remain_connected(tab, app):
    menu = tab._build_context_menu()
    assert isinstance(menu, glass_menu.GlassMenu)
    assert menu._source_menu.isWindow() and menu._source_menu.isHidden()
    assert menu.actions() == menu._source_menu.actions()
    assert not hasattr(tab, "settings_btn")
    assert _action(menu, "本图数据与图例...") is not None
    fit = _action(menu, "按比例适应标签页")
    assert fit.isChecked() and tab._settings_fit_action.isChecked()
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    menu.setActiveAction(fit)
    QTest.keyClick(menu, Qt.Key_Return)
    assert not tab._fit_to_view and not tab._settings_fit_action.isChecked()
    fit.trigger()
    assert tab._fit_to_view and tab._settings_fit_action.isChecked()
    ratio = _action(menu, "图片比例")
    assert isinstance(ratio.menu(), glass_menu.GlassMenu)
    _action(ratio.menu(), "16:9").trigger()
    width, height = tab.style.figure_size
    assert width / height == pytest.approx(16 / 9)
    menu.close()
    source, submenu = menu._source_menu, ratio.menu()
    menu.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(menu) and not isValid(source) and not isValid(submenu)


def test_keyboard_submenu_and_escape(tab):
    menu = tab._build_context_menu()
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    ratio = _action(menu, "图片比例")
    menu.setActiveAction(ratio)
    QTest.keyClick(menu, Qt.Key_Right)
    QTest.qWait(50)
    submenu = ratio.menu()
    assert submenu.isVisible()
    QTest.keyClick(submenu, Qt.Key_Escape)
    assert not submenu.isVisible() and menu.isVisible()
    QTest.keyClick(menu, Qt.Key_Escape)
    assert not menu.isVisible()
    menu.deleteLater()


def test_edge_position_and_repeated_disposal(tab):
    screen = tab.screen().availableGeometry()
    for _ in range(4):
        menu = tab._build_context_menu()
        source = menu._source_menu
        submenu = _action(menu, "图片比例").menu()
        menu.popup(screen.bottomRight() - QPoint(2, 2))
        QTest.qWait(30)
        assert screen.contains(menu.geometry())
        menu.setActiveAction(_action(menu, "图片比例"))
        QTest.keyClick(menu, Qt.Key_Right)
        QTest.qWait(30)
        assert submenu.isVisible() and screen.contains(submenu.geometry())
        menu.close()
        menu.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not isValid(menu) and not isValid(source) and not isValid(submenu)


@pytest.mark.parametrize("theme", ["default", "kon"])
@pytest.mark.parametrize("scale", [0.8, 1.0, 1.6])
def test_menu_fits_labels_and_has_transparent_corners(tab, app, theme, scale):
    app.setStyleSheet(application_stylesheet(scale, theme))
    tab._ui_scale = scale
    source = QMenu(tab)
    source.addAction("复制当前图像")
    source.addAction("当前图设置...")
    menu = popups.wrap_menu(source, tab, tab.glass_manager)
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    assert isinstance(menu, glass_menu.GlassMenu)
    for action in menu.actions():
        if action.text():
            available = menu.actionGeometry(action).width() - menu.tokens.scaled(47)
            assert menu.fontMetrics().horizontalAdvance(action.text()) <= available
    assert menu.grab().toImage().pixelColor(0, 0).alpha() == 0
    menu.close()
    menu.deleteLater()


@pytest.mark.parametrize("source_dpr,target_dpr", [(1.25, 1.25), (1.25, 1.5), (1.5, 2.0)])
def test_backdrop_samples_correct_region_and_fills_outside(app, source_dpr, target_dpr):
    class Source:
        def mapToGlobal(self, point):
            return QPoint(-100, 40)

        def grab(self):
            pixmap = QPixmap(round(160 * source_dpr), round(80 * source_dpr))
            pixmap.setDevicePixelRatio(source_dpr)
            pixmap.fill(QColor("#ee3030"))
            painter = QPainter(pixmap)
            painter.fillRect(QRect(80, 0, 80, 80), QColor("#3030ee"))
            painter.end()
            return pixmap

    backdrop = glass_menu.PlotBackdrop(Source(), UiTokens.from_scale(1.0))
    image = backdrop.material(QRect(-100, 40, 160, 80), target_dpr).toImage()
    left = image.pixelColor(round(30 * target_dpr), round(40 * target_dpr))
    right = image.pixelColor(round(130 * target_dpr), round(40 * target_dpr))
    assert left.red() > left.blue() and right.blue() > right.red()
    outside = backdrop.material(QRect(-250, -100, 60, 60), target_dpr).toImage()
    color = outside.pixelColor(round(30 * target_dpr), round(30 * target_dpr))
    assert min(color.red(), color.green(), color.blue()) >= 166


def test_transparent_window_pixels_do_not_expose_other_windows(app):
    class TransparentSource:
        def mapToGlobal(self, point):
            return QPoint()

        def grab(self):
            pixmap = QPixmap(80, 80)
            pixmap.fill(Qt.transparent)
            return pixmap

    backdrop = glass_menu.PlotBackdrop(TransparentSource(), UiTokens.from_scale(1.0))
    image = backdrop.material(QRect(0, 0, 60, 60), 1.0).toImage()
    assert image.pixelColor(30, 30) == QColor(glass_menu.theme_color("surface"))


def test_standard_menu_fallbacks(tab, monkeypatch):
    monkeypatch.setattr(glass_menu, "_glass_available", lambda: False)
    source = tab._build_settings_menu()
    assert glass_menu.build_glass_menu(source, tab) is source
    monkeypatch.setattr(glass_menu, "_glass_available", lambda: True)
    unsupported = QMenu(tab)
    unsupported.addAction(QWidgetAction(unsupported))
    assert glass_menu.build_glass_menu(unsupported, tab) is unsupported
    shortcut_menu = QMenu(tab)
    shortcut = shortcut_menu.addAction("Example")
    shortcut.setShortcut(QKeySequence("Ctrl+E"))
    assert glass_menu.build_glass_menu(shortcut_menu, tab) is shortcut_menu
    long_menu = QMenu(tab)
    long_menu.addAction("long label " * 200)
    assert glass_menu.build_glass_menu(long_menu, tab) is long_menu
    radio_menu = QMenu(tab)
    radio = radio_menu.addAction("Radio")
    radio.setCheckable(True)
    group = QActionGroup(radio_menu)
    group.setExclusive(True)
    group.addAction(radio)
    assert glass_menu.build_glass_menu(radio_menu, tab) is radio_menu
    source = tab._build_settings_menu()
    monkeypatch.setattr(glass_menu, "PlotBackdrop", lambda *args: (_ for _ in ()).throw(ValueError("unavailable")))
    assert glass_menu.build_glass_menu(source, tab) is source


def test_disable_flag(app, monkeypatch):
    class DesktopApp:
        @staticmethod
        def instance():
            return DesktopApp()

        @staticmethod
        def platformName():
            return "windows"

    monkeypatch.setattr(glass_menu, "QApplication", DesktopApp)
    monkeypatch.setattr(glass_menu, "_windows_transparency_enabled", lambda: True)
    monkeypatch.delenv("CVANALYSIS_GLASS_MENU", raising=False)
    assert glass_menu._glass_available()
    monkeypatch.setenv("CVANALYSIS_GLASS_MENU", "0")
    assert not glass_menu._glass_available()
    monkeypatch.delenv("CVANALYSIS_GLASS_MENU")
    monkeypatch.setattr(glass_menu, "Image", None)
    assert not glass_menu._glass_available()


def test_material_failure_uses_solid_panel(tab, monkeypatch):
    menu = tab._build_context_menu()
    monkeypatch.setattr(popups.LiquidBackdrop, "material", lambda *args: (_ for _ in ()).throw(ValueError("unavailable")))
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(20)
    assert menu.material.isNull()
    image = menu.grab().toImage()
    assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() == 255
    menu.close()
    menu.deleteLater()


def test_parent_destroyed_while_menu_is_open(tab):
    QTimer.singleShot(30, lambda: delete(tab))
    tab._show_context_menu(QPoint(30, 30))
    assert not isValid(tab)


def test_real_inspector_can_open_from_menu(tab, app):
    from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog

    menu = tab._build_context_menu()
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    menu.setActiveAction(_action(menu, "当前图设置..."))
    seen = []

    def close_dialog():
        dialog = app.activeModalWidget()
        seen.append(isinstance(dialog, PlotInspectorDialog))
        if dialog is not None:
            dialog.reject()

    QTimer.singleShot(100, close_dialog)
    QTest.keyClick(menu, Qt.Key_Return)
    assert seen == [True]
    menu.deleteLater()


def test_menu_does_not_change_scientific_svg(tab):
    def render():
        with mpl.rc_context({"svg.hashsalt": "glass-menu-test"}):
            data = render_svg_bytes(tab.dataset, tab.spec, tab.style,
                                    color_config=tab.color_config, fits=tab.fits,
                                    metrics=tab.metrics, text_values=tab.text_values)
        return re.sub(rb"<dc:date>.*?</dc:date>", b"", data)

    before = render()
    menu = tab._build_context_menu()
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    menu.close()
    menu.deleteLater()
    assert before == render()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows settings API")
@pytest.mark.parametrize("contrast,transparency,expected", [(0, 1, True), (1, 1, False), (0, 0, False)])
def test_windows_accessibility_settings_are_respected(monkeypatch, contrast, transparency, expected):
    class Query:
        def __call__(self, operation, size, data, flags):
            data._obj.flags = contrast
            return True

    class RegistryKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    registry = SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=lambda *args: RegistryKey(),
                               QueryValueEx=lambda *args: (transparency, 4))
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(glass_menu.ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=Query())))
    assert glass_menu._windows_transparency_enabled() is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows settings API")
def test_inaccessible_transparency_setting_falls_back(monkeypatch):
    class Query:
        def __call__(self, operation, size, data, flags):
            data._obj.flags = 0
            return True

    def unavailable(*args):
        raise FileNotFoundError("setting unavailable")

    registry = SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=unavailable)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(glass_menu.ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=Query())))
    assert not glass_menu._windows_transparency_enabled()


def test_disabled_menu_item_is_not_triggered(tab):
    menu = tab._build_context_menu()
    action = _action(menu, "复制当前图像")
    calls = []
    action.triggered.connect(lambda: calls.append(True))
    action.setEnabled(False)
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(action).center())
    assert not calls
    menu.close()
    menu.deleteLater()


def test_mnemonic_works_in_glass_menu(tab):
    source = QMenu(tab)
    action = source.addAction("&Fit")
    calls = []
    action.triggered.connect(lambda: calls.append(True))
    menu = glass_menu.build_glass_menu(source, tab)
    assert isinstance(menu, glass_menu.GlassMenu)
    menu.popup(tab.mapToGlobal(QPoint(30, 30)))
    QTest.qWait(30)
    QTest.keyClick(menu, Qt.Key_F)
    assert calls == [True]
    menu.close()
    menu.deleteLater()


