# -*- coding: utf-8 -*-
"""Concatenation order and per-file cycle ranges for CP capacity plots."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cvanalysis.analysis.cp import CPRunSummary, analyze_cp_run
from cvanalysis.analysis.cp_series import normalize_cp_concat_config
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.layout import fit_dialog
from cvanalysis.ui.theme import apply_button_role, apply_theme_role
from cvanalysis.ui.tokens import BASE_FONT_SIZE, UiTokens


class CPConcatDialog(QDialog):
    """Choose the file order and inclusive cycle ranges used by concatenation."""

    def __init__(self, runs, order=None, ranges=None, *, parent=None):
        super().__init__(parent)
        if isinstance(runs, Dataset):
            dataset = runs
            spec = order
            if not isinstance(spec, PlotSpec):
                raise TypeError(
                    "CPConcatDialog(dataset, spec) 需要绘图规格作为第二个参数"
                )
            selected = set(spec.run_ids)
            runs = [
                run
                for run in dataset.cp_runs
                if run.run_id in selected
            ]
            order = spec.analysis_options.get("cp_concat_order")
            ranges = spec.analysis_options.get("cp_concat_ranges")
        self._runs = list(runs)
        self._summaries = {
            run.run_id: (
                run.summary
                if isinstance(run.summary, CPRunSummary)
                else analyze_cp_run(run)
            )
            for run in self._runs
        }
        self._rows: list[dict] = []
        self._result_ranges: dict[str, dict[str, int]] | None = None
        self.setWindowTitle("CP 跨文件拼接设置")
        fit_dialog(self, 780, 560, min_width=600, min_height=380)
        self._build_ui(order, ranges)
        self._fit_to_rows()

    def _fit_to_rows(self) -> None:
        """Size the dialog to its actual file count instead of leaving dead space."""
        row_height = max(22, self.table.verticalHeader().defaultSectionSize())
        preferred_height = min(
            560, 300 + row_height * max(1, len(self._rows))
        )
        fit_dialog(
            self,
            780,
            preferred_height,
            min_width=600,
            min_height=380,
        )

    def _build_ui(self, order, ranges) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = QLabel(
            "按下方顺序把 CP 文件接成一条容量-循环曲线。"
            "可调整每个文件参与绘制的起止循环；至少保留一个循环。"
        )
        hint.setWordWrap(True)
        hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        apply_theme_role(hint, "hint")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["文件", "可用循环范围", "起始循环", "结束循环", "参与循环数"]
        )
        for column in (2, 3, 4):
            header_item = self.table.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        point_size = self.font().pointSizeF()
        if point_size <= 0:
            point_size = BASE_FONT_SIZE
        tokens = UiTokens.from_scale(point_size / BASE_FONT_SIZE)
        self.table.horizontalHeader().setMinimumSectionSize(tokens.scaled(72))
        for column in (1, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.table.itemSelectionChanged.connect(self._update_move_buttons)
        layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        self.up_button = QPushButton("上移")
        self.up_button.setToolTip("把选中的 CP 文件提前，改变拼接顺序（Ctrl+↑）")
        self.up_button.setAccessibleName("上移选中的 CP 文件")
        apply_button_role(self.up_button, "secondary")
        self.up_button.setShortcut(QKeySequence("Ctrl+Up"))
        self.up_button.clicked.connect(lambda: self._move_current(-1))
        self.down_button = QPushButton("下移")
        self.down_button.setToolTip("把选中的 CP 文件后移，改变拼接顺序（Ctrl+↓）")
        self.down_button.setAccessibleName("下移选中的 CP 文件")
        apply_button_role(self.down_button, "secondary")
        self.down_button.setShortcut(QKeySequence("Ctrl+Down"))
        self.down_button.clicked.connect(lambda: self._move_current(1))
        reset_button = QPushButton("全部使用完整范围")
        reset_button.setToolTip("把每个 CP 文件恢复为包含其全部循环")
        apply_button_role(reset_button, "secondary")
        reset_button.clicked.connect(self._reset_full_ranges)
        controls.addWidget(self.up_button)
        controls.addWidget(self.down_button)
        controls.addWidget(reset_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        apply_theme_role(self.summary_label, "muted")
        layout.addWidget(self.summary_label)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Maximum
        )
        apply_theme_role(self.error, "error")
        self.error.setVisible(False)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        ok_button.setText("确定")
        cancel_button.setText("取消")
        ok_button.setDefault(True)
        apply_button_role(ok_button, "primary", pill=True)
        self.ok_button = ok_button
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        normalized_order, normalized_ranges = normalize_cp_concat_config(
            self._runs,
            self._summaries,
            order=order,
            ranges=ranges,
        )
        by_id = {run.run_id: run for run in self._runs}
        for run_id in normalized_order:
            run = by_id.get(run_id)
            if run is None:
                continue
            bounds = normalized_ranges.get(run_id, {"start": 1, "end": 0})
            self._rows.append(
                {
                    "run": run,
                    "summary": self._summaries[run_id],
                    "start": int(bounds["start"]),
                    "end": int(bounds["end"]),
                }
            )
        self._rebuild_table()

    def _rebuild_table(self, select_row: int = 0) -> None:
        current_row = self.table.currentRow()
        if select_row is None:
            select_row = current_row
        self.table.setRowCount(0)
        for index, state in enumerate(self._rows):
            run = state["run"]
            summary = state["summary"]
            count = len(summary.cycles)
            self.table.insertRow(index)

            file_item = QTableWidgetItem(run.display_short_name)
            file_item.setToolTip(run.display_name)
            file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(index, 0, file_item)

            available = (
                f"1–{count}（{count} 个循环）" if count else "无可用循环"
            )
            available_item = QTableWidgetItem(available)
            available_item.setTextAlignment(Qt.AlignCenter)
            available_item.setFlags(available_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(index, 1, available_item)

            start_spin = QSpinBox()
            end_spin = QSpinBox()
            start_spin.setToolTip(f"{run.display_name}：起始循环（包含）")
            end_spin.setToolTip(f"{run.display_name}：结束循环（包含）")
            start_spin.setAccessibleName(f"{run.display_name} 起始循环")
            end_spin.setAccessibleName(f"{run.display_name} 结束循环")
            if count:
                state["start"] = min(max(int(state["start"]), 1), count)
                state["end"] = min(max(int(state["end"]), 1), count)
                if state["start"] > state["end"]:
                    state["start"], state["end"] = 1, count
                for spin in (start_spin, end_spin):
                    spin.setRange(1, count)
            else:
                state["start"], state["end"] = 1, 0
                for spin in (start_spin, end_spin):
                    spin.setRange(0, 0)
                    spin.setEnabled(False)
            start_spin.setValue(int(state["start"]))
            end_spin.setValue(int(state["end"]))
            start_spin.valueChanged.connect(
                lambda value, row=index: self._range_changed(row, "start", value)
            )
            end_spin.valueChanged.connect(
                lambda value, row=index: self._range_changed(row, "end", value)
            )
            state["start_spin"] = start_spin
            state["end_spin"] = end_spin
            self.table.setCellWidget(index, 2, start_spin)
            self.table.setCellWidget(index, 3, end_spin)

            count_item = QTableWidgetItem()
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            count_item.setToolTip("该文件在当前范围内实际参与拼接的循环数")
            self.table.setItem(index, 4, count_item)
            state["count_item"] = count_item
            self._update_row_count(state)

        if self._rows:
            row = min(max(int(select_row), 0), len(self._rows) - 1)
            self.table.selectRow(row)
        self._update_move_buttons()
        self._update_summary()

    def _participating(self, state: dict) -> int:
        start, end = int(state["start"]), int(state["end"])
        return sum(
            1
            for cycle in state["summary"].cycles
            if start <= cycle.index <= end
        )

    def _update_row_count(self, state: dict) -> None:
        count_item = state.get("count_item")
        if count_item is not None:
            count_item.setText(str(self._participating(state)))

    def _range_changed(self, row: int, field: str, value: int) -> None:
        if not 0 <= row < len(self._rows):
            return
        if self.table.currentRow() != row:
            self.table.selectRow(row)
        state = self._rows[row]
        state[field] = int(value)
        self._update_row_count(state)
        self._update_summary()

    def _update_summary(self) -> None:
        total = sum(self._participating(state) for state in self._rows)
        files = sum(
            1 for state in self._rows if self._participating(state) > 0
        )
        if total:
            self.summary_label.setText(
                f"将拼接 {files} 个文件，共 {total} 个循环。"
            )
        else:
            self.summary_label.setText("尚无参与循环，请至少为一个文件保留循环。")
        self._validate_live()

    def _validate_live(self) -> bool:
        for state in self._rows:
            if len(state["summary"].cycles) <= 0:
                continue
            if int(state["start"]) > int(state["end"]):
                self.error.setText(
                    f"{state['run'].display_name}：起始循环不能大于结束循环。"
                )
                self.error.setVisible(True)
                self.ok_button.setEnabled(False)
                return False
        if sum(self._participating(state) for state in self._rows) <= 0:
            self.error.setText("请至少为一个 CP 文件保留一个循环。")
            self.error.setVisible(True)
            self.ok_button.setEnabled(False)
            return False
        self.error.clear()
        self.error.setVisible(False)
        self.ok_button.setEnabled(True)
        return True

    def _update_move_buttons(self) -> None:
        row = self.table.currentRow()
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < len(self._rows) - 1)

    def _move_current(self, delta: int) -> None:
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < len(self._rows):
            return
        self._rows[row], self._rows[target] = (
            self._rows[target],
            self._rows[row],
        )
        self._rebuild_table(select_row=target)

    def _reset_full_ranges(self) -> None:
        for state in self._rows:
            count = len(state["summary"].cycles)
            state["start"] = 1
            state["end"] = count if count else 0
        self._rebuild_table(select_row=max(0, self.table.currentRow()))

    def order(self) -> list[str]:
        return [state["run"].run_id for state in self._rows]

    def _raw_ranges(self) -> dict[str, dict[str, int]]:
        return {
            state["run"].run_id: {
                "start": int(state["start"]),
                "end": int(state["end"]),
            }
            for state in self._rows
        }

    def ranges(self) -> dict[str, dict[str, int]]:
        if self._result_ranges is not None:
            return {
                run_id: dict(bounds)
                for run_id, bounds in self._result_ranges.items()
            }
        return self._raw_ranges()

    def config(self):
        """Return ``(order, ranges)`` for the current table state."""
        return self.order(), self.ranges()

    def accept(self) -> None:
        for index, state in enumerate(self._rows):
            count = len(state["summary"].cycles)
            if count <= 0:
                continue
            if int(state["start"]) > int(state["end"]):
                self.error.setText(
                    f"{state['run'].display_name}：起始循环不能大于结束循环。"
                )
                self.error.setVisible(True)
                self.table.selectRow(index)
                return
        if sum(self._participating(state) for state in self._rows) <= 0:
            self.error.setText(
                "请至少为一个 CP 文件保留一个循环。"
            )
            self.error.setVisible(True)
            return
        self.error.clear()
        self.error.setVisible(False)
        _order, normalized = normalize_cp_concat_config(
            self._runs,
            self._summaries,
            order=self.order(),
            ranges=self._raw_ranges(),
        )
        self._result_ranges = normalized
        super().accept()
