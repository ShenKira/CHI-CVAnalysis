# -*- coding: utf-8 -*-
"""Shared axis tick helpers.

The forced-unified mode makes X/Y use the same numeric major-tick interval.
This is especially useful for Nyquist plots whose axes have identical limits
but whose physical box is slightly wider than tall; Matplotlib's independent
AutoLocators would otherwise choose different steps (for example 0.2 vs 0.1).
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogFormatterMathtext, MaxNLocator, MultipleLocator, NullFormatter

from cvanalysis.plotting.axis_limits import common_axis_display_unit

_MAX_MAJOR_TICKS = 12


def _decimal_log_label(value: float, _position: int) -> str:
    if not math.isfinite(value) or value <= 0:
        return ""
    return format(Decimal(format(value, ".12g")), "f")


def apply_log_tick_formats(figure: Figure, analysis_options: dict | None) -> None:
    """Format logarithmic axes, leaving linear axes and old projects untouched.

    X and Y choices apply to every corresponding log axis, including subplots.
    """
    options = analysis_options or {}
    formats = options.get("log_tick_formats")
    if not isinstance(formats, dict):
        return
    for ax in figure.axes:
        for side, axis in (("x", ax.xaxis), ("y", ax.yaxis)):
            if (ax.get_xscale() if side == "x" else ax.get_yscale()) != "log":
                continue
            choice = formats.get(side)
            if choice == "decimal":
                axis.set_major_formatter(FuncFormatter(_decimal_log_label))
                axis.set_minor_formatter(NullFormatter())
            elif choice == "scientific":
                axis.set_major_formatter(LogFormatterMathtext())
                axis.set_minor_formatter(NullFormatter())


def _target_axes(figure: Figure, kind: str):
    if kind in {"eis_bode", "cp_capacity"}:
        return []
    if kind == "eis_fit":
        return [figure.axes[0]] if figure.axes else []
    return [figure.axes[0]] if len(figure.axes) == 1 else []


def _major_step(ax, side: str, low: float, high: float) -> float | None:
    if side == "x":
        raw = np.asarray(ax.get_xticks(), dtype=float)
    else:
        raw = np.asarray(ax.get_yticks(), dtype=float)
    raw = raw[np.isfinite(raw)]
    if raw.size >= 2:
        span = abs(high - low)
        tolerance = max(span * 1e-9, 1e-12)
        inside = raw[(raw >= min(low, high) - tolerance) & (raw <= max(low, high) + tolerance)]
        diffs = np.diff(np.sort(inside))
        diffs = diffs[diffs > 0]
        if diffs.size:
            return float(np.median(diffs))
    locator = MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10])
    values = locator.tick_values(min(low, high), max(low, high))
    diffs = np.diff(np.sort(np.asarray(values, dtype=float)))
    diffs = diffs[diffs > 0]
    if diffs.size:
        return float(np.median(diffs))
    return None


def _next_nice_step(step: float) -> float:
    exponent = math.floor(math.log10(step))
    base = step / (10.0 ** exponent)
    for candidate in (1.0, 2.0, 2.5, 5.0, 10.0):
        if candidate > base + 1e-9:
            return candidate * (10.0 ** exponent)
    return 10.0 ** (exponent + 1)


def _tick_count(low: float, high: float, step: float) -> int:
    if step <= 0 or not math.isfinite(step):
        return 0
    return int(math.floor(high / step) - math.ceil(low / step)) + 1


def _manual_interval(options: dict, ax) -> float | None:
    try:
        value = float(options.get("unified_tick_interval"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    stored = options.get("unified_tick_interval_unit")
    current = common_axis_display_unit(ax)
    if isinstance(stored, dict) and current is not None:
        try:
            stored_factor = float(stored.get("factor"))
            current_factor = float(current[1])
        except (TypeError, ValueError, OverflowError):
            return value
        if stored_factor > 0 and current_factor > 0:
            value *= current_factor / stored_factor
    return value


def apply_unified_ticks(
    figure: Figure,
    kind: str,
    analysis_options: dict | None,
) -> list[str]:
    """Apply the optional forced X/Y major-tick interval and return warnings."""
    options = analysis_options or {}
    if not bool(options.get("unified_xy_ticks", False)):
        return []
    warnings: list[str] = []
    for ax in _target_axes(figure, kind):
        if ax.get_xscale() != "linear" or ax.get_yscale() != "linear":
            warnings.append("强制统一刻度仅适用于线性 X/Y 轴，已忽略")
            continue
        x_low, x_high = (float(value) for value in ax.get_xlim())
        y_low, y_high = (float(value) for value in ax.get_ylim())
        if not all(math.isfinite(value) for value in (x_low, x_high, y_low, y_high)):
            warnings.append("强制统一刻度失败：坐标范围不是有限数值")
            continue
        if x_low == x_high or y_low == y_high:
            continue
        manual_step = _manual_interval(options, ax)
        if manual_step is not None:
            step = manual_step
            counts = (
                _tick_count(min(x_low, x_high), max(x_low, x_high), step),
                _tick_count(min(y_low, y_high), max(y_low, y_high), step),
            )
            if min(counts) < 2:
                warnings.append("手动主刻度间隔过大，有一轴不足两个刻度")
            elif max(counts) > 50:
                warnings.append("手动主刻度间隔较小，刻度数量较多")
        else:
            x_step = _major_step(ax, "x", x_low, x_high)
            y_step = _major_step(ax, "y", y_low, y_high)
            if x_step is None or y_step is None:
                warnings.append("强制统一刻度失败：无法确定 X/Y 主刻度间距")
                continue
            step = min(x_step, y_step)
            counts = (
                _tick_count(min(x_low, x_high), max(x_low, x_high), step),
                _tick_count(min(y_low, y_high), max(y_low, y_high), step),
            )
            while max(counts) > _MAX_MAJOR_TICKS:
                next_step = _next_nice_step(step)
                if next_step <= step:
                    break
                step = next_step
                counts = (
                    _tick_count(min(x_low, x_high), max(x_low, x_high), step),
                    _tick_count(min(y_low, y_high), max(y_low, y_high), step),
                )
            if min(counts) < 3:
                warnings.append(
                    "X/Y 范围跨度差异较大，统一刻度间隔后有一轴刻度较少；"
                    "可调整范围或关闭强制统一"
                )
        ax.xaxis.set_major_locator(MultipleLocator(step))
        ax.yaxis.set_major_locator(MultipleLocator(step))
    return warnings


__all__ = ["apply_unified_ticks"]
