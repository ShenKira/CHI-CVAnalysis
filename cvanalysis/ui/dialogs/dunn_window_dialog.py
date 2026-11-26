"""Edit a Dunn analysis window using a separate CV preview."""

from __future__ import annotations

from copy import deepcopy
import math

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cvanalysis.analysis.cv import analyze_cv_run, dunn_fraction_vs_scan_rate, dunn_input_coverage
from cvanalysis.domain.errors import AnalysisError
from cvanalysis.domain.units import charge_family, current_family, resolve_unit
from cvanalysis.ui.dialogs.dunn_basis import BASIS_LABELS
from cvanalysis.ui.layout import fit_dialog
from cvanalysis.ui.theme import apply_button_role, apply_theme_role, theme_color
from cvanalysis.ui.tokens import BASE_FONT_SIZE, UiTokens


def dunn_plot_runs(tab):
    """Read the live selection of the plot that owns the editor."""
    selected = set(tab.spec.run_ids)
    return [run for run in tab.dataset.cv_runs if run.run_id in selected]


def read_dunn_window(low_text: str, high_text: str) -> tuple[float, float] | None:
    if not low_text.strip() and not high_text.strip():
        return None
    try:
        low, high = float(low_text), float(high_text)
    except ValueError:
        raise ValueError("请填写两个有效的电位端点，或同时留空使用共同窗口。") from None
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise ValueError("电位上下限须为有限数值，且下限小于上限。")
    return low, high


def check_dunn_coverage(window, common) -> None:
    if window is not None and (common is None or window[0] < common[0] or window[1] > common[1]):
        raise ValueError("手动选区超出所选数据的共同实测范围。请调整端点、勾选数据或恢复共同窗口。")


class DunnWindowDialog(QDialog):
    def __init__(self, tab, branch, basis, windows, *, preview_rate=None):
        super().__init__(tab)
        self.tab = tab
        self._basis = basis
        self._windows = deepcopy(windows)
        self._edited: dict[str, tuple[str, str]] = {}
        self.branch = branch
        self._initial_rate = preview_rate
        self._coverage = None
        self._selection_signature = None
        self._result = None
        self._selector = None
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Dunn 电位选区与诊断 · {tab.spec.label}")
        fit_dialog(self, 920, 670, min_width=465, min_height=400)
        tokens = UiTokens.from_scale(self.font().pointSizeF() / BASE_FONT_SIZE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*([tokens.space_lg] * 4))
        outer.setSpacing(tokens.space_sm)
        controls = QFormLayout()
        controls.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.branch_combo = QComboBox()
        self.branch_combo.addItem("正扫（电位递增）", "up")
        self.branch_combo.addItem("反扫（电位递减）", "down")
        self.branch_combo.setCurrentIndex(max(0, self.branch_combo.findData(branch)))
        controls.addRow("扫描支路", self.branch_combo)
        window_row = QWidget()
        window_layout = QHBoxLayout(window_row)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(tokens.space_xs)
        self.low_edit, self.high_edit = QLineEdit(), QLineEdit()
        self.low_edit.setPlaceholderText("下限")
        self.high_edit.setPlaceholderText("上限")
        self.low_edit.setAccessibleName("Dunn 电位下限（V）")
        self.high_edit.setAccessibleName("Dunn 电位上限（V）")
        window_layout.addWidget(self.low_edit, 1)
        window_layout.addWidget(QLabel("–"))
        window_layout.addWidget(self.high_edit, 1)
        reset = QPushButton("恢复共同窗口")
        apply_button_role(reset, "secondary")
        reset.clicked.connect(lambda: self._set_edits("", "", changed=True))
        window_layout.addWidget(reset)
        controls.addRow("电位选区（V）", window_row)
        self.rate_combo = QComboBox()
        self.rate_combo.setToolTip("仅切换高亮和拟合预览，所有已选有效扫速仍参与回归。")
        controls.addRow("预览扫速", self.rate_combo)
        outer.addLayout(controls)
        self.support = QLabel()
        self.support.setWordWrap(True)
        apply_theme_role(self.support, "hint")
        outer.addWidget(self.support)

        self.pages = QTabWidget()
        self.pages.setUsesScrollButtons(True)
        outer.addWidget(self.pages, 1)
        self._raw_figure = Figure(layout="constrained")
        self._raw_ax = self._raw_figure.subplots()
        self._raw_canvas = FigureCanvasQTAgg(self._raw_figure)
        self._raw_canvas.setMinimumHeight(tokens.scaled(125))
        self._input_table = self._table(tokens)
        raw = QSplitter(Qt.Vertical)
        raw.setChildrenCollapsible(False)
        raw.addWidget(self._raw_canvas)
        raw.addWidget(self._input_table)
        raw.setStretchFactor(0, 4)
        raw.setStretchFactor(1, 1)
        self.pages.addTab(raw, "CV 与选区")

        self._fit_figure = Figure(layout="constrained")
        self._fit_ax, self._resid_ax = self._fit_figure.subplots(2, 1, sharex=True)
        self._fit_canvas = FigureCanvasQTAgg(self._fit_figure)
        self.pages.addTab(self._fit_canvas, "拟合与残差")
        self._diagnostics_table = self._table(tokens)
        diagnostics = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.setContentsMargins(0, tokens.space_sm, 0, 0)
        self._basis_hint = QLabel()
        self._basis_hint.setWordWrap(True)
        apply_theme_role(self._basis_hint, "hint")
        diagnostics_layout.addWidget(self._basis_hint)
        diagnostics_layout.addWidget(self._diagnostics_table, 1)
        self.pages.addTab(diagnostics, "诊断结果")

        self.error = QLabel()
        self.error.setTextFormat(Qt.PlainText)
        self.error.setWordWrap(True)
        apply_theme_role(self.error, "error")
        outer.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.confirm = buttons.button(QDialogButtonBox.Ok)
        self.confirm.setText("使用选区")
        apply_button_role(self.confirm, "primary", pill=True)
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._render_result)
        self.branch_combo.currentIndexChanged.connect(self._switch_branch)
        self.rate_combo.currentIndexChanged.connect(self._select_rate)
        for edit in (self.low_edit, self.high_edit):
            edit.textChanged.connect(self._edit_changed)
        self.pages.currentChanged.connect(self._schedule_result)
        self._load_branch()
        self._show_basis()
        tab.rendered.connect(self.refresh_data)
        self.refresh_data()

    @staticmethod
    def _table(tokens):
        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(tokens.row_height)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        return table

    @staticmethod
    def _rows(table, headers, rows, *, numeric_columns=()):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(value)
                if j in numeric_columns:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if value:
                    item.setToolTip(value)
                table.setItem(i, j, item)

    def refresh_data(self, *_args):
        runs = dunn_plot_runs(self.tab)
        for run in runs:
            if run.summary is None:
                analyze_cv_run(run)
        selection = self.tab.spec.cycle_selection
        signature = tuple((run.run_id, id(run.summary), tuple(selection[run.run_id])
                           if run.run_id in selection else None) for run in runs)
        if signature == self._selection_signature:
            return
        self._selection_signature = signature
        self._refresh_branch()

    def _refresh_branch(self):
        runs = dunn_plot_runs(self.tab)
        self._coverage = dunn_input_coverage(runs, self.tab.spec.cycle_selection, self.branch)
        previous = self.rate_combo.currentData()
        rates = sorted({float(row.scan_rate) for row in self._coverage.inputs
                        if row.cycle_indices and row.scan_rate is not None})
        with QSignalBlocker(self.rate_combo):
            self.rate_combo.clear()
            for rate in rates:
                self.rate_combo.addItem(f"{rate:.16g} V/s", rate)
            choice = previous if previous is not None else self._initial_rate
            self.rate_combo.setCurrentIndex(max(0, self.rate_combo.findData(choice)) if rates else -1)
        rows = []
        for row in self._coverage.inputs:
            notes = [row.reason] if row.reason else []
            if row.partial_cycle_indices:
                notes.append("部分循环 " + self._cycle_labels(row.partial_cycle_indices))
            if row.excluded_cycle_indices:
                notes.append("排除循环 " + self._cycle_labels(row.excluded_cycle_indices))
            if row.potential_window is not None:
                notes.append(f"{row.potential_window[0]:g}–{row.potential_window[1]:g} V")
            rows.append((row.label, self._number(row.scan_rate), self._cycle_labels(row.cycle_indices),
                         "，".join(notes)))
        self._rows(self._input_table, ("数据", "扫速（V/s）", "参与循环", "状态"), rows, numeric_columns=(1,))
        self._input_table.horizontalHeader().setStretchLastSection(True)
        common = self._coverage.common_window
        if common is None:
            self.support.setText("没有共同实测电位区间。")
        else:
            self.support.setText(f"共同实测范围 {common[0]:.12g}–{common[1]:.12g} V。"
                                 "拖动选区边界或输入端点。留空使用共同窗口。")
        self._result = None
        self._draw_raw()
        self._schedule_result()

    @staticmethod
    def _cycle_labels(cycles):
        return ", ".join(str(cycle) for cycle in cycles) or "—"

    @staticmethod
    def _number(value, factor=1.0):
        return f"{value * factor:.7g}" if value is not None and math.isfinite(value) else "—"

    def _load_branch(self):
        bounds = self._windows.get(self.branch)
        texts = self._edited.get(self.branch)
        if texts is None:
            texts = tuple(map(str, bounds)) if isinstance(bounds, (tuple, list)) and len(bounds) == 2 else ("", "")
        self._set_edits(*texts)

    def _switch_branch(self):
        self.branch = self.branch_combo.currentData()
        self._load_branch()
        self._refresh_branch()

    def _set_edits(self, low, high, *, changed=False):
        with QSignalBlocker(self.low_edit), QSignalBlocker(self.high_edit):
            self.low_edit.setText(low)
            self.high_edit.setText(high)
        if changed:
            self._edit_changed()

    def _edit_changed(self):
        self._edited[self.branch] = (self.low_edit.text(), self.high_edit.text())
        self._result = None
        self._update_span()
        self._schedule_result()

    def _select_rate(self):
        self._draw_raw()
        self._schedule_result()

    def set_basis(self, basis):
        if basis != self._basis:
            self._basis = basis
            self._show_basis()
            self._result = None
            self._schedule_result()

    def _show_basis(self):
        self._basis_hint.setText(f"当前占比基准为{BASIS_LABELS[self._basis]}。")

    def _window(self, *, validate=True):
        window = read_dunn_window(self.low_edit.text(), self.high_edit.text())
        if validate:
            check_dunn_coverage(window, self._coverage.common_window)
        return window

    def _draw_raw(self):
        if self._selector is not None:
            self._selector.disconnect_events()
        self._raw_ax.clear()
        rate = self.rate_combo.currentData()
        records = {item.run_id: item for item in self._coverage.inputs}
        traces = []
        for run in dunn_plot_runs(self.tab):
            record = records.get(run.run_id)
            accepted = set(record.cycle_indices) if record else set()
            for cycle in run.cycles:
                if cycle.index in accepted:
                    points = cycle.branch_up if self.branch == "up" else cycle.branch_down
                    traces.append((points, rate == record.scan_rate))
        current_unit, factor = resolve_unit(
            current_family(), (np.max(np.abs(points[:, 1])) for points, _ in traces)
        )
        for points, chosen in traces:
            self._raw_ax.plot(points[:, 0], points[:, 1] * factor,
                              alpha=.9 if chosen else .25, linewidth=1.3 if chosen else .8)
        self._raw_ax.set(xlabel="Potential (V)", ylabel=f"Raw current ({current_unit})")
        self._selector = SpanSelector(
            self._raw_ax, self._span_changed, "horizontal", interactive=True, button=1,
            props={"facecolor": theme_color("primary"), "alpha": .16},
            handle_props={"color": theme_color("primary")},
        )
        self._selector.set_active(self._coverage.common_window is not None)
        self._update_span()

    def _span_changed(self, low, high):
        if low != high:
            self._set_edits(repr(float(low)), repr(float(high)), changed=True)

    def _update_span(self):
        try:
            window = self._window(validate=False)
            check_dunn_coverage(window, self._coverage.common_window)
            self.error.clear()
            self.confirm.setEnabled(True)
        except ValueError as exc:
            try:
                window = self._window(validate=False)
            except ValueError:
                window = None
            self.error.setText(str(exc))
            self.confirm.setEnabled(False)
        if self._selector is not None:
            bounds = window or self._coverage.common_window
            self._selector.set_visible(bounds is not None)
            if bounds is not None:
                self._selector.extents = bounds
        self._raw_canvas.draw_idle()

    def _schedule_result(self, *_args):
        if self.pages.currentIndex():
            self._fit_timer.start(120)

    def _render_result(self):
        if not self.pages.currentIndex():
            return
        rate = self.rate_combo.currentData()
        try:
            window = self._window()
            if self._result is None:
                self._result = dunn_fraction_vs_scan_rate(
                    dunn_plot_runs(self.tab), normalization=self.tab.spec.normalization,
                    cycle_selection=self.tab.spec.cycle_selection, branch=self.branch,
                    fraction_basis=self._basis, potential_window=window,
                )
        except (ValueError, AnalysisError) as exc:
            self.error.setText(str(exc))
            self._fit_ax.clear()
            self._resid_ax.clear()
            self._fit_canvas.draw_idle()
            self._diagnostics_table.setRowCount(0)
            return
        self.error.clear()
        self._draw_diagnostics()
        self._draw_fit(rate)

    def _draw_fit(self, rate):
        fit = self._result.fit
        self._fit_ax.clear()
        self._resid_ax.clear()
        if fit is not None and rate is not None:
            index = int(np.argmin(np.abs(fit.rates - rate)))
            actual_rate = fit.rates[index]
            measured = fit.measured[index]
            capacitive, diffusive = fit.k1 * actual_rate, fit.k2 * np.sqrt(actual_rate)
            fitted = capacitive + diffusive
            unit, factor = resolve_unit(current_family(self._result.normalization),
                                        np.concatenate((measured, fitted)))
            for values, label in (
                (measured, "Measured"), (fitted, "Dunn fit"),
                (capacitive, "Capacitive-like"), (diffusive, "Diffusion-like"),
            ):
                self._fit_ax.plot(fit.grid, values * factor, label=label)
            self._fit_ax.set_ylabel(f"Current ({unit})")
            self._fit_ax.legend(loc="best", ncols=2)
            self._resid_ax.plot(fit.grid, (fitted - measured) * factor)
            self._resid_ax.axhline(0, color="0.5", linewidth=.8)
            self._resid_ax.set(xlabel="Potential (V)", ylabel=f"Residual ({unit})")
        self._fit_canvas.draw_idle()

    def _draw_diagnostics(self):
        charges = (row.q_fitted for row in self._result.diagnostics if row.q_fitted is not None)
        unit, factor = resolve_unit(charge_family(self._result.normalization), charges)
        rows = []
        for row in self._result.diagnostics:
            values = tuple(self._number(value, factor) for value in
                           (row.q_capacitive, row.q_diffusive, row.q_fitted, row.q_measured, row.q_residual))
            ratios = tuple(self._number(value, 100.0) for value in
                           (row.closure_error, row.relative_rmse, row.fitted_net_ratio, row.measured_net_ratio))
            status = {
                "ok": "通过当前检查",
                "diagnostic": "需结合诊断解释",
                "prediction": "仅模型预测",
                "undefined": "占比未定义",
            }.get(row.status, "—")
            rows.append((self._number(row.scan_rate), *values, *ratios, status))
        headers = ("扫速（V/s）", f"电容样电荷（{unit}）", f"扩散样电荷（{unit}）",
                   f"拟合净电荷（{unit}）", f"实测净电荷（{unit}）", f"电荷差（{unit}）",
                   "闭合差（%）", "相对残差 RMS（%）", "拟合净值/绝对积分（%）", "实测净值/绝对积分（%）", "状态")
        self._rows(self._diagnostics_table, headers, rows, numeric_columns=range(10))
        for column, hint in (
            (5, "拟合净电荷减去实测净电荷。"),
            (6, "电荷差除以带符号的实测净电荷。正值表示拟合净电荷相对实测值偏高。"),
            (7, "残差电流的均方根除以实测电流的均方根。按共同电位选区积分。"),
            (8, "拟合净电荷的绝对值除以两个分量的绝对积分之和。比值越小，抵消越强。"),
            (9, "实测净电荷的绝对值除以实测电流的绝对积分。比值越小，抵消越强。"),
        ):
            self._diagnostics_table.horizontalHeaderItem(column).setToolTip(hint)

    @property
    def windows(self):
        return deepcopy(self._windows)

    def accept(self):
        proposed = deepcopy(self._windows)
        try:
            self._window()
            for branch, bounds in self._edited.items():
                values = read_dunn_window(*bounds)
                coverage = self._coverage if branch == self.branch else dunn_input_coverage(
                    dunn_plot_runs(self.tab), self.tab.spec.cycle_selection, branch
                )
                check_dunn_coverage(values, coverage.common_window)
                if values is None:
                    proposed.pop(branch, None)
                else:
                    proposed[branch] = list(values)
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self._windows = proposed
        super().accept()
