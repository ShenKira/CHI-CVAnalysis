"""Content-sized starting widths without taking control away from the user."""

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableView


class ViewColumns(QObject):
    """Keep every column draggable; fit once and preserve subsequent adjustments."""

    def __init__(self, view, *, first_width=230, maximum_fit_width=320):
        super().__init__(view)
        self.view = view
        self.header = view.horizontalHeader() if isinstance(view, QTableView) else view.header()
        self.first_width = first_width
        self.maximum_fit_width = maximum_fit_width
        self._initialized = False
        view.setTextElideMode(Qt.ElideRight)
        view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.header.setMinimumSectionSize(56)
        self.header.setStretchLastSection(False)
        self.header.setSectionResizeMode(QHeaderView.Interactive)
        self.header.setResizeContentsPrecision(100)
        self.header.setToolTip("拖动列边界调整宽度；双击自动适配；右键可适配全部列。")
        self.header.sectionHandleDoubleClicked.connect(self.fit_column)
        self.header.setContextMenuPolicy(Qt.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self._show_menu)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self.fit_initial)
        view.model().modelReset.connect(lambda: self._fit_timer.start(0))
        # Resizing before the first data arrives is also a deliberate preference.
        self.header.sectionResized.connect(self._on_resized)
        self.reset()

    def _on_resized(self, *args):
        self._initialized = True

    def fit_initial(self):
        if not self._initialized and self.view.model().rowCount():
            self.fit_all()
            # A long filename should not consume the entire results panel on first load.
            self.header.resizeSection(0, self.first_width)

    def fit_column(self, column):
        if column < 0:
            return
        self.view.resizeColumnToContents(column)
        width = self.header.sectionSize(column)
        if column == 0:
            width = max(width, self.first_width)
        self.header.resizeSection(column, min(self.maximum_fit_width, width))

    def fit_all(self):
        for column in range(self.header.count()):
            self.fit_column(column)
        self._initialized = True

    def reset(self):
        for column in range(self.header.count()):
            self.header.resizeSection(column, self.first_width if column == 0 else 110)
        self._initialized = False
        self.fit_initial()

    def widths(self):
        # Header names keep saved widths attached to the same metric after schema changes.
        model = self.view.model()
        return {
            str(model.headerData(column, Qt.Horizontal)): self.header.sectionSize(column)
            for column in range(self.header.count())
        }

    def restore(self, widths):
        if not isinstance(widths, dict):
            return
        model = self.view.model()
        for column in range(self.header.count()):
            value = widths.get(str(model.headerData(column, Qt.Horizontal)))
            if isinstance(value, int) and not isinstance(value, bool) and 56 <= value <= 4096:
                self.header.resizeSection(column, value)
                self._initialized = True

    def _show_menu(self, position):
        menu = QMenu(self.view)
        column = self.header.logicalIndexAt(position)
        fit = menu.addAction("自动适配此列")
        fit.setEnabled(column >= 0)
        fit.triggered.connect(lambda: self.fit_column(column))
        menu.addAction("自动适配全部列", self.fit_all)
        menu.exec(self.header.mapToGlobal(position))
