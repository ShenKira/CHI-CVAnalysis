# -*- coding: utf-8 -*-
"""Window and dialog sizing helpers that respect the available screen."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from cvanalysis.ui.tokens import BASE_FONT_SIZE


class WorkspaceColumnAlignment(QObject):
    """Keep the bottom splitter aligned with the two workspace docks."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._updating = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.sync_from_docks)
        for widget in (window.dataset_dock, window.analysis_dock, window.bottom_splitter):
            widget.installEventFilter(self)
        window.bottom_splitter.splitterMoved.connect(self._splitter_moved)
        self._timer.start(0)

    def eventFilter(self, watched, event):
        if not self._updating and event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self._timer.start(0)
        return False

    def sync_from_docks(self):
        window = self.window
        splitter = window.bottom_splitter
        if self._updating or splitter.width() <= 0:
            return
        origin = splitter.mapTo(window, QPoint()).x()
        left = window.dataset_dock.mapTo(window, QPoint(window.dataset_dock.width(), 0)).x() - origin
        right_start = window.analysis_dock.mapTo(window, QPoint()).x() - origin
        right = splitter.width() - right_start
        middle = splitter.width() - left - right - 2 * splitter.handleWidth()
        if min(left, right, middle) <= 0:
            return
        current = splitter.sizes()
        if len(current) == 3 and all(abs(a - b) <= 1 for a, b in zip(current, (left, middle, right))):
            return
        self._updating = True
        try:
            splitter.setSizes([left, middle, right])
        finally:
            self._updating = False

    def _splitter_moved(self, position, index):
        if self._updating:
            return
        sizes = self.window.bottom_splitter.sizes()
        if len(sizes) != 3:
            return
        self._updating = True
        try:
            self.window.resizeDocks([self.window.dataset_dock, self.window.analysis_dock],
                                    [sizes[0], sizes[2]], Qt.Horizontal)
        finally:
            self._updating = False
        self._timer.start(0)


def _screen_available(widget: QWidget | None):
    screen = widget.screen() if widget is not None else None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else None


def fit_dialog(
    dialog: QWidget,
    preferred_width: int,
    preferred_height: int,
    *,
    min_width: int = 360,
    min_height: int = 280,
) -> None:
    """Resize a dialog so it stays usable on smaller or scaled screens."""
    try:
        scale = dialog.font().pointSizeF() / BASE_FONT_SIZE
    except Exception:
        scale = 1.0
    scale = max(0.85, min(1.45, scale))
    width = max(min_width, int(round(preferred_width * scale)))
    height = max(min_height, int(round(preferred_height * scale)))
    available = _screen_available(dialog)
    if available is not None:
        width = min(width, max(min_width, int(available.width() * 0.92)))
        height = min(height, max(min_height, int(available.height() * 0.90)))
    dialog.resize(width, height)


def initial_window_size() -> tuple[int, int]:
    """Choose a comfortable first-run size without overflowing the screen."""
    available = _screen_available(None)
    if available is None:
        return 1560, 960
    width = min(1560, max(900, int(available.width() * 0.92)))
    height = min(960, max(600, int(available.height() * 0.90)))
    return width, height
