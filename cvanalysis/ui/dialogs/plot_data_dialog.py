# -*- coding: utf-8 -*-
"""Per-plot data and legend template selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.domain.models import CPRun, CVRun, Dataset, EISRun
from cvanalysis.plotting.legend import (
    dataset_file_numbers,
    preview_label,
    render_legend_template,
    template_uses_cycle,
)
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.dialogs.legend_dialog import build_token_combo, insert_token
from cvanalysis.ui.widgets.view_columns import ViewColumns


class PlotDataDialog(QDialog):
    """Choose the runs (and CV cycles) drawn by one plot tab."""

    def __init__(
        self,
        dataset: Dataset,
        spec: PlotSpec,
        kind: str,
        *,
        parent=None,
    ):
        super().__init__(parent)
        self.dataset = dataset
        self.spec = spec
        self.kind = (
            "cv" if kind.startswith("cv_") else "cp" if kind.startswith("cp_") else "eis"
        )
        self._updating = False
        self._run_items: dict[str, QTreeWidgetItem] = {}
        self._template_edits: dict[str, QLineEdit] = {}
        self.setWindowTitle("选择本图绘制数据与图例")
        self.resize(920, 600)
        self._build_ui()
        self._refresh_previews()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(
            "勾选本图要绘制的数据。CV 数据可展开选择 Cycle；"
            "“本图模板”留空表示继承数据默认模板。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["绘制数据", "本图图例模板（空=继承）", "预览"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.columns = ViewColumns(self.tree, first_width=260, maximum_fit_width=360)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)

        selection_row = QHBoxLayout()
        select_all = QPushButton("全部勾选")
        select_all.setProperty("secondary", True)
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        clear_all = QPushButton("全部取消")
        clear_all.setProperty("secondary", True)
        clear_all.clicked.connect(lambda: self._set_all_checked(False))
        self.selection_label = QLabel("")
        self.selection_label.setStyleSheet("color: #546e7a;")
        selection_row.addWidget(select_all)
        selection_row.addWidget(clear_all)
        selection_row.addStretch(1)
        selection_row.addWidget(self.selection_label)
        layout.addLayout(selection_row)

        batch_group = QWidget()
        batch_layout = QVBoxLayout(batch_group)
        batch_layout.setContentsMargins(0, 6, 0, 0)
        batch_layout.setSpacing(5)
        batch_layout.addWidget(QLabel("批量设置本图模板（应用到勾选的数据）:"))
        batch_row = QHBoxLayout()
        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText(self._placeholder())
        self.batch_edit.returnPressed.connect(self._apply_batch_template)
        self.token_combo = build_token_combo(self, self.kind)
        self.token_combo.currentIndexChanged.connect(self._insert_token)
        apply_btn = QPushButton("应用到勾选数据")
        apply_btn.setProperty("secondary", True)
        apply_btn.clicked.connect(self._apply_batch_template)
        inherit_btn = QPushButton("继承数据默认")
        inherit_btn.setProperty("secondary", True)
        inherit_btn.clicked.connect(self._inherit_defaults)
        batch_row.addWidget(self.batch_edit, 1)
        batch_row.addWidget(self.token_combo)
        batch_row.addWidget(apply_btn)
        batch_row.addWidget(inherit_btn)
        batch_layout.addLayout(batch_row)
        layout.addWidget(batch_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_runs()
        self.columns.fit_initial()

    def _placeholder(self) -> str:
        if self.kind == "cv":
            return "例如 {CV_Voltage}-{Cycle_Number}"
        if self.kind == "cp":
            return "例如 {File_Name}-{Current}"
        return "例如 {File_Name}-{Low_Freq}"

    def _runs(self) -> list[CVRun | EISRun | CPRun]:
        if self.kind == "cv":
            return list(self.dataset.cv_runs)
        if self.kind == "cp":
            return list(self.dataset.cp_runs)
        return list(self.dataset.eis_runs)

    def _populate_runs(self) -> None:
        self._updating = True
        try:
            selected = set(self.spec.run_ids)
            for run in self._runs():
                item = QTreeWidgetItem()
                item.setText(0, run.display_short_name)
                item.setToolTip(0, self._run_tooltip(run))
                item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                )
                item.setCheckState(0, Qt.Checked if run.run_id in selected else Qt.Unchecked)
                self.tree.addTopLevelItem(item)
                self._run_items[run.run_id] = item

                editor = QLineEdit()
                editor.setPlaceholderText(
                    self._inherited_placeholder(run)
                )
                if run.run_id in self.spec.legend_templates:
                    editor.setText(self.spec.legend_templates[run.run_id])
                editor.setToolTip(
                    "本图覆盖模板。留空则使用数据默认模板："
                    + (run.legend_template or "<默认文件名/Cycle>")
                )
                editor.textChanged.connect(
                    lambda text, run_id=run.run_id: self._on_template_text_changed(run_id)
                )
                self.tree.setItemWidget(item, 1, editor)
                self._template_edits[run.run_id] = editor

                if isinstance(run, CVRun):
                    chosen = self.spec.cycle_selection.get(run.run_id)
                    for cycle in run.cycles:
                        child = QTreeWidgetItem()
                        child.setText(0, f"Cycle {cycle.index}" + ("" if cycle.valid else "（无效）"))
                        child.setFlags(
                            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                        )
                        if not cycle.valid:
                            child.setForeground(0, QColor("#a33"))
                            child.setToolTip(0, cycle.outlier_reason or cycle.warning or "无效循环")
                        checked = chosen is None or cycle.index in chosen
                        child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                        item.addChild(child)
        finally:
            self._updating = False
        self._refresh_selection_label()

    @staticmethod
    def _run_tooltip(run: CVRun | EISRun | CPRun) -> str:
        lines = [run.display_name]
        if run.source:
            lines.append(str(run.source))
        if isinstance(run, CVRun):
            if run.scan_rate and run.voltage_window:
                lines.append(
                    f"扫速 {run.scan_rate:g} V/s · 窗口 {run.voltage_window:g} V · {len(run.cycles)} 循环"
                )
            else:
                lines.append(f"{len(run.cycles)} 循环")
        elif isinstance(run, EISRun):
            if run.metadata.low_freq and run.metadata.high_freq:
                lines.append(
                    f"{run.metadata.low_freq:.3g}–{run.metadata.high_freq:.3g} Hz · {len(run.freq)} 点"
                )
            else:
                lines.append(f"{len(run.freq)} 点")
        else:
            hold = "含保持段记录" if run.has_hold_data else "无保持段记录"
            lines.append(f"CP · {run.voltage_window or 0:.3g} V 窗口 · {hold}")
        if run.legend_template:
            lines.append(f"数据默认图例: {run.legend_template}")
        return "\n".join(lines)

    @staticmethod
    def _inherited_placeholder(run: CVRun | EISRun | CPRun) -> str:
        if run.legend_template:
            return f"继承：{run.legend_template}"
        return "继承默认"

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        self._updating = True
        try:
            if item.parent() is None:
                state = item.checkState(0)
                for index in range(item.childCount()):
                    item.child(index).setCheckState(0, state)
            else:
                parent = item.parent()
                checked = any(
                    parent.child(index).checkState(0) == Qt.Checked
                    for index in range(parent.childCount())
                )
                parent.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._updating = False
        self._refresh_selection_label()
        self._refresh_previews()

    def _on_template_text_changed(self, run_id: str) -> None:
        if not self._updating:
            self._refresh_previews()

    def _insert_token(self, index: int) -> None:
        token = self.token_combo.itemData(index)
        if token:
            insert_token(self.batch_edit, token)
            self.token_combo.blockSignals(True)
            self.token_combo.setCurrentIndex(0)
            self.token_combo.blockSignals(False)

    def _set_all_checked(self, checked: bool) -> None:
        self._updating = True
        try:
            for item in self._run_items.values():
                item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                for index in range(item.childCount()):
                    item.child(index).setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._updating = False
        self._refresh_selection_label()
        self._refresh_previews()

    def _checked_run_ids(self) -> list[str]:
        result = []
        for run in self._runs():
            item = self._run_items.get(run.run_id)
            if item is not None and item.checkState(0) == Qt.Checked:
                result.append(run.run_id)
        return result

    def _apply_batch_template(self) -> None:
        template = self.batch_edit.text().strip()
        for run_id in self._checked_run_ids():
            self._template_edits[run_id].setText(template)
        self._refresh_previews()

    def _inherit_defaults(self) -> None:
        for run_id in self._checked_run_ids():
            self._template_edits[run_id].clear()
        self._refresh_previews()

    def _refresh_selection_label(self) -> None:
        count = len(self._checked_run_ids())
        total = len(self._run_items)
        self.selection_label.setText(f"已选 {count} / {total} 个数据")

    def _selected_cycle_indices(self, run: CVRun, item: QTreeWidgetItem) -> list[int]:
        indices: list[int] = []
        for index in range(item.childCount()):
            child = item.child(index)
            if child.checkState(0) == Qt.Checked:
                indices.append(run.cycles[index].index)
        return indices

    def _refresh_previews(self) -> None:
        self._updating = True
        checked_count = len(self._checked_run_ids())
        file_numbers = dataset_file_numbers(self.dataset)
        try:
            for run in self._runs():
                item = self._run_items.get(run.run_id)
                editor = self._template_edits.get(run.run_id)
                if item is None or editor is None:
                    continue
                override = editor.text().strip()
                template = override or run.legend_template
                selected_cycles = (
                    self._selected_cycle_indices(run, item) if isinstance(run, CVRun) else []
                )
                selected_numbers = {
                    cycle_index: position + 1
                    for position, cycle_index in enumerate(selected_cycles)
                }
                first_cycle_index = selected_cycles[0] if selected_cycles else None
                first_cycle = None
                if isinstance(run, CVRun):
                    first_cycle = next(
                        (cycle for cycle in run.cycles if cycle.index == first_cycle_index),
                        run.cycles[0] if run.cycles else None,
                    )
                first_number = first_cycle.index if first_cycle is not None else None
                if first_cycle is not None and self.spec.renumber_cycles:
                    first_number = selected_numbers.get(first_cycle.index, first_cycle.index)
                if first_cycle is not None:
                    fallback = (
                        f"Cycle {first_number}"
                        if checked_count <= 1
                        else run.legend_name
                    )
                else:
                    fallback = run.legend_name
                if template and first_cycle is not None and template_uses_cycle(template):
                    label, unknown = render_legend_template(
                        template,
                        run,
                        cycle=first_cycle,
                        cycle_number=first_number,
                        file_number=file_numbers.get(run.run_id),
                    )
                    if not label.strip():
                        label = fallback
                    if len(selected_cycles) > 1:
                        label += " …"
                else:
                    label, unknown = preview_label(
                        run,
                        template,
                        cycle=first_cycle,
                        cycle_number=first_number,
                        file_number=file_numbers.get(run.run_id),
                        fallback=fallback,
                    )
                if unknown:
                    label += "  （未知字段: " + "、".join("{" + token + "}" for token in unknown) + "）"
                    item.setForeground(2, QColor("#a33"))
                else:
                    item.setForeground(2, QColor("#263238"))
                item.setText(2, label)
                item.setToolTip(
                    2,
                    "图例来源：" + ("本图覆盖" if override else "数据默认" if run.legend_template else "默认"),
                )

                for index in range(item.childCount()):
                    child = item.child(index)
                    cycle = run.cycles[index]
                    child_checked = child.checkState(0) == Qt.Checked
                    child_number = cycle.index
                    if self.spec.renumber_cycles and child_checked:
                        child_number = selected_numbers.get(cycle.index, cycle.index)
                    child_template = override or run.legend_template
                    if child_template:
                        child_label, child_unknown = render_legend_template(
                            child_template,
                            run,
                            cycle=cycle,
                            cycle_number=child_number,
                            file_number=file_numbers.get(run.run_id),
                        )
                        if not child_label.strip():
                            child_label = f"Cycle {child_number}"
                    else:
                        child_label, child_unknown = f"Cycle {child_number}", []
                    if child_unknown:
                        child_label += "  （未知字段: " + "、".join(
                            "{" + token + "}" for token in child_unknown
                        ) + "）"
                    child.setText(2, child_label)
                    child.setForeground(2, QColor("#a33" if child_unknown else "#546e7a"))
        finally:
            self._updating = False

    def selected_run_ids(self) -> list[str]:
        return self._checked_run_ids()

    def cycle_selection(self) -> dict[str, list[int]]:
        if self.kind != "cv":
            return {}
        result: dict[str, list[int]] = {}
        for run in self.dataset.cv_runs:
            item = self._run_items.get(run.run_id)
            if item is None or item.checkState(0) != Qt.Checked or not item.childCount():
                continue
            selected = self._selected_cycle_indices(run, item)
            if len(selected) != len(run.cycles):
                result[run.run_id] = selected
        return result

    def legend_templates(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for run_id in self._checked_run_ids():
            text = self._template_edits[run_id].text().strip()
            if text:
                result[run_id] = text
        return result

    def accept(self) -> None:
        if not self.selected_run_ids():
            QMessageBox.information(self, "没有选择数据", "请至少勾选一个要绘制的数据")
            return
        unknown = self._unknown_tokens()
        if unknown:
            answer = QMessageBox.question(
                self,
                "模板包含未知字段",
                "以下字段无法识别，将按原样显示：\n"
                + "、".join("{" + token + "}" for token in unknown)
                + "\n\n仍要应用吗？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().accept()

    def _unknown_tokens(self) -> list[str]:
        unknown: list[str] = []
        for run in self._runs():
            item = self._run_items.get(run.run_id)
            editor = self._template_edits.get(run.run_id)
            if item is None or editor is None or item.checkState(0) != Qt.Checked:
                continue
            template = editor.text().strip()
            if not template:
                continue
            cycle = None
            if isinstance(run, CVRun) and run.cycles:
                cycle = run.cycles[0]
            _, unresolved = render_legend_template(template, run, cycle=cycle)
            for token in unresolved:
                if token not in unknown:
                    unknown.append(token)
        return unknown
