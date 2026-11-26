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
    assert reused.warnings == summary.warnings
    assert set(fresh.warnings) <= set(reused.warnings)


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
    assert np.isnan(cycle.ir_drop_V)  # holds hide the current switch
    assert any("IR 降留空" in warning for warning in summary.warnings)


@pytest.mark.parametrize("step", [.25, .5, 1.])
@pytest.mark.parametrize("jump", [0., .1])
def test_cp_ir_drop_excludes_capacitive_slope(step, jump):
    from cvanalysis.domain.models import CPMetadata, CPRun

    charge_time = np.arange(0, 4 + step, step)
    discharge_time = np.arange(4 + step, 8 + step, step)
    time = np.r_[charge_time, discharge_time]
    potential = np.r_[charge_time / 4, (1 - jump) * (8 - discharge_time) / 4]
    run = CPRun("test-cp-ir", "test", time, potential, CPMetadata(
        high_e=1, low_e=0, anodic_current_A=.01, cathodic_current_A=.01,
        switch_polarity="Potential",
    ))
    summary = analyze_cp_run(run)
    assert summary.cycles[0].ir_drop_V == pytest.approx(jump, abs=1e-9)


@pytest.mark.parametrize("mode,expected", [("Potential", "partial"), ("Time", "complete")])
def test_cp_cycle_uses_switch_protocol_and_keeps_missing_current_blank(mode, expected):
    from cvanalysis.domain.models import CPMetadata, CPRun
    from cvanalysis.services.export_service import cp_cycles_frame

    run = CPRun("test-cp-protocol", "test", np.arange(9.), np.r_[np.linspace(0, 1, 5), .95, .90, .85, .80],
                CPMetadata(high_e=1, low_e=0, anodic_current_A=.01, cathodic_current_A=.02,
                           anodic_time_s=4, cathodic_time_s=4, switch_polarity=mode))
    cycle = analyze_cp_run(run).cycles[0]
    assert cycle.completeness == expected
    if mode == "Time":
        assert cycle.coulombic_efficiency_pct == pytest.approx(200.)
    else:
        assert np.isnan(cycle.coulombic_efficiency_pct)
    run.metadata.cathodic_current_A = None
    summary = analyze_cp_run(run, force=True)
    assert np.isnan(summary.cycles[0].discharge_capacity_C)
    assert any("阴极恒流" in warning for warning in summary.warnings)
    frame = cp_cycles_frame(Dataset(cp_runs=[run]))
    assert frame.loc[0, "completeness"] == expected
    assert np.isnan(frame.loc[0, "coulombic_efficiency_pct"])


def test_cp_fallback_turn_detection_without_scipy():
    from cvanalysis.analysis.cp import _find_turns_fallback

    assert _find_turns_fallback(np.asarray([0.0, 1.0, 0.0])) == [1]
    assert _find_turns_fallback(np.asarray([2.0, 1.0, 2.0])) == [1]
    assert _find_turns_fallback(np.asarray([0.0, 1.0, 2.0, 2.0, 1.0, 0.0])) == [3]


@pytest.mark.parametrize("missing_sample", [False, True])
def test_cp_rounded_time_recovers_only_a_verified_sampling_grid(tmp_path, missing_sample):
    import json

    from cvanalysis.io.chi import ChiCPParser
    from cvanalysis.plotting.export import render_plot
    from cvanalysis.services.project_service import load_project, save_project

    branch = np.linspace(0, 1, 61)
    potential = np.r_[0.0, np.tile(np.r_[branch[1:], branch[-2::-1]], 180)]
    grid = .005 * np.arange(potential.size)
    tokens = [f"{value:.3e}" for value in grid]
    if missing_sample:
        del tokens[40]
        potential = np.delete(potential, 40)
    raw = np.array([float(token) for token in tokens])
    header = (
        "Chronopotentiometry\nHigh E Limit (V) = 1\nLow E Limit (V) = 0\n"
        "Anodic Current (A) = 1e-6\nCathodic Current (A) = 1e-6\n"
        "Current Switching Polarity = Potential\nData Storage Interval (s) = .005\n"
        "Time/sec, Potential/V\n"
    )
    rows = "\n".join(f"{token}, {value}" for token, value in zip(tokens, potential))
    parsed = ChiCPParser().parse(header + rows, tmp_path / "rounded.txt")
    run = parsed.runs[0]
    assert run.summary is None
    assert np.any(np.diff(raw) == 0)

    summary = analyze_cp_run(run)
    np.testing.assert_array_equal(run.time, raw)
    if missing_sample:
        assert run.time_grid_status == "unverified"
        np.testing.assert_array_equal(summary.analysis_time_s, raw)
        assert any("无法验证固定采样网格" in warning for warning in summary.warnings)
        return

    assert run.time_grid_status == "verified_text"
    assert any("逐行校验通过" in warning for warning in parsed.warnings)
    path = save_project(tmp_path / "rounded.cvproj", Dataset(cp_runs=[run]))
    restored = load_project(path).dataset.cp_runs[0]
    assert restored.time_grid_status == "verified_text"
    np.testing.assert_array_equal(restored.time, raw)
    np.testing.assert_allclose(analyze_cp_run(restored).analysis_time_s, grid)

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runs"][0]["data"].pop("time_grid_status")
    path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = load_project(path).dataset.cp_runs[0]
    assert legacy.time_grid_status == "verified_legacy"
    np.testing.assert_allclose(analyze_cp_run(legacy).analysis_time_s, grid)

    np.testing.assert_allclose(summary.analysis_time_s, grid)
    assert len(summary.complete_cycles) == 180
    assert [cycle.charge_capacity_C for cycle in summary.cycles] == pytest.approx(
        [3e-7] * 180, abs=1e-15
    )
    assert [cycle.coulombic_efficiency_pct for cycle in summary.cycles] == pytest.approx([100] * 180)
    assert [cycle.ir_drop_V for cycle in summary.cycles] == pytest.approx([0] * 180, abs=1e-9)
    figure = Figure()
    spec = PlotSpec("cp_gcd", [run.run_id])
    warnings = render_plot(figure, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    np.testing.assert_allclose(figure.axes[0].lines[0].get_xdata(), grid)
    assert any("逐行校验通过" in warning for warning in warnings)


@pytest.mark.parametrize("phase,perturb", [
    (0, "none"), (.002, "mixed"), (0, "curved"), (0, "unstable"),
])
def test_cp_switch_timing_with_known_boundaries(phase, perturb):
    from cvanalysis.domain.models import CPMetadata, CPRun
    from cvanalysis.services.export_service import cp_cycles_frame

    switches = np.array([.074, .365, .647, .939, 1.228, 1.521]) + phase
    time = np.arange(0, 1.58, .01)
    potential = 4.8 * (switches[0] - time)
    for index, (start, end) in enumerate(zip(switches, [*switches[1:], 1.8])):
        mask = (time >= start) & (time < end)
        first, last = (.22, 2.) if index % 2 == 0 else (1.78, 0.)
        potential[mask] = first + (last - first) * (time[mask] - start) / (end - start)
    first_after = np.searchsorted(time, switches[2], side="right")
    if perturb == "mixed":
        potential[first_after] = potential[first_after - 1] + .001
    if perturb == "curved":
        potential[first_after - 6 : first_after] += .030
    if perturb == "unstable":
        potential[first_after - 7 : first_after] = [.360, .295, .230, .165, .125, .085, .045]

    run = CPRun("switch-test", "test", time, potential, CPMetadata(
        high_e=2, low_e=0, anodic_current_A=1e-6, cathodic_current_A=1.04e-6,
        switch_polarity="Potential", sample_interval_s=.01,
    ))
    summary = analyze_cp_run(run)
    cycle = summary.cycles[0]
    charge, discharge = np.diff(switches[:3])
    expected_ce = 104 * discharge / charge
    assert cycle.completeness == "complete"
    assert cycle.ce_lower_pct <= expected_ce <= cycle.ce_upper_pct
    if perturb in {"curved", "unstable"}:
        chosen_end = time[first_after] - (.005 if perturb == "unstable" else 0.0)
        assert cycle.timing_method == "bounded"
        assert cycle.charge_duration_s == pytest.approx(charge)
        assert cycle.discharge_duration_s == pytest.approx(chosen_end - switches[1])
        assert cycle.coulombic_efficiency_pct == pytest.approx(104 * (chosen_end - switches[1]) / charge)
        assert 104 * (chosen_end - switches[1]) / charge != pytest.approx(cycle.sampled_ce_pct)
        assert summary.cycles[1].charge_duration_s == pytest.approx(switches[3] - chosen_end)
        assert any("含区间约束的切换时刻" in warning for warning in summary.warnings)
    else:
        assert cycle.timing_method == "estimated"
        assert cycle.charge_duration_s == pytest.approx(charge)
        assert cycle.discharge_duration_s == pytest.approx(discharge)
        assert cycle.coulombic_efficiency_pct == pytest.approx(expected_ce)
        assert cycle.coulombic_efficiency_pct > 100
    assert cycle.charge_capacity_C == pytest.approx(cycle.charge_duration_s * 1e-6)
    exported = cp_cycles_frame(Dataset(cp_runs=[run])).iloc[0]
    assert exported["timing_method"] == cycle.timing_method
    assert exported["ce_lower_pct"] == cycle.ce_lower_pct
    assert exported["sampled_ce_pct"] == cycle.sampled_ce_pct


def test_long_cp_record_skips_only_incomplete_cycles():
    from cvanalysis.domain.models import CPMetadata, CPRun
    from cvanalysis.plotting.export import render_plot

    potential = list(np.linspace(.6, 0, 11))
    incomplete = {2, 210}
    for index in range(1, 211):
        # Cycle 3 switches near the high cutoff between stored samples.
        high = {2: .65, 3: .973}.get(index, 1.0)
        low = .4 if index == 210 else 0
        potential.extend(np.linspace(0, high, 41)[1:])
        potential.extend(np.linspace(high, low, 41)[1:])
    potential = np.asarray(potential)
    run = CPRun("long-cp", "test", np.arange(potential.size, dtype=float), potential.copy(),
                CPMetadata(high_e=1, low_e=0, anodic_current_A=.01, cathodic_current_A=.01,
                           switch_polarity="Potential", segment=421))
    summary = analyze_cp_run(run)
    assert len(summary.segments) == 421
    assert {cycle.index for cycle in summary.cycles if cycle.completeness == "partial"} == incomplete
    expected = [index for index in range(1, 211) if index not in incomplete]
    assert [cycle.index for cycle in summary.complete_cycles] == expected

    dataset = Dataset(cp_runs=[run])
    style = BUILTIN_PRESETS["daily"]
    for concat in (False, True):
        figure = Figure()
        spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
            "cp_concat_enabled": concat,
            "cp_concat_cycle_mode": "cumulative",
            "capacity_percent_mode": "cycle",
            "capacity_percent_cycle": 2,
        })
        warnings = render_plot(figure, dataset, spec, style)
        assert any("已回退为实际容量/电容值" in warning for warning in warnings)
        assert any("Cycle 210：" in warning for warning in warnings)
        for axis in figure.axes:
            for line in axis.lines:
                assert list(line.get_xdata()) == expected
                assert np.isfinite(line.get_ydata()).all()
        assert figure.axes[0].lines and not figure.axes[0].texts

    figure = Figure()
    warnings = render_plot(figure, dataset, PlotSpec("cp_gcd", [run.run_id]), style)
    assert any("开头放电段" in warning for warning in warnings)
    assert any("Cycle 2：" in warning for warning in warnings)
    line = figure.axes[0].lines[0]
    visible = np.zeros(potential.size, dtype=bool)
    for cycle in summary.complete_cycles:
        visible[cycle.charge.start_index : cycle.discharge.end_index + 1] = True
    np.testing.assert_array_equal(line.get_xdata(), run.time)
    np.testing.assert_array_equal(line.get_ydata()[visible], potential[visible])
    assert np.isnan(line.get_ydata()[~visible]).all()
    np.testing.assert_array_equal(run.potential, potential)


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
    assert any("IR 降留空" in warning for warning in warnings)
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
    assert any("IR 降留空" in warning for warning in warnings)
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
    assert any("IR 降留空" in warning for warning in warnings)
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
