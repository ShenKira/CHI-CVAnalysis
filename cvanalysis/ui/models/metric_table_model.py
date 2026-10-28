# -*- coding: utf-8 -*-
"""Generic read-only table model used by analysis result views."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor


class MetricTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.headers = headers or []
        self.rows: list[list[Any]] = []
        self.colors: dict[tuple[int, int], str] = {}

    def set_data(self, headers: list[str], rows: list[list[Any]], colors: dict[tuple[int, int], str] | None = None) -> None:
        self.beginResetModel()
        self.headers = headers
        self.rows = rows
        self.colors = colors or {}
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        if index.column() >= len(row):
            return None
        if role == Qt.DisplayRole:
            value = row[index.column()]
            return "" if value is None else str(value)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            value = row[index.column()]
            return "" if value is None else str(value)
        if role == Qt.ForegroundRole:
            color = self.colors.get((index.row(), index.column()))
            if color:
                return QColor(color)
        return None

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and section < len(self.headers):
            return self.headers[section]
        return None
