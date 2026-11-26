# -*- coding: utf-8 -*-
"""Shared CP cycle-value helpers for concatenation, percentages and UI previews.

The functions in this module deliberately have no Qt or Matplotlib imports.
They convert one ``CPRunSummary`` cycle into the renderer's base units
(mAh / F after optional area or mass normalization) so that the plot renderer
and the analysis-options panel use exactly the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from cvanalysis.analysis.cp import CPCycle, CPRunSummary
from cvanalysis.domain.models import CPRun


@dataclass(frozen=True)
class CPCycleValue:
    """One CP cycle in the renderer's base unit (mAh or F, optionally normalized)."""

    index: int
    charge: float
    discharge: float
    mean: float
    efficiency_pct: float


@dataclass(frozen=True)
class CPConcatEntry:
    """A run participating in one concatenated capacity-cycle plot."""

    run: CPRun
    summary: CPRunSummary
    start: int
    end: int
    offset: int

    @property
    def run_id(self) -> str:
        return self.run.run_id

    @property
    def included_cycles(self) -> list[CPCycle]:
        return [
            cycle
            for cycle in self.summary.complete_cycles
            if self.start <= cycle.index <= self.end
        ]

    @property
    def included_count(self) -> int:
        return len(self.included_cycles)


@dataclass(frozen=True)
class CPReferenceValue:
    """A unified 100% reference resolved from one displayed cycle."""

    run_id: str
    cycle_index: int
    charge: float
    discharge: float
    mean: float


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float("nan")
    return number if np.isfinite(number) else float("nan")


def _capacity_divisor(run: CPRun, normalization: str) -> float:
    if normalization == "area":
        area = run.params.area_cm2
        if area and np.isfinite(area) and area > 0:
            return float(area)
        return float("nan")
    if normalization == "mass":
        mass = run.params.mass_mg
        if mass and np.isfinite(mass) and mass > 0:
            return float(mass) * 1e-3
        return float("nan")
    return 1.0


def _cycle_branch_value(
    cycle: CPCycle,
    branch: str,
    run: CPRun,
    *,
    quantity: str,
    normalization: str,
    include_holds: bool,
) -> float:
    if branch == "charge":
        raw = cycle.charge_capacity_with_holds_C if include_holds else cycle.charge_capacity_C
        segment = cycle.charge
    else:
        raw = cycle.discharge_capacity_with_holds_C if include_holds else cycle.discharge_capacity_C
        segment = cycle.discharge
    value = _finite(raw)
    if not np.isfinite(value):
        return float("nan")
    divisor = _capacity_divisor(run, normalization)
    if not np.isfinite(divisor) or divisor <= 0:
        return float("nan")
    value = value / divisor / 3.6
    if quantity == "capacitance":
        potential = np.asarray(segment.potential_V, dtype=float)
        if potential.size < 2:
            return float("nan")
        delta = abs(float(potential[-1] - potential[0]))
        if not np.isfinite(delta) or delta <= 0:
            return float("nan")
        value = value * 3.6 / delta
    return value


def cp_cycle_values(
    run: CPRun,
    summary: CPRunSummary,
    *,
    quantity: str = "capacity",
    normalization: str = "none",
    include_holds: bool = False,
) -> list[CPCycleValue]:
    """Return values for complete cycles in mAh / F base units for one run."""
    values: list[CPCycleValue] = []
    for cycle in summary.complete_cycles:
        charge = _cycle_branch_value(
            cycle,
            "charge",
            run,
            quantity=quantity,
            normalization=normalization,
            include_holds=include_holds,
        )
        discharge = _cycle_branch_value(
            cycle,
            "discharge",
            run,
            quantity=quantity,
            normalization=normalization,
            include_holds=include_holds,
        )
        mean = (
            (charge + discharge) / 2.0
            if np.isfinite(charge) and np.isfinite(discharge)
            else float("nan")
        )
        efficiency = _finite(
            cycle.coulombic_efficiency_with_holds_pct
            if include_holds
            else cycle.coulombic_efficiency_pct
        )
        values.append(
            CPCycleValue(
                index=int(cycle.index),
                charge=charge,
                discharge=discharge,
                mean=mean,
                efficiency_pct=efficiency,
            )
        )
    return values


def _coerce_limit(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _range_pair(raw: Any) -> tuple[int | None, int | None]:
    if isinstance(raw, Mapping):
        return _coerce_limit(raw.get("start")), _coerce_limit(raw.get("end"))
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return _coerce_limit(raw[0]), _coerce_limit(raw[1])
    return None, None


def normalize_cp_concat_config(
    runs: Sequence[CPRun],
    summaries: Mapping[str, CPRunSummary],
    order: Any = None,
    ranges: Any = None,
) -> tuple[list[str], dict[str, dict[str, int]]]:
    """Normalize a saved concatenation order and inclusive cycle ranges.

    Missing runs are appended in plot order; unknown runs are dropped.
    Invalid or missing ranges fall back to the full cycle range.  ``start``
    and ``end`` are clamped to the cycles that actually exist.
    """
    by_id = {run.run_id: run for run in runs}
    selected_order = [run.run_id for run in runs if run.run_id in by_id]
    normalized_order: list[str] = []
    if isinstance(order, (list, tuple)):
        for value in order:
            run_id = str(value) if value is not None else ""
            if run_id in by_id and run_id not in normalized_order:
                normalized_order.append(run_id)
    for run_id in selected_order:
        if run_id not in normalized_order:
            normalized_order.append(run_id)

    normalized_ranges: dict[str, dict[str, int]] = {}
    raw_ranges = ranges if isinstance(ranges, Mapping) else {}
    for run_id in normalized_order:
        summary = summaries.get(run_id)
        count = len(summary.cycles) if summary is not None else 0
        if count <= 0:
            normalized_ranges[run_id] = {"start": 1, "end": 0}
            continue
        start, end = _range_pair(raw_ranges.get(run_id))
        if start is None or end is None:
            start, end = 1, count
        start = min(max(start, 1), count)
        end = min(max(end, 1), count)
        if start > end:
            start, end = 1, count
        normalized_ranges[run_id] = {"start": int(start), "end": int(end)}
    return normalized_order, normalized_ranges


def cp_concat_entries(
    runs: Sequence[CPRun],
    summaries: Mapping[str, CPRunSummary],
    order: Any = None,
    ranges: Any = None,
) -> list[CPConcatEntry]:
    """Build ordered entries with cumulative full-cycle offsets."""
    normalized_order, normalized_ranges = normalize_cp_concat_config(
        runs, summaries, order=order, ranges=ranges
    )
    by_id = {run.run_id: run for run in runs}
    entries: list[CPConcatEntry] = []
    offset = 0
    for run_id in normalized_order:
        run = by_id.get(run_id)
        summary = summaries.get(run_id)
        if run is None or summary is None:
            continue
        bounds = normalized_ranges[run_id]
        entries.append(
            CPConcatEntry(
                run=run,
                summary=summary,
                start=int(bounds["start"]),
                end=int(bounds["end"]),
                offset=offset,
            )
        )
        offset += len(summary.cycles)
    return entries


def find_cp_cycle_value(
    values: Sequence[CPCycleValue],
    cycle_index: Any,
) -> CPCycleValue | None:
    target = _coerce_limit(cycle_index)
    if target is None:
        return None
    return next((value for value in values if value.index == target), None)


def resolve_cp_unified_reference(
    entries: Sequence[CPConcatEntry],
    values_by_run: Mapping[str, Sequence[CPCycleValue]],
    run_id: Any,
    cycle_index: Any,
    *,
    require_displayed: bool = True,
) -> tuple[CPReferenceValue | None, str | None]:
    """Resolve a unified reference, requiring it to be inside the drawn range."""
    wanted_run = str(run_id) if run_id is not None else ""
    if not wanted_run:
        return None, "未选择统一 100% 参考文件"
    entry = next((item for item in entries if item.run_id == wanted_run), None)
    if entry is None:
        return None, "统一 100% 参考文件不在当前图的数据范围内"
    target = _coerce_limit(cycle_index)
    if target is None:
        return None, "未选择统一 100% 参考循环"
    if entry.included_count <= 0:
        return None, "统一 100% 参考文件在当前范围内没有可显示的循环"
    if require_displayed and not (entry.start <= target <= entry.end):
        return None, (
            f"统一 100% 参考 Cycle {target} 不在当前显示范围 "
            f"Cycle {entry.start}–{entry.end} 内"
        )
    value = find_cp_cycle_value(values_by_run.get(wanted_run, ()), target)
    if value is None:
        if any(cycle.index == target for cycle in entry.summary.cycles):
            return None, f"统一 100% 参考 Cycle {target} 不完整"
        return None, f"统一 100% 参考 Cycle {target} 不存在"
    return (
        CPReferenceValue(
            run_id=wanted_run,
            cycle_index=target,
            charge=value.charge,
            discharge=value.discharge,
            mean=value.mean,
        ),
        None,
    )


__all__ = [
    "CPConcatEntry",
    "CPCycleValue",
    "CPReferenceValue",
    "cp_concat_entries",
    "cp_cycle_values",
    "find_cp_cycle_value",
    "normalize_cp_concat_config",
    "resolve_cp_unified_reference",
]
