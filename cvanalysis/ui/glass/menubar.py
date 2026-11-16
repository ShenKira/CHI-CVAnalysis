"""A quiet, full-width glass surface for Qt's native menu-bar interactions."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMenuBar

from cvanalysis.ui.theme import theme_color


class LiquidMenuBar(QMenuBar):
    """Paint the surface only; Qt continues to handle menus and keyboard input."""

    def __init__(self, parent, manager):
        super().__init__(parent)
        self.manager = manager
        self.setProperty("liquidGlassMenuBar", True)
        self.setNativeMenuBar(False)

    def paintEvent(self, event):
        if self.manager.mode != "solid":
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(theme_color("background")))
            tint = QColor(theme_color("surface"))
            tint.setAlpha(190)
            painter.fillRect(self.rect(), tint)
            edge = QColor(theme_color("border_control"))
            edge.setAlpha(55)
            painter.setPen(QPen(edge, 1))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            painter.end()
        super().paintEvent(event)
