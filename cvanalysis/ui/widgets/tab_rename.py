"""Inline renaming for plot-document tabs."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QLineEdit, QMenu, QTabBar, QToolButton
from shiboken6 import isValid

from cvanalysis.ui.glass.popups import wrap_menu
from cvanalysis.ui.widgets.plot_tab import PlotTab


class PlotTabRenamer(QObject):
    """Keep edits attached to the plot object while the tab bar changes."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.tabs = window.tabs
        self.bar = self.tabs.tabBar()
        self.editor = None
        self.plot = None
        self._initial_text = ""
        self._initial_name = ""
        self.bar.installEventFilter(self)
        self.tabs.tabBarDoubleClicked.connect(self.begin)
        self.bar.tabMoved.connect(self._schedule_position)
        self.bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bar.customContextMenuRequested.connect(self._show_menu)
        for button in self.bar.findChildren(QToolButton):
            button.installEventFilter(self)
            button.clicked.connect(self._schedule_position)

    def begin(self, index: int) -> None:
        plot = self.tabs.widget(index) if index >= 0 else None
        if not isinstance(plot, PlotTab):
            return
        self.finish(commit=True)
        self.plot = plot
        editor = QLineEdit(self.bar)
        self.editor = editor
        editor.setObjectName("plotTabNameEditor")
        editor.setAccessibleName("图标签名称")
        self._initial_name = plot.spec.tab_name
        self._initial_text = plot.spec.tab_name or self.window._plot_tab_title(plot.spec)
        editor.setText(self._initial_text)
        editor.installEventFilter(self)
        editor.returnPressed.connect(lambda: self.finish(commit=True))
        self._position()
        if self.editor is not editor:
            return
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.MouseFocusReason)
        editor.selectAll()

    def finish(self, *, commit: bool) -> None:
        editor, plot = self.editor, self.plot
        if editor is None:
            return
        self.editor = self.plot = None
        if commit and isValid(plot) and self.tabs.indexOf(plot) >= 0:
            name = editor.text().strip()
            # Leaving the proposed automatic text untouched keeps it dynamic.
            if not self._initial_name and name == self._initial_text:
                name = ""
            if name != plot.spec.tab_name:
                plot.spec.tab_name = name
                self.window._update_plot_tab_label(plot)
                self.window._mark_dirty()
        editor.removeEventFilter(self)
        editor.hide()
        editor.deleteLater()

    def cancel_for(self, plot=None) -> None:
        if plot is None or plot is self.plot:
            self.finish(commit=False)

    def _position(self) -> None:
        if self.editor is None or self.plot is None:
            return
        index = self.tabs.indexOf(self.plot)
        if index < 0:
            self.finish(commit=False)
            return
        rect = self.bar.tabRect(index).intersected(self.bar.rect())
        for side in (QTabBar.LeftSide, QTabBar.RightSide):
            button = self.bar.tabButton(index, side)
            if button is not None and button.isVisible():
                bounds = button.geometry()
                if bounds.center().x() < rect.center().x():
                    rect.setLeft(max(rect.left(), bounds.right() + 1))
                else:
                    rect.setRight(min(rect.right(), bounds.left() - 1))
        for button in self.bar.findChildren(QToolButton, options=Qt.FindDirectChildrenOnly):
            if button.isVisible() and rect.intersects(button.geometry()):
                bounds = button.geometry()
                if bounds.center().x() < rect.center().x():
                    rect.setLeft(max(rect.left(), bounds.right() + 1))
                else:
                    rect.setRight(min(rect.right(), bounds.left() - 1))
        if rect.width() <= 8 or rect.height() <= 4:
            self.finish(commit=True)
            return
        self.editor.setGeometry(rect.adjusted(2, 1, -2, -1))

    def _schedule_position(self, *_args) -> None:
        if self.editor is not None:
            QTimer.singleShot(0, self._position)

    def _show_menu(self, position) -> None:
        index = self.bar.tabAt(position)
        plot = self.tabs.widget(index) if index >= 0 else None
        if not isinstance(plot, PlotTab) or self._over_button(index, position):
            return
        self.finish(commit=True)
        source = QMenu(self.bar)
        rename = source.addAction("重命名")
        reset = source.addAction("恢复自动名称")
        reset.setEnabled(bool(plot.spec.tab_name))
        # QAction fires while the popup still owns focus. Start editing after
        # the menu closes so the line edit retains keyboard focus.
        rename.triggered.connect(
            lambda: QTimer.singleShot(0, lambda: self.begin(self.tabs.indexOf(plot)) if isValid(plot) else None)
        )

        def reset_name():
            if isValid(plot) and self.tabs.indexOf(plot) >= 0 and plot.spec.tab_name:
                plot.spec.tab_name = ""
                self.window._update_plot_tab_label(plot)
                self.window._mark_dirty()

        reset.triggered.connect(reset_name)
        menu = wrap_menu(source, self.bar, self.window.glass_manager)
        try:
            menu.exec(self.bar.mapToGlobal(position))
        finally:
            if isValid(menu):
                menu.deleteLater()
            if isValid(source):
                source.deleteLater()

    def _over_button(self, index, position) -> bool:
        buttons = [self.bar.tabButton(index, side) for side in (QTabBar.LeftSide, QTabBar.RightSide)]
        buttons.extend(self.bar.findChildren(QToolButton, options=Qt.FindDirectChildrenOnly))
        return any(button is not None and button.isVisible() and button.geometry().contains(position)
                   for button in buttons)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.editor:
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.finish(commit=False)
                return True
            if event.type() == QEvent.FocusOut:
                self.finish(commit=True)
        elif watched is self.bar and event.type() == QEvent.MouseButtonDblClick:
            index = self.bar.tabAt(event.position().toPoint())
            if index < 0 or self._over_button(index, event.position().toPoint()):
                return True
        elif event.type() in (QEvent.Resize, QEvent.Move, QEvent.Wheel, QEvent.Show, QEvent.Hide):
            self._schedule_position()
        return super().eventFilter(watched, event)
