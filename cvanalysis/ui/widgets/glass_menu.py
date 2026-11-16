"""Frosted material for the plot context menu.

The material is a snapshot of this application's window, taken before any menu
is shown. It does not modify the plot, capture other applications, or depend
on Windows Acrylic. Normal QMenu remains the fallback on unsupported systems.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

try:
    from PIL import Image, ImageFilter
except ImportError:  # Keep the rest of the application usable if packaging is incomplete.
    Image = ImageFilter = None
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidgetAction

from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.tokens import UiTokens

log = logging.getLogger(__name__)


def _windows_transparency_enabled() -> bool:
    """Read the user's contrast and transparency settings; never change them."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        class HighContrast(ctypes.Structure):
            _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD),
                        ("scheme", wintypes.LPWSTR)]

        contrast = HighContrast()
        contrast.size = ctypes.sizeof(contrast)
        query = ctypes.windll.user32.SystemParametersInfoW
        query.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        query.restype = wintypes.BOOL
        if not query(0x0042, contrast.size, ctypes.byref(contrast), 0) or contrast.flags & 1:
            return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            enabled, _ = winreg.QueryValueEx(key, "EnableTransparency")
        return bool(enabled)
    except (OSError, AttributeError, ValueError):
        return False


def _glass_available() -> bool:
    app = QApplication.instance()
    return (Image is not None and os.environ.get("CVANALYSIS_GLASS_MENU", "1") != "0"
            and app is not None and app.platformName() == "windows"
            and _windows_transparency_enabled())


class PlotBackdrop:
    """One clean window sample shared by the main menu and all submenus."""

    def __init__(self, owner, tokens: UiTokens):
        self.tokens = tokens
        self.origin = owner.mapToGlobal(QPoint())
        pixmap = owner.grab()
        if pixmap.isNull():
            raise ValueError("window snapshot is empty")
        self.dpr = pixmap.devicePixelRatioF()
        image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
        self.image = Image.frombytes("RGBA", (image.width(), image.height()),
                                     bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine())

    def material(self, geometry: QRect, dpr: float) -> QPixmap:
        relative = geometry.topLeft() - self.origin
        x, y = round(relative.x() * self.dpr), round(relative.y() * self.dpr)
        width = max(1, round(geometry.width() * self.dpr))
        height = max(1, round(geometry.height() * self.dpr))
        pad = max(1, round(16 * self.dpr))
        bounds = (x - pad, y - pad, x + width + pad, y + height + pad)
        surface = QColor(theme_color("surface"))
        sample = Image.new("RGBA", (width + 2 * pad, height + 2 * pad), surface.getRgb())
        intersection = (max(0, bounds[0]), max(0, bounds[1]),
                        min(self.image.width, bounds[2]), min(self.image.height, bounds[3]))
        if intersection[2] > intersection[0] and intersection[3] > intersection[1]:
            sample.alpha_composite(self.image.crop(intersection),
                                   (intersection[0] - bounds[0], intersection[1] - bounds[1]))
        sample = sample.filter(ImageFilter.GaussianBlur(self.tokens.glass_blur * self.dpr))
        sample = sample.crop((pad, pad, pad + width, pad + height))
        sample = Image.blend(sample, Image.new("RGBA", sample.size, surface.getRgb()), self.tokens.glass_tint)
        sample = sample.point(lambda value: max(self.tokens.glass_min_channel, value))
        # The panel already contains its own backdrop. Never let transparent
        # pixels in an owner snapshot expose unrelated windows behind the app.
        sample.putalpha(255)
        if self.dpr != dpr:
            sample = sample.resize((max(1, round(geometry.width() * dpr)),
                                    max(1, round(geometry.height() * dpr))), Image.Resampling.LANCZOS)
        image = QImage(sample.tobytes(), sample.width, sample.height,
                       sample.width * 4, QImage.Format_RGBA8888).copy()
        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(dpr)
        return result


def _color(role: str, alpha: int) -> QColor:
    color = QColor(theme_color(role))
    color.setAlpha(alpha)
    return color


class GlassMenu(QMenu):
    """QMenu interaction with a single custom-painted material and items."""

    def __init__(self, parent, backdrop: PlotBackdrop, tokens: UiTokens):
        super().__init__(parent)
        self.backdrop = backdrop
        self.tokens = tokens
        self.material = QPixmap()
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        padding = tokens.glass_padding
        vertical = tokens.scaled(6, minimum=5)
        self.setStyleSheet(f"""
            QMenu {{ background: transparent; border: none; padding: {padding}px; }}
            QMenu::item {{ background: transparent; border: none;
                padding: {vertical}px {tokens.scaled(28)}px {vertical}px {tokens.scaled(22)}px; }}
            QMenu::separator {{ height: 1px; background: transparent; margin: 5px 8px; }}
        """)
        palette = self.palette()
        for role in (QPalette.Window, QPalette.Base, QPalette.Button, QPalette.AlternateBase):
            palette.setColor(role, Qt.transparent)
        self.setPalette(palette)
        self.setMinimumWidth(tokens.scaled(224))

    def showEvent(self, event):
        super().showEvent(event)
        screen = self.screen()
        if screen:
            bounds = screen.availableGeometry()
            self.move(max(bounds.left(), min(self.x(), bounds.right() - self.width() + 1)),
                      max(bounds.top(), min(self.y(), bounds.bottom() - self.height() + 1)))
        self._refresh_material()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self._refresh_material()

    def _refresh_material(self):
        try:
            self.material = self.backdrop.material(self.geometry(), self.devicePixelRatioF())
        except (OSError, RuntimeError, ValueError, MemoryError):
            log.warning("Could not prepare plot menu material; using a solid surface", exc_info=True)
            self.material = QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        margin = self.tokens.glass_margin + 0.5
        panel = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        radius = self.tokens.glass_radius
        path = QPainterPath()
        path.addRoundedRect(panel, radius, radius)
        for spread in range(self.tokens.glass_margin, 0, -1):
            shadow = QPainterPath()
            shadow.addRoundedRect(panel.adjusted(-spread, -spread + 1, spread, spread + 1),
                                  radius + spread, radius + spread)
            painter.fillPath(shadow.subtracted(path), _color("text", 3 + self.tokens.glass_margin - spread))
        painter.save()
        painter.setClipPath(path)
        if self.material.isNull():
            painter.fillPath(path, QColor(theme_color("surface")))
        else:
            painter.drawPixmap(QPoint(), self.material)
        sheen = QLinearGradient(0, panel.top(), 0, panel.bottom())
        sheen.setColorAt(0, _color("surface", 40))
        sheen.setColorAt(0.35, _color("surface", 8))
        sheen.setColorAt(1, _color("surface", 0))
        painter.fillPath(path, sheen)
        painter.restore()
        painter.setPen(QPen(_color("border_control", 55), 1))
        painter.drawPath(path)
        inner = QPainterPath()
        inner.addRoundedRect(panel.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        painter.setPen(QPen(_color("surface", 180), 1))
        painter.drawPath(inner)

        for action in self.actions():
            rect = self.actionGeometry(action)
            if not action.isVisible() or not rect.intersects(event.rect()):
                continue
            if action.isSeparator():
                painter.setPen(QPen(_color("text", 35), 1))
                painter.drawLine(rect.left() + 8, rect.center().y(), rect.right() - 8, rect.center().y())
                continue
            selected = action == self.activeAction() and action.isEnabled()
            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme_color("primary")))
                painter.drawRoundedRect(QRectF(rect), self.tokens.radius_md, self.tokens.radius_md)
            role = "primary_text" if selected else "text" if action.isEnabled() else "text_tertiary"
            color = QColor(theme_color(role))
            painter.setPen(color)
            painter.setFont(self.font())
            text_rect = rect.adjusted(self.tokens.scaled(23), 0, -self.tokens.scaled(24), 0)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic, action.text())
            if action.isChecked():
                x, y = rect.left() + self.tokens.scaled(11), rect.center().y()
                check = QPainterPath()
                check.moveTo(x - 4, y)
                check.lineTo(x - 1, y + 3)
                check.lineTo(x + 5, y - 4)
                painter.setPen(QPen(color, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(check)
            if action.menu() is not None:
                x, y = rect.right() - 9, rect.center().y()
                arrow = QPainterPath()
                arrow.moveTo(x - 2, y - 4)
                arrow.lineTo(x + 2, y)
                arrow.lineTo(x - 2, y + 4)
                painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(arrow)


def _supported(source: QMenu, available: QRect, tokens: UiTokens) -> bool:
    # Do not silently misrepresent forms, icons, sections, shortcuts or menus
    # which require Qt's built-in scrolling indicators.
    size = source.sizeHint()
    extra_height = len(source.actions()) * tokens.scaled(6)
    extra_width = 2 * tokens.glass_padding + tokens.scaled(50)
    if (size.width() + extra_width > available.width()
            or size.height() + extra_height > available.height()):
        return False
    for action in source.actions():
        group = action.actionGroup()
        if (isinstance(action, QWidgetAction) or not action.icon().isNull()
                or (action.isSeparator() and action.text()) or "\t" in action.text()
                or not action.shortcut().isEmpty()
                or (action.isCheckable() and group is not None and group.isExclusive())):
            return False
        if action.menu() and not _supported(action.menu(), available, tokens):
            return False
    return True


def build_glass_menu(source: QMenu, owner, *, scale: float = 1.0) -> QMenu:
    """Wrap the actual plot actions or return the untouched standard menu."""
    if (not _glass_available() or not owner.window().isVisible()
            or owner.layoutDirection() == Qt.RightToLeft):
        return source
    # This light material is intended for the application's light themes.
    if QColor(theme_color("text")).lightness() > 150:
        return source
    tokens = UiTokens.from_scale(scale)
    screen = owner.screen()
    if screen is None or not _supported(source, screen.availableGeometry(), tokens):
        return source
    try:
        backdrop = PlotBackdrop(owner.window(), tokens)
    except (OSError, RuntimeError, ValueError, MemoryError):
        log.warning("Could not capture plot menu background; using a standard menu", exc_info=True)
        return source

    def wrap(base, parent):
        menu = GlassMenu(parent, backdrop, tokens)
        menu.setTitle(base.title())
        for action in base.actions():
            if action.menu():
                action.setMenu(wrap(action.menu(), menu))
            menu.addAction(action)
        return menu

    menu = wrap(source, owner)
    # setParent(parent) alone removes Qt.Popup and paints the source menu as a
    # child on top of the glass. Keep its flags and QAction ownership intact.
    source.setParent(menu, source.windowFlags())
    source.hide()
    menu._source_menu = source
    return menu
