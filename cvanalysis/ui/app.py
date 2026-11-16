# -*- coding: utf-8 -*-
"""Qt application bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, Qt, QTranslator
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.theme import application_stylesheet
from cvanalysis.ui.tokens import FONT_FAMILIES, UiTokens
from cvanalysis.ui.widgets.wheel_guard import install_wheel_guard


def application_icon_path() -> Path:
    """Locate the bundled icon in source, installed and Nuitka payload layouts."""
    return Path(__file__).resolve().parents[1] / "resources" / "icons" / "cvanalysis.ico"


def _set_windows_app_id() -> None:
    """Give script launches their own taskbar identity instead of Python's."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                ctypes.c_wchar_p("CVAnalysis.CVAnalysis")
            )
        except (AttributeError, OSError):
            pass


def create_application(argv: list[str] | None = None) -> QApplication:
    _set_windows_app_id()
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or sys.argv)
    # Qt's combo popup animation can expose a black intermediate window on
    # Windows. Keep combo popups immediate without changing menu animations.
    QApplication.setEffectEnabled(Qt.UI_AnimateCombo, False)
    app.setApplicationName("CVAnalysis")
    app.setApplicationDisplayName("CVAnalysis v2")
    app.setOrganizationName("CVAnalysis")
    app.setWindowIcon(QIcon(str(application_icon_path())))
    try:
        translator = QTranslator(app)
        translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load("qtbase_zh_CN", translations):
            app.installTranslator(translator)
            app._qt_translator = translator
    except Exception:
        pass
    tokens = UiTokens.from_scale(1.0)
    font = QFont()
    font.setFamilies(list(FONT_FAMILIES))
    font.setPointSizeF(tokens.font_size_pt)
    app.setFont(font)
    app.setStyleSheet(application_stylesheet())
    install_wheel_guard(app)
    return app


def run(argv: list[str] | None = None) -> int:
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
