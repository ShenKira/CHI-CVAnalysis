# -*- coding: utf-8 -*-
"""Cross-layer checks for CP concatenation (render/export, project, UI sync)."""

from __future__ import annotations

import copy

import numpy as np
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QDialog

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.cp_renderer import draw_cp_capacity
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


def _second_run(run):
    second = copy.deepcopy(run)
    second.run_id = "cp_second"
    second.name = "cp_second"
    return second


def test_export_pipeline_draws_same_concatenated_series(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "capacity_series": "both",
            "cp_display_unit": "mAh",
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": 1},
                second.run_id: {"start": 2, "end": 2},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": second.run_id,
            "capacity_percent_reference_cycle": 2,
        },
    )
    data = Dataset(cp_runs=[first, second])
    direct = Figure()
    draw_cp_capacity(direct, data, spec, STYLE)
    exported = Figure()
    render_plot(exported, data, spec, STYLE)
    assert len(direct.axes[0].lines) == len(exported.axes[0].lines) == 2
    for expected, actual in zip(direct.axes[0].lines, exported.axes[0].lines):
        np.testing.assert_allclose(actual.get_xdata(), expected.get_xdata())
        np.testing.assert_allclose(actual.get_ydata(), expected.get_ydata())
    assert "%" in exported.axes[0].get_ylabel()


def test_project_roundtrip_renders_concatenated_percentage(synthetic_cp_run, tmp_path):
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    from cvanalysis.services.project_service import load_project, save_project

    first = synthetic_cp_run
    second = _second_run(first)
    cycle_count = len(first.summary.cycles)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "capacity_series": "discharge",
            "cp_display_unit": "mAh",
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": 1},
                second.run_id: {"start": 2, "end": 2},
            },
            "cp_concat_cycle_mode": "cumulative",
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": second.run_id,
            "capacity_percent_reference_cycle": 2,
        },
    )
    path = tmp_path / "concat-two.cvproj"
    save_project(path, Dataset(cp_runs=[first, second]), plots=[spec])
    restored = load_project(path)
    refresh_analysis(restored.dataset, AnalysisSettings(), force=True)
    restored_spec = restored.plots[0]
    assert len(restored_spec.run_ids) == 2
    assert restored_spec.analysis_options["cp_concat_order"] == restored_spec.run_ids
    figure = Figure()
    warnings = draw_cp_capacity(
        figure, restored.dataset, restored_spec, STYLE
    )
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    line = figure.axes[0].lines[0]
    expected_x = cycle_count + 2
    np.testing.assert_allclose(line.get_xdata(), [1, expected_x])
    assert line.get_ydata()[-1] == 100.0
    assert "%" in figure.axes[0].get_ylabel()


def test_panel_unified_reference_with_mass_fallback(synthetic_cp_run):
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    first.params.mass_mg = 4.0
    refresh_analysis(Dataset(cp_runs=[first, second]), AnalysisSettings(), force=True)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        normalization="mass",
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": len(first.summary.cycles)},
                second.run_id: {"start": 1, "end": len(second.summary.cycles)},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": first.run_id,
            "capacity_percent_reference_cycle": 1,
        },
    )
    tab = PlotTab(spec, STYLE, Dataset(cp_runs=[first, second]))
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        panel.apply()
        assert "已应用" in panel.error.text()
        assert spec.analysis_options["capacity_percent_reference_run_id"] == first.run_id
        assert spec.analysis_options["capacity_percent_reference_cycle"] == 1
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_range_dialog_excludes_reference_cycle_and_window_adjusts(
    synthetic_cp_run, tmp_path, monkeypatch
):
    from cvanalysis.ui import main_window as main_window_module
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": len(first.summary.cycles)},
                second.run_id: {"start": 1, "end": len(second.summary.cycles)},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": second.run_id,
            "capacity_percent_reference_cycle": 2,
        },
    )

    class FakeDialog:
        def __init__(self, runs, order=None, ranges=None, parent=None):
            self._order = [run.run_id for run in runs]
            self._ranges = {
                run.run_id: {
                    "start": 1,
                    "end": 1 if run.run_id == second.run_id else len(run.summary.cycles),
                }
                for run in runs
            }

        def exec(self):
            return QDialog.Accepted

        def order(self):
            return list(self._order)

        def ranges(self):
            return {key: dict(value) for key, value in self._ranges.items()}

    monkeypatch.setattr(main_window_module, "CPConcatDialog", FakeDialog)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    try:
        window.dataset = Dataset(cp_runs=[first, second])
        window._refresh_model_and_panel()
        tab = window._add_plot_tab(spec)
        window._edit_cp_concat(tab)
        assert spec.analysis_options["capacity_percent_reference_cycle"] == 1
        assert spec.analysis_options["cp_concat_ranges"][second.run_id] == {
            "start": 1,
            "end": 1,
        }
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()
