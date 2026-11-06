# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from matplotlib.figure import Figure

from cvanalysis.analysis.cp import analyze_cp_run, completed_cp_series, split_hold_records
from cvanalysis.domain.models import Dataset, ElectrodeParams
from cvanalysis.plotting.cp_renderer import draw_cp_capacity, draw_gcd_curve
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis


def test_cp_parser_and_hold_block(synthetic_cp_run):
    run = synthetic_cp_run
    assert run.metadata.high_e == 2.0
    assert run.metadata.low_e == 0.0
    assert run.metadata.high_hold_s == 10.0
    assert run.metadata.low_hold_s == 10.0
    assert run.has_hold_data
    assert len(run.time) > 400
    holds = split_hold_records(run)
    assert len(holds) == 5
    assert [hold.polarity for hold in holds] == [-1, 1, -1, 1, -1]
    assert all(hold.duration_s == pytest.approx(10.0) for hold in holds)


def test_cp_hold_completion_and_segments(synthetic_cp_run):
    run = synthetic_cp_run
    raw_end = float(run.time[-1])
    series = completed_cp_series(run, complete_holds=True)
    assert series.completed
    assert series.time_s[-1] > raw_end + 45
    assert series.hold_mask.sum() > 4000
    assert np.isclose(series.potential_V[series.hold_mask].max(), 2.0)
    low = series.potential_V[series.hold_mask]
    assert np.isclose(low.min(), 0.0)

    summary = analyze_cp_run(run, force=True)
    assert len(summary.segments) == 5
    assert len(summary.holds) == 5
    assert summary.completed_hold_count == 5
    assert summary.cycle_count == 2
    assert summary.cycles[0].charge_capacity_C == pytest.approx(2e-6, rel=0.05)
    assert summary.cycles[0].discharge_capacity_C == pytest.approx(2e-6, rel=0.05)
    assert summary.cycles[0].coulombic_efficiency_pct == pytest.approx(100.0, rel=0.05)


def test_completed_cp_series_reuses_summary_segments(synthetic_cp_run):
    run = synthetic_cp_run
    summary = analyze_cp_run(run, force=True)
    fresh = completed_cp_series(run, complete_holds=True)
    reused = completed_cp_series(
        run,
        complete_holds=True,
        segments=summary.segments,
        holds=summary.holds,
        warnings=summary.warnings,
    )
    assert reused.completed == fresh.completed
    assert np.array_equal(reused.time_s, fresh.time_s)
    assert np.array_equal(reused.potential_V, fresh.potential_V)
    assert np.array_equal(reused.current_A, fresh.current_A)
    assert np.array_equal(reused.hold_mask, fresh.hold_mask)
    assert reused.warnings == fresh.warnings


def test_cp_gcd_redraw_does_not_rebuild_segments(synthetic_cp_run, monkeypatch):
    import cvanalysis.analysis.cp as cp_module

    run = synthetic_cp_run
    analyze_cp_run(run, force=True)
    calls = []
    original = cp_module.build_segments

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cp_module, "build_segments", counted)
    figure = Figure(figsize=(8, 6))
    draw_gcd_curve(
        figure,
        Dataset(cp_runs=[run]),
        PlotSpec("cp_gcd", [run.run_id]),
        BUILTIN_PRESETS["daily"],
    )
    assert calls == []


def test_apply_params_refreshes_cp_summary(synthetic_cp_run):
    from cvanalysis.services.dataset_service import apply_params

    run = synthetic_cp_run
    run.params = ElectrodeParams(area_cm2=0.5, mass_mg=1.0)
    analyze_cp_run(run, force=True)
    before = run.summary.mean_areal_capacity_mAh_cm2
    assert np.isfinite(before)

    dataset = Dataset(cp_runs=[run])
    apply_params(dataset, ElectrodeParams(area_cm2=2.0, mass_mg=1.0), run_ids=[run.run_id])
    assert run.params.area_cm2 == 2.0
    assert run.summary.mean_areal_capacity_mAh_cm2 == pytest.approx(before / 4.0)
    assert run.summary.mean_areal_capacity_mAh_cm2 == pytest.approx(
        run.summary.mean_discharge_capacity_C / 2.0 / 3.6
    )
    assert np.isfinite(run.summary.mean_specific_capacity_mAh_g)


def test_cp_metrics_use_electrode_params(synthetic_cp_run):
    run = synthetic_cp_run
    run.params = ElectrodeParams(area_cm2=2.0, mass_mg=1.0)
    summary = analyze_cp_run(run, force=True)
    cycle = summary.cycles[0]
    assert cycle.specific_capacity_C_g == pytest.approx(2e-6 / 1e-3, rel=0.05)
    assert cycle.specific_capacity_mAh_g == pytest.approx(2e-6 / 1e-3 / 3.6, rel=0.05)
    assert cycle.areal_capacity_C_cm2 == pytest.approx(2e-6 / 2.0, rel=0.05)
    assert np.isfinite(cycle.discharge.energy_J) and cycle.discharge.energy_J > 0
    assert cycle.ir_drop_V >= 0


def test_cp_fallback_turn_detection_without_scipy():
    from cvanalysis.analysis.cp import _find_turns_fallback

    assert _find_turns_fallback(np.asarray([0.0, 1.0, 0.0])) == [1]
    assert _find_turns_fallback(np.asarray([2.0, 1.0, 2.0])) == [1]
    assert _find_turns_fallback(np.asarray([0.0, 1.0, 2.0, 2.0, 1.0, 0.0])) == [3]


def test_cp_hold_assignment_validates_polarity(synthetic_cp_run):
    from dataclasses import replace

    from cvanalysis.analysis.cp import _assign_holds, build_segments

    run = synthetic_cp_run
    segments, holds, _ = build_segments(run, warn=False)
    high = run.metadata.high_e
    low = run.metadata.low_e
    span = run.metadata.voltage_window or 0.0
    tolerance = max(0.02, span * 0.05)

    def expected_polarity(segment):
        end = segment.end_potential_V
        if high is not None and abs(end - high) <= tolerance:
            return 1
        if low is not None and abs(end - low) <= tolerance:
            return -1
        return 0

    reversed_holds = list(reversed(holds))
    warnings = []
    assignments = _assign_holds(run, segments, reversed_holds, warnings)
    assert len(assignments) == len(segments)
    for index, record in assignments.items():
        assert record.polarity == expected_polarity(segments[index])

    positive_only = [
        replace(hold, current_A=np.abs(hold.current_A), mean_current_A=abs(hold.mean_current_A))
        for hold in holds
    ]
    warnings = []
    assignments = _assign_holds(run, segments, positive_only, warnings)
    assert all(record.polarity == 1 for record in assignments.values())
    assert all(
        index not in assignments
        for index, segment in enumerate(segments)
        if expected_polarity(segment) == -1
    )
    assert warnings

    old_high, old_low = run.metadata.high_e, run.metadata.low_e
    try:
        run.metadata.high_e = None
        run.metadata.low_e = None
        assignments = _assign_holds(run, segments, reversed_holds, [])
        assert assignments == {
            index: reversed_holds[index] for index in range(len(segments))
        }
    finally:
        run.metadata.high_e, run.metadata.low_e = old_high, old_low


def test_cp_area_capacity_honours_include_holds(synthetic_cp_run):
    run = synthetic_cp_run
    run.params = ElectrodeParams(area_cm2=1.0, mass_mg=1.0)
    dataset = Dataset(cp_runs=[run])
    refresh_analysis(dataset, AnalysisSettings(), force=True)
    style = BUILTIN_PRESETS["daily"]

    figure = Figure(figsize=style.figure_size, dpi=style.dpi)
    spec = PlotSpec(
        "cp_capacity",
        [run.run_id],
        normalization="area",
        analysis_options={
            "include_holds": True,
            "show_charge": True,
            "show_efficiency": False,
        },
    )
    warnings = draw_cp_capacity(figure, dataset, spec, style)
    assert not warnings
    lines = figure.axes[0].lines
    expected_discharge = [
        cycle.areal_capacity_with_holds_mAh_cm2 for cycle in run.summary.cycles
    ]
    expected_charge = [
        cycle.charge_capacity_with_holds_C / run.params.area_cm2 / 3.6
        for cycle in run.summary.cycles
    ]
    assert list(lines[0].get_ydata()) == pytest.approx(expected_discharge)
    assert list(lines[1].get_ydata()) == pytest.approx(expected_charge)
    assert run.summary.mean_areal_capacity_with_holds_mAh_cm2 == pytest.approx(
        sum(expected_discharge) / len(expected_discharge)
    )

    figure = Figure(figsize=style.figure_size, dpi=style.dpi)
    spec = PlotSpec(
        "cp_capacity",
        [run.run_id],
        normalization="area",
        analysis_options={
            "include_holds": False,
            "show_charge": True,
            "show_efficiency": False,
        },
    )
    draw_cp_capacity(figure, dataset, spec, style)
    assert list(figure.axes[0].lines[0].get_ydata()) == pytest.approx(
        [cycle.areal_capacity_mAh_cm2 for cycle in run.summary.cycles]
    )


def test_cp_plot_renderers(synthetic_cp_run):
    run = synthetic_cp_run
    run.params = ElectrodeParams(area_cm2=2.0, mass_mg=1.0)
    dataset = Dataset(cp_runs=[run])
    style = BUILTIN_PRESETS["daily"]

    figure = Figure(figsize=style.figure_size, dpi=style.dpi)
    spec = PlotSpec(
        "cp_gcd",
        [run.run_id],
        analysis_options={"complete_holds": True},
    )
    warnings = draw_gcd_curve(figure, dataset, spec, style)
    assert not warnings
    assert figure.axes[0].get_xlabel() == "Time (s)"
    assert figure.axes[0].get_ylabel() == "Potential (V)"
    assert figure.axes[0].get_legend() is not None

    figure = Figure(figsize=style.figure_size, dpi=style.dpi)
    spec = PlotSpec(
        "cp_capacity",
        [run.run_id],
        normalization="mass",
        analysis_options={"include_holds": False, "show_charge": True, "show_efficiency": True},
    )
    warnings = draw_cp_capacity(figure, dataset, spec, style)
    assert not warnings
    assert figure.axes[0].get_xlabel() == "Cycle"
    assert "mAh/g" in figure.axes[0].get_ylabel()
    assert len(figure.axes) == 2


def test_cp_project_round_trip(tmp_path, synthetic_cp_run):
    from cvanalysis.services.project_service import load_project, save_project

    run = synthetic_cp_run
    run.params = ElectrodeParams(area_cm2=2.0, mass_mg=2.0)
    dataset = Dataset(cp_runs=[run])
    spec = PlotSpec("cp_gcd", [run.run_id], analysis_options={"complete_holds": False})
    path = tmp_path / "cp.cvproj"
    save_project(path, dataset, plots=[spec])
    state = load_project(path)
    assert len(state.dataset.cp_runs) == 1
    loaded = state.dataset.cp_runs[0]
    assert loaded.has_hold_data
    assert loaded.params.mass_mg == 2.0
    assert loaded.time.shape == run.time.shape
    assert loaded.hold_current.shape == run.hold_current.shape
    assert state.plots[0].kind == "cp_gcd"
    assert state.plots[0].analysis_options["complete_holds"] is False


def test_cp_csv_export(tmp_path, synthetic_cp_run):
    from cvanalysis.services.export_service import export_analysis_csv

    dataset = Dataset(cp_runs=[synthetic_cp_run])
    refresh_analysis(dataset, AnalysisSettings())
    written = export_analysis_csv(dataset, tmp_path)
    names = {path.name for path in written}
    assert "cp_summary.csv" in names
    assert "cp_cycles.csv" in names


def test_cp_gui_smoke(tmp_path, synthetic_cp_run):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cp_runs=[synthetic_cp_run]), [])
    app.processEvents()
    assert window.tabs.count() >= 1
    assert window.results_panel.cp_model.rowCount() == 1
    assert "CP / GCD 数据" in [
        window.dataset_model.data(window.dataset_model.index(row, 0))
        for row in range(window.dataset_model.rowCount())
    ]
    assert set(window.quick_analysis_buttons) == {"CV 分析", "EIS 分析", "CP / GCD 分析"}
    for kind in ("cp_gcd", "cp_capacity"):
        window._request_plot(kind)
        app.processEvents()
    tab = window.tabs.currentWidget()
    assert tab.spec.kind == "cp_capacity"
    window.options_panel.bind(tab)
    assert "show_efficiency" in window.options_panel.controls
    assert "complete_holds" not in window.options_panel.controls
    window.close()
