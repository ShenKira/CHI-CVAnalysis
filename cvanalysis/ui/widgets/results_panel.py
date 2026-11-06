# -*- coding: utf-8 -*-
"""CV/EIS/CP result tables shown in the bottom-left workspace."""

from __future__ import annotations

import math
from typing import Iterable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QPushButton,
    QTabWidget,
    QTreeView,
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
from cvanalysis.ui.models.metric_tree_model import MetricTreeModel
from cvanalysis.ui.theme import theme_color
from cvanalysis.ui.widgets.view_columns import ViewColumns

_EXPANSION_TOOLTIP = "双击文件行展开/收起每个循环的分析结果"
_TABLE_ALIASES = {
    "cv": "cv",
    "cv_table": "cv",
    "eis": "eis",
    "eis_table": "eis",
    "cp": "cp",
    "cp_table": "cp",
}


class _ResultTreeView(QTreeView):
    """QTreeView with the QTableView header accessor used by existing code."""

    def horizontalHeader(self):
        return self.header()


class ResultsPanel(QWidget):
    """Own the CV/EIS/CP metric tables independently from the analysis controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dataset = Dataset()
        self._selected_run_ids: list[str] = []
        self._visible_run_ids: list[str] | None = None
        self._display_kind = None
        self._expanded_run_ids: dict[str, set[str]] = {"cv": set(), "eis": set(), "cp": set()}
        self._updating_tables = False
        self._table_views: dict[str, tuple[QTreeView, MetricTreeModel]] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.results_tabs = QTabWidget()
        self.cv_table = _ResultTreeView()
        self.cv_model = MetricTreeModel(
            ["文件", "扫速", "循环", "有效", "平均电容", "C/A", "C/m", "SD", "CV%", "备注"]
        )
        self.cv_table.setModel(self.cv_model)
        self._configure_table(self.cv_table)
        self.cv_columns = ViewColumns(self.cv_table, first_width=180)

        self.eis_table = _ResultTreeView()
        self.eis_model = MetricTreeModel(
            ["文件", "Rs", "Rct", "f0", "Cdl", "相位@1Hz", "低频 |Z|", "备注"]
        )
        self.eis_table.setModel(self.eis_model)
        self._configure_table(self.eis_table)
        self.eis_columns = ViewColumns(self.eis_table, first_width=180)

        self.cp_table = _ResultTreeView()
        self.cp_model = MetricTreeModel(
            ["文件", "循环", "放电容量", "比容量", "库伦效率", "IR 降", "保持段", "备注"]
        )
        self.cp_table.setModel(self.cp_model)
        self._configure_table(self.cp_table)
        self.cp_columns = ViewColumns(self.cp_table, first_width=180)

        self._table_views = {
            "cv": (self.cv_table, self.cv_model),
            "eis": (self.eis_table, self.eis_model),
            "cp": (self.cp_table, self.cp_model),
        }
        for key, (view, model) in self._table_views.items():
            view.expanded.connect(
                lambda index, key=key, model=model: self._on_expansion_changed(
                    key, model, index, True
                )
            )
            view.collapsed.connect(
                lambda index, key=key, model=model: self._on_expansion_changed(
                    key, model, index, False
                )
            )

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
    def _configure_table(table: QTreeView) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setExpandsOnDoubleClick(True)
        table.setItemsExpandable(True)
        table.setRootIsDecorated(True)
        table.setToolTip(_EXPANSION_TOOLTIP)

    def _fit_current(self) -> None:
        columns = [self.cv_columns, self.eis_columns, self.cp_columns][
            max(0, min(2, self.results_tabs.currentIndex()))
        ]
        columns.fit_all()

    # -- expansion helpers ----------------------------------------------
    def _table_key(self, table) -> str:
        if isinstance(table, QTreeView):
            for key, (view, _) in self._table_views.items():
                if view is table:
                    return key
        key = _TABLE_ALIASES.get(str(table).strip().lower())
        if key is None:
            raise ValueError(f"未知结果表: {table!r}")
        return key

    def _table_pair(self, table) -> tuple[str, QTreeView, MetricTreeModel]:
        key = self._table_key(table)
        view, model = self._table_views[key]
        return key, view, model

    @staticmethod
    def _run_table_args(run_id, table):
        """Accept both ``(run_id, table)`` and legacy ``(table, run_id)``."""
        if isinstance(run_id, str) and run_id.strip().lower() in _TABLE_ALIASES:
            if _TABLE_ALIASES.get(str(table).strip().lower()) is None:
                return table, run_id
        return run_id, table

    def _on_expansion_changed(
        self,
        key: str,
        model: MetricTreeModel,
        index: QModelIndex,
        expanded: bool,
    ) -> None:
        if self._updating_tables:
            return
        run_id = model.run_id_for_index(index)
        if run_id is None:
            return
        if expanded:
            self._expanded_run_ids[key].add(run_id)
        else:
            self._expanded_run_ids[key].discard(run_id)

    def _restore_expansion(self, key: str) -> None:
        view, model = self._table_views[key]
        for run_id in self._expanded_run_ids[key]:
            index = model.index_for_run(run_id)
            if index.isValid() and model.rowCount(index):
                view.expand(index)

    def run_index(self, run_id: str, table="cv") -> QModelIndex:
        """Return the top-level index for ``run_id`` in a result table."""
        run_id, table = self._run_table_args(run_id, table)
        _, _, model = self._table_pair(table)
        return model.index_for_run(run_id)

    def is_run_expanded(self, run_id: str, table="cv") -> bool:
        run_id, table = self._run_table_args(run_id, table)
        _, view, model = self._table_pair(table)
        index = model.index_for_run(run_id)
        return bool(index.isValid() and view.isExpanded(index))

    def expand_run(self, run_id: str, table="cv") -> bool:
        run_id, table = self._run_table_args(run_id, table)
        _, view, model = self._table_pair(table)
        index = model.index_for_run(run_id)
        if not index.isValid():
            return False
        view.expand(index)
        return view.isExpanded(index)

    def collapse_run(self, run_id: str, table="cv") -> bool:
        run_id, table = self._run_table_args(run_id, table)
        _, view, model = self._table_pair(table)
        index = model.index_for_run(run_id)
        if not index.isValid():
            return False
        view.collapse(index)
        return not view.isExpanded(index)

    def cv_run_index(self, run_id: str) -> QModelIndex:
        return self.run_index(run_id, "cv")

    def cv_is_run_expanded(self, run_id: str) -> bool:
        return self.is_run_expanded(run_id, "cv")

    def cv_expand_run(self, run_id: str) -> bool:
        return self.expand_run(run_id, "cv")

    def cv_collapse_run(self, run_id: str) -> bool:
        return self.collapse_run(run_id, "cv")

    def eis_run_index(self, run_id: str) -> QModelIndex:
        return self.run_index(run_id, "eis")

    def eis_is_run_expanded(self, run_id: str) -> bool:
        return self.is_run_expanded(run_id, "eis")

    def eis_expand_run(self, run_id: str) -> bool:
        return self.expand_run(run_id, "eis")

    def eis_collapse_run(self, run_id: str) -> bool:
        return self.collapse_run(run_id, "eis")

    def cp_run_index(self, run_id: str) -> QModelIndex:
        return self.run_index(run_id, "cp")

    def cp_is_run_expanded(self, run_id: str) -> bool:
        return self.is_run_expanded(run_id, "cp")

    def cp_expand_run(self, run_id: str) -> bool:
        return self.expand_run(run_id, "cp")

    def cp_collapse_run(self, run_id: str) -> bool:
        return self.collapse_run(run_id, "cp")

    # -- dataset updates -------------------------------------------------
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
        existing_ids = {run.run_id for run in dataset.all_runs()}
        for expanded in self._expanded_run_ids.values():
            expanded.intersection_update(existing_ids)
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
        elif dataset.is_empty:
            self.results_tabs.setCurrentIndex(0)
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

    @staticmethod
    def _finite(value) -> bool:
        return value is not None and math.isfinite(value)

    @staticmethod
    def _normalized(value, divisor):
        if not ResultsPanel._finite(value) or not divisor or divisor <= 0:
            return None
        return value / divisor

    @staticmethod
    def _cv_cycle_status(cycle) -> str:
        if cycle.is_outlier:
            return "排除"
        return "有效" if cycle.valid else "无效"

    def _update_tables(self, cv_runs: list[CVRun], eis_runs: list[EISRun], cp_runs: list[CPRun] | None = None) -> None:
        cv_rows = []
        cv_children = []
        cv_run_ids = []
        cv_colors = {}
        cv_child_colors = {}
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
            cv_run_ids.append(run.run_id)
            if remark:
                cv_colors[(row_index, 9)] = theme_color("error")

            params = run.params
            area_cm2 = params.area_cm2 if params else None
            mass_kg = params.mass_mg * 1e-3 if params and params.mass_mg else None
            child_rows = []
            for child_index, cycle in enumerate(run.cycles):
                child_remark = cycle.outlier_reason or cycle.warning or ""
                capacitance = cycle.capacitance_F if self._finite(cycle.capacitance_F) else None
                child_rows.append(
                    [
                        f"Cycle {cycle.index}",
                        "",
                        "",
                        self._cv_cycle_status(cycle),
                        format_with_unit(capacitance, CAPACITANCE, digits=4),
                        format_with_unit(
                            self._normalized(capacitance, area_cm2),
                            AREAL_CAPACITANCE,
                            digits=4,
                        ),
                        format_with_unit(
                            self._normalized(capacitance, mass_kg),
                            SPECIFIC_CAPACITANCE,
                            digits=4,
                        ),
                        "",
                        "",
                        child_remark,
                    ]
                )
                if child_remark:
                    cv_child_colors[(row_index, child_index, 9)] = theme_color("error")
            cv_children.append(child_rows)

        eis_rows = []
        eis_run_ids = []
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
            eis_run_ids.append(run.run_id)
            if remark:
                eis_colors[(row_index, 7)] = theme_color("error")

        cp_rows = []
        cp_children = []
        cp_run_ids = []
        cp_colors = {}
        cp_child_colors = {}
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
            cp_run_ids.append(run.run_id)
            if remark:
                cp_colors[(row_index, 7)] = theme_color("error")

            child_rows = []
            for child_index, cycle in enumerate(summary.cycles if summary else []):
                discharge = (
                    f"{cycle.discharge_capacity_C / 3.6:.4g} mAh"
                    if self._finite(cycle.discharge_capacity_C)
                    else "—"
                )
                cycle_specific = (
                    f"{cycle.specific_capacity_mAh_g:.4g} mAh/g"
                    if self._finite(cycle.specific_capacity_mAh_g)
                    else "—"
                )
                cycle_efficiency = (
                    f"{cycle.coulombic_efficiency_pct:.2f}%"
                    if self._finite(cycle.coulombic_efficiency_pct)
                    else "—"
                )
                cycle_ir_drop = (
                    f"{cycle.ir_drop_V:.3g} V" if self._finite(cycle.ir_drop_V) else "—"
                )
                child_remark = getattr(cycle, "warning", None) or ""
                child_rows.append(
                    [
                        f"Cycle {cycle.index}",
                        "",
                        discharge,
                        cycle_specific,
                        cycle_efficiency,
                        cycle_ir_drop,
                        "",
                        child_remark,
                    ]
                )
                if child_remark:
                    cp_child_colors[(row_index, child_index, 7)] = theme_color("error")
            cp_children.append(child_rows)

        self._updating_tables = True
        try:
            self.cv_model.set_tree_data(
                self.cv_model.headers,
                cv_rows,
                cv_children,
                colors=cv_colors,
                child_colors=cv_child_colors,
                run_ids=cv_run_ids,
            )
            self.eis_model.set_tree_data(
                self.eis_model.headers,
                eis_rows,
                None,
                colors=eis_colors,
                run_ids=eis_run_ids,
            )
            self.cp_model.set_tree_data(
                self.cp_model.headers,
                cp_rows,
                cp_children,
                colors=cp_colors,
                child_colors=cp_child_colors,
                run_ids=cp_run_ids,
            )
        finally:
            self._updating_tables = False
        self._restore_expansion("cv")
        self._restore_expansion("eis")
        self._restore_expansion("cp")
