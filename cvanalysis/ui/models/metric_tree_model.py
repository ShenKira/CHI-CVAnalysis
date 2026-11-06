# -*- coding: utf-8 -*-
"""Read-only tree model used by the analysis result views.

The result tables show one parent row per run.  CV and CP runs may expose one
child row per analysed cycle.  ``MetricTableModel`` remains as a
backward-compatible name for callers that only need the original flat table
API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication


@dataclass(eq=False)
class _MetricNode:
    values: list[Any]
    parent: "_MetricNode | None" = None
    children: list["_MetricNode"] = field(default_factory=list)
    row: int = 0
    run_id: str | None = None
    colors: dict[int, str] = field(default_factory=dict)
    bold: bool = False


class MetricTreeModel(QAbstractItemModel):
    """Two-level result model with an optional flat-table compatibility mode."""

    def __init__(self, headers: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.headers = list(headers or [])
        self.rows: list[list[Any]] = []
        self.colors: dict[tuple[int, int], str] = {}
        self._root = _MetricNode([])
        self._run_nodes: dict[str, _MetricNode] = {}

    # -- data API --------------------------------------------------------
    def set_data(
        self,
        headers: list[str],
        rows: list[list[Any]],
        colors: dict[tuple[int, int], str] | None = None,
    ) -> None:
        """Set a flat table.

        This is the original ``MetricTableModel`` API used by callers that do
        not need per-cycle children.
        """
        self.set_tree_data(headers, rows, None, colors=colors)

    def set_tree_data(
        self,
        headers: list[str],
        rows: list[list[Any]],
        children: list[list[list[Any]]] | None = None,
        *,
        colors: dict[tuple[int, int], str] | None = None,
        child_colors: dict[tuple[int, int, int], str] | None = None,
        run_ids: Iterable[str | None] | None = None,
    ) -> None:
        """Reset the model with parent rows and optional per-run child rows."""
        row_ids = list(run_ids) if run_ids is not None else []
        parent_colors = colors or {}
        nested_colors = child_colors or {}
        child_rows = children or []

        self.beginResetModel()
        self.headers = list(headers)
        self.rows = rows
        self.colors = parent_colors
        self._root = _MetricNode([])
        self._run_nodes = {}
        for row_index, values in enumerate(rows):
            run_id = row_ids[row_index] if row_index < len(row_ids) else None
            node = _MetricNode(
                list(values),
                parent=self._root,
                row=row_index,
                run_id=run_id,
                colors={
                    column: color
                    for (parent_row, column), color in parent_colors.items()
                    if parent_row == row_index
                },
                bold=True,
            )
            run_children = child_rows[row_index] if row_index < len(child_rows) else []
            for child_index, child_values in enumerate(run_children):
                child = _MetricNode(
                    list(child_values),
                    parent=node,
                    row=child_index,
                    colors={
                        column: color
                        for (parent_row, child_row, column), color in nested_colors.items()
                        if parent_row == row_index and child_row == child_index
                    },
                )
                node.children.append(child)
            self._root.children.append(node)
            if run_id is not None:
                self._run_nodes[run_id] = node
        self.endResetModel()

    # -- Qt model API ----------------------------------------------------
    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        parent_node = self._node(parent)
        if (
            parent_node is None
            or (parent.isValid() and parent.column() != 0)
            or row < 0
            or row >= len(parent_node.children)
            or column < 0
            or column >= len(self.headers)
        ):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if node is None or node.parent is None or node.parent is self._root:
            return QModelIndex()
        return self.createIndex(node.parent.row, 0, node.parent)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self._node(parent).children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if node is None or index.column() >= len(node.values):
            return None
        if role == Qt.DisplayRole:
            value = node.values[index.column()]
            return "" if value is None else str(value)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            value = node.values[index.column()]
            return "" if value is None else str(value)
        if role == Qt.ForegroundRole:
            color = node.colors.get(index.column())
            if color:
                return QColor(color)
        if role == Qt.FontRole and node.bold:
            font = QApplication.font()
            font.setBold(True)
            return font
        return None

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if (
            orientation == Qt.Horizontal
            and role == Qt.DisplayRole
            and 0 <= section < len(self.headers)
        ):
            return self.headers[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # -- helpers ---------------------------------------------------------
    def _node(self, index: QModelIndex) -> _MetricNode:
        if not index.isValid():
            return self._root
        return index.internalPointer() or self._root

    def index_for_run(self, run_id: str) -> QModelIndex:
        node = self._run_nodes.get(run_id)
        if node is None:
            return QModelIndex()
        return self.createIndex(node.row, 0, node)

    def run_id_for_index(self, index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        node = index.internalPointer()
        if node is None:
            return None
        if node.run_id is not None:
            return node.run_id
        if node.parent is not None:
            return node.parent.run_id
        return None

    def run_ids(self) -> list[str]:
        return [node.run_id for node in self._root.children if node.run_id is not None]


# Keep the original class name importable for existing callers.
MetricTableModel = MetricTreeModel

__all__ = ["MetricTableModel", "MetricTreeModel"]
