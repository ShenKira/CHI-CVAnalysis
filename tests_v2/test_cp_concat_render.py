# -*- coding: utf-8 -*-
"""Renderer behavior for concatenated CP capacity plots and unified 100% refs."""
from __future__ import annotations

import copy

import numpy as np
import pytest
from matplotlib.figure import Figure

from cvanalysis.analysis.cp import analyze_cp_run
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.cp_renderer import draw_cp_capacity
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


def _second_run(run, run_id: str = "cp_second", *, scale: float = 1.0):
    second = copy.deepcopy(run)
    second.run_id = run_id
    second.name = run_id
    if scale != 1.0:
        second.metadata.cathodic_current_A *= scale
        second.metadata.anodic_current_A *= scale
        analyze_cp_run(second, force=True)
    return second


def _concat_spec(
    runs,
    *,
    ranges=None,
    cycle_mode: str = "sequential",
    order=None,
    **options,
):
    analysis = {
        "cp_concat_enabled": True,
        "cp_concat_order": list(order if order is not None else (run.run_id for run in runs)),
        "cp_concat_ranges": dict(ranges or {}),
        "cp_concat_cycle_mode": cycle_mode,
        "cp_display_unit": "mAh",
        "show_efficiency": False,
        **options,
    }
    return PlotSpec("cp_capacity", [run.run_id for run in runs], analysis_options=analysis)


def _draw(spec, runs):
    figure = Figure()
    warnings = draw_cp_capacity(figure, Dataset(cp_runs=list(runs)), spec, STYLE)
    return figure, warnings


def test_concat_sequential_draws_one_line_per_branch(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    ranges = {second.run_id: {"start": 2, "end": 2}}
    spec = _concat_spec(
        [first, second],
        ranges=ranges,
        capacity_series="both",
        show_efficiency=True,
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)

    capacity_ax, efficiency_ax = figure.axes
    # One merged discharge line, one merged charge line, one merged CE line.
    assert len(capacity_ax.lines) == 2
    assert len(efficiency_ax.lines) == 1
    expected_x = [1, 2, 3]
    for line in [*capacity_ax.lines, *efficiency_ax.lines]:
        np.testing.assert_allclose(line.get_xdata(), expected_x)
    expected_discharge = [
        cycle.discharge_capacity_C / 3.6 for cycle in first.summary.cycles
    ] + [second.summary.cycles[1].discharge_capacity_C / 3.6]
    np.testing.assert_allclose(capacity_ax.lines[0].get_ydata(), expected_discharge)
    # The excluded second-run cycle 1 never contributes a point.
    assert len(capacity_ax.lines[0].get_ydata()) == 3

    legend = capacity_ax.get_legend()
    assert legend is not None
    assert {text.get_text() for text in legend.get_texts()} == {
        "拼接 Discharge",
        "拼接 Charge",
        "拼接 CE",
    }


def test_concat_cumulative_uses_full_cycle_offsets_and_leaves_gaps(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    ranges = {second.run_id: {"start": 2, "end": 2}}
    spec = _concat_spec(
        [first, second],
        ranges=ranges,
        cycle_mode="cumulative",
        capacity_series="discharge",
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)

    line = figure.axes[0].lines[0]
    # First run 1..2, then the full first-run count plus second-run cycle 2.
    np.testing.assert_allclose(line.get_xdata(), [1, 2, 4])
    expected = [
        cycle.discharge_capacity_C / 3.6 for cycle in first.summary.cycles
    ] + [second.summary.cycles[1].discharge_capacity_C / 3.6]
    np.testing.assert_allclose(line.get_ydata(), expected)


@pytest.mark.parametrize("series", ["both", "mean"])
def test_concat_unified_reference_from_second_run_cycle(synthetic_cp_run, series):
    first = synthetic_cp_run
    second = _second_run(first, scale=2.0)
    spec = _concat_spec(
        [first, second],
        capacity_series=series,
        capacity_percent_mode="unified",
        capacity_percent_reference_run_id=second.run_id,
        capacity_percent_reference_cycle=2,
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)

    reference_x = len(first.summary.cycles) + 2
    lines = figure.axes[0].lines
    if series == "both":
        assert len(lines) == 2
        positions = [
            list(np.asarray(line.get_xdata(), dtype=float)).index(reference_x)
            for line in lines
        ]
        assert all(line.get_ydata()[position] == pytest.approx(100.0)
                   for line, position in zip(lines, positions))
        # The same second-file reference also normalizes the first file.
        expected = (
            first.summary.cycles[0].discharge_capacity_C
            / second.summary.cycles[1].discharge_capacity_C
            * 100.0
        )
        assert lines[0].get_ydata()[0] == pytest.approx(expected)
    else:
        assert len(lines) == 1
        position = list(np.asarray(lines[0].get_xdata(), dtype=float)).index(reference_x)
        assert lines[0].get_ydata()[position] == pytest.approx(100.0)
        expected = (
            first.summary.cycles[0].discharge_capacity_C
            + first.summary.cycles[0].charge_capacity_C
        ) / (
            second.summary.cycles[1].discharge_capacity_C
            + second.summary.cycles[1].charge_capacity_C
        ) * 100.0
        assert lines[0].get_ydata()[0] == pytest.approx(expected)
    assert "%" in figure.axes[0].get_ylabel()


def test_concat_unified_reference_outside_range_falls_back_to_absolute(
    synthetic_cp_run,
):
    first = synthetic_cp_run
    second = _second_run(first)
    spec = _concat_spec(
        [first, second],
        ranges={second.run_id: {"start": 1, "end": 1}},
        capacity_series="discharge",
        capacity_percent_mode="unified",
        capacity_percent_reference_run_id=second.run_id,
        capacity_percent_reference_cycle=2,
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings
    assert any("100%" in warning or "参考" in warning for warning in warnings)
    assert figure.axes[0].lines
    assert "%" not in figure.axes[0].get_ylabel()
    assert "mAh" in figure.axes[0].get_ylabel()


def test_unified_reference_works_without_concatenation(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "show_efficiency": False,
        "capacity_series": "discharge",
        "capacity_percent_mode": "unified",
        "capacity_percent_reference_run_id": run.run_id,
        "capacity_percent_reference_cycle": 1,
    })
    figure, warnings = _draw(spec, [run])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    assert figure.axes[0].lines[0].get_ydata()[0] == pytest.approx(100.0)
    assert "%" in figure.axes[0].get_ylabel()


def test_concat_custom_legend_text_overrides_defaults(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    spec = _concat_spec(
        [first, second],
        capacity_series="both",
        show_efficiency=True,
        cp_legend_discharge="{ }",
        cp_legend_charge="Merged charge [{unit}]",
        cp_legend_efficiency="Merged CE",
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    legend = figure.axes[0].get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == [
        "Merged charge [mAh]",
        "Merged CE",
    ]


def test_single_run_absolute_drawing_is_unchanged(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "show_efficiency": False,
        "capacity_series": "both",
        "cp_display_unit": "mAh",
    })
    figure, warnings = _draw(spec, [run])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    lines = figure.axes[0].lines
    assert len(lines) == 2
    expected_x = [cycle.index for cycle in run.summary.cycles]
    np.testing.assert_allclose(lines[0].get_xdata(), expected_x)
    np.testing.assert_allclose(lines[1].get_xdata(), expected_x)
    np.testing.assert_allclose(
        lines[0].get_ydata(),
        [cycle.discharge_capacity_C / 3.6 for cycle in run.summary.cycles],
    )
    np.testing.assert_allclose(
        lines[1].get_ydata(),
        [cycle.charge_capacity_C / 3.6 for cycle in run.summary.cycles],
    )
    assert "mAh" in figure.axes[0].get_ylabel()
    assert "%" not in figure.axes[0].get_ylabel()


@pytest.mark.parametrize("mode", ["manual", "cycle"])
def test_manual_and_cycle_percent_modes_work_with_concat(synthetic_cp_run, mode):
    first = synthetic_cp_run
    second = _second_run(first)
    options = {
        "capacity_series": "discharge",
        "capacity_percent_mode": mode,
    }
    if mode == "manual":
        options.update(
            capacity_percent_reference=first.summary.cycles[0].discharge_capacity_C / 3.6,
            capacity_percent_reference_unit="mAh",
        )
    else:
        options["capacity_percent_cycle"] = 2
    spec = _concat_spec(
        [first, second],
        ranges={second.run_id: {"start": 2, "end": 2}},
        **options,
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    line = figure.axes[0].lines[0]
    assert len(line.get_xdata()) == 3
    if mode == "manual":
        assert line.get_ydata()[0] == pytest.approx(100.0)
    else:
        # Both runs use their own cycle 2 reference.
        assert line.get_ydata()[1] == pytest.approx(100.0)
        assert line.get_ydata()[2] == pytest.approx(100.0)
    assert "%" in figure.axes[0].get_ylabel()


def test_concat_cycle_reference_can_lie_outside_displayed_range(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    spec = _concat_spec(
        [first, second],
        ranges={second.run_id: {"start": 1, "end": 1}},
        capacity_series="discharge",
        capacity_percent_mode="cycle",
        capacity_percent_cycle=2,
    )
    figure, warnings = _draw(spec, [first, second])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    line = figure.axes[0].lines[0]
    # First run cycles 1-2 plus second run cycle 1 only.
    np.testing.assert_allclose(line.get_xdata(), [1, 2, 3])
    assert line.get_ydata()[1] == pytest.approx(100.0)
    expected = (
        second.summary.cycles[0].discharge_capacity_C
        / second.summary.cycles[1].discharge_capacity_C
        * 100.0
    )
    assert line.get_ydata()[2] == pytest.approx(expected)
    assert "%" in figure.axes[0].get_ylabel()
