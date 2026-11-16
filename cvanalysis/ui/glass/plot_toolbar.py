"""Floating glass shell for an existing Matplotlib navigation toolbar."""
from __future__ import annotations

import math
import weakref

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QToolButton, QWidget
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from shiboken6 import isValid

from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.glass.material import GlassMaterial, GlassRenderer, GlassStyle, paint_glass


def _tone(role, alpha):
    color = QColor(theme_color(role))
    color.setAlpha(alpha)
    return color


def _rgba(role, alpha):
    color = _tone(role, alpha)
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def _format_coordinate(value):
    """Four significant digits, with a compact scientific exponent."""
    if value == 0:
        return "0"
    # Keep trailing zeroes so the requested four significant digits are
    # visible even for values such as 1.0 or 1e5.
    value_text = f"{value:#.4g}"
    if "e" in value_text:
        mantissa, exponent = value_text.split("e", 1)
        return f"{mantissa}e{int(exponent)}"
    return value_text


class CompactNavigationToolbar(NavigationToolbar2QT):
    """Keep Matplotlib navigation while showing bounded numeric coordinates."""

    message_changed = Signal()

    def set_message(self, message):
        super().set_message(message)
        self.message_changed.emit()

    @staticmethod
    def _mouse_event_to_message(event):
        if event.inaxes is None or not event.inaxes.get_navigate():
            return ""
        x, y = event.xdata, event.ydata
        if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
            return ""
        return f"{_format_coordinate(x)}, {_format_coordinate(y)}"


class FloatingPlotToolbar(QWidget):
    """Place the original navigation toolbar above its canvas, with a fold button."""

    def __init__(self, tab, manager, *, expanded=False):
        super().__init__(tab.canvas_host)
        self.tab = tab
        self.canvas = tab.canvas
        self.toolbar = tab.toolbar
        self.manager = manager
        self.expanded = bool(expanded)
        self._material = None
        self._optics = GlassMaterial(thickness=.38, frost=.30, strength=5,
                                     bevel=6, pad=16, ior_edge=1.7,
                                     ior_inner=1.34, chroma=.01, disp_glow=9,
                                     disp_saturation=.2, disp_width=1.0,
                                     reflect=.38, f0=.035, max_frost_sigma=7)
        self._style = GlassStyle(tint_top=85, tint_bottom=85, sheen_alpha=3,
                                 rim_top=155, rim_mid=55, rim_bottom=85)
        self.setObjectName("floatingPlotGlass")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        # Keep the same toolbar, QAction objects, keyboard shortcuts and canvas
        # connections; only its parent and placement change in this demo.
        tab.layout().removeWidget(self.toolbar)
        self.toolbar.setParent(self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(22, 22))
        self._style_toolbar()
        self.coordinates = None
        if hasattr(self.toolbar, "locLabel"):
            self.coordinates = self.toolbar.locLabel
            # Put the label beside the toolbar rather than among its actions:
            # when space is tight, Qt can overflow buttons without hiding the
            # coordinate readout itself.
            action = next((item for item in self.toolbar.actions()
                           if self.toolbar.widgetForAction(item) is self.coordinates), None)
            self.coordinates.setParent(self)
            if action is not None:
                self.toolbar.removeAction(action)
            self.coordinates.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            self._coordinate_base_font = QFont(self.coordinates.font())
            self._coordinate_font_css = None
            self._style_coordinates()
            self.toolbar.message_changed.connect(self._fit_coordinate_text)
        self.toolbar.ensurePolished()
        self.toolbar.layout().setContentsMargins(0, 0, 0, 0)
        self._natural_width = max(120, self.toolbar.sizeHint().width())

        self.toggle = QToolButton(self)
        self.toggle.setObjectName("floatingPlotToggle")
        self.toggle.setText("⋯")
        label = "收起绘图工具栏" if self.expanded else "展开绘图工具栏"
        self.toggle.setAccessibleName(label)
        self.toggle.setToolTip(label)
        self.toggle.setFixedSize(34, 30 if self.expanded else 20)
        self._style_toggle()
        self.toggle.clicked.connect(self.toggle_expanded)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3 if self.expanded else 2, 4, 3 if self.expanded else 2)
        layout.setSpacing(2)
        layout.addWidget(self.toolbar)
        if self.coordinates is not None:
            layout.addWidget(self.coordinates)
        layout.addWidget(self.toggle)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._capture_material)
        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.timeout.connect(self.reposition)
        self.parentWidget().installEventFilter(self)
        self.canvas.installEventFilter(self)
        callback_id = self.canvas.mpl_connect("draw_event", self._on_canvas_draw)
        canvas_ref = weakref.ref(self.canvas)

        def disconnect_canvas(*_):
            canvas = canvas_ref()
            if canvas is not None and isValid(canvas):
                canvas.mpl_disconnect(callback_id)

        self.destroyed.connect(disconnect_canvas)
        self.toolbar.setVisible(self.expanded)
        if self.coordinates is not None:
            self.coordinates.setVisible(self.expanded)
        self.show()
        self._position_timer.start(0)

    def _style_toolbar(self):
        self.toolbar.setStyleSheet(f"""
            QToolBar {{ background: transparent; border: none; padding: 0px; margin: 0px; spacing: 1px; }}
            QToolBar::separator {{ background: {_rgba('border_control', 48)}; width: 1px; margin: 6px 3px; }}
            QToolButton {{ background: transparent; border: 1px solid transparent;
                           border-radius: 16px; padding: 3px; min-height: 0px; }}
            QToolButton:hover {{ background: {_rgba('text_secondary', 42)}; }}
            QToolButton:checked, QToolButton:pressed {{ background: {_rgba('primary', 88)}; }}
            QToolButton:checked:hover {{ background: {_rgba('primary', 112)}; }}
            QToolButton:focus {{ border: 2px solid {theme_color('focus')}; padding: 2px; }}
            QLabel {{ background: transparent; color: {theme_color('text')}; padding: 0 4px; }}
        """)

    def _style_coordinates(self, font_css=None):
        self._coordinate_font_css = font_css
        font_rule = f"font-size: {font_css};" if font_css else ""
        self.coordinates.setStyleSheet(
            f"QLabel {{ background: transparent; border: none; color: {theme_color('text')}; "
            f"padding: 0 3px; {font_rule} }}"
        )

    def _coordinate_preferred_width(self):
        if self.coordinates is None:
            return 0
        # Reserve a compact, stable width for typical coordinates. Longer
        # scientific values use the text-fit fallback without truncation.
        metrics = QFontMetricsF(self._coordinate_base_font)
        return math.ceil(metrics.horizontalAdvance("-0.01234, -123.4")) + 8

    def _fit_coordinate_text(self):
        if self.coordinates is None:
            return
        text = self.coordinates.text()
        self.coordinates.setToolTip(text)
        font = QFont(self._coordinate_base_font)
        available = max(1, self.coordinates.width() - 12)
        text_width = QFontMetricsF(font).horizontalAdvance(text)
        if text_width > available:
            factor = available / text_width * .96
            if font.pointSizeF() > 0:
                # Half-point steps avoid repeated stylesheet updates as the
                # pointer moves across similarly sized numbers.
                font.setPointSizeF(max(1.0, math.floor(font.pointSizeF() * factor * 2) / 2))
            elif font.pixelSize() > 0:
                font.setPixelSize(max(1, int(font.pixelSize() * factor)))
        if font.pointSizeF() > 0:
            font_css = f"{font.pointSizeF():.2f}pt"
        else:
            font_css = f"{max(1, font.pixelSize())}px"
        if self._coordinate_font_css != font_css:
            self._style_coordinates(font_css)

    def _style_toggle(self):
        radius = 15 if self.expanded else 10
        font_size = 18 if self.expanded else 15
        self.toggle.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {theme_color('text')}; border: 1px solid transparent;
                          border-radius: {radius}px; font-size: {font_size}px; padding: 0;
                          min-width: 0px; min-height: 0px; }}
            QToolButton:hover {{ background: {_rgba('text_secondary', 42)}; border-color: {_rgba('surface', 160)}; }}
            QToolButton:pressed {{ background: {_rgba('primary', 88)}; }}
            QToolButton:focus {{ border: 2px solid {theme_color('focus')}; }}
        """)

    def toggle_expanded(self):
        self.expanded = not self.expanded
        self.toolbar.setVisible(self.expanded)
        if self.coordinates is not None:
            self.coordinates.setVisible(self.expanded)
        self.toggle.setFixedSize(34, 30 if self.expanded else 20)
        self.layout().setContentsMargins(4, 3 if self.expanded else 2, 4, 3 if self.expanded else 2)
        self._style_toggle()
        label = "收起绘图工具栏" if self.expanded else "展开绘图工具栏"
        self.toggle.setToolTip(label)
        self.toggle.setAccessibleName(label)
        self.reposition()
        # There is no transition: render the new size before the next paint,
        # avoiding a temporary opaque flash between the two capsule shapes.
        if self.manager.mode != "solid" and self.isVisible() and self.canvas.isVisible():
            self._refresh_timer.stop()
            self._capture_material()

    def reposition(self):
        if not isValid(self.canvas) or not isValid(self.parentWidget()):
            return
        host = self.parentWidget()
        area = self.canvas.geometry().intersected(host.rect())
        if area.isEmpty():
            area = host.rect()
        available = max(44, min(host.width() - 12, area.width() - 12))
        coordinate_width = min(self._coordinate_preferred_width(), max(0, available - 44 - 32))
        if self.coordinates is not None:
            self.coordinates.setFixedWidth(coordinate_width)
            self._fit_coordinate_text()
        toolbar_width = min(self._natural_width, max(1, available - 44 - coordinate_width - 2))
        self.toolbar.setFixedWidth(toolbar_width)
        width = min(available, toolbar_width + coordinate_width + 46) if self.expanded else min(42, available)
        height = max(36, min(44, self.toolbar.sizeHint().height() + 6)) if self.expanded else 24
        x = max(0, min(host.width() - width, area.center().x() - width // 2))
        y = max(0, min(host.height() - height, area.top() + (11 if self.expanded else 2)))
        geometry = QRect(x, y, width, height)
        if self.geometry() != geometry:
            self.setGeometry(geometry)
            self.schedule_refresh()
        self.raise_()

    def schedule_refresh(self):
        if self.manager.mode != "solid" and self.isVisible():
            self._refresh_timer.start()

    def refresh_mode(self):
        self._style_toolbar()
        self._style_toggle()
        if self.coordinates is not None:
            self._coordinate_base_font = QFont(self.font())
            self._style_coordinates()
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setMaximumWidth(16777215)
        self.toolbar.ensurePolished()
        self.toolbar.layout().setContentsMargins(0, 0, 0, 0)
        self._natural_width = max(120, self.toolbar.sizeHint().width())
        self.reposition()
        self._refresh_timer.stop()
        self.schedule_refresh()
        self.update()

    def _on_canvas_draw(self, event):
        self.schedule_refresh()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self._position_timer.start(0)
        return False

    def _capture_material(self):
        if not self.isVisible() or not self.canvas.isVisible() or self.manager.mode == "solid":
            return
        try:
            dpr = min(self.devicePixelRatioF(), 1.0)
            radius = min(self.width(), self.height()) / 2
            renderer = GlassRenderer(self.width(), self.height(), radius, dpr, self._optics)
            origin = self.canvas.mapFromGlobal(self.mapToGlobal(QPoint()))
            pad = math.ceil(renderer.kernel.pad / dpr)
            sample_rect = QRect(origin.x() - pad, origin.y() - pad,
                                self.width() + 2 * pad, self.height() + 2 * pad).intersected(self.canvas.rect())
            if sample_rect.isEmpty():
                self._material = None
            else:
                sample = self.canvas.grab(sample_rect)
                image = sample.toImage().convertToFormat(QImage.Format_RGBA8888)
                raw = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
                rgba = raw[:, :image.width() * 4].reshape(image.height(), image.width(), 4).copy()
                panel_origin = self.mapToGlobal(QPoint()) - self.canvas.mapToGlobal(sample_rect.topLeft())
                self._material = renderer.render(rgba, panel_origin, sample.devicePixelRatioF(),
                                                 QColor(theme_color("surface")).getRgb()[:3])
        except (MemoryError, OSError, RuntimeError, ValueError):
            self._material = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        radius = min(rect.width(), rect.height()) / 2
        if self.manager.mode != "solid" and isinstance(self._material, QPixmap) and not self._material.isNull():
            paint_glass(painter, rect, radius, self._material, self._style)
            if not self.expanded:
                shape = QPainterPath()
                shape.addRoundedRect(rect, radius, radius)
                painter.fillPath(shape, _tone("text_secondary", 34))
            painter.setPen(QPen(_tone("border_control", 46), .8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        else:
            shape = QPainterPath()
            shape.addRoundedRect(rect, radius, radius)
            color = QColor(theme_color("surface")) if self.manager.mode == "solid" else _tone("surface_sunken", 120)
            painter.fillPath(shape, color)
            painter.setPen(QPen(_tone("border_control", 65), 1))
            painter.drawPath(shape)
        painter.end()
