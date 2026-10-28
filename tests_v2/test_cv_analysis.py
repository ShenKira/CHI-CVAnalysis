# -*- coding: utf-8 -*-
import numpy as np
import pytest
from types import SimpleNamespace

from cvanalysis.analysis.cv import (
    analyze_cv_run,
    collect_scan_rate_points,
    dunn_analysis,
    dunn_fraction_vs_scan_rate,
    fit_b_value,
    scan_window_warning,
    trasatti_analysis,
)
from cvanalysis.domain.errors import AnalysisError


def test_cycle_segmentation_and_capacitance(cv_file_factory):
    path = cv_file_factory("cv.txt", scan_rate=0.1, capacitance=1e-4)
    from cvanalysis.io.registry import parse_file

    run = parse_file(path).runs[0]
    summary = analyze_cv_run(run)
    assert len(run.cycles) == 2
    assert summary.valid_cycles == 2
    assert summary.mean_capacitance_F == pytest.approx(1e-4, rel=1e-6)
    assert summary.sd_capacitance_F == pytest.approx(0.0, abs=1e-12)
    for cycle in run.cycles:
        assert cycle.branch_up.shape[0] >= 2 and cycle.branch_down.shape[0] >= 2
        assert cycle.area_C == pytest.approx(2e-5, rel=1e-6)


def test_scan_rate_points_and_b_value(synthetic_cv_runs):
    points = collect_scan_rate_points(synthetic_cv_runs, target_voltage=0.5)
    assert len(points) == 3
    for point in points:
        expected = 1e-4 * point.scan_rate
        assert point.current_abs_A == pytest.approx(expected, rel=1e-6)
        assert point.capacitance_F == pytest.approx(1e-4, rel=1e-6)
    result = fit_b_value(points)
    assert result.slope == pytest.approx(1.0, abs=1e-6)
    assert result.r2 == pytest.approx(1.0, abs=1e-9)


def test_partial_first_cycle_is_flagged_without_exclusion(cv_file_factory):
    path = cv_file_factory("partial.txt", scan_rate=0.1)
    lines = path.read_text(encoding="utf-8").splitlines()
    header = next(
        index for index, line in enumerate(lines) if line.startswith("Potential/V")
    )
    data = []
    started = False
    for line in lines[header + 1 :]:
        if not line.strip():
            continue
        potential = float(line.split(",")[0])
        if not started and potential < 0.5:
            continue
        started = True
        data.append(line)
    path.write_text("\n".join([*lines[: header + 1], *data]) + "\n", encoding="utf-8")
    from cvanalysis.io.registry import parse_file

    run = parse_file(path).runs[0]
    summary = analyze_cv_run(run)
    assert run.cycles[0].is_partial
    assert any("不完整循环" in warning for warning in summary.warnings)
    # The partial cycle still participates in the default statistics.
    assert summary.valid_cycles == len([cycle for cycle in run.cycles if cycle.valid])


def test_outlier_threshold_mode_is_optional(synthetic_cv_runs):
    from cvanalysis.analysis.cv import summarize_run

    run = synthetic_cv_runs[0]
    while len(run.cycles) < 3:
        import copy

        run.cycles.append(copy.deepcopy(run.cycles[0]))
    for index, (cycle, value) in enumerate(zip(run.cycles, [1.0, 1.0, 10.0]), 1):
        cycle.index = index
        cycle.capacitance_F = value
        cycle.is_outlier = False
    trimmed = summarize_run(run, outlier_count=1)
    assert trimmed.outlier_cycles == [3]
    assert trimmed.mean_capacitance_F == pytest.approx(1.0)
    no_threshold = summarize_run(run, outlier_count=1, outlier_z=2.0)
    assert no_threshold.outlier_cycles == []
    assert no_threshold.mean_capacitance_F == pytest.approx(4.0)
    threshold = summarize_run(run, outlier_count=1, outlier_z=1.0)
    assert threshold.outlier_cycles == [3]
    assert threshold.mean_capacitance_F == pytest.approx(1.0)


def test_b_value_current_modes_use_requested_branch(cv_file_factory):
    from cvanalysis.io.registry import load_files
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis

    capacitance = 1e-4
    offset = 2e-4
    paths = [
        cv_file_factory(
            f"offset_{rate:g}.txt",
            scan_rate=rate,
            capacitance=capacitance,
            offset_current=offset,
        )
        for rate in (0.01, 0.02, 0.05)
    ]
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())

    up = collect_scan_rate_points(dataset.cv_runs, target_voltage=0.5, current_mode="up")
    down = collect_scan_rate_points(
        dataset.cv_runs, target_voltage=0.5, current_mode="down"
    )
    average = collect_scan_rate_points(
        dataset.cv_runs, target_voltage=0.5, current_mode="absolute"
    )
    for up_point, down_point, average_point in zip(up, down, average):
        rate = up_point.scan_rate
        assert up_point.current_abs_A == pytest.approx(capacitance * rate + offset)
        assert down_point.current_abs_A == pytest.approx(abs(-capacitance * rate + offset))
        assert average_point.current_abs_A == pytest.approx(
            (up_point.current_abs_A + down_point.current_abs_A) / 2.0
        )
    assert fit_b_value(up).slope != pytest.approx(fit_b_value(average).slope)


def test_trasatti_ideal_capacitor(synthetic_cv_runs):
    points = collect_scan_rate_points(synthetic_cv_runs)
    result = trasatti_analysis(points)
    assert all(point.integration_width_V == pytest.approx(1.0) for point in points)
    # Ideal capacitor: all charge is capacitive, so the intercept equals the
    # charge at every scan rate and the diffusion slope is ~0.
    assert result.q_capacitive_C == pytest.approx(1e-4, rel=1e-5)
    assert result.capacitive_fraction_low_rate == pytest.approx(1.0, abs=1e-5)
    assert result.q_total_C == pytest.approx(1e-4, rel=1e-5)
    assert result.capacitive_fraction_total == pytest.approx(1.0, abs=1e-5)


def test_trasatti_uses_actual_integration_width(synthetic_cv_runs):
    from dataclasses import replace

    points = collect_scan_rate_points(synthetic_cv_runs)
    narrowed = [
        replace(point, integration_width_V=0.5, voltage_window=1.0)
        for point in points
    ]
    result = trasatti_analysis(narrowed)
    assert result.charges_C == pytest.approx([5e-5] * len(narrowed))
    assert result.q_capacitive_C == pytest.approx(5e-5)
    assert result.q_total_C == pytest.approx(5e-5)


def test_trasatti_uses_lowest_rate_for_unsorted_points(synthetic_cv_runs):
    points = collect_scan_rate_points(synthetic_cv_runs)
    ordered = trasatti_analysis(points)
    shuffled = trasatti_analysis(list(reversed(points)))
    assert shuffled.capacitive_fraction_low_rate == pytest.approx(
        ordered.capacitive_fraction_low_rate
    )
    assert shuffled.q_diffusive_low_rate_C == pytest.approx(
        ordered.q_diffusive_low_rate_C
    )


def test_scan_window_warning_for_mixed_windows(cv_file_factory):
    from cvanalysis.io.registry import load_files
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis

    paths = [
        cv_file_factory("window_1.txt", scan_rate=0.01, high=1.0, low=0.0),
        cv_file_factory("window_2.txt", scan_rate=0.02, high=2.0, low=0.0),
    ]
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    points = collect_scan_rate_points(dataset.cv_runs)
    warning = scan_window_warning(points)
    assert warning is not None
    assert "窗口不一致" in warning


def test_dunn_ideal_capacitor(synthetic_cv_runs):
    result = dunn_analysis(synthetic_cv_runs, normalization="none", selected_scan_rate=0.02)
    assert result.capacitive_fraction == pytest.approx(1.0, abs=1e-5)
    assert np.max(np.abs(result.diffusive_current)) < 1e-12


def test_scan_rate_analysis_requires_multiple_rates(cv_file_factory):
    path = cv_file_factory("one.txt", scan_rate=0.1)
    from cvanalysis.io.registry import parse_file

    run = parse_file(path).runs[0]
    analyze_cv_run(run)
    points = collect_scan_rate_points([run], target_voltage=0.5)
    with pytest.raises(AnalysisError):
        fit_b_value(points)
    with pytest.raises(AnalysisError):
        trasatti_analysis(points)
    with pytest.raises(AnalysisError):
        dunn_analysis([run])


def test_cycle_selection_restricts_scan_rate_points(synthetic_cv_runs):
    run = synthetic_cv_runs[0]
    points = collect_scan_rate_points(
        [run],
        target_voltage=0.5,
        cycle_selection={run.run_id: [1]},
    )
    assert len(points) == 1
    assert points[0].valid_cycles == 1
    with pytest.raises(AnalysisError):
        dunn_analysis([run], cycle_selection={run.run_id: []})


def test_area_and_mass_normalization(cv_file_factory):
    from cvanalysis.domain.models import ElectrodeParams
    from cvanalysis.io.registry import parse_file

    path = cv_file_factory("normalized.txt", scan_rate=0.1, capacitance=1e-4)
    run = parse_file(path).runs[0]
    run.params = ElectrodeParams(area_cm2=0.5, mass_mg=2.0)
    summary = analyze_cv_run(run)
    assert summary.mean_cap_per_area == pytest.approx(2e-4, rel=1e-6)
    assert summary.mean_cap_per_mass == pytest.approx(0.05, rel=1e-6)


def test_dunn_fraction_vs_scan_rate_ideal_capacitor(synthetic_cv_runs):
    result = dunn_fraction_vs_scan_rate(synthetic_cv_runs)
    assert list(result.scan_rates) == [0.01, 0.02, 0.05]
    assert result.capacitive_fraction == pytest.approx([1.0, 1.0, 1.0], abs=1e-5)
    assert result.diffusive_fraction == pytest.approx([0.0, 0.0, 0.0], abs=1e-5)


def test_dunn_contributions_use_the_standard_transformed_regression():
    potential = np.linspace(0.0, 1.0, 31)
    rates = np.asarray([0.01, 0.04, 0.09])
    k1 = -0.2 + 0.1 * potential
    k2 = 0.8 - 0.15 * potential
    currents = rates[:, None] * k1 + np.sqrt(rates)[:, None] * k2
    currents += np.asarray([0.0, 0.01, -0.006])[:, None] * np.cos(np.pi * potential)[None, :]
    runs = [
        SimpleNamespace(
            run_id=f"run-{index}",
            metadata=SimpleNamespace(scan_rate=rate),
            cycles=[SimpleNamespace(valid=True, branch_up=np.column_stack((potential, row)))],
        )
        for index, (rate, row) in enumerate(zip(rates, currents))
    ]

    result = dunn_fraction_vs_scan_rate(runs)

    design = np.column_stack((np.sqrt(rates), np.ones_like(rates)))
    coefficients, *_ = np.linalg.lstsq(design, currents / np.sqrt(rates)[:, None], rcond=None)
    capacitive = np.abs(coefficients[0][None, :] * rates[:, None])
    diffusive = np.abs(coefficients[1][None, :] * np.sqrt(rates)[:, None])
    cap_area = np.trapezoid(capacitive, potential, axis=1)
    diff_area = np.trapezoid(diffusive, potential, axis=1)
    expected = cap_area / (cap_area + diff_area)
    assert result.capacitive_fraction == pytest.approx(expected)
    assert result.diffusive_fraction == pytest.approx(1.0 - expected)
    single_rate = dunn_analysis(runs, selected_scan_rate=float(rates[1]))
    assert single_rate.capacitive_fraction == pytest.approx(result.capacitive_fraction[1])
    grid = np.linspace(float(potential[0]), float(potential[-1]), 200)
    sampled_currents = np.vstack([np.interp(grid, potential, row) for row in currents])
    coefficient_grid = np.vstack([np.interp(grid, potential, row) for row in coefficients])
    transformed_prediction = design @ coefficient_grid
    transformed = sampled_currents / np.sqrt(rates)[:, None]
    ss_res = np.sum((transformed - transformed_prediction) ** 2, axis=0)
    ss_tot = np.sum((transformed - transformed.mean(axis=0)) ** 2, axis=0)
    assert result.mean_r2 == pytest.approx(np.mean(1.0 - ss_res / ss_tot))
