# -*- coding: utf-8 -*-
"""Prevent accidental wheel changes in spin boxes and combo boxes."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QWidget


class WheelGuard(QObject):
    """Allow wheel changes only after an explicit click on the input."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._armed_widget: QWidget | None = None

    @staticmethod
    def _input_widget(watched: QObject) -> QWidget | None:
        current = watched
        while isinstance(current, QWidget):
            if isinstance(current, (QAbstractSpinBox, QComboBox)):
                return current
            current = current.parentWidget()
        return None

    @staticmethod
    def _allows(widget: QWidget) -> bool:
        cursor = QCursor.pos()
        if isinstance(widget, QComboBox):
            view = widget.view()
            if view is not None and view.isVisible():
                if view.rect().contains(view.mapFromGlobal(cursor)):
                    return True
        if not widget.hasFocus():
            return False
        position = widget.mapFromGlobal(cursor)
        return widget.rect().contains(position)

    def _wheel_allowed(self, widget: QWidget) -> bool:
        return widget is self._armed_widget and self._allows(widget)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                input_widget = self._input_widget(watched)
                if input_widget is not None:
                    self._armed_widget = input_widget
        elif event.type() == QEvent.Type.Wheel:
            input_widget = self._input_widget(watched)
            if input_widget is not None and not self._wheel_allowed(input_widget):
                event.ignore()
                return True
        return super().eventFilter(watched, event)


def install_wheel_guard(app: QApplication | None) -> WheelGuard | None:
    if app is None:
        return None
    guard = getattr(app, "_cvanalysis_wheel_guard", None)
    if guard is None:
        guard = WheelGuard(app)
        app.installEventFilter(guard)
        app._cvanalysis_wheel_guard = guard
    return guard
