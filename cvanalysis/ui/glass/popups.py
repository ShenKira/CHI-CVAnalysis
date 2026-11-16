"""Modern popup menus using the application's own local backdrop."""
from __future__ import annotations

from dataclasses import replace
from time import perf_counter
import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QMenu, QWidgetAction
from shiboken6 import isValid
from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.tokens import UiTokens
from cvanalysis.ui.widgets.glass_menu import GlassMenu, PlotBackdrop
from cvanalysis.ui.glass.material import GlassMaterial, GlassRenderer, GlassStyle, paint_glass


def _tone(role, alpha):
    color = QColor(theme_color(role))
    color.setAlpha(alpha)
    return color

MENU_GLASS = GlassMaterial(thickness=.46, frost=.72, strength=13, bevel=10, pad=26,
                           ior_edge=1.95, ior_inner=1.34, chroma=.018,
                           disp_glow=22, disp_saturation=.24, disp_width=1.4,
                           reflect=.46, f0=.035, max_frost_sigma=9)
MENU_STYLE = GlassStyle(tint_top=16, tint_bottom=6, sheen_alpha=8,
                        sheen_extent=.46, rim_top=125, rim_mid=28,
                        rim_bottom=70, rim_width=1)


def _supports_dropdown_menu(menu, available, tokens):
    """Keep scrolling/custom-widget menus native; paint ordinary actions fully."""
    size = menu.sizeHint()
    extra_height = len(menu.actions()) * tokens.scaled(5)
    extra_width = 2 * tokens.glass_padding + tokens.scaled(50)
    if size.width() + extra_width > available.width() or size.height() + extra_height > available.height():
        return False
    for action in menu.actions():
        if isinstance(action, QWidgetAction) or (action.isSeparator() and action.text()) or "\t" in action.text():
            return False
        if action.menu() and not _supports_dropdown_menu(action.menu(), available, tokens):
            return False
    return True


class LiquidBackdrop(PlotBackdrop):
    """One app snapshot shared by PyGlass-style kernels for the menu tree."""
    def __init__(self, owner, tokens, sample_region=None):
        self.tokens = tokens
        if sample_region is None:
            super().__init__(owner, tokens)
        else:
            self.origin = owner.mapToGlobal(sample_region.topLeft())
            pixmap = owner.grab(sample_region)
            if pixmap.isNull():
                raise ValueError("dropdown snapshot is empty")
            self.dpr = pixmap.devicePixelRatioF()
            image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
            self.image = Image.frombytes("RGBA", (image.width(), image.height()),
                                         bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine())
        self.backdrop = np.asarray(self.image, dtype=np.uint8).copy()
        self.renderers = {}

    def material(self, geometry, dpr):
        relative = geometry.topLeft() - self.origin
        margin = self.tokens.glass_margin + .5
        rect = geometry.adjusted(round(margin), round(margin), -round(margin), -round(margin))
        width, height = max(1, rect.width()), max(1, rect.height())
        radius = min(self.tokens.glass_radius, height / 2)
        # NumPy gather cost grows with device pixels; cap this transient popup's
        # optical buffer at 1x and let Qt scale the cached result to screen DPR.
        render_dpr = min(dpr, 1.0)
        key = (width, height, round(radius, 2), round(render_dpr, 3), MENU_GLASS)
        renderer = self.renderers.get(key)
        if renderer is None:
            renderer = GlassRenderer(width, height, radius, render_dpr, MENU_GLASS)
            self.renderers[key] = renderer
        panel_origin = relative + rect.topLeft() - geometry.topLeft()
        return renderer.render(self.backdrop, panel_origin, self.dpr,
                               QColor(theme_color("surface")).getRgb()[:3])


class LayeredMenu(GlassMenu):
    def __init__(self, parent, backdrop, tokens):
        super().__init__(parent, backdrop, tokens)
        self._liquid_rect = QRectF()
        self._light_point = QPointF()
        self._pointer_inside = False
        self._glass_enabled = True
        # Keep the menu's rounded outer corners transparent. Popup animations
        # are disabled separately; an opaque full-window fallback squares off
        # the silhouette and looks like a white frame around the glass.
        self.hovered.connect(self._select_action)
        self.aboutToShow.connect(self._queue_popup_setup)
        self.setMouseTracking(True)

    def _select_action(self, action):
        if not action or not action.isEnabled() or action.isSeparator():
            return
        self._liquid_rect = QRectF(self.actionGeometry(action)).adjusted(1, 1, -1, -1)
        self.update()

    def mouseMoveEvent(self, event):
        if self._glass_enabled:
            self._pointer_inside = True
            self._light_point = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._pointer_inside = False
        self.update()
        super().leaveEvent(event)

    def _queue_popup_setup(self):
        self.material = QPixmap()
        self._material_key = None
        if getattr(self, "_sample_owner", None) is not None:
            self.backdrop = None
        QTimer.singleShot(0, lambda: self._finish_popup_setup() if isValid(self) else None)

    def _finish_popup_setup(self):
        if not self.isVisible():
            return
        # At high DPI Qt may show a submenu without dispatching the Python
        # showEvent override. aboutToShow supplies a safe fallback path.
        if self.backdrop is None and getattr(self, "_sample_owner", None) is not None:
            self._prepare_backdrop()
            if self._glass_enabled and self.backdrop is not None:
                self._refresh_material()
        self._disable_native_shadow()

    def _prepare_backdrop(self):
        owner = getattr(self, "_sample_owner", None)
        if owner is not None:
            app_window = owner.window()
            manager = getattr(app_window, "glass_manager", None)
            mode = getattr(manager, "mode", "balanced")
            self._glass_enabled = mode != "solid"
            screen = self.screen()
            available = screen.availableGeometry() if screen is not None else QRect()
            if not available.isEmpty():
                self.move(max(available.left(), min(self.x(), available.right() - self.width() + 1)),
                          max(available.top(), min(self.y(), available.bottom() - self.height() + 1)))
            if self._glass_enabled:
                pad = MENU_GLASS.pad_px(1.0)
                global_top = self.mapToGlobal(QPoint())
                owner_top = owner.mapToGlobal(QPoint())
                local_top = global_top - owner_top
                region = QRect(local_top.x() - pad, local_top.y() - pad,
                               self.width() + 2 * pad, self.height() + 2 * pad).intersected(owner.rect())
                try:
                    started = perf_counter()
                    self.backdrop = LiquidBackdrop(owner, self.tokens, sample_region=region)
                    if hasattr(app_window, "_menu_capture_ms"):
                        app_window._menu_capture_ms.append((perf_counter() - started) * 1000)
                except (MemoryError, OSError, RuntimeError, ValueError):
                    self.backdrop = None
            else:
                self.backdrop = None

    def showEvent(self, event):
        self._prepare_backdrop()
        super().showEvent(event)
        # On Windows Qt may attach its own dark drop-shadow effect to QMenu
        # during show; it survives even with NoDropShadowWindowHint.
        self._disable_native_shadow()
        QTimer.singleShot(0, lambda: self._disable_native_shadow() if isValid(self) else None)

    def _disable_native_shadow(self):
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setEnabled(False)

    def _refresh_material(self):
        if self.backdrop is None:
            self.material = QPixmap()
            self._material_key = None
            self.update()
            return
        key = (self.geometry().x(), self.geometry().y(), self.width(), self.height(), self.devicePixelRatioF())
        if getattr(self, "_material_key", None) == key and not self.material.isNull():
            return
        super()._refresh_material()
        self._material_key = key if not self.material.isNull() else None

    def paintEvent(self, event):
        # Paint the complete menu here: the production prototype's layered dark
        # shadows and inset rings were visually too heavy for this experiment.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        margin = self.tokens.glass_margin + 0.5
        rect = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        radius = self.tokens.glass_radius
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if self._glass_enabled:
            if self.material.isNull():
                painter.fillPath(path, QColor(theme_color("surface")))
            paint_glass(painter, rect, radius, self.material if not self.material.isNull() else None, MENU_STYLE)
        else:
            painter.setPen(QPen(_tone("border_control", 80), 1))
            painter.setBrush(QColor(theme_color("surface")))
            painter.drawRoundedRect(rect, radius, radius)

        if self._pointer_inside:
            painter.save()
            edge = QPainterPath()
            edge.addRoundedRect(rect.adjusted(1, 1, -1, -1), max(1, radius - 1), max(1, radius - 1))
            painter.setClipPath(path.subtracted(edge))
            glow = QRadialGradient(self._light_point, 75)
            glow.setColorAt(0, _tone("surface", 220))
            glow.setColorAt(1, _tone("surface", 0))
            painter.fillPath(path, glow)
            painter.restore()

        if self.activeAction() and not self._liquid_rect.isEmpty():
            painter.setPen(QPen(_tone("surface", 132), 1))
            painter.setBrush(_tone("text_secondary", 42))
            painter.drawRoundedRect(self._liquid_rect, 7, 7)

        visible_actions = [action for action in self.actions()
                           if action.isVisible() and not action.isSeparator()]
        has_checks = any(action.isCheckable() for action in visible_actions)
        has_icons = any(not action.icon().isNull() for action in visible_actions)
        for action in self.actions():
            item = self.actionGeometry(action)
            if not action.isVisible() or not item.intersects(event.rect()):
                continue
            if action.isSeparator():
                painter.setPen(QPen(_tone("text_secondary", 32), 1))
                painter.drawLine(item.left() + 9, item.center().y(), item.right() - 9, item.center().y())
                continue
            painter.setBrush(Qt.NoBrush)
            role = "text" if action.isEnabled() else "text_tertiary"
            color = QColor(theme_color(role))
            group = action.actionGroup()
            exclusive = action.isCheckable() and group is not None and group.isExclusive()
            leading = item.left() + self.tokens.scaled(10)
            if action.isCheckable():
                if exclusive:
                    painter.setPen(QPen(color, 1.35))
                    painter.drawEllipse(QPointF(leading + 5, item.center().y()), 4.1, 4.1)
                    if action.isChecked():
                        painter.setBrush(color)
                        painter.setPen(Qt.NoPen)
                        painter.drawEllipse(QPointF(leading + 5, item.center().y()), 2, 2)
                        painter.setBrush(Qt.NoBrush)
                elif action.isChecked():
                    check = QPainterPath()
                    check.moveTo(leading, item.center().y())
                    check.lineTo(leading + 3, item.center().y() + 3)
                    check.lineTo(leading + 9, item.center().y() - 4)
                    painter.setPen(QPen(color, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    painter.drawPath(check)
            if has_checks:
                leading += self.tokens.scaled(19)
            if has_icons:
                icon_size = min(self.tokens.scaled(18), max(12, item.height() - 4))
                icon_rect = QRect(int(leading), int(item.center().y() - icon_size / 2), icon_size, icon_size)
                if not action.icon().isNull():
                    icon_mode = QIcon.Normal if action.isEnabled() else QIcon.Disabled
                    icon_state = QIcon.On if action.isChecked() else QIcon.Off
                    action.icon().paint(painter, icon_rect, Qt.AlignCenter, icon_mode, icon_state)
                leading += self.tokens.scaled(18) + self.tokens.scaled(7)

            right = item.right() - (self.tokens.scaled(18) if action.menu() else self.tokens.scaled(12))
            shortcut = action.shortcut().toString()
            if shortcut:
                shortcut_width = self.fontMetrics().horizontalAdvance(shortcut)
                shortcut_rect = QRectF(right - shortcut_width, item.top(), shortcut_width, item.height())
                secondary = QColor(theme_color("text_secondary"))
                painter.setPen(secondary)
                painter.drawText(shortcut_rect, Qt.AlignVCenter | Qt.AlignRight, shortcut)
                right = int(shortcut_rect.left()) - self.tokens.scaled(8)

            painter.setPen(color)
            painter.setFont(self.font())
            text_rect = QRectF(leading, item.top(), max(0, right - leading), item.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextShowMnemonic, action.text())
            if action.menu() is not None:
                x, y = item.right() - 9, item.center().y()
                arrow = QPainterPath()
                arrow.moveTo(x - 2, y - 4)
                arrow.lineTo(x + 2, y)
                arrow.lineTo(x - 2, y + 4)
                painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(arrow)


def _modern_solid_menu(menu, tokens):
    """Keep Qt's own scroll and widget-action handling for complex menus."""
    surface = theme_color("surface")
    text = theme_color("text")
    hover = theme_color("surface_alt")
    border = theme_color("border_control")
    menu.setStyleSheet(f"""
        QMenu {{ background: {surface}; color: {text}; border: 1px solid {border};
                 border-radius: {tokens.radius_lg}px; padding: {tokens.space_xs}px; }}
        QMenu::item {{ padding: {tokens.space_sm}px {tokens.space_lg}px;
                       border-radius: {tokens.radius_md}px; }}
        QMenu::item:selected {{ background: {hover}; }}
    """)
    return menu


def wrap_menu(source, owner, manager=None):
    """Wrap an application popup, retaining its QAction objects and ownership."""
    if source.property("liquidGlassWrapped"):
        return source
    window = owner.window()
    manager = manager or getattr(window, "glass_manager", None)
    scale = getattr(window, "_ui_scale", 1.0)
    tokens = UiTokens.from_scale(scale)
    tokens = replace(tokens, glass_radius=tokens.scaled(17))
    screen = owner.screen()
    if screen is None or not _supports_dropdown_menu(source, screen.availableGeometry(), tokens):
        return _modern_solid_menu(source, tokens)

    def wrap(base, parent):
        menu = LayeredMenu(parent, None, tokens)
        menu._sample_owner = owner
        menu.setTitle(base.title())
        for action in base.actions():
            if action.menu():
                action.setMenu(wrap(action.menu(), menu))
            menu.addAction(action)
        base.setParent(menu, base.windowFlags())
        base.hide()
        menu._source_menu = base
        menu.setProperty("liquidGlassWrapped", True)
        return menu

    return wrap(source, source.parentWidget() or owner)


