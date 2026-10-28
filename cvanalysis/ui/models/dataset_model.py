# -*- coding: utf-8 -*-
"""Tree model for CV/EIS/CP runs and CV cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QAbstractItemModel, QMimeData, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from cvanalysis.analysis.cp import CPRunSummary
from cvanalysis.analysis.cv import CVRunSummary
from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.domain.models import CPRun, CVRun, Dataset, EISRun, abbreviate_name
from cvanalysis.domain.units import (
    AREAL_CAPACITANCE,
    CAPACITANCE,
    CURRENT,
    IMPEDANCE,
    SPECIFIC_CAPACITANCE,
    format_with_unit,
)


COLUMNS = [
    "名称",
    "扫速 / 高频 / 电流",
    "窗口 / 频率",
    "循环 / 点数",
    "平均电容 / Rs / 放电容量",
    "单位面积 / Rct / 比容量",
    "质量比 / Cdl / 保持段",
    "状态",
]


@dataclass(eq=False)
class TreeNode:
    kind: str
    label: str = ""
    parent: "TreeNode | None" = None
    children: list["TreeNode"] = field(default_factory=list)
    run: CVRun | EISRun | None = None
    cycle_index: int | None = None
    checked: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def row(self) -> int:
        if self.parent is None:
            return 0
        for index, child in enumerate(self.parent.children):
            if child is self:
                return index
        return -1


def _status_for_run(run: CVRun | EISRun) -> str:
    if isinstance(run, CVRun):
        summary = run.summary
        if isinstance(summary, CVRunSummary):
            if summary.valid_cycles == 0:
                return "无有效循环"
            if summary.outlier_cycles:
                return f"有效 {summary.valid_cycles}，统计排除 {len(summary.outlier_cycles)}"
            if summary.excluded_cycles:
                return f"有效 {summary.valid_cycles}，排除 {summary.excluded_cycles}"
            return "正常"
        return "未分析"
    if isinstance(run, EISRun):
        metrics = run.summary
        if isinstance(metrics, EISMetrics):
            return "拟合" if metrics.method == "equivalent-circuit-fit" else "正常"
        return "未分析"
    if isinstance(run, CPRun):
        summary = run.summary
        if isinstance(summary, CPRunSummary):
            if summary.cycle_count == 0:
                return "无完整 GCD 循环"
            return f"正常（{summary.cycle_count} 循环）"
        return "未分析"
    return ""


class DatasetTreeModel(QAbstractItemModel):
    selection_changed = Signal()
    order_changed = Signal()
    RUN_MIME_TYPE = "application/x-cvanalysis-runs"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = TreeNode("root")
        self._nodes: dict[str, TreeNode] = {}
        self.visible_runs: dict[str, bool] = {}
        self.cycle_selection: dict[str, list[int]] = {}
        self.dataset = Dataset()
        self._drag_id = uuid4().hex

    # -- Qt model API ----------------------------------------------------
    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        parent_node = self._node(parent)
        if not parent_node or row < 0 or row >= len(parent_node.children) or column < 0 or column >= len(COLUMNS):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        node = self._node(index)
        if node is None or node.parent is None or node.parent is self.root:
            return QModelIndex()
        return self.createIndex(node.parent.row(), 0, node.parent)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._node(parent).children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(COLUMNS):
            return COLUMNS[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        node = self._node(index)
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if node and node.kind in {"run", "cycle", "group"}:
            flags |= Qt.ItemIsUserCheckable
        if node and node.kind == "run":
            flags |= Qt.ItemIsDragEnabled
        elif node and node.kind == "group":
            flags |= Qt.ItemIsDropEnabled
        return flags

    def supportedDropActions(self):
        return Qt.MoveAction

    def supportedDragActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [self.RUN_MIME_TYPE]

    def mimeData(self, indexes):
        selected = {
            node.run.run_id
            for index in indexes
            if index.isValid() and (node := self._node(index)).kind == "run" and node.run
        }
        mime = QMimeData()
        if selected:
            ids = [run.run_id for run in self.dataset.all_runs() if run.run_id in selected]
            payload = json.dumps({"model": self._drag_id, "runs": ids}).encode("utf-8")
            mime.setData(self.RUN_MIME_TYPE, payload)
        return mime

    def _drop_runs(self, data, action, row, column, parent):
        group = self._node(parent)
        if action != Qt.MoveAction or column > 0 or not group or group.kind != "group":
            return None
        if row < -1 or row > len(group.children) or not data.hasFormat(self.RUN_MIME_TYPE):
            return None
        try:
            payload = json.loads(bytes(data.data(self.RUN_MIME_TYPE)))
            ids = payload["runs"]
            if payload["model"] != self._drag_id or not isinstance(ids, list) or not ids:
                return None
            nodes = [self._nodes[run_id] for run_id in ids]
        except (ValueError, KeyError, TypeError):
            return None
        if any(node.parent is not group for node in nodes):
            return None
        return group, set(ids)

    def canDropMimeData(self, data, action, row, column, parent):
        return self._drop_runs(data, action, row, column, parent) is not None

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.IgnoreAction:
            return True
        target = self._drop_runs(data, action, row, column, parent)
        if target is None:
            return False
        group, selected = target
        old = group.children
        row = len(old) if row == -1 else row
        moving = [node for node in old if node.run.run_id in selected]
        remaining = [node for node in old if node.run.run_id not in selected]
        insertion = row - sum(node.run.run_id in selected for node in old[:row])
        reordered = remaining[:insertion] + moving + remaining[insertion:]
        if reordered == old:
            return False

        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        group.children = reordered
        runs = [node.run for node in reordered]
        if isinstance(runs[0], CVRun):
            self.dataset.cv_runs[:] = runs
        elif isinstance(runs[0], EISRun):
            self.dataset.eis_runs[:] = runs
        else:
            self.dataset.cp_runs[:] = runs
        self.changePersistentIndexList(
            persistent,
            [self.createIndex(self._node(index).row(), index.column(), self._node(index)) for index in persistent],
        )
        self.layoutChanged.emit()
        self.order_changed.emit()
        return True

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._node(index)
        if node is None:
            return None
        column = index.column()
        if role == Qt.CheckStateRole and column == 0 and node.kind in {"run", "cycle", "group"}:
            return Qt.Checked if node.checked else Qt.Unchecked
        if role == Qt.DisplayRole:
            return self._display(node, column)
        if role == Qt.ToolTipRole:
            return self._tooltip(node)
        if role == Qt.FontRole and node.kind == "group":
            font = QApplication.font()
            font.setBold(True)
            return font
        if role == Qt.ForegroundRole and node.kind == "cycle" and node.extra.get("invalid"):
            return QColor("#a33")
        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.CheckStateRole or index.column() != 0:
            return False
        node = self._node(index)
        if node is None or node.kind not in {"run", "cycle", "group"}:
            return False
        checked = value == Qt.Checked or value == 2
        if node.kind == "group":
            for child in node.children:
                self._set_node_checked(child, checked)
        else:
            self._set_node_checked(node, checked)
        self.selection_changed.emit()
        return True

    # -- model helpers ---------------------------------------------------
    def _node(self, index: QModelIndex) -> TreeNode | None:
        if not index.isValid():
            return self.root
        return index.internalPointer()

    def _set_node_checked(self, node: TreeNode, checked: bool) -> None:
        node.checked = checked
        if node.kind == "run" and isinstance(node.run, CVRun):
            self.visible_runs[node.run.run_id] = checked
            for child in node.children:
                child.checked = checked
            self.cycle_selection[node.run.run_id] = [child.cycle_index for child in node.children if checked]
            if len(self.cycle_selection[node.run.run_id]) == len(node.children):
                self.cycle_selection.pop(node.run.run_id, None)
        elif node.kind in {"run", "cycle"} and isinstance(node.run, (EISRun, CPRun)):
            self.visible_runs[node.run.run_id] = checked
        elif node.kind == "cycle" and node.parent and isinstance(node.parent.run, CVRun):
            run_id = node.parent.run.run_id
            node.checked = checked
            selected = [child.cycle_index for child in node.parent.children if child.checked]
            self.cycle_selection[run_id] = selected
            if len(selected) == len(node.parent.children):
                self.cycle_selection.pop(run_id, None)
            node.parent.checked = bool(selected)
            # Keep the run visible; an empty cycle selection means "no cycles".
            self.visible_runs[run_id] = True
        if node.kind in {"run", "cycle"}:
            parent = node.parent
            if parent and parent.kind == "group":
                parent.checked = any(child.checked for child in parent.children)
        self._emit_subtree_changed(node)

    def _emit_subtree_changed(self, node: TreeNode) -> None:
        parent_index = self.index_for_node(node.parent) if node.parent else QModelIndex()
        if node.parent:
            row = node.row()
            top_left = self.index(row, 0, parent_index)
            bottom_right = self.index(row, len(COLUMNS) - 1, parent_index)
            self.dataChanged.emit(top_left, bottom_right)
        if node.children:
            first = self.index(0, 0, self.index_for_node(node))
            last = self.index(len(node.children) - 1, len(COLUMNS) - 1, self.index_for_node(node))
            self.dataChanged.emit(first, last)

    def index_for_node(self, node: TreeNode | None) -> QModelIndex:
        if node is None or node is self.root:
            return QModelIndex()
        return self.createIndex(node.row(), 0, node)

    def index_for_run(self, run_id: str) -> QModelIndex:
        node = self._nodes.get(run_id)
        return self.index_for_node(node) if node else QModelIndex()

    def run_ids_for_index(self, index: QModelIndex) -> list[str]:
        node = self._node(index)
        if node is None:
            return []
        if node.kind == "run" and node.run:
            return [node.run.run_id]
        if node.kind == "cycle" and node.parent and node.parent.run:
            return [node.parent.run.run_id]
        if node.kind == "group":
            return [child.run.run_id for child in node.children if child.run]
        return []

    def visible_run_ids(self, kind: str | None = None) -> list[str]:
        result = []
        for run in self.dataset.all_runs():
            if kind == "cv" and not isinstance(run, CVRun):
                continue
            if kind == "eis" and not isinstance(run, EISRun):
                continue
            if kind == "cp" and not isinstance(run, CPRun):
                continue
            if self.visible_runs.get(run.run_id, True):
                result.append(run.run_id)
        return result

    def selected_cycle_indices(self, run_id: str) -> list[int] | None:
        if run_id in self.cycle_selection:
            return list(self.cycle_selection[run_id])
        return None

    # -- rebuild ---------------------------------------------------------
    def set_dataset(self, dataset: Dataset, visible_runs: dict[str, bool] | None = None,
                    cycle_selection: dict[str, list[int]] | None = None) -> None:
        self.beginResetModel()
        self.dataset = dataset
        self.visible_runs = dict(visible_runs or {})
        self.cycle_selection = {key: list(value) for key, value in (cycle_selection or {}).items()}
        self.root = TreeNode("root")
        self._nodes = {}
        self._short_labels = {}
        used_labels: set[str] = set()
        for run in dataset.all_runs():
            base = abbreviate_name(run.display_name, 30)
            candidate = base
            duplicate = 2
            while candidate in used_labels:
                candidate = f"{abbreviate_name(run.display_name, 26)} #{duplicate}"
                duplicate += 1
            used_labels.add(candidate)
            self._short_labels[run.run_id] = candidate
        if dataset.cv_runs:
            cv_group = TreeNode("group", "CV 数据", self.root, checked=True)
            self.root.children.append(cv_group)
            for run in dataset.cv_runs:
                self._add_cv_run(cv_group, run)
            cv_group.checked = any(child.checked for child in cv_group.children)
        if dataset.eis_runs:
            eis_group = TreeNode("group", "EIS 数据", self.root, checked=True)
            self.root.children.append(eis_group)
            for run in dataset.eis_runs:
                self._add_eis_run(eis_group, run)
            eis_group.checked = any(child.checked for child in eis_group.children)
        if dataset.cp_runs:
            cp_group = TreeNode("group", "CP / GCD 数据", self.root, checked=True)
            self.root.children.append(cp_group)
            for run in dataset.cp_runs:
                self._add_cp_run(cp_group, run)
            cp_group.checked = any(child.checked for child in cp_group.children)
        self.endResetModel()
        self.selection_changed.emit()

    def _add_cv_run(self, parent: TreeNode, run: CVRun) -> None:
        visible = self.visible_runs.get(run.run_id, True)
        node = TreeNode("run", self._short_labels.get(run.run_id, run.display_short_name), parent, run=run, checked=visible)
        parent.children.append(node)
        self._nodes[run.run_id] = node
        selected = self.cycle_selection.get(run.run_id)
        for cycle in run.cycles:
            checked = visible and (selected is None or cycle.index in selected)
            child = TreeNode(
                "cycle",
                f"Cycle {cycle.index}",
                node,
                run=run,
                cycle_index=cycle.index,
                checked=checked,
                extra={"invalid": not cycle.valid},
            )
            node.children.append(child)

    def _add_eis_run(self, parent: TreeNode, run: EISRun) -> None:
        visible = self.visible_runs.get(run.run_id, True)
        node = TreeNode("run", self._short_labels.get(run.run_id, run.display_short_name), parent, run=run, checked=visible)
        parent.children.append(node)
        self._nodes[run.run_id] = node

    def _add_cp_run(self, parent: TreeNode, run: CPRun) -> None:
        visible = self.visible_runs.get(run.run_id, True)
        node = TreeNode("run", self._short_labels.get(run.run_id, run.display_short_name), parent, run=run, checked=visible)
        parent.children.append(node)
        self._nodes[run.run_id] = node

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    # -- display ---------------------------------------------------------
    def _display(self, node: TreeNode, column: int) -> str:
        if column == 0:
            return node.label
        if node.kind == "group":
            if column == 3:
                return f"{len(node.children)} 个数据"
            return ""
        if node.kind == "run" and node.run is not None:
            return self._run_column(node.run, column)
        if node.kind == "cycle" and isinstance(node.run, CVRun) and node.cycle_index is not None:
            cycle = next((item for item in node.run.cycles if item.index == node.cycle_index), None)
            if cycle is None:
                return ""
            if column == 2:
                return f"{cycle.voltage_window:.3g} V"
            if column == 4:
                return format_with_unit(cycle.capacitance_F, CAPACITANCE, digits=4)
            if column == 5:
                return f"{cycle.integral_area_A_V:.3e} A·V"
            if column == 7:
                return cycle.outlier_reason or cycle.warning or ("有效" if cycle.valid else "无效")
        return ""

    def _run_column(self, run: CVRun | EISRun | CPRun, column: int) -> str:
        if isinstance(run, CVRun):
            summary = run.summary if isinstance(run.summary, CVRunSummary) else None
            if column == 1:
                return f"{run.scan_rate:g} V/s" if run.scan_rate else "—"
            if column == 2:
                return f"{run.voltage_window:.3g} V" if run.voltage_window else "—"
            if column == 3:
                return f"{len(run.cycles)} 循环"
            if column == 4:
                return format_with_unit(summary.mean_capacitance_F if summary else None, CAPACITANCE, digits=4)
            if column == 5:
                if summary and summary.mean_cap_per_area:
                    return format_with_unit(summary.mean_cap_per_area, AREAL_CAPACITANCE, digits=4)
                return "—"
            if column == 6:
                if summary and summary.mean_cap_per_mass:
                    return format_with_unit(summary.mean_cap_per_mass, SPECIFIC_CAPACITANCE, digits=4)
                return "—"
            if column == 7:
                return _status_for_run(run)
        elif isinstance(run, EISRun):
            metrics = run.summary if isinstance(run.summary, EISMetrics) else None
            if column == 1:
                return f"{run.metadata.high_freq:.3g} Hz" if run.metadata.high_freq else "—"
            if column == 2:
                return f"{run.metadata.low_freq:.3g}–{run.metadata.high_freq:.3g} Hz" if run.metadata.low_freq and run.metadata.high_freq else "—"
            if column == 3:
                return f"{len(run.freq)} 点"
            if column == 4:
                return format_with_unit(metrics.rs_ohm if metrics else None, IMPEDANCE, digits=4)
            if column == 5:
                return format_with_unit(metrics.rct_ohm if metrics else None, IMPEDANCE, digits=4)
            if column == 6:
                return format_with_unit(metrics.cdl_F if metrics else None, CAPACITANCE, digits=4)
            if column == 7:
                return _status_for_run(run)
        elif isinstance(run, CPRun):
            summary = run.summary if isinstance(run.summary, CPRunSummary) else None
            if column == 1:
                return format_with_unit(run.applied_current_A, CURRENT, digits=3)
            if column == 2:
                return f"{run.voltage_window:.3g} V" if run.voltage_window else "—"
            if column == 3:
                return f"{summary.cycle_count} 循环" if summary else "—"
            if column == 4:
                if summary and np.isfinite(summary.mean_discharge_capacity_C):
                    return f"{summary.mean_discharge_capacity_C / 3.6:.4g} mAh"
                return "—"
            if column == 5:
                if summary and np.isfinite(summary.mean_specific_capacity_mAh_g):
                    return f"{summary.mean_specific_capacity_mAh_g:.4g} mAh/g"
                return "—"
            if column == 6:
                return "已记录" if summary and summary.has_hold_data else "无"
            if column == 7:
                return _status_for_run(run)
        return ""

    def _tooltip(self, node: TreeNode) -> str:
        if node.run is None:
            return ""
        run = node.run
        lines = [run.display_name]
        if run.source:
            lines.append(str(run.source))
        if run.legend_template:
            lines.append(f"图例模板: {run.legend_template}")
        if isinstance(run, CVRun):
            lines.append(
                f"扫速 {run.scan_rate:g} V/s · 窗口 {run.voltage_window:g} V · {len(run.cycles)} 循环"
                if run.scan_rate and run.voltage_window
                else f"{len(run.cycles)} 循环"
            )
        elif isinstance(run, EISRun):
            lines.append(
                f"{run.metadata.low_freq:.3g}–{run.metadata.high_freq:.3g} Hz · {len(run.freq)} 点"
                if run.metadata.low_freq and run.metadata.high_freq
                else f"{len(run.freq)} 点"
            )
        else:
            current = format_with_unit(run.applied_current_A, CURRENT, digits=3)
            hold = "含保持段电流" if run.has_hold_data else "无保持段电流"
            lines.append(f"CP · 电流 {current} · 窗口 {run.voltage_window or 0:.3g} V · {hold}")
        if isinstance(run, CVRun) and isinstance(run.summary, CVRunSummary):
            lines.extend(run.summary.warnings)
        if isinstance(run, EISRun) and isinstance(run.summary, EISMetrics):
            lines.extend(run.summary.warnings)
        if isinstance(run, CPRun) and isinstance(run.summary, CPRunSummary):
            lines.extend(run.summary.warnings)
        return "\n".join(lines)
