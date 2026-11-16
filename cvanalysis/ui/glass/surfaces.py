"""Cached glass with an SDF-inspired edge lens and Qt optical highlights."""
from __future__ import annotations

from collections import defaultdict, deque
from time import perf_counter
import sys
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid
from cvanalysis.ui.theme import theme_color


def _tone(role, alpha):
    color = QColor(theme_color(role))
    color.setAlpha(alpha)
    return color


def effective_mode(material):
    if material == "solid":
        return "solid"
    app = QApplication.instance()
    if sys.platform == "win32" and app is not None and app.platformName() == "windows":
        if not _windows_allows_glass():
            return "solid"
    return "balanced"


def _windows_allows_glass():
    """Respect explicit Windows accessibility settings; tolerate a missing key."""
    try:
        import winreg

        class HighContrast(ctypes.Structure):
            _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD),
                        ("scheme", wintypes.LPWSTR)]

        contrast = HighContrast()
        contrast.size = ctypes.sizeof(contrast)
        if not ctypes.windll.user32.SystemParametersInfoW(0x0042, contrast.size, ctypes.byref(contrast), 0):
            return False
        if contrast.flags & 1:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                enabled, _ = winreg.QueryValueEx(key, "EnableTransparency")
        except FileNotFoundError:
            # Some Windows installations do not have the optional value.
            return True
        return bool(enabled)
    except (OSError, AttributeError, ValueError):
        return False


def environment(painter, rect, warm=False):
    """Uniform neutral canvas; theme accents belong to content and controls."""
    painter.fillRect(rect, QColor(theme_color("background")))


def rim(painter, rect, radius, *, glow=0.0, outer=True):
    """One neutral contour and one thin specular rim; no shaded panel bands."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if outer:
        painter.setPen(QPen(_tone("border_control", 60), 1))
        painter.drawPath(path)
    for inset, opacity in ((1, 170),):
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                             max(1, radius - inset), max(1, radius - inset))
        diagonal = QLinearGradient(rect.topLeft(), rect.bottomRight())
        diagonal.setColorAt(0, _tone("surface", opacity))
        diagonal.setColorAt(0.25, _tone("surface", 0))
        diagonal.setColorAt(0.75, _tone("surface", 0))
        diagonal.setColorAt(1, _tone("surface", opacity))
        painter.setPen(QPen(diagonal, 1))
        painter.drawPath(inner)
    if glow:
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        painter.setPen(QPen(_tone("surface", round(240 * glow)), 1.5))
        painter.drawPath(inner)


class MaterialManager:
    def __init__(self, window, mode="balanced", animations=True):
        self.window = window
        self.mode = mode
        self.animations = bool(animations)
        self.surfaces = []
        self.backdrop = QPixmap()
        self.samples = defaultdict(lambda: deque(maxlen=512))
        self.hits = 0
        self.builds = 0
        self.flushes = 0
        self.timer = QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.flush)

    def schedule(self):
        # Keep scaling the previous backing store during a resize; rebuild only
        # after geometry settles. No timer is active while the app is idle.
        self.timer.start()

    def flush(self):
        self.flushes += 1
        self.backdrop = QPixmap()
        self.surfaces = [surface for surface in self.surfaces if isValid(surface)]
        for surface in self.surfaces:
            surface.cache = QPixmap()
            surface.update()
        self.window.update()

    def set_mode(self, mode):
        self.mode = mode
        self.timer.stop()
        if mode == "solid":
            from cvanalysis.ui.glass.material import _cached_kernel
            _cached_kernel.cache_clear()
        self.flush()

    def _environment(self):
        if not self.backdrop.isNull():
            return
        started = perf_counter()
        # Refraction cannot change a uniform colour. Keep one texel instead of
        # allocating and warping a window-sized background for every panel.
        pixmap = QPixmap(1, 1)
        pixmap.fill(QColor(theme_color("background")))
        self.backdrop = pixmap
        self.samples["shared_background_ms"].append((perf_counter() - started) * 1000)

    def material(self, surface):
        started = perf_counter()
        if self.mode != "solid":
            self._environment()
        output = QPixmap(1, 1)
        output.fill(QColor(theme_color("surface")))
        self.builds += 1
        self.samples["surface_build_ms"].append((perf_counter() - started) * 1000)
        return output

    @property
    def cache_bytes(self):
        pixmaps = [self.backdrop] + [surface.cache for surface in self.surfaces if isValid(surface)]
        return sum(image.width() * image.height() * 4 for image in pixmaps)


class GlassBacking(QWidget):
    """An input-transparent child behind the existing widget's native controls."""

    def __init__(self, target, manager, *, radius=14, region=None):
        super().__init__(target)
        self.target = target
        self.manager = manager
        self.radius = radius
        self.region = region
        self.cache = QPixmap()
        self.hover = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        target.installEventFilter(self)
        self.setGeometry(self.region() if self.region else target.rect())
        self.lower()
        self.show()
        manager.surfaces.append(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self.setGeometry(self.region() if self.region else self.target.rect())
            self.lower()
            self.manager.schedule()
        elif event.type() in (QEvent.Enter, QEvent.Leave):
            if self.manager.mode != "solid" and self.manager.animations:
                self.hover = 0.45 if event.type() == QEvent.Enter else 0.0
                self.update()
        return super().eventFilter(watched, event)

    def _build_frame(self):
        started = perf_counter()
        material = self.manager.material(self)
        dpr = min(self.devicePixelRatioF(), 1.25)
        self.cache = QPixmap(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
        self.cache.setDevicePixelRatio(dpr)
        self.cache.fill(Qt.transparent)
        painter = QPainter(self.cache)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3.5, 3.5, -3.5, -4.5)
        path = QPainterPath()
        radius = min(self.radius, max(1, rect.height() / 2))
        path.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(path)
        painter.drawPixmap(rect, material, QRectF(material.rect()))
        painter.restore()
        if self.manager.mode == "solid":
            painter.setPen(QPen(_tone("border_control", 100), 1))
            painter.drawPath(path)
        else:
            rim(painter, rect, radius)
        painter.end()
        self.manager.samples["optical_frame_build_ms"].append((perf_counter() - started) * 1000)

    def paintEvent(self, event):
        if self.cache.isNull():
            self._build_frame()
        else:
            self.manager.hits += 1
        painter = QPainter(self)
        if self.cache.deviceIndependentSize().toSize() == self.size():
            painter.drawPixmap(QPoint(), self.cache)
        else:
            painter.drawPixmap(QRectF(self.rect()), self.cache, QRectF(self.cache.rect()))
        if self.hover and self.manager.mode != "solid" and self.manager.animations:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(_tone("surface", round(220 * self.hover)), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(5, 5, -5, -6), self.radius - 1, self.radius - 1)
