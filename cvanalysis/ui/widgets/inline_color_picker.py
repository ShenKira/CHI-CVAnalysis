"""Compact inline HSV picker with keyboard and exact hex input."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget


class _ColorField(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hue, self.saturation, self.value = 0, 255, 255
        self.setMinimumSize(180, 120)
        self.setMaximumHeight(220)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("色相与饱和度；方向键可调整")

    def setColor(self, color):
        hue, saturation, value, _ = color.getHsv()
        if hue >= 0:
            self.hue = hue
        self.saturation, self.value = saturation, value
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        shape = QPainterPath()
        shape.addRoundedRect(rect, 8, 8)
        p.setClipPath(shape)
        hues = QLinearGradient(rect.topLeft(), rect.topRight())
        for i in range(7):
            hues.setColorAt(i / 6, QColor.fromHsv((i * 60) % 360, 255, 255))
        p.fillRect(rect, hues)
        saturation = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        saturation.setColorAt(0, QColor(255, 255, 255, 255))
        saturation.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(rect, saturation)
        # Keep the spectrum usable when the currently selected color is black.
        if self.value:
            p.fillRect(rect, QColor(0, 0, 0, 255 - self.value))
        p.setClipping(False)
        x = rect.left() + self.hue / 359 * rect.width()
        y = rect.top() + self.saturation / 255 * rect.height()
        x = max(rect.left() + 6, min(rect.right() - 6, x))
        y = max(rect.top() + 6, min(rect.bottom() - 6, y))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawEllipse(QPointF(x, y), 5, 5)
        p.setPen(QPen(Qt.white, 1.5))
        p.drawEllipse(QPointF(x, y), 5, 5)

    def _set_position(self, pos):
        if self.value == 0:
            self.value = 255
        self.hue = max(0, min(359, round(pos.x() / max(1, self.width() - 1) * 359)))
        self.saturation = max(0, min(255, round(pos.y() / max(1, self.height() - 1) * 255)))
        self.update()
        self.colorChanged.emit(QColor.fromHsv(self.hue, self.saturation, self.value))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._set_position(event.position())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_position(event.position())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        if event.key() == Qt.Key_Left:
            self.hue = max(0, self.hue - step)
        elif event.key() == Qt.Key_Right:
            self.hue = min(359, self.hue + step)
        elif event.key() == Qt.Key_Up:
            self.saturation = max(0, self.saturation - step)
        elif event.key() == Qt.Key_Down:
            self.saturation = min(255, self.saturation + step)
        else:
            return super().keyPressEvent(event)
        if self.value == 0:
            self.value = 255
        self.update()
        self.colorChanged.emit(QColor.fromHsv(self.hue, self.saturation, self.value))
        event.accept()


class InlineColorPicker(QWidget):
    """A bounded picker which never opens a second dialog."""

    currentColorChanged = Signal(QColor)
    PRESETS = ("#000000", "#555555", "#999999", "#ffffff", "#e53935", "#fb8c00", "#fdd835", "#43a047",
               "#00897b", "#00acc1", "#1e88e5", "#3949ab", "#8e24aa", "#d81b60", "#795548", "#607d8b")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#000000")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.field = _ColorField(self)
        self.field.colorChanged.connect(self.setCurrentColor)
        layout.addWidget(self.field)
        brightness = QHBoxLayout()
        brightness.addWidget(QLabel("亮度"))
        self.value_slider = QSlider(Qt.Horizontal)
        self.value_slider.setRange(0, 255)
        self.value_slider.setAccessibleName("颜色亮度")
        self.value_slider.valueChanged.connect(self._brightness_changed)
        brightness.addWidget(self.value_slider, 1)
        layout.addLayout(brightness)
        exact = QHBoxLayout()
        exact.addWidget(QLabel("颜色值"))
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("#RRGGBB")
        self.hex_input.setAccessibleName("十六进制颜色值")
        self.hex_input.editingFinished.connect(self._hex_edited)
        exact.addWidget(self.hex_input, 1)
        self.preview = QLabel()
        self.preview.setFixedSize(32, 28)
        exact.addWidget(self.preview)
        layout.addLayout(exact)
        layout.addWidget(QLabel("常用颜色"))
        presets = QGridLayout()
        presets.setSpacing(5)
        for index, value in enumerate(self.PRESETS):
            button = QPushButton()
            button.setFixedSize(26, 26)
            button.setAccessibleName("常用颜色 " + value)
            button.setToolTip(value)
            button.setStyleSheet(f"QPushButton {{ background: {value}; border: 1px solid #9099a2; border-radius: 5px; padding: 0; min-width: 0; min-height: 0; }}")
            button.clicked.connect(lambda checked=False, color=value: self.setCurrentColor(QColor(color)))
            presets.addWidget(button, index // 8, index % 8)
        presets.setColumnStretch(8, 1)
        layout.addLayout(presets)
        layout.addStretch(1)
        self.setCurrentColor(self._color)

    def currentColor(self):
        return QColor(self._color)

    def setCurrentColor(self, color):
        color = QColor(color)
        if not color.isValid():
            return
        color.setAlpha(255)
        changed = color != self._color
        self._color = color
        self.field.setColor(color)
        with QSignalBlocker(self.value_slider):
            self.value_slider.setValue(color.value())
        with QSignalBlocker(self.hex_input):
            self.hex_input.setText(color.name(QColor.HexRgb))
        self.preview.setStyleSheet(f"background: {color.name(QColor.HexRgb)}; border: 1px solid #9099a2; border-radius: 5px;")
        if changed:
            self.currentColorChanged.emit(QColor(color))

    def _brightness_changed(self, value):
        self.setCurrentColor(QColor.fromHsv(self.field.hue, self.field.saturation, value))

    def _hex_edited(self):
        value = self.hex_input.text().strip()
        color = QColor(value)
        if color.isValid():
            self.setCurrentColor(color)
        else:
            self.hex_input.setText(self._color.name(QColor.HexRgb))
