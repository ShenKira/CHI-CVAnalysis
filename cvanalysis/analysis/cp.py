# -*- coding: utf-8 -*-
"""Chronopotentiometry / GCD analysis.

The CHI export stores the active-current potential-time curve separately from
the optional high/low potential-hold current block.  This module:

* splits the hold block into individual records;
* detects monotonic charge/discharge windows in the active data;
* optionally inserts the hold intervals into the potential-time series;
* pairs charge -> following discharge windows into GCD cycles;
* computes capacity, specific capacity, coulombic efficiency, IR drop and
  energy metrics without any Qt dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cvanalysis.domain.models import CPRun


try:
    _trapz = np.trapezoid
except AttributeError:
    _trapz = np.trapz


@dataclass
class CPHoldRecord:
    index: int
    time_s: np.ndarray
    current_A: np.ndarray
    duration_s: float
    mean_current_A: float

    @property
    def polarity(self) -> int:
        return int(np.sign(self.mean_current_A))

    @property
    def capacity_C(self) -> float:
        if self.time_s.size < 2:
            return float("nan")
        return float(abs(_trapz(self.current_A, self.time_s)))

    @property
    def kind(self) -> str:
        if self.polarity > 0:
            return "high"
        if self.polarity < 0:
            return "low"
        return "hold"


@dataclass
class CPSegment:
    index: int
    start_index: int
    end_index: int
    time_s: np.ndarray
    potential_V: np.ndarray
    current_A: float
    direction: int
    hold: CPHoldRecord | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "charge" if self.direction > 0 else "discharge"

    @property
    def label(self) -> str:
        return "充电" if self.direction > 0 else "放电"

    @property
    def duration_s(self) -> float:
        if self.time_s.size < 2:
            return 0.0
        return max(0.0, float(self.time_s[-1] - self.time_s[0]))

    @property
    def valid(self) -> bool:
        return (
            self.time_s.size >= 2
            and np.isfinite(self.current_A)
            and self.current_A != 0
            and self.duration_s > 0
        )

    @property
    def capacity_C(self) -> float:
        if not self.valid:
            return float("nan")
        return abs(float(self.current_A)) * self.duration_s

    @property
    def hold_capacity_C(self) -> float:
        if self.hold is None:
            return 0.0
        value = self.hold.capacity_C
        return value if np.isfinite(value) else 0.0

    @property
    def capacity_with_holds_C(self) -> float:
        base = self.capacity_C
        if not np.isfinite(base):
            return base
        return base + self.hold_capacity_C

    @property
    def mean_potential_V(self) -> float:
        if self.potential_V.size == 0:
            return float("nan")
        return float(np.nanmean(self.potential_V))

    @property
    def start_potential_V(self) -> float:
        return float(self.potential_V[0]) if self.potential_V.size else float("nan")

    @property
    def end_potential_V(self) -> float:
        return float(self.potential_V[-1]) if self.potential_V.size else float("nan")

    @property
    def energy_J(self) -> float:
        if not self.valid:
            return float("nan")
        current = np.full_like(self.time_s, self.current_A, dtype=float)
        return float(abs(_trapz(self.potential_V * current, self.time_s)))

    @property
    def hold_energy_J(self) -> float:
        if self.hold is None:
            return 0.0
        potential = self.end_potential_V
        if not np.isfinite(potential):
            return 0.0
        return float(abs(potential * _trapz(self.hold.current_A, self.hold.time_s)))

    @property
    def energy_with_holds_J(self) -> float:
        base = self.energy_J
        if not np.isfinite(base):
            return base
        return base + self.hold_energy_J


@dataclass
class CPCycle:
    index: int
    charge: CPSegment
    discharge: CPSegment
    charge_capacity_C: float
    discharge_capacity_C: float
    charge_capacity_with_holds_C: float
    discharge_capacity_with_holds_C: float
    coulombic_efficiency_pct: float
    coulombic_efficiency_with_holds_pct: float
    specific_capacity_C_g: float
    specific_capacity_mAh_g: float
    specific_capacity_with_holds_C_g: float
    specific_capacity_with_holds_mAh_g: float
    areal_capacity_C_cm2: float
    areal_capacity_mAh_cm2: float
    discharge_energy_Wh: float
    specific_energy_Wh_kg: float
    power_W_kg: float
    mean_discharge_potential_V: float
    ir_drop_V: float
    areal_capacity_with_holds_C_cm2: float = float("nan")
    areal_capacity_with_holds_mAh_cm2: float = float("nan")

    @property
    def valid(self) -> bool:
        return (
            np.isfinite(self.charge_capacity_C)
            and np.isfinite(self.discharge_capacity_C)
            and self.charge_capacity_C > 0
            and self.discharge_capacity_C > 0
        )


@dataclass
class CPRunSummary:
    cycles: list[CPCycle]
    segments: list[CPSegment]
    holds: list[CPHoldRecord]
    warnings: list[str] = field(default_factory=list)
    has_hold_data: bool = False
    completed_hold_count: int = 0
    mean_charge_capacity_C: float = float("nan")
    mean_discharge_capacity_C: float = float("nan")
    mean_discharge_capacity_with_holds_C: float = float("nan")
    mean_specific_capacity_C_g: float = float("nan")
    mean_specific_capacity_mAh_g: float = float("nan")
    mean_areal_capacity_C_cm2: float = float("nan")
    mean_areal_capacity_mAh_cm2: float = float("nan")
    mean_coulombic_efficiency_pct: float = float("nan")
    mean_coulombic_efficiency_with_holds_pct: float = float("nan")
    mean_discharge_energy_Wh: float = float("nan")
    mean_specific_energy_Wh_kg: float = float("nan")
    mean_power_W_kg: float = float("nan")
    mean_ir_drop_V: float = float("nan")
    mean_areal_capacity_with_holds_C_cm2: float = float("nan")
    mean_areal_capacity_with_holds_mAh_cm2: float = float("nan")

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def charge_segments(self) -> list[CPSegment]:
        return [segment for segment in self.segments if segment.direction > 0]

    @property
    def discharge_segments(self) -> list[CPSegment]:
        return [segment for segment in self.segments if segment.direction < 0]


@dataclass
class CPTimeSeries:
    time_s: np.ndarray
    potential_V: np.ndarray
    current_A: np.ndarray
    hold_mask: np.ndarray
    completed: bool
    warnings: list[str] = field(default_factory=list)


def _finite_mean(values) -> float:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    return float(np.mean(array)) if array.size else float("nan")


def _find_turns_fallback(potential: np.ndarray) -> list[int]:
    """Find turning points from direction changes when scipy is unavailable."""
    if potential.size < 3:
        return []
    diff = np.diff(potential)
    span = float(np.nanmax(potential) - np.nanmin(potential))
    if not np.isfinite(span) or span <= 0:
        return []
    epsilon = max(1e-12, span * 1e-9)
    signs = np.zeros_like(diff, dtype=int)
    last = 0
    for index, value in enumerate(diff):
        if value > epsilon:
            last = 1
        elif value < -epsilon:
            last = -1
        signs[index] = last
    turns: list[int] = []
    for index in range(1, len(signs)):
        if signs[index] != 0 and signs[index] != signs[index - 1]:
            turns.append(index)
    return turns


def _find_turns(potential: np.ndarray) -> list[int]:
    """Return well-separated turning-point indices without extra dependencies."""
    if potential.size < 3:
        return []
    span = float(np.nanmax(potential) - np.nanmin(potential))
    if not np.isfinite(span) or span <= 0:
        return []
    try:
        from scipy.signal import find_peaks

        prominence = max(1e-9, span * 0.04)
        peaks, _ = find_peaks(potential, prominence=prominence)
        troughs, _ = find_peaks(-potential, prominence=prominence)
    except Exception:
        return _find_turns_fallback(potential)
    raw: list[tuple[int, int]] = [(int(index), 1) for index in peaks]
    raw.extend((int(index), -1) for index in troughs)
    raw.sort()
    if not raw:
        return []

    # Flat high/low plateaus produce several adjacent extrema; merge them.
    min_gap = max(2, potential.size // 200)
    clusters: list[list[tuple[int, int]]] = []
    for item in raw:
        if clusters and item[0] - clusters[-1][-1][0] <= min_gap:
            clusters[-1].append(item)
        else:
            clusters.append([item])

    turns: list[int] = []
    for cluster in clusters:
        indices = [index for index, _ in cluster]
        values = potential[indices]
        if all(kind > 0 for _, kind in cluster):
            chosen = indices[int(np.argmax(values))]
        elif all(kind < 0 for _, kind in cluster):
            chosen = indices[int(np.argmin(values))]
        else:
            middle = float(np.nanmedian(potential))
            chosen = indices[int(np.argmax(np.abs(values - middle)))]
        if turns and chosen - turns[-1] <= min_gap:
            continue
        turns.append(chosen)
    return turns


def _split_hold_block(time_s: np.ndarray, current_A: np.ndarray) -> list[tuple[int, int]]:
    if time_s.size < 2:
        return []
    resets = np.where(np.diff(time_s) < -1e-9)[0] + 1
    base_starts = [0, *resets.tolist()]
    base_ends = [start - 1 for start in base_starts[1:]] + [time_s.size - 1]
    blocks: list[tuple[int, int]] = []
    for start, end in zip(base_starts, base_ends):
        if end <= start:
            continue
        signs = np.sign(current_A[start : end + 1])
        signs[signs == 0] = 1
        changes = np.where(np.diff(signs) != 0)[0]
        sub_starts = [start, *(start + changes + 1).tolist()]
        sub_ends = [start + int(change) for change in changes] + [end]
        for sub_start, sub_end in zip(sub_starts, sub_ends):
            if sub_end > sub_start:
                blocks.append((int(sub_start), int(sub_end)))
    return blocks


def split_hold_records(run: CPRun) -> list[CPHoldRecord]:
    """Split the optional hold block into individual high/low records."""
    if not run.has_hold_data:
        return []
    time_s = np.asarray(run.hold_time, dtype=float)
    current_A = np.asarray(run.hold_current, dtype=float)
    finite = np.isfinite(time_s) & np.isfinite(current_A)
    time_s = time_s[finite]
    current_A = current_A[finite]
    if time_s.size < 2:
        return []
    records: list[CPHoldRecord] = []
    dt = float(np.median(np.diff(time_s))) if time_s.size >= 2 else 0.0
    for start, end in _split_hold_block(time_s, current_A):
        block_t = time_s[start : end + 1]
        block_i = current_A[start : end + 1]
        if block_t.size < 2:
            continue
        span = float(block_t[-1] - block_t[0])
        mean_current = float(np.nanmean(block_i))
        polarity = int(np.sign(mean_current))
        nominal = (
            run.metadata.high_hold_s
            if polarity > 0
            else run.metadata.low_hold_s
            if polarity < 0
            else None
        )
        if nominal and nominal > 0 and abs(span - nominal) <= max(0.1, nominal * 0.05):
            duration = float(nominal)
        else:
            duration = span + max(0.0, dt)
        records.append(
            CPHoldRecord(
                index=len(records),
                time_s=block_t - block_t[0],
                current_A=block_i,
                duration_s=duration,
                mean_current_A=mean_current,
            )
        )
    return records


def _segment_windows(run: CPRun) -> list[tuple[int, int, int]]:
    """Return ``(start_index, end_index, direction)`` active windows."""
    potential = np.asarray(run.potential, dtype=float)
    if potential.size < 3:
        return []
    turns = _find_turns(potential)
    bounds = [0, *turns, potential.size - 1]
    windows: list[tuple[int, int, int]] = []
    for start, end in zip(bounds[:-1], bounds[1:]):
        if end - start < 2:
            continue
        delta = float(potential[end] - potential[start])
        direction = int(np.sign(delta))
        if direction == 0:
            slope = float(np.nanmedian(np.diff(potential[start : end + 1])))
            direction = int(np.sign(slope))
        if direction == 0:
            continue
        windows.append((int(start), int(end), direction))
    if not windows and potential.size >= 3:
        delta = float(potential[-1] - potential[0])
        direction = int(np.sign(delta))
        if direction:
            windows.append((0, potential.size - 1, direction))
    merged: list[tuple[int, int, int]] = []
    for start, end, direction in windows:
        if merged and direction == merged[-1][2] and start <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], end, direction)
        else:
            merged.append((start, end, direction))
    return merged


def _fallback_current(run: CPRun, holds: list[CPHoldRecord]) -> float | None:
    values = [
        abs(record.mean_current_A)
        for record in holds
        if np.isfinite(record.mean_current_A) and record.mean_current_A != 0
    ]
    if values:
        return float(np.median(values))
    return None


def _segment_current(
    run: CPRun,
    direction: int,
    fallback: float | None,
) -> tuple[float, str | None]:
    metadata = run.metadata
    value = metadata.anodic_current_A if direction > 0 else metadata.cathodic_current_A
    if value is None or not np.isfinite(value) or value == 0:
        value = metadata.cathodic_current_A if direction > 0 else metadata.anodic_current_A
    if value is None or not np.isfinite(value) or value == 0:
        if fallback is not None:
            return float(abs(fallback)), None
        return float("nan"), "缺少施加电流信息，无法计算容量"
    return float(abs(value)), None


def _merge_close_segments(segments: list[CPSegment]) -> list[CPSegment]:
    if len(segments) < 2:
        return segments
    merged: list[CPSegment] = []
    for segment in segments:
        if merged and segment.direction == merged[-1].direction:
            previous = merged[-1]
            start = previous.start_index
            end = segment.end_index
            if end - start < 3:
                continue
            current = previous.current_A if np.isfinite(previous.current_A) else segment.current_A
            previous = CPSegment(
                index=previous.index,
                start_index=start,
                end_index=end,
                time_s=np.concatenate([previous.time_s, segment.time_s]),
                potential_V=np.concatenate([previous.potential_V, segment.potential_V]),
                current_A=current,
                direction=previous.direction,
                hold=segment.hold or previous.hold,
                warnings=[*previous.warnings, *segment.warnings],
            )
            merged[-1] = previous
        else:
            merged.append(segment)
    for index, segment in enumerate(merged):
        segment.index = index
    return merged


def _assign_holds(
    run: CPRun,
    segments: list[CPSegment],
    holds: list[CPHoldRecord],
    warnings: list[str],
) -> dict[int, CPHoldRecord]:
    if not segments or not holds:
        return {}
    high = run.metadata.high_e
    low = run.metadata.low_e
    span = run.metadata.voltage_window or (
        float(np.nanmax(run.potential) - np.nanmin(run.potential))
        if run.potential.size
        else 0.0
    )
    tolerance = max(0.02, span * 0.05)
    expected: list[int] = []
    for segment in segments:
        end_v = segment.end_potential_V
        polarity = 0
        if high is not None and abs(end_v - high) <= tolerance:
            polarity = 1
        elif low is not None and abs(end_v - low) <= tolerance:
            polarity = -1
        expected.append(polarity)

    # CHI writes the hold block in acquisition order, so an equal-length block
    # normally maps one-to-one.  Keep that proven path when it does not
    # contradict the segment end potentials; otherwise rematch conservatively.
    if len(holds) == len(segments) and all(
        polarity == 0 or holds[index].polarity == polarity
        for index, polarity in enumerate(expected)
    ):
        return {index: holds[index] for index in range(len(segments))}

    assignments: dict[int, CPHoldRecord] = {}
    used: set[int] = set()
    # Resolve segments with a known expected polarity first so they cannot be
    # starved by segments for which the end potential is inconclusive.
    order = sorted(range(len(segments)), key=lambda index: expected[index] == 0)
    for index in order:
        polarity = expected[index]
        candidate = None
        if polarity:
            candidate = next(
                (
                    record
                    for record in holds
                    if record.index not in used and record.polarity == polarity
                ),
                None,
            )
        else:
            # Without high/low limits there is no physical check available;
            # retain the historical chronological fallback for such files.
            candidate = next((record for record in holds if record.index not in used), None)
        if candidate is not None:
            assignments[index] = candidate
            used.add(candidate.index)
    if len(used) < len(holds):
        warnings.append(
            f"保持段记录 {len(holds)} 条，实际匹配 {len(used)} 条；未匹配的保持段不会插入曲线"
        )
    return assignments


def build_segments(run: CPRun, *, warn: bool = True) -> tuple[list[CPSegment], list[CPHoldRecord], list[str]]:
    warnings: list[str] = []
    holds = split_hold_records(run)
    fallback = _fallback_current(run, holds)
    time_s = np.asarray(run.time, dtype=float)
    potential = np.asarray(run.potential, dtype=float)
    segments: list[CPSegment] = []
    for index, (start, end, direction) in enumerate(_segment_windows(run)):
        current, warning = _segment_current(run, direction, fallback)
        if warning and warning not in warnings:
            warnings.append(warning)
        segment = CPSegment(
            index=index,
            start_index=start,
            end_index=end,
            time_s=time_s[start : end + 1],
            potential_V=potential[start : end + 1],
            current_A=current,
            direction=direction,
        )
        segments.append(segment)
    segments = _merge_close_segments(segments)
    assignments = _assign_holds(run, segments, holds, warnings)
    for index, record in assignments.items():
        if 0 <= index < len(segments):
            segments[index].hold = record
    if holds and len(assignments) < len(segments):
        segments_without = len(segments) - len(assignments)
        warnings.append(f"{segments_without} 个充放电段没有对应的保持段记录")
    if warn:
        for message in warnings:
            run.add_warning(message)
    return segments, holds, warnings


def completed_cp_series(run: CPRun, *, complete_holds: bool = True) -> CPTimeSeries:
    """Build potential-time-current arrays, optionally inserting hold plateaus."""
    segments, holds, warnings = build_segments(run, warn=False)
    time_s = np.asarray(run.time, dtype=float)
    potential = np.asarray(run.potential, dtype=float)
    if not complete_holds or not holds:
        return CPTimeSeries(
            time_s=time_s.copy(),
            potential_V=potential.copy(),
            current_A=_active_current_array(run, segments),
            hold_mask=np.zeros(time_s.size, dtype=bool),
            completed=False,
            warnings=warnings,
        )

    times: list[np.ndarray] = []
    potentials: list[np.ndarray] = []
    currents: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    shift = 0.0
    completed = False
    high = run.metadata.high_e
    low = run.metadata.low_e
    span = run.metadata.voltage_window or (
        float(np.nanmax(potential) - np.nanmin(potential)) if potential.size else 0.0
    )
    tolerance = max(0.02, span * 0.05)
    for segment in segments:
        segment_time = time_s[segment.start_index : segment.end_index + 1] + shift
        segment_potential = potential[segment.start_index : segment.end_index + 1]
        current = segment.current_A if np.isfinite(segment.current_A) else float("nan")
        times.append(segment_time)
        potentials.append(segment_potential)
        currents.append(np.full(segment_time.size, current, dtype=float))
        masks.append(np.zeros(segment_time.size, dtype=bool))
        if segment.hold is None:
            continue
        record = segment.hold
        relative = record.time_s
        if relative.size < 2:
            continue
        hold_time = segment_time[-1] + relative
        plateau = segment_potential[-1]
        if high is not None and abs(plateau - high) <= tolerance:
            plateau = high
        elif low is not None and abs(plateau - low) <= tolerance:
            plateau = low
        hold_potential = np.full(relative.size, plateau, dtype=float)
        times.append(hold_time)
        potentials.append(hold_potential)
        currents.append(np.asarray(record.current_A, dtype=float))
        masks.append(np.ones(relative.size, dtype=bool))
        shift += max(0.0, record.duration_s)
        completed = True
    if not completed:
        warnings.append("没有可插入的电位保持段，已显示原始时间轴")
        return CPTimeSeries(
            time_s=time_s.copy(),
            potential_V=potential.copy(),
            current_A=_active_current_array(run, segments),
            hold_mask=np.zeros(time_s.size, dtype=bool),
            completed=False,
            warnings=warnings,
        )
    return CPTimeSeries(
        time_s=np.concatenate(times),
        potential_V=np.concatenate(potentials),
        current_A=np.concatenate(currents),
        hold_mask=np.concatenate(masks),
        completed=True,
        warnings=warnings,
    )


def _active_current_array(run: CPRun, segments: list[CPSegment]) -> np.ndarray:
    current = np.full(run.time.size, np.nan, dtype=float)
    for segment in segments:
        current[segment.start_index : segment.end_index + 1] = segment.current_A
    return current


def _pair_cycles(segments: list[CPSegment]) -> tuple[list[tuple[CPSegment, CPSegment]], list[str]]:
    warnings: list[str] = []
    cycles: list[tuple[CPSegment, CPSegment]] = []
    pending: CPSegment | None = None
    for segment in segments:
        if segment.direction > 0:
            pending = segment
            continue
        if pending is None:
            continue
        if segment.valid:
            cycles.append((pending, segment))
        pending = None
    if pending is not None:
        warnings.append("末尾充电段没有对应的放电段，未计入循环")
    return cycles, warnings


def _mass_g(run: CPRun) -> float | None:
    if run.params.mass_mg and run.params.mass_mg > 0:
        return float(run.params.mass_mg) * 1e-3
    return None


def _area_cm2(run: CPRun) -> float | None:
    if run.params.area_cm2 and run.params.area_cm2 > 0:
        return float(run.params.area_cm2)
    return None


def _build_cycle(index: int, charge: CPSegment, discharge: CPSegment, run: CPRun) -> CPCycle:
    charge_capacity = charge.capacity_C
    discharge_capacity = discharge.capacity_C
    charge_with_holds = charge.capacity_with_holds_C
    discharge_with_holds = discharge.capacity_with_holds_C
    efficiency = (
        discharge_capacity / charge_capacity * 100.0
        if np.isfinite(charge_capacity)
        and np.isfinite(discharge_capacity)
        and charge_capacity > 0
        else float("nan")
    )
    efficiency_with_holds = (
        discharge_with_holds / charge_with_holds * 100.0
        if np.isfinite(charge_with_holds)
        and np.isfinite(discharge_with_holds)
        and charge_with_holds > 0
        else float("nan")
    )
    mass_g = _mass_g(run)
    area_cm2 = _area_cm2(run)
    specific = discharge_capacity / mass_g if mass_g and np.isfinite(discharge_capacity) else float("nan")
    specific_with_holds = (
        discharge_with_holds / mass_g
        if mass_g and np.isfinite(discharge_with_holds)
        else float("nan")
    )
    areal = discharge_capacity / area_cm2 if area_cm2 and np.isfinite(discharge_capacity) else float("nan")
    areal_with_holds = (
        discharge_with_holds / area_cm2
        if area_cm2 and np.isfinite(discharge_with_holds)
        else float("nan")
    )
    energy_J = discharge.energy_J
    energy_Wh = energy_J / 3600.0 if np.isfinite(energy_J) else float("nan")
    specific_energy = (
        energy_Wh / (mass_g * 1e-3)
        if mass_g and np.isfinite(energy_Wh)
        else float("nan")
    )
    power = (
        energy_J / discharge.duration_s / (mass_g * 1e-3)
        if mass_g and np.isfinite(energy_J) and discharge.duration_s > 0
        else float("nan")
    )
    mean_potential = (
        energy_J / discharge_capacity
        if np.isfinite(energy_J) and np.isfinite(discharge_capacity) and discharge_capacity > 0
        else float("nan")
    )
    # The first discharge points are still on the shared turning plateau.  Use
    # the largest initial potential step as the current-reversal IR drop.
    ir_drop = float("nan")
    if discharge.potential_V.size >= 2 and charge.potential_V.size >= 1:
        early = max(3, min(discharge.potential_V.size - 1, int(discharge.potential_V.size * 0.05)))
        dt = np.diff(discharge.time_s[: early + 1])
        dv = np.abs(np.diff(discharge.potential_V[: early + 1]))
        valid = np.isfinite(dt) & (dt >= 0) & np.isfinite(dv)
        if np.any(valid):
            ir_drop = float(np.nanmax(dv[valid]))
    return CPCycle(
        index=index,
        charge=charge,
        discharge=discharge,
        charge_capacity_C=charge_capacity,
        discharge_capacity_C=discharge_capacity,
        charge_capacity_with_holds_C=charge_with_holds,
        discharge_capacity_with_holds_C=discharge_with_holds,
        coulombic_efficiency_pct=efficiency,
        coulombic_efficiency_with_holds_pct=efficiency_with_holds,
        specific_capacity_C_g=specific,
        specific_capacity_mAh_g=specific / 3.6 if np.isfinite(specific) else float("nan"),
        specific_capacity_with_holds_C_g=specific_with_holds,
        specific_capacity_with_holds_mAh_g=(
            specific_with_holds / 3.6 if np.isfinite(specific_with_holds) else float("nan")
        ),
        areal_capacity_C_cm2=areal,
        areal_capacity_mAh_cm2=areal / 3.6 if np.isfinite(areal) else float("nan"),
        discharge_energy_Wh=energy_Wh,
        specific_energy_Wh_kg=specific_energy,
        power_W_kg=power,
        mean_discharge_potential_V=mean_potential,
        ir_drop_V=ir_drop,
        areal_capacity_with_holds_C_cm2=areal_with_holds,
        areal_capacity_with_holds_mAh_cm2=(
            areal_with_holds / 3.6 if np.isfinite(areal_with_holds) else float("nan")
        ),
    )


def analyze_cp_run(run: CPRun, *, force: bool = False) -> CPRunSummary:
    cached = run.summary
    if isinstance(cached, CPRunSummary) and not force:
        return cached
    segments, holds, warnings = build_segments(run, warn=True)
    pairs, pair_warnings = _pair_cycles(segments)
    warnings.extend(pair_warnings)
    cycles = [_build_cycle(index + 1, charge, discharge, run) for index, (charge, discharge) in enumerate(pairs)]
    completed = sum(1 for segment in segments if segment.hold is not None)
    if not cycles:
        warnings.append("未找到完整的“充电→放电”循环，无法计算 GCD 容量")
    if segments and not holds:
        warnings.append("文件未记录保持段电流；电位-时间图仅使用原始活动电流区间")
    summary = CPRunSummary(
        cycles=cycles,
        segments=segments,
        holds=holds,
        warnings=list(dict.fromkeys(warnings)),
        has_hold_data=bool(holds),
        completed_hold_count=completed,
        mean_charge_capacity_C=_finite_mean(cycle.charge_capacity_C for cycle in cycles),
        mean_discharge_capacity_C=_finite_mean(cycle.discharge_capacity_C for cycle in cycles),
        mean_discharge_capacity_with_holds_C=_finite_mean(
            cycle.discharge_capacity_with_holds_C for cycle in cycles
        ),
        mean_specific_capacity_C_g=_finite_mean(cycle.specific_capacity_C_g for cycle in cycles),
        mean_specific_capacity_mAh_g=_finite_mean(
            cycle.specific_capacity_mAh_g for cycle in cycles
        ),
        mean_areal_capacity_C_cm2=_finite_mean(cycle.areal_capacity_C_cm2 for cycle in cycles),
        mean_areal_capacity_mAh_cm2=_finite_mean(
            cycle.areal_capacity_mAh_cm2 for cycle in cycles
        ),
        mean_areal_capacity_with_holds_C_cm2=_finite_mean(
            cycle.areal_capacity_with_holds_C_cm2 for cycle in cycles
        ),
        mean_areal_capacity_with_holds_mAh_cm2=_finite_mean(
            cycle.areal_capacity_with_holds_mAh_cm2 for cycle in cycles
        ),
        mean_coulombic_efficiency_pct=_finite_mean(
            cycle.coulombic_efficiency_pct for cycle in cycles
        ),
        mean_coulombic_efficiency_with_holds_pct=_finite_mean(
            cycle.coulombic_efficiency_with_holds_pct for cycle in cycles
        ),
        mean_discharge_energy_Wh=_finite_mean(cycle.discharge_energy_Wh for cycle in cycles),
        mean_specific_energy_Wh_kg=_finite_mean(
            cycle.specific_energy_Wh_kg for cycle in cycles
        ),
        mean_power_W_kg=_finite_mean(cycle.power_W_kg for cycle in cycles),
        mean_ir_drop_V=_finite_mean(cycle.ir_drop_V for cycle in cycles),
    )
    run.summary = summary
    return summary


__all__ = [
    "CPCycle",
    "CPHoldRecord",
    "CPRunSummary",
    "CPSegment",
    "CPTimeSeries",
    "analyze_cp_run",
    "build_segments",
    "completed_cp_series",
    "split_hold_records",
]
