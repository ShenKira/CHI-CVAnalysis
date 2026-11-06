# -*- coding: utf-8 -*-
"""Result panel tree behaviour: flat compatibility and per-cycle children."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, ElectrodeParams
from cvanalysis.domain.units import (
    AREAL_CAPACITANCE,
    CAPACITANCE,
    SPECIFIC_CAPACITANCE,
    format_with_unit,
)
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
from cvanalysis.ui.widgets.results_panel import ResultsPanel


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _double_click(view, index) -> None:
    """Send a real double-click sequence to a viewport in offscreen mode."""
    position = view.visualRect(index).center()
    global_position = view.viewport().mapToGlobal(position)
    modifiers = Qt.NoModifier
    press = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(position),
        QPointF(global_position),
        Qt.LeftButton,
        Qt.LeftButton,
        modifiers,
    )
    release = QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(position),
        QPointF(global_position),
        Qt.LeftButton,
        Qt.NoButton,
        modifiers,
    )
    double_click = QMouseEvent(
        QEvent.MouseButtonDblClick,
        QPointF(position),
        QPointF(global_position),
        Qt.LeftButton,
        Qt.LeftButton,
        modifiers,
    )
    viewport = view.viewport()
    QApplication.sendEvent(viewport, press)
    QApplication.sendEvent(viewport, release)
    QApplication.sendEvent(viewport, press)
    QApplication.sendEvent(viewport, double_click)
    QApplication.sendEvent(viewport, release)


def test_flat_set_data_remains_backward_compatible():
    app = _application()
    panel = ResultsPanel()
    row = ["sample", "0.01", 2, 2, "100 μF", "", "", "", "", ""]
    panel.cv_model.set_data(panel.cv_model.headers, [row])

    assert panel.cv_model.rowCount() == 1
    parent = panel.cv_model.index(0, 0)
    assert parent.isValid()
    assert not panel.cv_model.parent(parent).isValid()
    assert panel.cv_model.rowCount(parent) == 0
    for column, value in enumerate(row):
        assert panel.cv_model.data(panel.cv_model.index(0, column)) == str(value)
    assert panel.cv_model.headerData(0, Qt.Horizontal) == "文件"

    panel.deleteLater()
    app.processEvents()


def test_cv_tree_rows_children_and_normalized_values(synthetic_cv_runs):
    app = _application()
    runs = synthetic_cv_runs
    for run in runs:
        run.params = ElectrodeParams(area_cm2=2.0, mass_mg=4.0)
    dataset = Dataset(cv_runs=list(runs))
    panel = ResultsPanel()
    panel.update_dataset(dataset)

    model = panel.cv_model
    assert model.rowCount() == len(runs)
    run = runs[0]
    parent = model.index(0, 0)
    assert model.data(parent) == run.display_name
    assert model.rowCount(parent) == len(run.cycles)

    cycle = run.cycles[0]
    child = model.index(0, 0, parent)
    assert child.isValid()
    assert model.parent(child) == parent
    assert model.data(child) == f"Cycle {cycle.index}"
    assert model.data(model.index(0, 1, parent)) == ""
    assert model.data(model.index(0, 2, parent)) == ""
    assert model.data(model.index(0, 3, parent)) == "有效"
    assert model.data(model.index(0, 4, parent)) == format_with_unit(
        cycle.capacitance_F, CAPACITANCE, digits=4
    )
    assert model.data(model.index(0, 5, parent)) == format_with_unit(
        cycle.capacitance_F / 2.0, AREAL_CAPACITANCE, digits=4
    )
    assert model.data(model.index(0, 6, parent)) == format_with_unit(
        cycle.capacitance_F / (4.0 * 1e-3), SPECIFIC_CAPACITANCE, digits=4
    )
    assert model.data(model.index(0, 7, parent)) == ""
    assert model.data(model.index(0, 8, parent)) == ""
    assert model.data(model.index(0, 9, parent)) == ""

    # The parent remains the current one-line run summary.
    assert model.data(model.index(0, 4)) == format_with_unit(
        run.summary.mean_capacitance_F, CAPACITANCE, digits=4
    )

    # Outlier/exclusion state and remark colouring are exposed on child rows.
    excluded = run.cycles[1]
    excluded.is_outlier = True
    excluded.outlier_reason = "测试排除"
    panel.update_dataset(dataset)
    parent = model.index(0, 0)
    assert model.data(model.index(1, 3, parent)) == "排除"
    assert model.data(model.index(1, 9, parent)) == "测试排除"
    colour = model.data(model.index(1, 9, parent), Qt.ForegroundRole)
    assert colour is not None and colour == QColor("#a33")

    panel.deleteLater()
    app.processEvents()


def test_double_click_expands_and_state_survives_update(synthetic_cv_runs):
    app = _application()
    panel = ResultsPanel()
    panel.resize(900, 320)
    panel.show()
    app.processEvents()
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    panel.update_dataset(dataset)
    app.processEvents()

    run = synthetic_cv_runs[0]
    assert panel.cv_table.expandsOnDoubleClick()
    assert panel.cv_table.itemsExpandable()
    assert panel.cv_table.rootIsDecorated()
    parent = panel.cv_run_index(run.run_id)
    assert parent.isValid()
    _double_click(panel.cv_table, parent)
    app.processEvents()
    assert panel.cv_is_run_expanded(run.run_id)

    # A deliberate collapse must not be undone by a refresh.
    assert panel.cv_collapse_run(run.run_id)
    panel.update_dataset(dataset)
    app.processEvents()
    assert not panel.cv_is_run_expanded(run.run_id)

    assert panel.cv_expand_run(run.run_id)
    assert panel.cv_is_run_expanded(run.run_id)
    panel.update_dataset(dataset, visible_run_ids=[run.run_id])
    app.processEvents()
    assert panel.cv_is_run_expanded(run.run_id)

    panel.close()


def test_cp_children_and_eis_has_no_children(synthetic_cp_run, synthetic_eis_run):
    app = _application()
    synthetic_cp_run.params = ElectrodeParams(area_cm2=1.5, mass_mg=2.0)
    dataset = Dataset(cp_runs=[synthetic_cp_run])
    refresh_analysis(dataset, AnalysisSettings(), force=True)
    panel = ResultsPanel()
    panel.update_dataset(dataset)

    model = panel.cp_model
    assert model.rowCount() == 1
    parent = model.index(0, 0)
    summary = synthetic_cp_run.summary
    assert summary.cycle_count == len(summary.cycles)
    assert model.rowCount(parent) == summary.cycle_count

    cycle = summary.cycles[0]
    child = model.index(0, 0, parent)
    assert model.parent(child) == parent
    assert model.data(child) == f"Cycle {cycle.index}"
    assert model.data(model.index(0, 1, parent)) == ""
    assert model.data(model.index(0, 2, parent)) == (
        f"{cycle.discharge_capacity_C / 3.6:.4g} mAh"
    )
    assert model.data(model.index(0, 3, parent)) == (
        f"{cycle.specific_capacity_mAh_g:.4g} mAh/g"
    )
    assert model.data(model.index(0, 4, parent)) == (
        f"{cycle.coulombic_efficiency_pct:.2f}%"
    )
    assert model.data(model.index(0, 5, parent)) == f"{cycle.ir_drop_V:.3g} V"
    assert model.data(model.index(0, 6, parent)) == ""
    assert model.data(model.index(0, 7, parent)) == ""

    panel.update_dataset(Dataset(eis_runs=[synthetic_eis_run]))
    assert panel.eis_model.rowCount() == 1
    eis_parent = panel.eis_model.index(0, 0)
    assert panel.eis_model.rowCount(eis_parent) == 0
    assert not panel.eis_is_run_expanded(synthetic_eis_run.run_id)

    panel.deleteLater()
    app.processEvents()
