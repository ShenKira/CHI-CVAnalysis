# -*- coding: utf-8 -*-
"""Cyclic-voltammetry analysis.

The numerical core is intentionally independent from Qt and from the plotting
layer.  Results carry their method name/version so exports and project files
remain reproducible when algorithms evolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from cvanalysis.domain.errors import AnalysisError
from cvanalysis.domain.models import CVCycle, CVRun
from cvanalysis.domain.units import normalize_capacitance, normalize_current, normalize_charge

try:  # scipy is part of the v2 environment; keep a numpy fallback for parsers/CLI
    from scipy.signal import find_peaks
except Exception:  # pragma: no cover - exercised only in minimal environments
    find_peaks = None


METHOD_VERSION = 2
try:
    _trapz = np.trapezoid
except AttributeError:
    _trapz = np.trapz


@dataclass
class CVRunSummary:
    run_id: str
    scan_rate: float | None
    voltage_window: float | None
    total_cycles: int
    valid_cycles: int
    excluded_cycles: int
    outlier_cycles: list[int]
    mean_area_C: float | None
    mean_capacitance_F: float | None
    sd_capacitance_F: float | None
    cv_percent: float | None
    min_capacitance_F: float | None
    max_capacitance_F: float | None
    mean_cap_per_area: float | None = None
    mean_cap_per_mass: float | None = None
    warnings: list[str] = field(default_factory=list)
    method: str = "robust-integral"
    method_version: int = METHOD_VERSION
    mean_integration_width_V: float | None = None

    @property
    def specific_capacitance(self) -> float | None:
        return self.mean_cap_per_area

    @property
    def mass_capacitance(self) -> float | None:
        return self.mean_cap_per_mass


@dataclass
class ScanRatePoint:
    run_id: str
    label: str
    scan_rate: float
    capacitance_F: float | None
    capacitance_sd_F: float | None
    current_up_A: float | None
    current_down_A: float | None
    current_abs_A: float | None
    voltage_window: float | None
    area_cm2: float | None
    mass_mg: float | None
    valid_cycles: int
    integration_width_V: float | None = None


@dataclass
class BValueResult:
    scan_rates: np.ndarray
    currents: np.ndarray
    labels: list[str]
    slope: float
    intercept: float
    r2: float
    warnings: list[str] = field(default_factory=list)
    method: str = "log-i-log-v"
    method_version: int = METHOD_VERSION


@dataclass
class TrasattiResult:
    scan_rates: np.ndarray
    charges_C: np.ndarray
    inv_sqrt_rate: np.ndarray
    q_capacitive_C: float
    slope: float
    r2: float
    q_diffusive_low_rate_C: float | None
    capacitive_fraction_low_rate: float | None
    warnings: list[str] = field(default_factory=list)
    method: str = "trasatti"
    method_version: int = METHOD_VERSION
    q_total_C: float | None = None
    capacitive_fraction_total: float | None = None


@dataclass
class DunnResult:
    potential: np.ndarray
    total_current: np.ndarray
    capacitive_current: np.ndarray
    diffusive_current: np.ndarray
    scan_rate: float
    capacitive_fraction: float
    mean_r2: float
    normalization: str = "none"
    warnings: list[str] = field(default_factory=list)
    method: str = "dunn"
    method_version: int = METHOD_VERSION


@dataclass
class DunnScanRateResult:
    scan_rates: np.ndarray
    capacitive_fraction: np.ndarray
    diffusive_fraction: np.ndarray
    mean_r2: float
    normalization: str = "none"
    warnings: list[str] = field(default_factory=list)
    method: str = "dunn-scan-rate"
    method_version: int = METHOD_VERSION


# ---------------------------------------------------------------------------
# Cycle segmentation


def _monotonic_branch(points: np.ndarray) -> np.ndarray:
    """Sort a branch by potential and merge duplicate potential samples."""
    if points.size == 0:
        return np.empty((0, 2), dtype=float)
    order = np.argsort(points[:, 0], kind="stable")
    potential = points[order, 0]
    current = points[order, 1]
    unique, inverse = np.unique(potential, return_inverse=True)
    if unique.size < potential.size:
        counts = np.bincount(inverse)
        current = np.bincount(inverse, weights=current) / np.maximum(counts, 1)
    return np.column_stack([unique, current])


def _sign_changes_fallback(potential: np.ndarray) -> list[int]:
    diff = np.diff(potential)
    span = float(np.nanmax(potential) - np.nanmin(potential))
    epsilon = max(1e-12, span * 1e-9)
    signs = np.zeros_like(diff, dtype=int)
    last = 0
    for index, value in enumerate(diff):
        if value > epsilon:
            last = 1
        elif value < -epsilon:
            last = -1
        signs[index] = last
    changes = [0]
    for index in range(1, len(signs)):
        if signs[index] != signs[index - 1]:
            changes.append(index)
    changes.append(len(potential) - 1)
    return changes


def _find_extrema(potential: np.ndarray, metadata) -> list[int]:
    n = len(potential)
    if n < 5:
        return []
    span = float(np.nanmax(potential) - np.nanmin(potential))
    if span <= 0:
        return []
    expected_cycles = getattr(metadata, "expected_cycles", None)

    extrema_with_score: list[tuple[int, float]] = []
    if find_peaks is not None:
        sample_interval = getattr(metadata, "sample_interval", None)
        prominence = max(span * 0.005, (sample_interval or 0.0) * 2.0, 1e-12)
        distance = max(3, n // 2000)
        peaks, peak_props = find_peaks(potential, prominence=prominence, distance=distance)
        valleys, valley_props = find_peaks(-potential, prominence=prominence, distance=distance)
        extrema_with_score.extend(
            (int(index), float(score)) for index, score in zip(peaks, peak_props.get("prominences", np.zeros_like(peaks)))
        )
        extrema_with_score.extend(
            (int(index), float(score)) for index, score in zip(valleys, valley_props.get("prominences", np.zeros_like(valleys)))
        )
    else:
        extrema_with_score = [(index, 1.0) for index in _sign_changes_fallback(potential)[1:-1]]

    if not extrema_with_score:
        return []

    if expected_cycles is not None:
        expected_segments = max(1, int(expected_cycles) * 2)
        max_extrema = expected_segments - 1
        if len(extrema_with_score) > max_extrema:
            # Noise can create extra extrema.  Keep the strongest turns, then
            # restore chronological order.
            extrema_with_score = sorted(extrema_with_score, key=lambda item: item[1], reverse=True)[:max_extrema]

    extrema = sorted(index for index, _ in extrema_with_score)
    # Remove extremum candidates that would create extremely short segments.
    min_segment = 3
    changed = True
    while changed and extrema:
        changed = False
        boundaries = [0, *extrema, n - 1]
        lengths = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
        shortest = int(np.argmin(lengths))
        if lengths[shortest] >= min_segment:
            break
        if shortest == 0:
            extrema.pop(0)
        elif shortest == len(lengths) - 1:
            extrema.pop()
        else:
            # Remove the extremum shared by the two shortest neighbours.
            left_len = lengths[shortest]
            right_len = lengths[shortest + 1] if shortest + 1 < len(lengths) else left_len
            if left_len <= right_len:
                extrema.pop(shortest - 1 if shortest - 1 < len(extrema) else 0)
            else:
                extrema.pop(shortest if shortest < len(extrema) else -1)
        changed = True
    return extrema


def _segments(potential: np.ndarray, metadata) -> list[tuple[int, int, int]]:
    n = len(potential)
    extrema = _find_extrema(potential, metadata)
    boundaries = [0, *extrema, n - 1]
    result: list[tuple[int, int, int]] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end <= start:
            continue
        direction = 1 if potential[end] >= potential[start] else -1
        result.append((start, end, direction))
    return result


def segment_cycles(run: CVRun, *, method: str = "robust") -> list[CVCycle]:
    """Split a CV trace into complete cycles.

    The robust path detects potential turning points with a prominence filter,
    which is much less sensitive to small noise than the old per-sample sign
    test.  ``method='legacy'`` keeps the v1 behaviour for reproducibility.
    """
    potential = np.asarray(run.potential, dtype=float)
    current = np.asarray(run.current, dtype=float)
    if method == "legacy":
        return _segment_cycles_legacy(run)

    segments = _segments(potential, run.metadata)
    if not segments:
        return []

    full_window = run.voltage_window
    first_segment = segments[0]
    first_span = abs(
        float(potential[first_segment[1]]) - float(potential[first_segment[0]])
    )
    first_partial = bool(
        full_window is not None
        and full_window > 0
        and first_span < 0.95 * float(full_window)
    )
    if first_partial:
        run.add_warning("首个循环从非极限电位起始，可能是不完整循环；默认仍参与统计")

    cycles: list[CVCycle] = []
    index = 1
    for pair_index in range(0, len(segments) - 1, 2):
        first = segments[pair_index]
        second = segments[pair_index + 1]
        if first[2] == second[2]:
            run.add_warning(f"第 {index} 个循环的两个分支方向相同，已跳过")
            index += 1
            continue
        start = first[0]
        end = second[1]
        if end <= start:
            continue
        cycle_potential = potential[start : end + 1]
        cycle_current = current[start : end + 1]

        first_points = np.column_stack(
            [potential[first[0] : first[1] + 1], current[first[0] : first[1] + 1]]
        )
        second_points = np.column_stack(
            [potential[second[0] : second[1] + 1], current[second[0] : second[1] + 1]]
        )
        # CHI data often contains the turning potential twice (end of one
        # segment and start of the next).  Keeping both would mix opposite
        # branch currents and bias the integral.  For the first branch keep the
        # last duplicate at its start; for the second branch drop the shared
        # turning point entirely.
        if first_points.shape[0] > 1:
            offset = 0
            while (
                offset + 1 < first_points.shape[0]
                and first_points[offset + 1, 0] == first_points[offset, 0]
            ):
                offset += 1
            first_points = first_points[offset:]
        if second_points.shape[0] > 1:
            turn_potential = first_points[-1, 0]
            offset = 0
            while (
                offset < second_points.shape[0]
                and second_points[offset, 0] == turn_potential
            ):
                offset += 1
            if offset < second_points.shape[0]:
                second_points = second_points[offset:]
        up = _monotonic_branch(first_points if first[2] > 0 else second_points)
        down = _monotonic_branch(second_points if first[2] > 0 else first_points)
        if up.size < 2 or down.size < 2:
            index += 1
            continue
        cycles.append(
            CVCycle(
                index=index,
                potential=cycle_potential,
                current=cycle_current,
                branch_up=up,
                branch_down=down,
                is_partial=bool(first_partial and pair_index == 0),
            )
        )
        index += 1

    if len(cycles) < len(segments) // 2:
        run.add_warning("存在未配对的 CV 分支，最后一段未计入循环统计")
    return cycles


def _segment_cycles_legacy(run: CVRun) -> list[CVCycle]:
    """Compatibility implementation of the v1 direction-change splitter."""
    data = np.column_stack([run.potential, run.current])
    if len(data) < 2:
        return []
    segment = run.metadata.segment or 10
    expected_cycles = max(1, segment // 2)
    direction_changes = [0]
    for index in range(1, len(data)):
        delta = data[index, 0] - data[index - 1, 0]
        if delta > 0:
            direction_changes.append(1)
        elif delta < 0:
            direction_changes.append(-1)
        else:
            direction_changes.append(direction_changes[-1])
    change_indices = [0]
    for index in range(1, len(direction_changes)):
        if direction_changes[index] != direction_changes[index - 1]:
            change_indices.append(index)
    boundaries = [0, *change_indices[1:], len(data)]
    raw_cycles = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end - start >= 2:
            raw_cycles.append(data[start:end])
    if len(raw_cycles) > expected_cycles:
        raw_cycles = [
            np.concatenate([raw_cycles[i], raw_cycles[i + 1]])
            for i in range(0, len(raw_cycles) - 1, 2)
        ]

    cycles: list[CVCycle] = []
    for index, cycle_data in enumerate(raw_cycles, 1):
        cycle_data = np.asarray(cycle_data, dtype=float)
        max_index = int(np.argmax(cycle_data[:, 0]))
        first = cycle_data[: max_index + 1]
        second = cycle_data[max_index:]
        up = _monotonic_branch(first)
        down = _monotonic_branch(second)
        if up.size < 2 or down.size < 2:
            continue
        cycles.append(
            CVCycle(
                index=index,
                potential=cycle_data[:, 0],
                current=cycle_data[:, 1],
                branch_up=up,
                branch_down=down,
            )
        )
    return cycles


# ---------------------------------------------------------------------------
# Cycle metrics


def _cycle_metrics(cycle: CVCycle, run: CVRun, sensitivity_factor: float) -> None:
    cycle.is_outlier = False
    cycle.outlier_reason = None
    cycle.warning = None
    cycle.capacitance_F = float("nan")
    cycle.area_C = float("nan")
    cycle.integration_width_V = float("nan")
    if cycle.branch_up.size < 2 or cycle.branch_down.size < 2:
        cycle.warning = "循环分支数据不足"
        return
    up = cycle.branch_up
    down = cycle.branch_down
    overlap_low = max(float(up[0, 0]), float(down[0, 0]))
    overlap_high = min(float(up[-1, 0]), float(down[-1, 0]))
    if overlap_high <= overlap_low:
        cycle.warning = "正反扫电位窗口没有重叠"
        return
    full_low = float(np.nanmin(cycle.potential))
    full_high = float(np.nanmax(cycle.potential))
    full_width = full_high - full_low
    overlap_width = overlap_high - overlap_low
    if full_width > 0 and overlap_width >= 0.95 * full_width:
        low, high = full_low, full_high
    else:
        low, high = overlap_low, overlap_high
    width = high - low
    if width <= 0:
        cycle.warning = "正反扫电位窗口没有重叠"
        return

    sensitivity = run.metadata.sensitivity
    if sensitivity is not None and sensitivity > 0 and sensitivity_factor > 0:
        threshold = sensitivity * sensitivity_factor
        if np.nanmax(np.abs(cycle.current)) > threshold:
            cycle.is_outlier = True
            cycle.outlier_reason = "电流溢出"
            cycle.warning = f"电流超出 {sensitivity_factor:g} 倍灵敏度范围，本循环不参与统计"
            return

    count = max(60, min(2000, max(up.shape[0], down.shape[0])))
    grid = np.linspace(low, high, count)
    i_up = np.interp(grid, up[:, 0], up[:, 1])
    i_down = np.interp(grid, down[:, 0], down[:, 1])
    area = float(abs(_trapz(i_up - i_down, grid)))
    cycle.area_C = area
    cycle.integration_width_V = width

    scan_rate = run.metadata.scan_rate
    if scan_rate is None or scan_rate <= 0:
        cycle.warning = "缺少有效扫速，无法计算电容"
        return
    cycle.capacitance_F = area / (2.0 * scan_rate * width)


def _robust_mean(
    values: Sequence[float],
    outlier_count: int,
    *,
    z_threshold: float | None = None,
) -> tuple[float, list[int]]:
    clean = [float(value) for value in values if value is not None and np.isfinite(value)]
    if not clean:
        return float("nan"), []
    if z_threshold is not None and z_threshold > 0 and len(clean) > 1:
        mean = float(np.mean(clean))
        sd = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
        if sd == 0 or np.allclose(clean, mean, rtol=1e-10, atol=0):
            return mean, []
        z_scores = np.abs((np.asarray(clean) - mean) / sd)
        excluded = [int(index) for index in np.where(z_scores > z_threshold)[0]]
        if not excluded:
            return mean, []
        remaining = [value for index, value in enumerate(clean) if index not in set(excluded)]
        return float(np.mean(remaining)) if remaining else mean, excluded
    if len(clean) <= max(0, outlier_count):
        return float(np.mean(clean)), []
    mean = float(np.mean(clean))
    sd = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    if sd == 0 or np.allclose(clean, mean, rtol=1e-10, atol=0):
        return mean, []
    z_scores = np.abs((np.asarray(clean) - mean) / sd)
    order = np.argsort(z_scores)[::-1]
    excluded = [int(index) for index in order[: max(0, outlier_count)]]
    remaining = [value for index, value in enumerate(clean) if index not in set(excluded)]
    return float(np.mean(remaining)) if remaining else mean, excluded


def summarize_run(
    run: CVRun,
    *,
    outlier_count: int = 1,
    outlier_z: float | None = None,
) -> CVRunSummary:
    valid = [cycle for cycle in run.cycles if cycle.valid]
    capacitances = [cycle.capacitance_F for cycle in valid]
    mean_cap, excluded_indices = _robust_mean(
        capacitances,
        outlier_count,
        z_threshold=outlier_z,
    )
    outlier_cycles = [valid[index].index for index in excluded_indices]
    valid = [cycle for index, cycle in enumerate(valid) if index not in excluded_indices]
    capacitances = [cycle.capacitance_F for cycle in valid]
    if len(capacitances) > 1:
        sd = float(np.std(capacitances, ddof=1))
    else:
        sd = 0.0 if capacitances else float("nan")
    cv_percent = (sd / mean_cap * 100.0) if mean_cap and np.isfinite(mean_cap) else float("nan")
    areas = [cycle.area_C for cycle in valid if np.isfinite(cycle.area_C)]
    widths = [
        cycle.integration_width_V
        for cycle in valid
        if np.isfinite(cycle.integration_width_V) and cycle.integration_width_V > 0
    ]

    area = run.params.area_cm2
    mass_g = run.params.mass_mg * 1e-3 if run.params.mass_mg else None
    mean_cap_area = mean_cap / area if area and np.isfinite(mean_cap) else None
    mean_cap_mass = mean_cap / mass_g if mass_g and np.isfinite(mean_cap) else None

    warnings = list(run.warnings)
    if not valid:
        warnings.append("没有有效循环可用于统计")
    elif len(valid) < 2:
        warnings.append("有效循环少于 2 个，标准差和变异系数不可靠")
    if run.metadata.scan_rate is None:
        warnings.append("缺少扫速信息")

    return CVRunSummary(
        run_id=run.run_id,
        scan_rate=run.metadata.scan_rate,
        voltage_window=run.voltage_window,
        total_cycles=len(run.cycles),
        valid_cycles=len(valid),
        excluded_cycles=len(run.cycles) - len(valid),
        outlier_cycles=outlier_cycles,
        mean_area_C=float(np.mean(areas)) if areas else None,
        mean_capacitance_F=mean_cap if np.isfinite(mean_cap) else None,
        sd_capacitance_F=sd if np.isfinite(sd) else None,
        cv_percent=cv_percent if np.isfinite(cv_percent) else None,
        min_capacitance_F=float(np.min(capacitances)) if capacitances else None,
        max_capacitance_F=float(np.max(capacitances)) if capacitances else None,
        mean_cap_per_area=mean_cap_area,
        mean_cap_per_mass=mean_cap_mass,
        mean_integration_width_V=float(np.mean(widths)) if widths else None,
        warnings=warnings,
    )


def analyze_cv_run(
    run: CVRun,
    *,
    sensitivity_factor: float = 10.0,
    outlier_count: int = 1,
    outlier_z: float | None = None,
    segmentation: str = "robust",
    force: bool = False,
) -> CVRunSummary:
    if force or not run.cycles:
        run.cycles = segment_cycles(run, method=segmentation)
    for cycle in run.cycles:
        _cycle_metrics(cycle, run, sensitivity_factor)
    summary = summarize_run(run, outlier_count=outlier_count, outlier_z=outlier_z)
    run.summary = summary
    return summary


# ---------------------------------------------------------------------------
# Scan-rate analyses


def _cycles_for_run(run: CVRun, cycle_selection: dict[str, list[int]] | None) -> list[CVCycle]:
    if cycle_selection is not None and run.run_id in cycle_selection:
        selected = set(cycle_selection[run.run_id])
        return [cycle for cycle in run.cycles if cycle.index in selected]
    return list(run.cycles)


def current_at_potential(
    run: CVRun,
    potential: float,
    cycles: Iterable[CVCycle] | None = None,
) -> tuple[float, float, int]:
    """Return ``(forward, reverse, n_cycles)`` median current at potential."""
    ups: list[float] = []
    downs: list[float] = []
    for cycle in cycles if cycles is not None else run.cycles:
        if not cycle.valid:
            continue
        up, down = cycle.current_at(potential)
        if np.isfinite(up):
            ups.append(up)
        if np.isfinite(down):
            downs.append(down)
    if not ups and not downs:
        return float("nan"), float("nan"), 0
    up_value = float(np.median(ups)) if ups else float("nan")
    down_value = float(np.median(downs)) if downs else float("nan")
    return up_value, down_value, max(len(ups), len(downs))


def collect_scan_rate_points(
    runs: Iterable[CVRun],
    *,
    target_voltage: float | None = None,
    current_mode: str = "absolute",
    cycle_selection: dict[str, list[int]] | None = None,
) -> list[ScanRatePoint]:
    points: list[ScanRatePoint] = []
    for run in runs:
        summary = run.summary
        if summary is None:
            summary = summarize_run(run)
        if summary.scan_rate is None or summary.scan_rate <= 0:
            continue
        selected_cycles = _cycles_for_run(run, cycle_selection)
        cycles = [cycle for cycle in selected_cycles if cycle.valid]
        if not cycles:
            continue
        capacitances = [cycle.capacitance_F for cycle in cycles if np.isfinite(cycle.capacitance_F)]
        if not capacitances:
            continue
        use_summary = (
            run.run_id not in cycle_selection
            if cycle_selection is not None
            else True
        ) or len(selected_cycles) == len(run.cycles)
        if use_summary and summary.mean_capacitance_F is not None:
            cycles = [cycle for cycle in cycles if cycle.index not in summary.outlier_cycles]
            mean_cap = float(summary.mean_capacitance_F)
            sd_cap = float(summary.sd_capacitance_F) if summary.sd_capacitance_F is not None else 0.0
        else:
            mean_cap = float(np.mean(capacitances))
            sd_cap = float(np.std(capacitances, ddof=1)) if len(capacitances) > 1 else 0.0
        widths = [
            cycle.integration_width_V
            for cycle in cycles
            if np.isfinite(cycle.integration_width_V) and cycle.integration_width_V > 0
        ]
        if use_summary and summary.mean_integration_width_V is not None:
            integration_width = float(summary.mean_integration_width_V)
        elif widths:
            integration_width = float(np.mean(widths))
        else:
            integration_width = summary.voltage_window
        up_value = down_value = None
        if target_voltage is not None:
            up_value, down_value, _ = current_at_potential(run, target_voltage, cycles)
        if up_value is None or not np.isfinite(up_value):
            current_abs = None
        elif down_value is None or not np.isfinite(down_value):
            current_abs = abs(up_value)
        elif current_mode == "up":
            current_abs = abs(up_value)
        elif current_mode == "down":
            current_abs = abs(down_value)
        else:
            current_abs = (abs(up_value) + abs(down_value)) / 2.0
        points.append(
            ScanRatePoint(
                run_id=run.run_id,
                label=run.display_name,
                scan_rate=float(summary.scan_rate),
                capacitance_F=mean_cap,
                capacitance_sd_F=sd_cap,
                current_up_A=up_value,
                current_down_A=down_value,
                current_abs_A=current_abs,
                voltage_window=summary.voltage_window,
                area_cm2=run.params.area_cm2,
                mass_mg=run.params.mass_mg,
                valid_cycles=len(cycles),
                integration_width_V=integration_width,
            )
        )
    return sorted(points, key=lambda point: point.scan_rate)


def fit_b_value(points: Iterable[ScanRatePoint]) -> BValueResult:
    usable = [
        point
        for point in points
        if point.scan_rate > 0 and point.current_abs_A is not None and point.current_abs_A > 0
    ]
    if len(usable) < 2:
        raise AnalysisError("b 值分析至少需要两个不同扫速下的有效电流")
    rates = np.asarray([point.scan_rate for point in usable], dtype=float)
    currents = np.asarray([point.current_abs_A for point in usable], dtype=float)
    x = np.log10(rates)
    y = np.log10(currents)
    slope, intercept = np.polyfit(x, y, 1)
    prediction = slope * x + intercept
    ss_res = float(np.sum((y - prediction) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    warnings: list[str] = []
    if len(usable) < 3:
        warnings.append("只有两个扫速，b 值仅作粗略估计")
    if np.unique(np.round(rates, 12)).size < 2:
        warnings.append("扫速点重复，b 值不可靠")
    return BValueResult(
        scan_rates=rates,
        currents=currents,
        labels=[point.label for point in usable],
        slope=float(slope),
        intercept=float(intercept),
        r2=float(r2),
        warnings=warnings,
    )


def scan_window_warning(
    points: Iterable[ScanRatePoint],
    *,
    relative: float = 0.01,
    absolute: float = 0.001,
) -> str | None:
    """Warn when scan-rate points come from incompatible potential windows."""
    windows = [
        abs(float(point.voltage_window))
        for point in points
        if point.voltage_window is not None and np.isfinite(point.voltage_window)
    ]
    if len(windows) < 2:
        return None
    low = min(windows)
    high = max(windows)
    reference = max(abs(float(np.mean(windows))), 0.0)
    tolerance = max(absolute, relative * reference)
    if high - low <= tolerance:
        return None
    return (
        f"所选 CV 文件的电位窗口不一致（{low:g}–{high:g} V）；"
        "扫速相关结果仅作参考，建议只选择同一窗口的数据"
    )


def trasatti_analysis(points: Iterable[ScanRatePoint]) -> TrasattiResult:
    usable = [
        point
        for point in points
        if point.scan_rate > 0
        and point.capacitance_F is not None
        and point.voltage_window is not None
        and np.isfinite(point.capacitance_F)
    ]
    if len(usable) < 2:
        raise AnalysisError("Trasatti 分析至少需要两个不同扫速")
    rates = np.asarray([point.scan_rate for point in usable], dtype=float)
    if np.unique(np.round(rates, 12)).size < 2:
        raise AnalysisError("Trasatti 分析需要至少两个不同扫速")
    widths = np.asarray(
        [
            point.integration_width_V
            if point.integration_width_V is not None
            and np.isfinite(point.integration_width_V)
            and point.integration_width_V > 0
            else point.voltage_window
            for point in usable
        ],
        dtype=float,
    )
    charges = np.asarray(
        [point.capacitance_F * width for point, width in zip(usable, widths)],
        dtype=float,
    )
    x = 1.0 / np.sqrt(rates)
    slope, intercept = np.polyfit(x, charges, 1)
    prediction = slope * x + intercept
    ss_res = float(np.sum((charges - prediction) ** 2))
    ss_tot = float(np.sum((charges - np.mean(charges)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    sqrt_rates = np.sqrt(rates)
    _total_slope, total_intercept = np.polyfit(sqrt_rates, charges, 1)
    q_total = float(total_intercept)
    fraction_total = intercept / q_total if q_total > 0 else None
    warnings: list[str] = []
    if intercept < 0:
        warnings.append("拟合得到的电容电荷为负，扫速范围可能不足")
    if len(usable) < 3:
        warnings.append("少于三个扫速，线性拟合仅作参考")
    window_warning = scan_window_warning(usable)
    if window_warning:
        warnings.append(window_warning)
    if q_total <= 0:
        warnings.append("q–v^{1/2} 外推得到的总电荷非正，无法计算 q_outer/q_total")
    if fraction_total is not None and not -1e-6 <= fraction_total <= 1.0 + 1e-6:
        warnings.append("q_outer/q_total 超出 0–1，线性外推可能不适用")
    lowest_index = int(np.argmin(rates))
    q_low = float(charges[lowest_index])
    q_diff = q_low - intercept
    fraction = intercept / q_low if q_low > 0 else None
    return TrasattiResult(
        scan_rates=rates,
        charges_C=charges,
        inv_sqrt_rate=x,
        q_capacitive_C=float(intercept),
        slope=float(slope),
        r2=float(r2),
        q_diffusive_low_rate_C=float(q_diff),
        capacitive_fraction_low_rate=float(fraction) if fraction is not None else None,
        q_total_C=q_total if np.isfinite(q_total) else None,
        capacitive_fraction_total=(
            float(fraction_total) if fraction_total is not None and np.isfinite(fraction_total) else None
        ),
        warnings=warnings,
    )


def _representative_branch(
    run: CVRun,
    grid: np.ndarray,
    branch: str = "up",
    cycles: Iterable[CVCycle] | None = None,
) -> np.ndarray:
    values: list[np.ndarray] = []
    for cycle in cycles if cycles is not None else run.cycles:
        if not cycle.valid:
            continue
        points = cycle.branch_up if branch == "up" else cycle.branch_down
        if points.shape[0] < 2:
            continue
        values.append(np.interp(grid, points[:, 0], points[:, 1]))
    if not values:
        return np.full_like(grid, np.nan, dtype=float)
    return np.nanmedian(np.vstack(values), axis=0)


def _dunn_fit_data(
    runs: Iterable[CVRun],
    normalization: str,
    cycle_selection: dict[str, list[int]] | None,
):
    runs = list(runs)
    selected_cycles = {
        run.run_id: [cycle for cycle in _cycles_for_run(run, cycle_selection) if cycle.valid]
        for run in runs
    }
    usable = [
        run
        for run in runs
        if selected_cycles[run.run_id]
        and run.metadata.scan_rate
        and run.metadata.scan_rate > 0
    ]
    if len(usable) < 2:
        raise AnalysisError("Dunn 分析至少需要两个不同扫速")
    rates = np.asarray([run.metadata.scan_rate for run in usable], dtype=float)
    if np.unique(np.round(rates, 12)).size < 2:
        raise AnalysisError("Dunn 分析需要至少两个不同扫速")

    lows = []
    highs = []
    for run in usable:
        for cycle in selected_cycles[run.run_id]:
            if cycle.branch_up.shape[0] >= 2:
                lows.append(float(cycle.branch_up[0, 0]))
                highs.append(float(cycle.branch_up[-1, 0]))
    if not lows:
        raise AnalysisError("没有可用的正扫分支")
    low = max(lows)
    high = min(highs)
    if high <= low:
        raise AnalysisError("不同文件的电位窗口没有重叠，无法进行贡献分解")
    grid = np.linspace(low, high, 200)

    currents = np.vstack(
        [_representative_branch(run, grid, "up", selected_cycles[run.run_id]) for run in usable]
    )
    warnings: list[str] = []
    if normalization == "area" and not all(run.params.has_area() for run in usable):
        warnings.append("部分数据缺少电极面积，贡献分解回退为原始电流")
        normalization = "none"
    if normalization == "mass" and not all(run.params.has_mass() for run in usable):
        warnings.append("部分数据缺少活性物质质量，贡献分解回退为原始电流")
        normalization = "none"
    if normalization != "none":
        currents = np.vstack(
            [
                normalize_current(
                    row,
                    normalization,
                    area_cm2=run.params.area_cm2,
                    mass_mg=run.params.mass_mg,
                )
                for run, row in zip(usable, currents)
            ]
        )

    sqrt_rates = np.sqrt(rates)
    # Dunn's usual linearization is i/sqrt(v) = k1*sqrt(v) + k2.
    # Regress in that space so scan rates receive the same weighting as the
    # transformed method, rather than minimizing errors in untransformed i.
    design = np.column_stack([sqrt_rates, np.ones_like(sqrt_rates)])
    transformed = np.nan_to_num(currents, nan=0.0) / sqrt_rates[:, np.newaxis]
    coefficients, *_ = np.linalg.lstsq(design, transformed, rcond=None)
    k1 = coefficients[0, :]
    k2 = coefficients[1, :]

    transformed_predictions = design @ coefficients
    r2_values: list[float] = []
    for column in range(currents.shape[1]):
        measured = transformed[:, column]
        predicted = transformed_predictions[:, column]
        ss_res = float(np.sum((measured - predicted) ** 2))
        ss_tot = float(np.sum((measured - np.mean(measured)) ** 2))
        if ss_tot > 0:
            r2_values.append(1.0 - ss_res / ss_tot)
    mean_r2 = float(np.mean(r2_values)) if r2_values else float("nan")
    if len(usable) < 3:
        warnings.append("少于三个扫速，Dunn 分解结果的可靠性有限")
    return grid, rates, k1, k2, mean_r2, normalization, warnings


def dunn_analysis(
    runs: Iterable[CVRun],
    *,
    normalization: str = "none",
    selected_scan_rate: float | None = None,
    cycle_selection: dict[str, list[int]] | None = None,
) -> DunnResult:
    grid, rates, k1, k2, mean_r2, normalization, warnings = _dunn_fit_data(
        runs, normalization, cycle_selection
    )
    if selected_scan_rate is None:
        selected_scan_rate = float(np.median(rates))
    selected_scan_rate = min(max(selected_scan_rate, float(np.min(rates))), float(np.max(rates)))
    capacitive = k1 * selected_scan_rate
    diffusive = k2 * np.sqrt(selected_scan_rate)
    total = capacitive + diffusive
    denominator = float(np.sum(np.abs(capacitive)) + np.sum(np.abs(diffusive)))
    fraction = float(np.sum(np.abs(capacitive)) / denominator) if denominator > 0 else float("nan")
    return DunnResult(
        potential=grid,
        total_current=total,
        capacitive_current=capacitive,
        diffusive_current=diffusive,
        scan_rate=selected_scan_rate,
        capacitive_fraction=fraction,
        mean_r2=mean_r2,
        normalization=normalization,
        warnings=warnings,
    )


def dunn_fraction_vs_scan_rate(
    runs: Iterable[CVRun],
    *,
    normalization: str = "none",
    cycle_selection: dict[str, list[int]] | None = None,
) -> DunnScanRateResult:
    """Return capacitive/diffusive percentages at each measured scan rate.

    The Dunn coefficients k1(V), k2(V) are fitted once across all scan rates;
    the fraction at each rate uses integrated absolute capacitive and
    diffusive current contributions over the common potential window.
    """
    grid, rates, k1, k2, mean_r2, normalization, warnings = _dunn_fit_data(
        runs, normalization, cycle_selection
    )
    capacitive_current = k1[np.newaxis, :] * rates[:, np.newaxis]
    diffusive_current = k2[np.newaxis, :] * np.sqrt(rates)[:, np.newaxis]
    capacitive_area = _trapz(np.abs(capacitive_current), grid, axis=1)
    diffusive_area = _trapz(np.abs(diffusive_current), grid, axis=1)
    denominator = capacitive_area + diffusive_area
    capacitive_fraction = np.divide(
        capacitive_area,
        denominator,
        out=np.full_like(capacitive_area, np.nan, dtype=float),
        where=denominator > 0,
    )

    unique_rates: list[float] = []
    fractions: list[float] = []
    for rate in np.unique(np.round(rates, 12)):
        mask = np.isclose(rates, rate, rtol=0.0, atol=1e-12)
        value = float(np.nanmean(capacitive_fraction[mask]))
        unique_rates.append(float(rate))
        fractions.append(value)
    fraction_array = np.asarray(fractions, dtype=float)
    return DunnScanRateResult(
        scan_rates=np.asarray(unique_rates, dtype=float),
        capacitive_fraction=fraction_array,
        diffusive_fraction=1.0 - fraction_array,
        mean_r2=mean_r2,
        normalization=normalization,
        warnings=warnings,
    )
