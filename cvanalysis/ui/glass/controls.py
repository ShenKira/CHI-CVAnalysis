"""Pointer-responsive demo controls over the application's native widgets.

Only the three explicitly selected tab bars intercept painting; their tab
geometry, input, keyboard navigation and page ownership remain Qt's own.
"""
from __future__ import annotations

import math
from collections import deque
from time import perf_counter

import numpy as np
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPalette, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QAbstractButton, QComboBox, QDialogButtonBox, QFrame, QGraphicsDropShadowEffect, QListView, QMenu, QMenuBar, QSizePolicy, QStyle, QStyleOptionTab, QStylePainter, QTabWidget, QToolButton, QWidget
from shiboken6 import isValid
from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.glass.material import GlassMaterial, GlassRenderer, GlassStyle, paint_glass


def _tone(role, alpha):
    color = QColor(theme_color(role))
    color.setAlpha(max(0, min(255, round(alpha))))
    return color


def _rgba(role, alpha):
    color = _tone(role, alpha)
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


class LightOverlay(QWidget):
    """Transparent, non-interactive specular layer above a native control."""
    def __init__(self, target):
        super().__init__(target)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.point = QPointF(target.width() / 2, target.height() / 2)
        self.target_point = QPointF(self.point)
        self.intensity = 0.0
        self.goal = 0.0
        self.press = 0.0
        self.press_goal = 0.0
        self.paint_samples = None
        self.is_combo = isinstance(target, QComboBox)
        self.setGeometry(target.rect())
        self.show()

    def paintEvent(self, event):
        # Qt builds without an SVG image plugin still need a visible dropdown
        # affordance. This child never receives mouse or keyboard input.
        if self.is_combo:
            arrow = QPainter(self)
            arrow.setRenderHint(QPainter.Antialiasing)
            rim = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            arrow.setBrush(Qt.NoBrush)
            arrow.setPen(QPen(_tone("surface", 180), 1))
            arrow.drawRoundedRect(rim, min(8.0, rim.height() / 2), min(8.0, rim.height() / 2))
            arrow.setPen(QPen(_tone("text_secondary", 255), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x, y = self.width() - 12, self.height() / 2 - 1
            path = QPainterPath()
            path.moveTo(x - 4, y - 2)
            path.lineTo(x, y + 2)
            path.lineTo(x + 4, y - 2)
            arrow.drawPath(path)
            arrow.end()
        if self.intensity < .01:
            return
        started = perf_counter()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Flex the luminous rim within the control's unchanged hit target.
        rect = QRectF(self.rect()).adjusted(1 - self.press, 1 + self.press,
                                           -1 + self.press, -1 - self.press)
        radius = min(10.0, rect.height() / 2)
        outer = QPainterPath()
        outer.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(outer)
        spot = QRadialGradient(self.point, max(25, min(85, rect.width() * .5)))
        spot.setColorAt(0, _tone("surface", 26 * self.intensity))
        spot.setColorAt(1, _tone("surface", 0))
        painter.fillPath(outer, spot)
        painter.restore()
        inner = QPainterPath()
        inner.addRoundedRect(rect.adjusted(2.5, 2.5, -2.5, -2.5),
                             max(1, radius - 2.5), max(1, radius - 2.5))
        painter.setClipPath(outer.subtracted(inner))
        glow = QRadialGradient(self.point, max(20, min(95, rect.width() * .55)))
        glow.setColorAt(0, _tone("surface", 210 * self.intensity))
        glow.setColorAt(.4, _tone("surface", 90 * self.intensity))
        glow.setColorAt(1, _tone("surface", 0))
        painter.fillPath(outer, glow)
        painter.end()
        if self.paint_samples is not None:
            self.paint_samples.append((perf_counter() - started) * 1000)


class PointerLights(QObject):
    """One event-driven timer shared by all button-edge highlights."""
    def __init__(self, window):
        super().__init__(window)
        self.mode = "balanced"
        self.animations = True
        self.overlays = {}
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.last = perf_counter()
        self.ticks = 0
        self.tick_samples = deque(maxlen=512)
        self.paint_samples = deque(maxlen=512)

    def attach(self, widget):
        if widget in self.overlays:
            return
        overlay = LightOverlay(widget)
        overlay.setVisible(self.mode != "solid")
        overlay.paint_samples = self.paint_samples
        self.overlays[widget] = overlay
        widget.destroyed.connect(lambda *_, item=widget: self.overlays.pop(item, None))
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def set_mode(self, mode):
        self.mode = mode
        self.timer.stop()
        for widget, overlay in list(self.overlays.items()):
            if isValid(widget) and isValid(overlay):
                overlay.goal = overlay.intensity = 0.0
                overlay.press = overlay.press_goal = 0.0
                overlay.setVisible(mode != "solid")
                overlay.update()

    def eventFilter(self, widget, event):
        overlay = self.overlays.get(widget)
        if overlay is None or not isValid(overlay):
            return False
        kind = event.type()
        if kind in (QEvent.Resize, QEvent.Show):
            overlay.setGeometry(widget.rect())
            overlay.raise_()
        if self.mode == "solid":
            return False
        if kind in (QEvent.Enter, QEvent.MouseMove, QEvent.MouseButtonPress):
            if kind == QEvent.Enter:
                overlay.target_point = QPointF(widget.mapFromGlobal(QCursor.pos()))
            else:
                overlay.target_point = event.position()
            overlay.goal = 1.0 if widget.isEnabled() else 0.0
            if kind == QEvent.MouseButtonPress:
                overlay.press_goal = 1.0
                overlay.point = QPointF(overlay.target_point)  # immediate response at the contact
            self._start()
        elif kind in (QEvent.Leave, QEvent.Hide, QEvent.EnabledChange):
            overlay.goal = 0.0
            overlay.press_goal = 0.0
            self._start()
        elif kind == QEvent.MouseButtonRelease:
            overlay.press_goal = 0.0
            self._start()
        return False

    def _start(self):
        if not self.animations:
            for overlay in self.overlays.values():
                if isValid(overlay):
                    overlay.intensity = overlay.goal
                    overlay.press = overlay.press_goal
                    overlay.point = QPointF(overlay.target_point)
                    overlay.update()
            return
        if not self.timer.isActive():
            self.last = perf_counter()
            self.timer.start()

    def _tick(self):
        now = perf_counter()
        dt = min(.05, now - self.last)
        self.last = now
        self.ticks += 1
        blend = 1 - math.exp(-dt * 20)
        pending = False
        for widget, overlay in list(self.overlays.items()):
            if not isValid(widget) or not isValid(overlay):
                self.overlays.pop(widget, None)
                continue
            if not (overlay.intensity or overlay.goal or overlay.press or overlay.press_goal):
                continue
            overlay.intensity += (overlay.goal - overlay.intensity) * blend
            overlay.press += (overlay.press_goal - overlay.press) * blend
            delta = overlay.target_point - overlay.point
            overlay.point += delta * blend
            if (abs(overlay.goal - overlay.intensity) > .015 or abs(overlay.press_goal - overlay.press) > .015
                    or (overlay.goal and abs(delta.x()) + abs(delta.y()) > .4)):
                pending = True
            else:
                overlay.intensity = overlay.goal
                overlay.press = overlay.press_goal
                overlay.point = QPointF(overlay.target_point)
            if overlay.isVisible():
                overlay.update()
        if not pending:
            self.timer.stop()
        self.tick_samples.append((perf_counter() - now) * 1000)


class _ButtonGroupGlass(QWidget):
    """One shared glass surface and specular response for a connected control group."""
    def __init__(self, host, members, manager, orientation="horizontal"):
        super().__init__(host)
        self.host = host
        self.members = list(members)
        self.manager = manager
        self.orientation = orientation
        self.point = QPointF()
        self.target_point = QPointF()
        self.hovered = None
        self.pressed = None
        self.light = 0.0
        self.press = 0.0
        self.target_light = 0.0
        self.target_press = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(host.rect())
        self.show()
        self.lower()

    def group_rect(self):
        rect = QRectF()
        for member in self.members:
            if isValid(member) and member.isVisible() and member.width() > 0 and member.height() > 0:
                local = QRectF(member.geometry())
                rect = local if rect.isNull() else rect.united(local)
        return rect.adjusted(-1, -1, 1, 1) if not rect.isNull() else rect

    @staticmethod
    def _pill(painter, rect, radius, fill, stroke=None, width=1):
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, fill)
        if stroke is not None:
            painter.setPen(QPen(stroke, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

    def paintEvent(self, event):
        if self.manager.mode == "solid":
            return
        bounds = self.group_rect()
        if bounds.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = min(13.0, bounds.height() / 2, bounds.width() / 2)

        # A milky but transparent base, bounded by a bright outer bevel and a
        # quieter inner edge. This gives the shared material more depth without
        # adding an Aero-style drop shadow.
        self._pill(painter, bounds, radius, _tone("surface", 76),
                   _tone("surface", 232), 1.2)

        inner = bounds.adjusted(1.35, 1.35, -1.35, -1.35)
        if inner.width() > 2 and inner.height() > 2:
            self._pill(painter, inner, max(1, radius - 1), _tone("surface", 30),
                       _tone("border_control", 70), .8)

        # Persistent selection and the short press response use the same cool
        # tint, while a hover stays clear and receives only moving light.
        for member in self.members:
            if not isValid(member) or not member.isVisible():
                continue
            selected = ((isinstance(member, QAbstractButton) and member.isCheckable() and member.isChecked())
                        or self.manager.popup_is_open(member))
            pressed = member is self.pressed and self.press > .02
            if not selected and not pressed:
                continue
            segment = QRectF(member.geometry()).adjusted(1.6, 1.6, -1.6, -1.6)
            color = _tone("primary", 82 if selected else 100 * self.press)
            self._pill(painter, segment, min(9, segment.height() / 2), color,
                       _tone("surface", 108 if selected else 82), .8)

        # Hairline separators make the individual targets legible while the
        # common outline keeps the group reading as one continuous piece.
        visible = [m for m in self.members if isValid(m) and m.isVisible()]
        ordered = sorted(visible, key=lambda m: (m.geometry().center().x() if self.orientation == "horizontal"
                                                  else m.geometry().center().y()))
        if len(ordered) > 1:
            painter.setPen(QPen(_tone("surface", 170), .8))
            for first, second in zip(ordered, ordered[1:]):
                a, b = first.geometry(), second.geometry()
                if self.orientation == "horizontal":
                    x = (a.right() + b.left()) / 2
                    painter.drawLine(QPointF(x, bounds.top() + 6), QPointF(x, bounds.bottom() - 6))
                else:
                    y = (a.bottom() + b.top()) / 2
                    painter.drawLine(QPointF(bounds.left() + 7, y), QPointF(bounds.right() - 7, y))

        if self.hovered is not None and self.light > .01:
            segment = QRectF(self.hovered.geometry()).adjusted(1.1, 1.1, -1.1, -1.1)
            segment_radius = min(10.0, segment.height() / 2)
            shape = QPainterPath()
            shape.addRoundedRect(segment, segment_radius, segment_radius)
            painter.save()
            painter.setClipPath(shape)
            painter.fillPath(shape, _tone("text_secondary", 38 * self.light))
            light = QRadialGradient(self.point, max(24, min(95, segment.width() * .75)))
            light.setColorAt(0, _tone("surface", 72 * self.light))
            light.setColorAt(.52, _tone("surface", 24 * self.light))
            light.setColorAt(1, _tone("surface", 0))
            painter.fillPath(shape, light)
            painter.setPen(QPen(_tone("surface", 92 * self.light), 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(shape)
            painter.restore()
        for member in self.members:
            if isValid(member) and member.isVisible() and member.isEnabled() and member.hasFocus():
                focus = QRectF(member.geometry()).adjusted(2, 2, -2, -2)
                painter.setPen(QPen(_tone("focus", 210), 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(focus, min(8.0, focus.height() / 2), min(8.0, focus.height() / 2))
        painter.end()


class LiquidButtonGroups(QObject):
    """Attach connected glass backplates without replacing native controls."""
    def __init__(self, root, mode="balanced"):
        super().__init__(root)
        self.root = root
        self.mode = mode
        self.animations = True
        self._groups = []
        self._members = set()
        self._watched = set()
        self._popup_owners = {}
        self._open_popups = set()
        self._pending_watch = set()
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.timeout.connect(self._scan_pending)
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self.refresh_popups)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.last = perf_counter()
        self.watch(root)

    def add(self, members, orientation="horizontal"):
        items = []
        for member in members:
            if member is not None and isValid(member) and member not in items:
                items.append(member)
        if len(items) < 2 or len({item.parentWidget() for item in items}) != 1:
            return None
        host = items[0].parentWidget()
        if host is None:
            return None
        overlay = _ButtonGroupGlass(host, items, self, orientation)
        overlay.paint_samples = None
        if self.mode == "solid":
            overlay.hide()
        self._groups.append(overlay)
        if host not in self._watched:
            self._watched.add(host)
            host.installEventFilter(self)
        for member in items:
            member.setProperty("liquidGroupMember", True)
            member.setMouseTracking(True)
            member.installEventFilter(self)
            member.destroyed.connect(lambda *_, item=member: self._members.discard(item))
            self._members.add(member)
            if isinstance(member, QAbstractButton):
                member.toggled.connect(lambda *_args, surface=overlay: surface.update())
        self._lower_backings(host)
        return overlay

    def _lower_backings(self, host):
        # The panel backing and group surfaces are siblings. Keep the panel
        # below every group even when a LayoutRequest restacks the latter.
        material_manager = getattr(self.root, "glass_manager", None)
        for surface in getattr(material_manager, "surfaces", ()):
            if isValid(surface) and surface.parentWidget() is host:
                surface.lower()

    def refresh_popups(self):
        """Bind the current popup after menus/views have been wrapped."""
        for member in list(self._members):
            if not isValid(member):
                self._members.discard(member)
                continue
            popup = member.menu() if isinstance(member, QToolButton) else None
            if isinstance(member, QComboBox):
                popup = member.view().window()
                if popup is member or popup is member.window():
                    popup = None
            if popup is None or not isValid(popup) or popup in self._popup_owners:
                continue
            self._popup_owners[popup] = member
            popup.installEventFilter(self)
            popup.destroyed.connect(lambda *_, item=popup: self._forget_popup(item))
            self.watch(popup)
            if popup.isVisible():
                self._open_popups.add(popup)

    def schedule_popup_refresh(self):
        self._popup_timer.start(0)

    def _forget_popup(self, popup):
        member = self._popup_owners.pop(popup, None)
        self._open_popups.discard(popup)
        for group in self._groups:
            if isValid(group) and member in group.members:
                group.update()

    def popup_is_open(self, member):
        return any(self._popup_owners.get(popup) is member for popup in self._open_popups)

    def _hover_at_global(self, position):
        for group in self._groups:
            if not isValid(group):
                continue
            target = next((member for member in group.members
                           if isValid(member) and member.isVisible() and member.isEnabled()
                           and member.rect().contains(member.mapFromGlobal(position))), None)
            if target is not group.hovered or target is not None:
                group.hovered = target
                group.target_light = 1.0 if target is not None else 0.0
                if target is not None:
                    group.target_point = QPointF(group.host.mapFromGlobal(position))
        self._start()

    def set_mode(self, mode):
        self.mode = mode
        for group in self._groups:
            if isValid(group):
                group.target_light = group.target_press = group.light = group.press = 0
                group.setVisible(mode != "solid")
                group.update()
        self.timer.stop()

    def watch(self, widget):
        if not isValid(widget):
            return
        if widget not in self._watched:
            self._watched.add(widget)
            widget.installEventFilter(self)
            widget.destroyed.connect(lambda *_, item=widget: self._watched.discard(item))
        # Plot color chips are rebuilt when the active plot changes. Keep them
        # grouped without coupling the demo to the production widget code.
        if hasattr(widget, "_swatches_layout") and hasattr(widget, "swatches"):
            swatches = widget.swatches
            if swatches not in self._watched:
                swatches.installEventFilter(self)
                self._watched.add(swatches)
                swatches._liquid_glass_group_manager = self
            self._sync_dynamic_group(swatches)
        if isinstance(widget, QDialogButtonBox):
            self._sync_dynamic_group(widget)
        elif hasattr(widget, "_liquid_glass_group_manager"):
            self._sync_dynamic_group(widget)
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            self.watch(child)

    def _scan_pending(self):
        pending, self._pending_watch = self._pending_watch, set()
        for widget in pending:
            if isValid(widget):
                self.watch(widget)

    def _sync_dynamic_group(self, host):
        members = host.findChildren(QAbstractButton, options=Qt.FindDirectChildrenOnly)
        if len(members) < 2:
            return
        overlay = getattr(host, "_liquid_glass_group", None)
        if overlay is not None and isValid(overlay):
            old = {member for member in overlay.members if isValid(member)}
            new = set(members)
            for member in old - new:
                member.setProperty("liquidGroupMember", False)
                self._members.discard(member)
            overlay.members = members
            for member in new - old:
                member.setProperty("liquidGroupMember", True)
                member.setMouseTracking(True)
                member.installEventFilter(self)
                self._members.add(member)
                if isinstance(member, QAbstractButton):
                    member.toggled.connect(lambda *_args, surface=overlay: surface.update())
            overlay.update()
            return
        overlay = self.add(members, "horizontal")
        if overlay is not None:
            host._liquid_glass_group = overlay

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.ChildAdded:
            # ChildAdded fires while Qt is constructing a widget. Inspect the
            # finished parent's children later so Shiboken does not cache an
            # incomplete QWidget wrapper for e.g. a new QStatusBar.
            if isinstance(watched, QWidget):
                self._pending_watch.add(watched)
                self._watch_timer.start(0)
            return False
        if watched in self._popup_owners:
            member = self._popup_owners[watched]
            if kind == QEvent.Show:
                self._open_popups.add(watched)
                for group in self._groups:
                    if isValid(group) and member in group.members:
                        # Popup menus can consume the release event.
                        group.pressed = None
                        group.press = group.target_press = 0.0
                        group.update()
                self._hover_at_global(QCursor.pos())
            elif kind == QEvent.Hide:
                self._open_popups.discard(watched)
                for group in self._groups:
                    if isValid(group) and member in group.members:
                        group.pressed = None
                        group.press = group.target_press = 0.0
                        group.update()
                self._hover_at_global(QCursor.pos())
        if (self._open_popups and kind == QEvent.MouseMove and isinstance(watched, QWidget)
                and watched.window() in self._open_popups):
            self._hover_at_global(event.globalPosition().toPoint())
        if watched not in self._members:
            if watched in self._watched and kind in (QEvent.Resize, QEvent.LayoutRequest, QEvent.Show):
                for group in self._groups:
                    if isValid(group) and group.host is watched:
                        group.setGeometry(watched.rect())
                        group.lower()
                        group.update()
                self._lower_backings(watched)
            return False
        group = next((candidate for candidate in self._groups if isValid(candidate) and watched in candidate.members), None)
        if group is None:
            return False
        if kind in (QEvent.Enter, QEvent.MouseMove, QEvent.MouseButtonPress):
            if kind == QEvent.MouseButtonPress and isinstance(watched, (QToolButton, QComboBox)):
                self.refresh_popups()
            pos = event.position() if hasattr(event, "position") else QPointF(watched.rect().center())
            group.target_point = QPointF(watched.mapTo(group.host, pos.toPoint()))
            group.hovered = watched
            group.target_light = 1.0 if watched.isEnabled() else 0.0
            if kind == QEvent.MouseButtonPress:
                group.pressed = watched
                group.press = group.target_press = 1.0
                group.point = QPointF(group.target_point)
            self._start()
        elif kind in (QEvent.Leave, QEvent.Hide, QEvent.EnabledChange):
            cursor = QCursor.pos()
            target = next((m for m in group.members if isValid(m) and m.isVisible()
                           and m.rect().contains(m.mapFromGlobal(cursor))), None)
            group.hovered = target
            group.target_light = 1.0 if target is not None and target.isEnabled() else 0.0
            self._start()
        elif kind == QEvent.MouseButtonRelease:
            group.pressed = None
            group.target_press = 0.0
            self._start()
        elif kind in (QEvent.Resize, QEvent.Show, QEvent.Move):
            group.update()
        elif kind in (QEvent.FocusIn, QEvent.FocusOut):
            group.update()
        return False

    def _start(self):
        if self.mode == "solid":
            return
        if not self.animations:
            for group in self._groups:
                if isValid(group):
                    group.light = group.target_light
                    group.press = group.target_press
                    group.point = QPointF(group.target_point)
                    group.update()
            return
        if not self.timer.isActive():
            self.last = perf_counter()
            self.timer.start()

    def _tick(self):
        now = perf_counter()
        blend = 1 - math.exp(-min(.05, now - self.last) * 22)
        self.last = now
        pending = False
        for group in list(self._groups):
            if not isValid(group):
                self._groups.remove(group)
                continue
            delta = group.target_point - group.point
            if not (group.light or group.target_light or group.press or group.target_press
                    or (group.hovered is not None and group.target_light)
                    or abs(delta.x()) + abs(delta.y()) > .4):
                continue
            group.light += (group.target_light - group.light) * blend
            group.press += (group.target_press - group.press) * blend
            group.point += delta * blend
            if (abs(group.target_light - group.light) > .015 or abs(group.target_press - group.press) > .015
                    or (group.target_light and abs((group.target_point - group.point).x())
                        + abs((group.target_point - group.point).y()) > .4)):
                pending = True
            else:
                group.light, group.press = group.target_light, group.target_press
                group.point = QPointF(group.target_point)
            group.update()
        if not pending:
            self.timer.stop()


class LiquidComboView(QListView):
    """Keep Qt's model, delegate and input while painting glass under its rows."""
    def __init__(self, combo, manager):
        super().__init__()
        self.combo = combo
        self.manager = manager
        self._material = None
        self._popup = None
        self._shadow_timer = QTimer(self)
        self._shadow_timer.setSingleShot(True)
        self._shadow_timer.timeout.connect(self._disable_shadow)
        self._optics = GlassMaterial(thickness=.43, frost=.65, strength=10,
                                     bevel=8, pad=20, ior_edge=1.8,
                                     ior_inner=1.34, chroma=.015, disp_glow=16,
                                     disp_saturation=.20, disp_width=1.1,
                                     reflect=.4, f0=.035, max_frost_sigma=8)
        self._style = GlassStyle(tint_top=16, tint_bottom=6, sheen_alpha=5,
                                 rim_top=100, rim_mid=22, rim_bottom=58)
        self.setFrameShape(QFrame.NoFrame)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WA_TranslucentBackground, False)
        self.viewport().setAutoFillBackground(False)
        self.refresh_theme()

    def refresh_theme(self):
        self.setStyleSheet(f"""
            QListView {{ background: transparent; border: none; padding: 5px; outline: none; }}
            QListView::item {{ padding: 5px 10px; border-radius: 7px; }}
            QListView::item:selected {{ background: {_rgba('primary', 52)}; color: {theme_color('text')}; }}
            QListView::item:hover:!selected {{ background: {_rgba('text_secondary', 34)}; }}
        """)

    def _watch_popup(self):
        popup = self.window()
        if popup is self or popup is self.combo.window():
            return
        if popup is not self._popup:
            if self._popup is not None:
                self._popup.removeEventFilter(self)
            self._popup = popup
            popup.installEventFilter(self)
        # Keep the top-level popup opaque; the viewport paints its own glass.
        popup.setAttribute(Qt.WA_TranslucentBackground, False)
        popup.setAttribute(Qt.WA_NoSystemBackground, False)
        popup.setAttribute(Qt.WA_StyledBackground, True)
        popup.setAutoFillBackground(True)
        palette = popup.palette()
        for role in (QPalette.Window, QPalette.Base, QPalette.Button):
            palette.setColor(role, QColor(theme_color("surface")))
        popup.setPalette(palette)
        popup.setStyleSheet(f"QFrame {{ background: {theme_color('surface')}; border: none; }}")
        popup.style().unpolish(popup)
        popup.style().polish(popup)
        popup.update()
        self._disable_shadow()
        self._shadow_timer.start(0)

    def _disable_shadow(self):
        if self._popup is not None and isValid(self._popup):
            effect = self._popup.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                effect.setEnabled(False)

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self and kind == QEvent.Show:
            self._material = None
            self._watch_popup()
        elif watched is self and kind == QEvent.Hide:
            self._material = None
        elif watched is self._popup and kind in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self._material = None
            if kind == QEvent.Show:
                self._shadow_timer.start(0)
        elif watched is self._popup and kind == QEvent.Hide:
            self._material = None
        return super().eventFilter(watched, event)

    def _capture_material(self):
        viewport = self.viewport()
        width, height = viewport.width(), viewport.height()
        if width < 2 or height < 2:
            return None
        owner = self.combo.window()
        dpr = min(self.devicePixelRatioF(), 1.0)
        radius = min(13.0, height / 2)
        renderer = GlassRenderer(width, height, radius, dpr, self._optics)
        origin_global = viewport.mapToGlobal(QPoint())
        origin_owner = owner.mapFromGlobal(origin_global)
        source_pad = round(renderer.kernel.pad / dpr * owner.devicePixelRatioF())
        sample_rect = QRect(origin_owner.x() - source_pad, origin_owner.y() - source_pad,
                            width + 2 * source_pad, height + 2 * source_pad).intersected(owner.rect())
        if sample_rect.isEmpty():
            return None
        pixmap = owner.grab(sample_rect)
        if pixmap.isNull():
            return None
        source = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
        raw = np.frombuffer(source.constBits(), dtype=np.uint8).reshape(source.height(), source.bytesPerLine())
        rgba = raw[:, :source.width() * 4].reshape(source.height(), source.width(), 4).copy()
        sample_origin = owner.mapToGlobal(sample_rect.topLeft())
        panel_origin = origin_global - sample_origin
        return renderer.render(rgba, panel_origin, pixmap.devicePixelRatioF(),
                               QColor(theme_color("surface")).getRgb()[:3])

    def paintEvent(self, event):
        viewport = self.viewport()
        radius = min(13.0, viewport.height() / 2)
        if self.manager.mode == "solid":
            painter = QPainter(viewport)
            path = QPainterPath()
            path.addRoundedRect(QRectF(viewport.rect()), radius, radius)
            painter.fillPath(path, QColor(theme_color("surface")))
            painter.end()
        else:
            if self._material is None:
                try:
                    self._material = self._capture_material()
                except (MemoryError, OSError, RuntimeError, ValueError):
                    self._material = False
            if isinstance(self._material, QPixmap):
                painter = QPainter(viewport)
                paint_glass(painter, QRectF(viewport.rect()), radius, self._material, self._style)
                painter.end()
            else:
                painter = QPainter(viewport)
                painter.fillRect(viewport.rect(), QColor(theme_color("surface")))
                painter.end()
        super().paintEvent(event)


def install_liquid_combo(combo, manager, pointer_lights=None):
    """Replace the popup view, preserving the combo's model and row delegate."""
    if combo.property("liquidPopupInstalled") and isinstance(combo.view(), LiquidComboView):
        return
    old_view = combo.view()
    delegate = old_view.itemDelegate()
    popup_view = LiquidComboView(combo, manager)
    popup_view.setUniformItemSizes(old_view.uniformItemSizes())
    popup_view.setSelectionMode(old_view.selectionMode())
    if delegate is not None and delegate.parent() is old_view:
        delegate.setParent(popup_view)
    combo.setView(popup_view)
    popup_view.setModel(combo.model())
    popup_view.setModelColumn(combo.modelColumn())
    popup_view.setRootIndex(combo.rootModelIndex())
    if delegate is not None:
        popup_view.setItemDelegate(delegate)
    popup_view._watch_popup()
    combo.setProperty("liquidPopupInstalled", True)
    if not combo.property("liquidGroupMember"):
        combo.setProperty("liquidControl", True)
        combo.style().unpolish(combo)
        combo.style().polish(combo)
    if pointer_lights is not None and combo.property("liquidControl") and not combo.property("liquidGroupMember"):
        pointer_lights.attach(combo)


class LiquidComboRegistry(QObject):
    """Apply popup skins to current and dynamically created controls."""
    def __init__(self, root, manager, pointer_lights, menu_wrapper=None, glass_enabled=True):
        super().__init__(root)
        self.manager = manager
        self.pointer_lights = pointer_lights
        self.menu_wrapper = menu_wrapper
        self.glass_enabled = glass_enabled
        self._watched = set()
        self._pending_watch = set()
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.timeout.connect(self._scan_pending)
        self.watch(root)

    def _scan_pending(self):
        pending, self._pending_watch = self._pending_watch, set()
        for widget in pending:
            if isValid(widget):
                self.watch(widget)

    def watch(self, widget):
        if not isValid(widget):
            return
        if widget not in self._watched:
            self._watched.add(widget)
            widget.installEventFilter(self)
            widget.destroyed.connect(lambda *_, item=widget: self._watched.discard(item))
        if isinstance(widget, QComboBox):
            if self.glass_enabled:
                install_liquid_combo(widget, self.manager, self.pointer_lights)
        elif self.glass_enabled and isinstance(widget, QToolButton) and widget.menu() and self.menu_wrapper:
            parent = widget.parentWidget()
            while parent is not None and not isinstance(parent, QMenuBar):
                parent = parent.parentWidget()
            if parent is None:
                widget.setMenu(self.menu_wrapper(widget.menu(), widget.window()))
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            self.watch(child)

    def refresh(self):
        """Pick up menus created after the last scan or after an appearance switch."""
        self.watch(self.parent())
        for widget in tuple(self._watched):
            if isValid(widget) and isinstance(widget, QComboBox) and isinstance(widget.view(), LiquidComboView):
                widget.view().refresh_theme()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ChildAdded:
            if isinstance(watched, QWidget):
                self._pending_watch.add(watched)
                self._watch_timer.start(0)
        return False


class LiquidTabs(QObject):
    """Draw a sliding lens under native tab labels while retaining Qt input."""
    def __init__(self, bar, manager):
        super().__init__(bar)
        self.bar = bar
        self.manager = manager
        bar.setExpanding(True)
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tab_widget = bar.parentWidget() if isinstance(bar.parentWidget(), QTabWidget) else None
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._fill_tab_row)
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.timeout.connect(self._sync_geometry)
        if self.tab_widget is not None:
            self.tab_widget.installEventFilter(self)
            self._layout_timer.start(0)
        self.current = QRectF()
        self.pointer = QPointF()
        self.hover = False
        self.hover_index = -1
        self.animation = QVariantAnimation(self)
        self._animation_duration = 260
        self.animation.setDuration(self._animation_duration)
        # A monotonic easing prevents the selected lens from briefly crossing
        # the end tabs' border before settling back.
        self.animation.setEasingCurve(QEasingCurve(QEasingCurve.OutCubic))
        self.animation.valueChanged.connect(self._move)
        bar.setMouseTracking(True)
        bar.installEventFilter(self)
        bar.currentChanged.connect(self._select)

    def _rect(self, index):
        return QRectF(self.bar.tabRect(index)).adjusted(2, 2, -2, -2) if index >= 0 and isValid(self.bar) else QRectF()

    def _move(self, rect):
        self.current = QRectF(rect)
        if isValid(self.bar):
            self.bar.update()

    def _select(self, index):
        target = self._rect(index)
        if target.isEmpty():
            return
        self.animation.stop()
        if (not self.manager.animations or self.manager.mode != "balanced"
                or self.current.isEmpty() or self.current == target):
            self.current = target
            self.bar.update()
            return
        self.animation.setDuration(self._animation_duration)
        self.animation.setStartValue(self.current)
        self.animation.setEndValue(target)
        self.animation.start()

    def _retarget(self, target):
        """Keep the visible lens continuous when tab geometry changes mid-flight."""
        if target.isEmpty() or target == self.animation.endValue():
            return
        remaining = max(60, self.animation.duration() - self.animation.currentTime())
        start = QRectF(self.current)
        bounds = QRectF(self.bar.rect())
        if not bounds.isEmpty() and not start.isEmpty():
            width = min(start.width(), bounds.width())
            height = min(start.height(), bounds.height())
            left = min(max(start.left(), bounds.left()), bounds.right() - width)
            top = min(max(start.top(), bounds.top()), bounds.bottom() - height)
            start = QRectF(left, top, width, height)
        self.animation.stop()
        self.current = start
        self.animation.setDuration(remaining)
        self.animation.setStartValue(start)
        self.animation.setEndValue(target)
        self.animation.start()

    def reset(self):
        self.animation.stop()
        self.current = self._rect(self.bar.currentIndex())
        self.bar.update()

    def _sync_geometry(self):
        if not isValid(self.bar):
            return
        target = self._rect(self.bar.currentIndex())
        if self.animation.state() == QVariantAnimation.Running:
            self._retarget(target)
        else:
            self.current = target
            self.bar.update()

    def _fill_tab_row(self):
        if self.tab_widget is None or not isValid(self.tab_widget) or not isValid(self.bar):
            return
        corner = self.tab_widget.cornerWidget()
        right = self.tab_widget.width()
        if corner is not None and corner.isVisible():
            right = corner.mapTo(self.tab_widget, QPoint()).x() - 4
        geometry = self.bar.geometry()
        width = max(1, right - geometry.left())
        if geometry.width() != width:
            self.bar.setGeometry(geometry.x(), geometry.y(), width, geometry.height())

    def eventFilter(self, watched, event):
        kind = event.type()
        if not isValid(self.bar):
            if isValid(self.animation):
                self.animation.stop()
            return False
        if watched is self.tab_widget:
            if kind in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
                self._layout_timer.start(0)
            return False
        if self.manager.mode == "solid":
            return False
        if kind == QEvent.Paint:
            self._paint()
            return True
        if kind in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            # Selecting a tab can trigger a layout request as font weights and
            # widths change. Retarget the in-flight lens instead of cancelling
            # it, otherwise Qt snaps the pill immediately to the new tab.
            if self.animation.state() == QVariantAnimation.Running:
                target = self._rect(self.bar.currentIndex())
                self._retarget(target)
            else:
                self.reset()
            # Qt recalculates tabRect after the resize event filter returns.
            self._geometry_timer.start(0)
        elif kind == QEvent.MouseMove:
            self.pointer = event.position()
            self.hover = True
            self.hover_index = self.bar.tabAt(event.position().toPoint())
            self.bar.update()
        elif kind == QEvent.Enter:
            self.pointer = QPointF(self.bar.mapFromGlobal(QCursor.pos()))
            self.hover = True
            self.hover_index = self.bar.tabAt(self.pointer.toPoint())
            self.bar.update()
        elif kind in (QEvent.Leave, QEvent.Hide):
            self.hover = False
            self.hover_index = -1
            self.bar.update()
        elif kind in (QEvent.FocusIn, QEvent.FocusOut):
            self.bar.update()
        return False

    def _paint(self):
        bar = self.bar
        painter = QStylePainter(bar)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(bar.rect()).adjusted(.5, 1, -.5, -1)
        painter.setPen(QPen(_tone("surface", 198), 1))
        painter.setBrush(_tone("surface", 72))
        radius = min(bounds.height() / 2, 20)
        painter.drawRoundedRect(bounds, radius, radius)
        painter.setPen(QPen(_tone("border_control", 65), .8))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bounds.adjusted(1.2, 1.2, -1.2, -1.2), max(1, radius - 1), max(1, radius - 1))
        if not self.animation.state() == QVariantAnimation.Running:
            self.current = self._rect(bar.currentIndex())
        if not self.current.isEmpty():
            lens = QRectF(self.current)
            painter.setPen(QPen(_tone("surface", 238), 1.1))
            painter.setBrush(_tone("primary", 76))
            lens_radius = min(lens.height() / 2, 18)
            painter.drawRoundedRect(lens, lens_radius, lens_radius)
            painter.setPen(QPen(_tone("primary", 62), .8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(lens.adjusted(1.3, 1.3, -1.3, -1.3), max(1, lens_radius - 1), max(1, lens_radius - 1))
            if self.hover:
                painter.save()
                shape = QPainterPath()
                shape.addRoundedRect(lens.adjusted(1, 1, -1, -1), max(1, lens_radius - 1), max(1, lens_radius - 1))
                painter.setClipPath(shape)
                glow = QRadialGradient(self.pointer, max(35, lens.width() * .8))
                glow.setColorAt(0, _tone("surface", 105))
                glow.setColorAt(.55, _tone("surface", 42))
                glow.setColorAt(1, _tone("surface", 0))
                painter.fillPath(shape, glow)
                painter.restore()
        if self.hover and self.hover_index >= 0 and self.hover_index != bar.currentIndex():
            hover_rect = self._rect(self.hover_index)
            if not hover_rect.isEmpty():
                shape = QPainterPath()
                hover_radius = min(hover_rect.height() / 2, 18)
                shape.addRoundedRect(hover_rect, hover_radius, hover_radius)
                painter.save()
                painter.setClipPath(shape)
                painter.fillPath(shape, _tone("text_secondary", 30))
                glow = QRadialGradient(self.pointer, max(35, hover_rect.width() * .8))
                glow.setColorAt(0, _tone("surface", 92))
                glow.setColorAt(.55, _tone("surface", 28))
                glow.setColorAt(1, _tone("surface", 0))
                painter.fillPath(shape, glow)
                painter.setPen(QPen(_tone("surface", 132), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(shape)
                painter.restore()
        if bar.hasFocus() and not self.current.isEmpty():
            focus = self.current.adjusted(1.5, 1.5, -1.5, -1.5)
            painter.setPen(QPen(_tone("focus", 210), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(focus, 6, 6)
        for index in range(bar.count()):
            option = QStyleOptionTab()
            bar.initStyleOption(option, index)
            painter.drawControl(QStyle.CE_TabBarTabLabel, option)
