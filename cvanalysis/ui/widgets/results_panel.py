# -*- coding: utf-8 -*-
"""CV/EIS/CP result tables shown in the bottom-left workspace."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from cvanalysis.analysis.cp import CPRunSummary
from cvanalysis.analysis.cv import CVRunSummary
from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.domain.models import CPRun, CVRun, Dataset, EISRun
from cvanalysis.domain.units import (
    AREAL_CAPACITANCE,
    CAPACITANCE,
    IMPEDANCE,
    SPECIFIC_CAPACITANCE,
    format_with_unit,
)
from cvanalysis.ui.models.metric_table_model import MetricTableModel
from cvanalysis.ui.widgets.view_columns import ViewColumns


class ResultsPanel(QWidget):
    """Own the CV/EIS/CP metric tables independently from the analysis controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dataset = Dataset()
        self._selected_run_ids: list[str] = []
        self._visible_run_ids: list[str] | None = None
        self._display_kind = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.results_tabs = QTabWidget()
        self.cv_table = QTableView()
        self.cv_model = MetricTableModel(
            ["文件", "扫速", "循环", "有效", "平均电容", "C/A", "C/m", "SD", "CV%", "备注"]
        )
        self.cv_table.setModel(self.cv_model)
        self._configure_table(self.cv_table)
        self.cv_columns = ViewColumns(self.cv_table, first_width=180)

        self.eis_table = QTableView()
        self.eis_model = MetricTableModel(
            ["文件", "Rs", "Rct", "f0", "Cdl", "相位@1Hz", "低频 |Z|", "备注"]
        )
        self.eis_table.setModel(self.eis_model)
        self._configure_table(self.eis_table)
        self.eis_columns = ViewColumns(self.eis_table, first_width=180)

        self.cp_table = QTableView()
        self.cp_model = MetricTableModel(
            ["文件", "循环", "放电容量", "比容量", "库伦效率", "IR 降", "保持段", "备注"]
        )
        self.cp_table.setModel(self.cp_model)
        self._configure_table(self.cp_table)
        self.cp_columns = ViewColumns(self.cp_table, first_width=180)

        self.results_tabs.addTab(self.cv_table, "CV 结果")
        self.results_tabs.addTab(self.eis_table, "EIS 结果")
        self.results_tabs.addTab(self.cp_table, "CP / GCD 结果")
        fit_columns_btn = QPushButton("适配列宽")
        fit_columns_btn.setProperty("secondary", True)
        fit_columns_btn.setToolTip("按内容适配当前结果表；也可拖动或双击列边界。")
        fit_columns_btn.clicked.connect(self._fit_current)
        self.results_tabs.setCornerWidget(fit_columns_btn)
        layout.addWidget(self.results_tabs, 1)

    @staticmethod
    def _configure_table(table: QTableView) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def _fit_current(self) -> None:
        columns = [self.cv_columns, self.eis_columns, self.cp_columns][
            max(0, min(2, self.results_tabs.currentIndex()))
        ]
        columns.fit_all()

    def update_dataset(
        self,
        dataset: Dataset,
        *,
        selected_run_ids: Iterable[str] | None = None,
        visible_run_ids: Iterable[str] | None = None,
    ) -> None:
        self._dataset = dataset
        self._selected_run_ids = list(selected_run_ids or [])
        self._visible_run_ids = None if visible_run_ids is None else list(visible_run_ids)
        cv_runs = self._runs_for_display(dataset, CVRun)
        eis_runs = self._runs_for_display(dataset, EISRun)
        cp_runs = self._runs_for_display(dataset, CPRun)
        self._update_tables(cv_runs, eis_runs, cp_runs)

        selected_types = {
            "cv"
            if isinstance(run, CVRun)
            else "cp"
            if isinstance(run, CPRun)
            else "eis"
            for run in dataset.all_runs()
            if run.run_id in self._selected_run_ids
        }
        kind = next(iter(selected_types)) if len(selected_types) == 1 else (
            "eis"
            if eis_runs and not cv_runs and not cp_runs
            else "cv"
            if cv_runs and not eis_runs and not cp_runs
            else "cp"
            if cp_runs and not cv_runs and not eis_runs
            else None
        )
        if kind and kind != self._display_kind:
            self.results_tabs.setCurrentIndex({"cv": 0, "eis": 1, "cp": 2}[kind])
        self._display_kind = kind

    def _runs_for_display(self, dataset: Dataset, run_type):
        selected = [
            run
            for run in dataset.all_runs()
            if run.run_id in set(self._selected_run_ids) and isinstance(run, run_type)
        ]
        if selected:
            return selected
        if self._visible_run_ids is not None:
            visible = set(self._visible_run_ids)
            return [
                run
                for run in dataset.all_runs()
                if run.run_id in visible and isinstance(run, run_type)
            ]
        return [run for run in dataset.all_runs() if isinstance(run, run_type)]

    def _update_tables(self, cv_runs: list[CVRun], eis_runs: list[EISRun], cp_runs: list[CPRun] | None = None) -> None:
        cv_rows = []
        cv_colors = {}
        for row_index, run in enumerate(cv_runs):
            summary = run.summary if isinstance(run.summary, CVRunSummary) else None
            remark = "；".join(summary.warnings[:1]) if summary and summary.warnings else ""
            row = [
                run.display_name,
                f"{run.scan_rate:g}" if run.scan_rate else "—",
                len(run.cycles),
                summary.valid_cycles if summary else "—",
                format_with_unit(
                    summary.mean_capacitance_F if summary else None,
                    CAPACITANCE,
                    digits=4,
                ),
                format_with_unit(
                    summary.mean_cap_per_area if summary else None,
                    AREAL_CAPACITANCE,
                    digits=4,
                ),
                format_with_unit(
                    summary.mean_cap_per_mass if summary else None,
                    SPECIFIC_CAPACITANCE,
                    digits=4,
                ),
                format_with_unit(
                    summary.sd_capacitance_F if summary else None,
                    CAPACITANCE,
                    digits=3,
                ),
                f"{summary.cv_percent:.2f}" if summary and summary.cv_percent is not None else "—",
                remark,
            ]
            cv_rows.append(row)
            if remark:
                cv_colors[(row_index, 9)] = "#a33"
        self.cv_model.set_data(self.cv_model.headers, cv_rows, cv_colors)

        eis_rows = []
        eis_colors = {}
        for row_index, run in enumerate(eis_runs):
            metrics = run.summary if isinstance(run.summary, EISMetrics) else None
            remark = "；".join(metrics.warnings[:1]) if metrics and metrics.warnings else ""
            row = [
                run.display_name,
                format_with_unit(metrics.rs_ohm if metrics else None, IMPEDANCE, digits=4),
                format_with_unit(metrics.rct_ohm if metrics else None, IMPEDANCE, digits=4),
                f"{metrics.f_peak_hz:.3g} Hz" if metrics and metrics.f_peak_hz else "—",
                format_with_unit(metrics.cdl_F if metrics else None, CAPACITANCE, digits=4),
                f"{metrics.phase_at_1hz_deg:.2f}°"
                if metrics and metrics.phase_at_1hz_deg is not None
                else "—",
                format_with_unit(
                    metrics.low_freq_mag_ohm if metrics else None,
                    IMPEDANCE,
                    digits=4,
                ),
                remark,
            ]
            eis_rows.append(row)
            if remark:
                eis_colors[(row_index, 7)] = "#a33"
        self.eis_model.set_data(self.eis_model.headers, eis_rows, eis_colors)

        cp_rows = []
        cp_colors = {}
        for row_index, run in enumerate(cp_runs or []):
            summary = run.summary if isinstance(run.summary, CPRunSummary) else None
            remark = "；".join(summary.warnings[:1]) if summary and summary.warnings else ""
            capacity = (
                f"{summary.mean_discharge_capacity_C / 3.6:.4g} mAh"
                if summary and summary.mean_discharge_capacity_C == summary.mean_discharge_capacity_C
                else "—"
            )
            specific = (
                f"{summary.mean_specific_capacity_mAh_g:.4g} mAh/g"
                if summary and summary.mean_specific_capacity_mAh_g == summary.mean_specific_capacity_mAh_g
                else "—"
            )
            efficiency = (
                f"{summary.mean_coulombic_efficiency_pct:.2f}%"
                if summary and summary.mean_coulombic_efficiency_pct == summary.mean_coulombic_efficiency_pct
                else "—"
            )
            ir_drop = (
                f"{summary.mean_ir_drop_V:.3g} V"
                if summary and summary.mean_ir_drop_V == summary.mean_ir_drop_V
                else "—"
            )
            row = [
                run.display_name,
                summary.cycle_count if summary else "—",
                capacity,
                specific,
                efficiency,
                ir_drop,
                "含记录" if summary and summary.has_hold_data else "无",
                remark,
            ]
            cp_rows.append(row)
            if remark:
                cp_colors[(row_index, 7)] = "#a33"
        self.cp_model.set_data(self.cp_model.headers, cp_rows, cp_colors)
        self.cv_table.resizeRowsToContents()
        self.eis_table.resizeRowsToContents()
        self.cp_table.resizeRowsToContents()
