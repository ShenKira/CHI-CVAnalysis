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
DUNN_METHOD_VERSION = 5
DUNN_CLOSURE_WARNING = 0.03
# Reporting limits for net/gross charge. These are independent of instrument
# accuracy and of the fitted-versus-measured charge closure.
DUNN_MIN_NET_RATIO = 0.001
DUNN_LOW_NET_RATIO = 0.10
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
    charge_C: float | None = None
    integration_bounds_V: tuple[float, float] | None = None


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
    method_version: int = 3
    q_total_C: float | None = None
    capacitive_fraction_total: float | None = None


@dataclass(frozen=True)
class DunnInput:
    run_id: str
    label: str
    scan_rate: float | None
    cycle_indices: tuple[int, ...]
    partial_cycle_indices: tuple[int, ...]
    excluded_cycle_indices: tuple[int, ...]
    potential_window: tuple[float, float] | None
    reason: str = ""


@dataclass(frozen=True)
class DunnCoverage:
    inputs: tuple[DunnInput, ...]
    common_window: tuple[float, float] | None


@dataclass(frozen=True)
class DunnRateDiagnostic:
    scan_rate: float
    q_capacitive: float
    q_diffusive: float
    q_fitted: float
    q_measured: float
    q_residual: float
    closure_error: float
    relative_rmse: float
    fitted_net_ratio: float
    measured_net_ratio: float
    status: str


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
    method_version: int = DUNN_METHOD_VERSION
    measured_current: np.ndarray | None = None
    fraction_basis: str = "fitted"
    diffusive_fraction: float = float("nan")
    fit: _DunnFit | None = None
    diagnostic: DunnRateDiagnostic | None = None


@dataclass
class DunnScanRateResult:
    scan_rates: np.ndarray
    capacitive_fraction: np.ndarray
    diffusive_fraction: np.ndarray
    mean_r2: float
    normalization: str = "none"
    warnings: list[str] = field(default_factory=list)
    method: str = "dunn-scan-rate"
    method_version: int = DUNN_METHOD_VERSION
    potential_window: tuple[float, float] | None = None
    fraction_basis: str = "fitted"
    fit: _DunnFit | None = None
    diagnostics: tuple[DunnRateDiagnostic, ...] = ()


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
        # Preserve separate measured currents at duplicate turning potentials.
        # A single shared turning sample belongs to the incoming branch.
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
            end = len(first_points) - 1
            while end > 0 and first_points[end - 1, 0] == turn_potential:
                end -= 1
            offset = 0
            while (
                offset < second_points.shape[0]
                and second_points[offset, 0] == turn_potential
            ):
                offset += 1
            if offset < second_points.shape[0]:
                repeated_turn = offset > 1 or end < len(first_points) - 1
                second_points = second_points[offset - 1 if repeated_turn else offset:]
            first_points = first_points[:end + 1]
        end = len(second_points) - 1
        while end > 0 and second_points[end - 1, 0] == second_points[end, 0]:
            end -= 1
        second_points = second_points[:end + 1]
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

    grid = np.union1d(
        up[(up[:, 0] >= low) & (up[:, 0] <= high), 0],
        down[(down[:, 0] >= low) & (down[:, 0] <= high), 0],
    )
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
    warnings.extend(dict.fromkeys(cycle.warning for cycle in run.cycles if cycle.warning))
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
        areas = [cycle.integral_area_A_V for cycle in cycles if np.isfinite(cycle.integral_area_A_V)]
        charge = float(np.mean(areas) / (2.0 * summary.scan_rate)) if areas else None
        bounds = (
            max(max(c.branch_up[0, 0], c.branch_down[0, 0]) for c in cycles),
            min(min(c.branch_up[-1, 0], c.branch_down[-1, 0]) for c in cycles),
        ) if cycles else None
        up_value = down_value = None
        if target_voltage is not None:
            up_value, down_value, _ = current_at_potential(run, target_voltage, cycles)
        current_abs = None
        if target_voltage is not None:
            if current_mode in ("up", "down"):
                value = up_value if current_mode == "up" else down_value
                if np.isfinite(value):
                    current_abs = abs(value)
            elif np.isfinite(up_value) and np.isfinite(down_value):
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
                charge_C=charge,
                integration_bounds_V=bounds,
            )
        )
    return sorted(points, key=lambda point: point.scan_rate)


def _average_by_scan_rate(rates: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    unique, groups = np.unique(rates, return_inverse=True)
    return unique, np.bincount(groups, weights=values) / np.bincount(groups)


def fit_b_value(
    points: Iterable[ScanRatePoint], *, normalization: str = "none", allow_unfitted: bool = False,
) -> BValueResult:
    usable = [
        point
        for point in points
        if np.isfinite(point.scan_rate) and point.scan_rate > 0
        and point.current_abs_A is not None and np.isfinite(point.current_abs_A) and point.current_abs_A > 0
    ]
    rates = np.asarray([point.scan_rate for point in usable], dtype=float)
    currents = np.asarray([
        normalize_current(point.current_abs_A, normalization, area_cm2=point.area_cm2, mass_mg=point.mass_mg)
        for point in usable
    ], dtype=float)
    valid = np.isfinite(currents) & (currents > 0)
    rates, currents = rates[valid], currents[valid]
    fit_rates, fit_currents = _average_by_scan_rate(rates, currents)
    warnings = []
    labels = [point.label for point, keep in zip(usable, valid) if keep]
    if fit_rates.size < 2:
        if not allow_unfitted:
            raise AnalysisError("b 值分析至少需要两个不同扫速下的有效电流")
        return BValueResult(rates, currents, labels, np.nan, np.nan, np.nan,
                            ["b 值分析至少需要两个不同扫速下的有效电流"])
    x = np.log10(fit_rates)
    y = np.log10(fit_currents)
    slope, intercept = np.polyfit(x, y, 1)
    prediction = slope * x + intercept
    ss_res = float(np.sum((y - prediction) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    if fit_rates.size == 2:
        warnings.append("仅两个不同扫速，b 值拟合没有残差自由度")
    return BValueResult(
        scan_rates=rates,
        currents=currents,
        labels=labels,
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
    points = list(points)
    bounds = [point.integration_bounds_V for point in points if point.integration_bounds_V is not None]
    if bounds:
        endpoints = np.asarray(bounds, dtype=float)
        widths = endpoints[:, 1] - endpoints[:, 0]
        tolerance = max(absolute, relative * float(np.mean(np.maximum(widths, 0))))
        inconsistent_cycles = any(
            point.integration_width_V is not None
            and point.integration_width_V - (point.integration_bounds_V[1] - point.integration_bounds_V[0]) > tolerance
            for point in points if point.integration_bounds_V is not None
        )
        if inconsistent_cycles or np.any(widths <= 0) or np.any(np.ptp(endpoints, axis=0) > tolerance):
            return "所选循环的实际积分电位窗口不一致；扫速相关结果仅作参考"
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


def trasatti_analysis(
    points: Iterable[ScanRatePoint], *, normalization: str = "none", allow_unfitted: bool = False,
) -> TrasattiResult:
    usable = []
    charges = []
    for point in points:
        if not np.isfinite(point.scan_rate) or point.scan_rate <= 0:
            continue
        charge = point.charge_C
        if charge is None:
            # Older callers may supply capacitance and width only.
            width = point.integration_width_V or point.voltage_window
            if point.capacitance_F is None or width is None or width <= 0:
                continue
            charge = point.capacitance_F * width
        charge = normalize_charge(charge, normalization, area_cm2=point.area_cm2, mass_mg=point.mass_mg)
        if charge is not None and np.isfinite(charge) and charge > 0:
            usable.append(point)
            charges.append(float(charge))
    rates = np.asarray([point.scan_rate for point in usable], dtype=float)
    charges = np.asarray(charges, dtype=float)
    fit_rates, fit_charges = _average_by_scan_rate(rates, charges)
    x = 1.0 / np.sqrt(fit_rates)
    if fit_rates.size < 2:
        message = "Trasatti 分析至少需要两个不同扫速下的正电荷"
        if not allow_unfitted:
            raise AnalysisError(message)
        return TrasattiResult(rates, charges, 1.0 / np.sqrt(rates), np.nan, np.nan, np.nan,
                              None, None, warnings=[message])
    slope, intercept = np.polyfit(x, fit_charges, 1)
    prediction = slope * x + intercept
    ss_res = float(np.sum((fit_charges - prediction) ** 2))
    ss_tot = float(np.sum((fit_charges - np.mean(fit_charges)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    _, inverse_total = np.polyfit(np.sqrt(fit_rates), 1.0 / fit_charges, 1)
    q_total = float(1.0 / inverse_total) if inverse_total > 0 else None
    fraction_total = intercept / q_total if q_total is not None and np.isfinite(q_total) else None
    warnings: list[str] = []
    if intercept < 0:
        warnings.append("外推得到的外表面可及电荷为负")
    if fit_rates.size == 2:
        warnings.append("仅两个不同扫速，Trasatti 外推没有残差自由度")
    window_warning = scan_window_warning(usable)
    if window_warning:
        warnings.append(window_warning)
    if fraction_total is None:
        warnings.append("1/q–√v 外推的零扫速截距无效，无法计算总电荷")
    if fraction_total is not None and not -1e-6 <= fraction_total <= 1.0 + 1e-6:
        warnings.append("q_outer/q_total 超出 0–1，线性外推可能不适用")
        fraction_total = None
    q_low = float(fit_charges[0])
    fraction = intercept / q_low
    if not -1e-6 <= fraction <= 1.0 + 1e-6:
        warnings.append("外表面可及电荷与最低实测扫速电荷之比超出 0–1")
        fraction = None
    return TrasattiResult(
        scan_rates=rates,
        charges_C=charges,
        inv_sqrt_rate=1.0 / np.sqrt(rates),
        q_capacitive_C=float(intercept),
        slope=float(slope),
        r2=float(r2),
        q_diffusive_low_rate_C=float(q_low - intercept) if fraction is not None else None,
        capacitive_fraction_low_rate=float(fraction) if fraction is not None else None,
        q_total_C=q_total if q_total is not None and np.isfinite(q_total) else None,
        capacitive_fraction_total=(
            float(fraction_total) if fraction_total is not None and np.isfinite(fraction_total) else None
        ),
        warnings=warnings,
    )


def _collect_dunn_inputs(runs, cycle_selection, branch):
    if branch not in ("up", "down"):
        raise AnalysisError("Dunn 分析需要选择正扫或反扫支路")
    inputs: list[DunnInput] = []
    usable = []
    for run in runs:
        try:
            rate = float(run.metadata.scan_rate)
        except (TypeError, ValueError, OverflowError):
            rate = float("nan")
        rate = rate if np.isfinite(rate) and rate > 0 else None
        explicit = cycle_selection is not None and run.run_id in cycle_selection
        selected = _cycles_for_run(run, cycle_selection)
        included: list[int] = []
        excluded: list[int] = []
        partial: list[int] = []
        branches: list[np.ndarray] = []
        for position, cycle in enumerate(selected, 1):
            index = getattr(cycle, "index", position)
            incomplete = getattr(cycle, "is_partial", False)
            if incomplete:
                partial.append(index)
            points = cycle.branch_up if branch == "up" else cycle.branch_down
            if (rate is None or not cycle.valid or (incomplete and not explicit)
                    or len(points) < 2 or not np.isfinite(points).all()
                    or np.any(np.diff(points[:, 0]) <= 0)):
                excluded.append(index)
                continue
            included.append(index)
            branches.append(points)
        window = None
        if branches:
            window = (max(float(p[0, 0]) for p in branches), min(float(p[-1, 0]) for p in branches))
            usable.append((run, rate, branches))
        reasons = []
        if rate is None:
            reasons.append("缺少有效扫速")
        elif not selected:
            reasons.append("未选循环")
        if set(excluded) & set(partial):
            reasons.append("已排除未完整扫描的循环")
        if set(included) & set(partial):
            reasons.append("包含手动选中的部分循环")
        if set(excluded) - set(partial) and rate is not None:
            reasons.append("已排除无效循环或支路")
        inputs.append(DunnInput(
            run.run_id, getattr(run, "display_name", run.run_id), rate,
            tuple(included), tuple(partial), tuple(excluded), window, "，".join(reasons),
        ))
    windows = [row.potential_window for row in inputs if row.potential_window is not None]
    common = None
    if windows:
        low = max(window[0] for window in windows)
        high = min(window[1] for window in windows)
        if low < high:
            common = (low, high)
    return DunnCoverage(tuple(inputs), common), usable


def dunn_input_coverage(
    runs: Iterable[CVRun],
    cycle_selection: dict[str, list[int]] | None = None,
    branch: str = "up",
) -> DunnCoverage:
    """Inspect selected cycles and common support without fitting any current."""
    coverage, _ = _collect_dunn_inputs(runs, cycle_selection, branch)
    return coverage


def _dunn_window(common, requested):
    if common is None:
        raise AnalysisError("所选文件和循环没有共同实测电位窗口")
    if requested is None:
        return common
    if not isinstance(requested, (tuple, list, np.ndarray)):
        raise AnalysisError("Dunn 选区需要填写两个电位边界")
    try:
        low, high = map(float, requested)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AnalysisError("Dunn 选区需要填写两个电位边界") from exc
    if not np.isfinite([low, high]).all() or low >= high:
        raise AnalysisError("Dunn 选区需要两个有限且按从低到高排列的电位边界")
    if low < common[0] or high > common[1]:
        raise AnalysisError(f"Dunn 选区超出共同实测窗口 {common[0]:g}–{common[1]:g} V，请调整选区或数据")
    return low, high


def _branch_median(branches, grid):
    if len(branches) == 1:
        points = branches[0]
        return np.interp(grid, points[:, 0], points[:, 1])
    # Bound the working array even for files with many selected cycles.
    chunk_size = max(1, 1_000_000 // len(branches))
    result = np.empty_like(grid)
    for offset in range(0, grid.size, chunk_size):
        nodes = grid[offset : offset + chunk_size]
        matrix = np.vstack([np.interp(nodes, p[:, 0], p[:, 1]) for p in branches])
        result[offset : offset + nodes.size] = np.median(matrix, axis=0)
    return result


def _dunn_grid(usable, low: float, high: float, warnings: list[str]) -> np.ndarray:
    # Outside the ROI we only need the adjacent points used by interpolation.
    points = (branch[:, 0] for _, _, branches in usable for branch in branches)
    grid = np.unique(np.concatenate([
        [low, high], *(p[(p > low) & (p < high)] for p in points),
    ]))
    # The median of more than two piecewise-linear curves can have extra
    # corners between acquisition knots, where their order changes.
    nonlinear = [branches for _, _, branches in usable if len(branches) > 2]
    if not nonlinear:
        return grid
    fractions = np.array([.25, .5, .75])
    for _ in range(8):
        probes = grid[:-1, None] + np.diff(grid)[:, None] * fractions
        refine = np.zeros(grid.size - 1, dtype=bool)
        for branches in nonlinear:
            ends = _branch_median(branches, grid)
            truth = _branch_median(branches, probes.ravel()).reshape(probes.shape)
            linear = ends[:-1, None] * (1 - fractions) + ends[1:, None] * fractions
            scale = max(float(np.max(np.abs(ends))), float(np.max(np.abs(truth))))
            refine |= np.any(np.abs(truth - linear) > scale * 1e-5, axis=1)
        if not refine.any():
            return grid
        expanded = np.unique(np.concatenate((grid, probes[refine].ravel())))
        if expanded.size == grid.size:
            return grid
        grid = expanded
    warnings.append("Dunn 循环中位数网格已达到细化上限，积分仍可能受局部交叉影响")
    return grid


@dataclass
class _DunnFit:
    grid: np.ndarray
    rates: np.ndarray
    measured: np.ndarray
    k1: np.ndarray
    k2: np.ndarray
    mean_r2: float
    normalization: str
    warnings: list[str]
    common_window: tuple[float, float]
    branch: str
    inputs: tuple[DunnInput, ...]
    opposing_fraction: float


def _dunn_fit_data(
    runs: Iterable[CVRun],
    normalization: str,
    cycle_selection: dict[str, list[int]] | None,
    branch: str,
    potential_window: tuple[float, float] | None = None,
) -> _DunnFit:
    coverage, selected = _collect_dunn_inputs(runs, cycle_selection, branch)
    usable = [run for run, _, _ in selected]
    rates = np.asarray([rate for _, rate, _ in selected], dtype=float)
    unique_rates, groups = np.unique(rates, return_inverse=True)
    if unique_rates.size < 2:
        raise AnalysisError("Dunn 分析需要至少两个不同扫速")
    low, high = _dunn_window(coverage.common_window, potential_window)
    common_low, common_high = coverage.common_window
    warnings = [f"{row.label}：{row.reason}" for row in coverage.inputs if row.reason]
    widest = max(float(p[-1, 0] - p[0, 0]) for _, _, branches in selected for p in branches)
    if common_high - common_low < 0.95 * widest:
        warnings.append(f"支路共同窗口缩小至 {common_low:g}–{common_high:g} V")
    grid = _dunn_grid(selected, low, high, warnings)
    currents = np.vstack([_branch_median(branches, grid) for _, _, branches in selected])
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

    if not np.isfinite(currents).all():
        raise AnalysisError("所选支路缺少有限电流数据，无法进行 Dunn 拟合")
    currents = np.stack([np.mean(currents[groups == i], axis=0) for i in range(len(unique_rates))])
    rates = unique_rates
    sqrt_rates = np.sqrt(rates)
    # Dunn's usual linearization is i/sqrt(v) = k1*sqrt(v) + k2.
    # Regress in that space so scan rates receive the same weighting as the
    # transformed method, rather than minimizing errors in untransformed i.
    # Column scaling protects the rank calculation from the unit/magnitude
    # of the scan rates while leaving the OLS objective unchanged.
    design = np.column_stack([sqrt_rates / sqrt_rates[-1], np.ones_like(sqrt_rates)])
    transformed = currents / sqrt_rates[:, np.newaxis]
    coefficients, _, rank, singular_values = np.linalg.lstsq(design, transformed, rcond=None)
    if rank < 2:
        raise AnalysisError("不同扫速间距过小，无法独立确定 Dunn 两个分量")
    if singular_values[0] / singular_values[-1] > 100:
        warnings.append("扫速跨度较窄，Dunn 分量可能对电流误差敏感")
    k1 = coefficients[0, :] / sqrt_rates[-1]
    k2 = coefficients[1, :]

    transformed_predictions = design @ coefficients
    ss_res = np.sum((transformed - transformed_predictions) ** 2, axis=0)
    ss_tot = np.sum((transformed - np.mean(transformed, axis=0)) ** 2, axis=0)
    floor = (8 * np.finfo(float).eps) ** 2 * np.sum(transformed ** 2, axis=0)
    defined = ss_tot > floor
    r2 = 1.0 - np.divide(ss_res, ss_tot, out=np.zeros_like(ss_res), where=defined)
    # Voltage weighting keeps clusters of original/higher-resolution knots
    # from dominating the reported mean.
    mean_r2 = float("nan")
    if defined.any():
        mean_r2 = float(_trapz(np.where(defined, r2, 0.0), grid) / _trapz(defined.astype(float), grid))
    if len(rates) < 3:
        warnings.append("仅两个不同扫速，直线拟合没有残差自由度")

    # Ignore roundoff in a vanishing component (e.g. an ideal capacitor).
    cap = k1 * rates[-1]
    diff = k2 * sqrt_rates[-1]
    tolerance = 1e-12 * np.maximum(np.abs(cap), np.abs(diff))
    opposing = (np.sign(cap) != np.sign(diff)) & (np.minimum(np.abs(cap), np.abs(diff)) > tolerance)
    opposing_fraction = float(_trapz(opposing.astype(float), grid) / (high - low))
    if opposing_fraction:
        warnings.append(f"约 {opposing_fraction:.1%} 的电位区间内拟合分量异号，储能机理占比需谨慎解释")
    return _DunnFit(
        grid, rates, currents, k1, k2, mean_r2, normalization, warnings,
        coverage.common_window, branch, coverage.inputs, opposing_fraction,
    )


def _absolute_linear_area(values: np.ndarray, grid: np.ndarray) -> float:
    """Integrate magnitudes, including zeros inside linear intervals."""
    left, right = np.abs(values[:-1]), np.abs(values[1:])
    crossing = (left > 0) & (right > 0) & (np.signbit(values[:-1]) != np.signbit(values[1:]))
    area = float(_trapz(np.abs(values), grid))
    return area - float(np.sum(
        np.diff(grid)[crossing] * left[crossing] * right[crossing] / (left[crossing] + right[crossing])
    ))


def _squared_linear_area(values: np.ndarray, grid: np.ndarray) -> float:
    left, right = values[:-1], values[1:]
    return float(np.sum(np.diff(grid) * (left ** 2 + left * right + right ** 2) / 3.0))


def _dunn_report(fit: _DunnFit, rates: np.ndarray, measured: np.ndarray | None, basis: str):
    if basis not in ("fitted", "measured"):
        raise AnalysisError("Dunn 占比基准必须为拟合分量之和或实测净电荷")
    curves = None if measured is None else np.atleast_2d(measured)
    grid = fit.grid
    q_cap = float(_trapz(fit.k1, grid))
    q_diff_at_one = float(_trapz(fit.k2, grid))
    gross_cap = _absolute_linear_area(fit.k1, grid)
    gross_diff_at_one = _absolute_linear_area(fit.k2, grid)
    cap_fractions = np.full_like(rates, np.nan)
    diff_fractions = np.full_like(rates, np.nan)
    rows = []
    undefined_rates, low_fitted, low_measured, nonclosing_rates = [], [], [], []
    for index, rate in enumerate(rates):
        sqrt_rate = np.sqrt(rate)
        q_diff = q_diff_at_one / sqrt_rate
        q_fit = q_cap + q_diff
        gross_fit = gross_cap + gross_diff_at_one / sqrt_rate
        fit_ratio = abs(q_fit) / gross_fit if gross_fit > 0 else 0.0
        q_observed = q_residual = obs_ratio = closure = rmse = float("nan")
        if fit_ratio < DUNN_LOW_NET_RATIO:
            low_fitted.append(rate)
        if curves is not None:
            observed = curves[index]
            q_observed = float(_trapz(observed, grid) / rate)
            gross_observed = _absolute_linear_area(observed, grid) / rate
            obs_ratio = abs(q_observed) / gross_observed if gross_observed > 0 else 0.0
            q_residual = q_fit - q_observed
            if obs_ratio >= DUNN_MIN_NET_RATIO:
                closure = q_residual / q_observed
            residual = fit.k1 * rate + fit.k2 * sqrt_rate - observed
            observed_energy = _squared_linear_area(observed, grid)
            if observed_energy > 0:
                rmse = float(np.sqrt(_squared_linear_area(residual, grid) / observed_energy))
            if obs_ratio < DUNN_LOW_NET_RATIO:
                low_measured.append(rate)
            if abs(closure) > DUNN_CLOSURE_WARNING:
                nonclosing_rates.append(rate)
        denom, net_ratio = (q_fit, fit_ratio) if basis == "fitted" else (q_observed, obs_ratio)
        if np.isfinite(denom) and net_ratio >= DUNN_MIN_NET_RATIO:
            cap_fractions[index] = q_cap / denom
            diff_fractions[index] = q_diff / denom
            status = "diagnostic" if (
                fit.opposing_fraction or fit_ratio < DUNN_LOW_NET_RATIO
                or obs_ratio < DUNN_LOW_NET_RATIO or abs(closure) > DUNN_CLOSURE_WARNING
                or len(fit.rates) == 2
            ) else "ok"
            if curves is None:
                status = "prediction"
        else:
            status = "undefined"
            if np.isfinite(denom):
                undefined_rates.append(rate)
            elif curves is None:
                status = "prediction"
        rows.append(DunnRateDiagnostic(
            float(rate), q_cap, float(q_diff), float(q_fit), q_observed, q_residual,
            closure, rmse, float(fit_ratio), obs_ratio, status,
        ))
    for values, message in (
        (undefined_rates, f"{'拟合' if basis == 'fitted' else '实测'}净电荷为零或低于绝对积分的 {DUNN_MIN_NET_RATIO:.1%}，占比未定义"),
        (low_fitted, f"拟合净电荷低于分量绝对积分之和的 {DUNN_LOW_NET_RATIO:.0%}，存在抵消"),
        (low_measured, f"实测净电荷低于绝对积分的 {DUNN_LOW_NET_RATIO:.0%}，存在抵消"),
        (nonclosing_rates, f"拟合总电荷与实测净电荷的相对偏差超过 {DUNN_CLOSURE_WARNING:.0%}"),
    ):
        if values:
            fit.warnings.append(f"{', '.join(f'{v:g}' for v in values)} V/s {message}")
    return cap_fractions, diff_fractions, tuple(rows)


def dunn_analysis(
    runs: Iterable[CVRun],
    *,
    normalization: str = "none",
    selected_scan_rate: float | None = None,
    cycle_selection: dict[str, list[int]] | None = None,
    branch: str = "up",
    fraction_basis: str = "fitted",
    potential_window: tuple[float, float] | None = None,
) -> DunnResult:
    fit = _dunn_fit_data(runs, normalization, cycle_selection, branch, potential_window)
    rates = fit.rates
    if selected_scan_rate is None:
        selected_scan_rate = float(rates[(len(rates) - 1) // 2])
    if not np.isfinite(selected_scan_rate):
        raise AnalysisError("分解扫速必须为有限数值")
    if selected_scan_rate < rates[0] or selected_scan_rate > rates[-1]:
        fit.warnings.append("请求扫速超出实测范围，已使用最近的实测扫速")
    selected_scan_rate = min(max(selected_scan_rate, float(np.min(rates))), float(np.max(rates)))
    index = int(np.argmin(np.abs(rates - selected_scan_rate)))
    measured = None
    if np.isclose(rates[index], selected_scan_rate, rtol=1e-12, atol=0):
        selected_scan_rate = float(rates[index])
        measured = fit.measured[index]
    else:
        fit.warnings.append("该扫速无实测曲线，仅显示模型预测")
    cap, diff, diagnostics = _dunn_report(fit, np.array([selected_scan_rate]), measured, fraction_basis)
    capacitive = fit.k1 * selected_scan_rate
    diffusive = fit.k2 * np.sqrt(selected_scan_rate)
    return DunnResult(
        potential=fit.grid,
        total_current=capacitive + diffusive,
        measured_current=measured,
        capacitive_current=capacitive,
        diffusive_current=diffusive,
        scan_rate=selected_scan_rate,
        capacitive_fraction=float(cap[0]),
        diffusive_fraction=float(diff[0]),
        fraction_basis=fraction_basis,
        mean_r2=fit.mean_r2,
        normalization=fit.normalization,
        warnings=fit.warnings,
        fit=fit,
        diagnostic=diagnostics[0],
    )


def dunn_fraction_vs_scan_rate(
    runs: Iterable[CVRun],
    *,
    normalization: str = "none",
    cycle_selection: dict[str, list[int]] | None = None,
    branch: str = "up",
    fraction_basis: str = "fitted",
    potential_window: tuple[float, float] | None = None,
) -> DunnScanRateResult:
    """Return signed charge fractions relative to the fitted or measured sweep."""
    fit = _dunn_fit_data(runs, normalization, cycle_selection, branch, potential_window)
    cap, diff, diagnostics = _dunn_report(fit, fit.rates, fit.measured, fraction_basis)
    return DunnScanRateResult(
        scan_rates=fit.rates,
        capacitive_fraction=cap,
        diffusive_fraction=diff,
        fraction_basis=fraction_basis,
        potential_window=(float(fit.grid[0]), float(fit.grid[-1])),
        mean_r2=fit.mean_r2,
        normalization=fit.normalization,
        warnings=fit.warnings,
        fit=fit,
        diagnostics=diagnostics,
    )
