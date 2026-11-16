# -*- coding: utf-8 -*-
"""Liquid Glass tooltips for the analysis panel.

Qt's native ``QToolTip`` is a flat popup.  The right-side "分析与参数" dock
uses this filter to draw a rounded glass tooltip while keeping the widget's
``toolTip`` text as the accessibility/fallback value.  Solid/high-contrast
fallbacks reuse the tooltip theme roles instead of transparent materials.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QHelpEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLabel,
    QTabBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.ui.glass.surfaces import effective_mode, rim
from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.tokens import BASE_FONT_SIZE, UiTokens


class LiquidTooltip(QWidget):
    """A top-level, mouse-transparent glass tooltip popup."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)

        self._manager = None
        self._radius = 6
        self._margin_x = 8
        self._margin_y = 6
        self._max_text_width = 360
        self._anchor: QWidget | None = None
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(90)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(9000)
        self._hide_timer.timeout.connect(self.hide_tooltip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._margin_x, self._margin_y, self._margin_x, self._margin_y
        )
        layout.setSpacing(0)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.label)

    def set_manager(self, manager) -> None:
        self._manager = manager

    @property
    def glass_mode(self) -> str:
        material = getattr(self._manager, "mode", "balanced")
        return effective_mode(material or "balanced")

    def _tokens(self) -> UiTokens:
        point_size = self.font().pointSizeF()
        if point_size <= 0:
            point_size = BASE_FONT_SIZE
        return UiTokens.from_scale(point_size / BASE_FONT_SIZE)

    def show_text(
        self,
        text: str,
        global_pos: QPoint,
        *,
        anchor: QWidget | None = None,
        font=None,
    ) -> None:
        text = str(text or "").strip()
        if not text:
            self.hide()
            return
        self._anchor = anchor
        self.setAccessibleDescription(text)
        if font is not None:
            self.setFont(font)
            self.label.setFont(font)
        tokens = self._tokens()
        self._radius = tokens.radius_md
        self._margin_x = max(tokens.space_sm, 8)
        self._margin_y = max(6, tokens.space_xs + 2)
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(
                self._margin_x, self._margin_y, self._margin_x, self._margin_y
            )
        self._max_text_width = max(220, min(420, tokens.scaled(360)))
        self.label.setText(text)
        metrics = self.label.fontMetrics()
        lines = text.splitlines() or [text]
        natural_width = max(
            metrics.horizontalAdvance(line) for line in lines
        )
        text_width = min(
            self._max_text_width,
            max(tokens.scaled(160), natural_width + 2),
        )
        self.label.setFixedWidth(text_width)
        label_height = self.label.heightForWidth(text_width)
        if label_height <= 0:
            label_height = self.label.sizeHint().height()
        self.label.setFixedHeight(max(1, label_height))
        palette = self.label.palette()
        palette.setColor(
            QPalette.WindowText, QColor(theme_color("tooltip_text"))
        )
        self.label.setPalette(palette)
        self.label.adjustSize()
        self.layout().activate()
        self.adjustSize()

        was_visible = self.isVisible()
        self._place(global_pos)
        animations = bool(
            getattr(self._manager, "animations", False)
        ) and self.glass_mode != "solid"
        if animations and not was_visible:
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:
            self._fade.stop()
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
        self._hide_timer.start()

    def _place(self, global_pos: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width = max(1, self.width())
        height = max(1, self.height())
        offset = QPoint(14, 18)
        x = global_pos.x() + offset.x()
        y = global_pos.y() + offset.y()
        if available is not None:
            if x + width > available.right():
                x = global_pos.x() - width - 12
            if y + height > available.bottom():
                y = global_pos.y() - height - 12
            x = min(max(x, available.left() + 4), max(available.left() + 4, available.right() - width - 4))
            y = min(max(y, available.top() + 4), max(available.top() + 4, available.bottom() - height - 4))
        self.move(x, y)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(self._radius, max(1.0, rect.height() / 2.0))
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        mode = self.glass_mode
        if mode == "solid":
            painter.fillPath(path, QColor(theme_color("tooltip_bg")))
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            top = QColor(theme_color("tooltip_bg"))
            top.setAlpha(242)
            bottom = QColor(theme_color("surface_alt"))
            bottom.setAlpha(228)
            gradient.setColorAt(0.0, top)
            gradient.setColorAt(1.0, bottom)
            painter.fillPath(path, gradient)
            rim(painter, rect, radius, glow=0.0, outer=False)

        border = QColor(theme_color("tooltip_border"))
        if mode != "solid":
            border.setAlpha(200)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)
        painter.end()

    def hide_tooltip(self) -> None:
        self._hide_timer.stop()
        self._fade.stop()
        self.hide()

    def hideEvent(self, event) -> None:
        self._anchor = None
        super().hideEvent(event)


class LiquidTooltipFilter(QObject):
    """Install a glass tooltip for a widget subtree (the analysis panel)."""

    def __init__(self, root: QWidget, manager=None, parent=None):
        super().__init__(parent if parent is not None else root)
        self.root = root
        self.manager = manager
        self.tooltip = LiquidTooltip(root.window())
        self.tooltip.set_manager(manager)
        self._watched: set[QWidget] = set()
        self._watch_tree(root)
        window = root.window()
        if window is not None and window is not root:
            window.installEventFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state)

    def _on_application_state(self, state) -> None:
        if state != Qt.ApplicationActive:
            self._hide()

    def _watch_tree(self, widget: QWidget) -> None:
        self._watch(widget)
        for child in widget.findChildren(QWidget):
            self._watch(child)

    def _watch(self, widget: QWidget | None) -> None:
        if widget is None or widget in self._watched:
            return
        self._watched.add(widget)
        widget.installEventFilter(self)
        if isinstance(widget, QComboBox):
            view = widget.view()
            self._watch(view)
            self._watch(view.viewport() if view is not None else None)

    def _is_inside_root(self, widget: QWidget) -> bool:
        if widget is self.root or self.root.isAncestorOf(widget):
            return True
        window = widget.window()
        if window is self.root:
            return True
        parent = window.parent()
        return parent is not None and (
            parent is self.root or self.root.isAncestorOf(parent)
        )

    def _tooltip_text(self, watched: QWidget, event) -> str:
        position = event.pos() if isinstance(event, QHelpEvent) else watched.rect().center()
        if isinstance(watched, QTabBar):
            index = watched.tabAt(position)
            if index >= 0:
                text = watched.tabToolTip(index)
                if text:
                    return str(text)
        view = watched if isinstance(watched, QAbstractItemView) else None
        if view is None:
            parent = watched.parent()
            if isinstance(parent, QAbstractItemView):
                view = parent
        if view is not None:
            index = view.indexAt(position)
            if index.isValid():
                text = index.data(Qt.ToolTipRole)
                if text:
                    return str(text)
        return str(watched.toolTip() or "")

    def _hide(self) -> None:
        self.tooltip.hide_tooltip()

    def eventFilter(self, watched, event) -> bool:
        if not isinstance(watched, QWidget):
            return False
        event_type = event.type()
        if event_type == QEvent.ChildAdded and watched in self._watched:
            child = event.child()
            if isinstance(child, QWidget):
                self._watch_tree(child)
            return False
        if event_type == QEvent.ToolTip:
            if not watched.isVisible() or not self._is_inside_root(watched):
                self._hide()
                return False
            text = self._tooltip_text(watched, event).strip()
            if not text:
                self._hide()
                return False
            if isinstance(event, QHelpEvent):
                position = event.globalPos()
            else:
                position = watched.mapToGlobal(watched.rect().center())
            QToolTip.hideText()
            self.tooltip.show_text(
                text,
                position,
                anchor=watched,
                font=self.root.font(),
            )
            return True
        if event_type in (QEvent.Move, QEvent.Resize):
            if self.tooltip._anchor is watched:
                self._hide()
            return False
        if event_type in (
            QEvent.Leave,
            QEvent.MouseButtonPress,
            QEvent.Wheel,
            QEvent.KeyPress,
            QEvent.Hide,
            QEvent.WindowDeactivate,
            QEvent.ApplicationDeactivate,
        ):
            anchor = self.tooltip._anchor
            if (
                event_type == QEvent.Leave
                and anchor is not None
                and watched is not anchor
            ):
                return False
            self._hide()
        return False


__all__ = ["LiquidTooltip", "LiquidTooltipFilter"]
