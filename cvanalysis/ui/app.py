# -*- coding: utf-8 -*-
"""Qt application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.theme import application_stylesheet
from cvanalysis.ui.widgets.wheel_guard import install_wheel_guard


def create_application(argv: list[str] | None = None) -> QApplication:
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or sys.argv)
    app.setApplicationName("CVAnalysis")
    app.setApplicationDisplayName("CVAnalysis v2")
    app.setOrganizationName("CVAnalysis")
    font = QFont("Microsoft YaHei")
    font.setPointSizeF(11.0)
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
