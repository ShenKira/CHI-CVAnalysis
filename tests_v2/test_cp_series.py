# -*- coding: utf-8 -*-
"""Pure helpers shared by CP concatenation renderer and UI."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from cvanalysis.analysis.cp_series import (
    cp_concat_entries,
    cp_cycle_values,
    find_cp_cycle_value,
    normalize_cp_concat_config,
    resolve_cp_unified_reference,
)


def _second_run(run, run_id="cp_second"):
    second = copy.deepcopy(run)
    second.run_id = run_id
    second.name = "cp_second"
    return second


def test_cycle_values_match_capacity_and_capacitance(synthetic_cp_run):
    run = synthetic_cp_run
    values = cp_cycle_values(run, run.summary)
    assert len(values) == len(run.summary.cycles)
    for value, cycle in zip(values, run.summary.cycles):
        assert value.charge == pytest.approx(cycle.charge_capacity_C / 3.6)
        assert value.discharge == pytest.approx(cycle.discharge_capacity_C / 3.6)
        assert value.mean == pytest.approx(
            (cycle.charge_capacity_C + cycle.discharge_capacity_C) / 2 / 3.6
        )
        assert value.efficiency_pct == pytest.approx(
            cycle.coulombic_efficiency_pct
        )

    capacitance = cp_cycle_values(run, run.summary, quantity="capacitance")
    for value, cycle in zip(capacitance, run.summary.cycles):
        delta = abs(
            float(cycle.discharge.potential_V[-1] - cycle.discharge.potential_V[0])
        )
        assert value.discharge == pytest.approx(cycle.discharge_capacity_C / delta)


def test_cycle_values_include_holds_and_normalization(synthetic_cp_run):
    run = synthetic_cp_run
    run.params.area_cm2 = 2.0
    run.params.mass_mg = 4.0
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    from cvanalysis.domain.models import Dataset

    refresh_analysis(Dataset(cp_runs=[run]), AnalysisSettings(), force=True)
    values = cp_cycle_values(
        run, run.summary, normalization="mass", include_holds=True
    )
    cycle = run.summary.cycles[0]
    assert values[0].charge == pytest.approx(
        cycle.charge_capacity_with_holds_C / (4.0 * 1e-3) / 3.6
    )
    assert values[0].discharge == pytest.approx(
        cycle.discharge_capacity_with_holds_C / (4.0 * 1e-3) / 3.6
    )

    areal = cp_cycle_values(run, run.summary, normalization="area")
    assert areal[0].discharge == pytest.approx(cycle.discharge_capacity_C / 2.0 / 3.6)


def test_normalize_config_clamps_and_keeps_order(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    summaries = {first.run_id: first.summary, second.run_id: second.summary}
    order, ranges = normalize_cp_concat_config(
        [first, second],
        summaries,
        order=[second.run_id],
        ranges={second.run_id: {"start": 2, "end": 999}},
    )
    assert order == [second.run_id, first.run_id]
    assert ranges[second.run_id] == {
        "start": 2,
        "end": len(second.summary.cycles),
    }
    assert ranges[first.run_id] == {"start": 1, "end": len(first.summary.cycles)}

    _, invalid = normalize_cp_concat_config(
        [first, second],
        summaries,
        ranges={first.run_id: {"start": 2, "end": 1}},
    )
    assert invalid[first.run_id] == {
        "start": 1,
        "end": len(first.summary.cycles),
    }


def test_concat_entries_offset_and_reference_range(synthetic_cp_run):
    first = synthetic_cp_run
    second = _second_run(first)
    summaries = {first.run_id: first.summary, second.run_id: second.summary}
    entries = cp_concat_entries(
        [first, second],
        summaries,
        order=[first.run_id, second.run_id],
        ranges={second.run_id: {"start": 2, "end": 2}},
    )
    assert [entry.run_id for entry in entries] == [first.run_id, second.run_id]
    assert entries[1].offset == len(first.summary.cycles)
    assert entries[1].included_count == 1
    expected_x = entries[1].offset + 2
    assert expected_x == len(first.summary.cycles) + 2

    values = {first.run_id: cp_cycle_values(first, first.summary),
              second.run_id: cp_cycle_values(second, second.summary)}
    reference, error = resolve_cp_unified_reference(
        entries, values, second.run_id, 2
    )
    assert error is None and reference is not None
    assert reference.cycle_index == 2

    missing, error = resolve_cp_unified_reference(
        entries, values, second.run_id, 1
    )
    assert missing is None and "显示范围" in (error or "")

    missing, error = resolve_cp_unified_reference(
        entries, values, "not_a_run", 1
    )
    assert missing is None and error

    cycle_value = find_cp_cycle_value(values[first.run_id], 1)
    assert cycle_value is not None and cycle_value.index == 1
    assert find_cp_cycle_value(values[first.run_id], "bad") is None
