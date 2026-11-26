# -*- coding: utf-8 -*-
"""Manual axis limits shared by every plot renderer.

Limits are stored per plot in ``PlotSpec.analysis_options["axis_limits"]``::

    {
        "main": {"x_min": 0.0, "x_max": 1.0, "y_min": None, "y_max": 2.0}
    }

Each plot kind exposes stable axis keys.  Kinds with two subplots (Bode / fit)
have one section per subplot; CP capacity uses a secondary Y axis section.

Optional ``analysis_options["axis_limit_units"]`` entries record the display
unit, scale factor and physical dimension used when a limit was entered.
Compatible units are converted; incompatible or invalid metadata clears the
affected side. Legacy ranges without metadata start in the displayed unit.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any

from matplotlib.figure import Figure
from cvanalysis.domain.units import CAPACITANCE, canonical_unit


@dataclass(frozen=True)
class PlotAxisSpec:
    key: str
    label: str
    index: int = 0
    editable_x: bool = True
    editable_y: bool = True


_MAIN = PlotAxisSpec("main", "主坐标轴", 0)
_BODE = (
    PlotAxisSpec("phase", "上图：相位角", 0),
    PlotAxisSpec("magnitude", "下图：阻抗模量", 1),
)
_FIT = (
    PlotAxisSpec("nyquist", "上图：Nyquist", 0),
    PlotAxisSpec("residual", "下图：拟合残差", 1),
)
_CP_CAPACITY = PlotAxisSpec("capacity", "左轴：容量", 0)
_CP_EFFICIENCY = PlotAxisSpec(
    "efficiency",
    "右轴：库仑效率",
    1,
    editable_x=False,
)


def plot_axis_specs(kind: str, figure: Figure | None = None) -> list[PlotAxisSpec]:
    """Return stable, user-facing axis sections for a plot kind."""
    if kind == "eis_bode":
        return list(_BODE)
    if kind == "eis_fit":
        return list(_FIT)
    if kind == "cp_capacity":
        specs = [_CP_CAPACITY]
        if figure is None or len(figure.axes) >= 2:
            specs.append(_CP_EFFICIENCY)
        return specs
    return [_MAIN]


def unit_dimension(label: str) -> str | None:
    """Return a physical quantity including its normalization, when known."""
    label = canonical_unit(label)
    fixed = {"V": "voltage", "s": "time", "Hz": "frequency", "°": "angle",
             "Cycle": "cycle", "%": "percentage", "(V/s)^-1/2": "inverse_sqrt_scan_rate"}
    if label in fixed:
        return fixed[label]
    if label == "V/s":
        return "scan_rate"
    if label.endswith("Ω·cm²"):
        prefix = label[:-len("Ω·cm²")]
        return "impedance_area" if prefix in {"", "m", "k", "M"} else None
    if "/" in label:
        current_part, denominator = label.rsplit("/", 1)
        if (
            denominator in {"F", "mF", "µF", "nF", "pF"}
            and current_part in {"A", "mA", "µA", "nA", "pA"}
        ):
            return "current_per_capacitance"
    suffix = ""
    for ending, kind in (("/cm²", "_area"), ("/g", "_mass")):
        if label.endswith(ending):
            label, suffix = label[:-len(ending)], kind
            break
    for base, dimension in (("Ah", "charge"), ("Ω", "impedance"), ("A", "current"),
                            ("F", "capacitance"), ("C", "charge")):
        if label.endswith(base) and label[:-len(base)] in {"", "m", "µ", "n", "p", "k", "M"}:
            return dimension + suffix
    return None


def _unit_scale(label: str) -> float | None:
    """Numerical multiplier from a quantity's canonical physical unit."""
    label = canonical_unit(label)
    if label in {"V", "s", "Hz", "°", "Cycle", "%", "V/s", "(V/s)^-1/2"}:
        return 1.0
    if label.endswith("Ω·cm²"):
        label = label[:-len("·cm²")]
    if "/" in label:
        current_part, denominator = label.rsplit("/", 1)
        cap_factor = dict(CAPACITANCE.units).get(denominator)
        current_factor = {"A": 1., "mA": 1e3, "µA": 1e6,
                          "nA": 1e9, "pA": 1e12}.get(current_part)
        if cap_factor and current_factor:
            return current_factor / cap_factor
    for ending in ("/cm²", "/g", "/F"):
        if label.endswith(ending):
            label = label[:-len(ending)]
            break
    prefixes = {"": 1., "m": 1e3, "µ": 1e6, "n": 1e9, "p": 1e12,
                "k": 1e-3, "M": 1e-6}
    for base in ("Ah", "Ω", "A", "F", "C"):
        if label.endswith(base):
            factor = prefixes.get(label[:-len(base)])
            if factor is None:
                return None
            return factor / 3600.0 if base == "Ah" else factor
    return None


def set_axis_display_units(ax, *, x=None, y=None, dimensions=None) -> None:
    """Record the display unit currently used by a rendered axis."""
    units = {}
    if x is not None:
        units["x"] = (str(x[0]), float(x[1]))
    if y is not None:
        units["y"] = (str(y[0]), float(y[1]))
    ax._cv_display_units = units
    ax._cv_display_dimensions = {
        side: (dimensions or {}).get(side) or unit_dimension(unit[0])
        for side, unit in units.items()
    }


def axis_display_units(ax) -> dict[str, tuple[str, float]]:
    """Return ``{"x": (label, factor), "y": ...}`` for a rendered axis."""
    units = getattr(ax, "_cv_display_units", None)
    return dict(units) if isinstance(units, dict) else {}


def axis_display_dimensions(ax) -> dict[str, str | None]:
    dimensions = getattr(ax, "_cv_display_dimensions", None)
    return dict(dimensions) if isinstance(dimensions, dict) else {}


def common_axis_display_unit(ax) -> tuple[str, float] | None:
    """Return the shared X/Y display unit, or ``None`` when they differ."""
    units = axis_display_units(ax)
    x_unit = units.get("x")
    y_unit = units.get("y")
    if x_unit is None or y_unit is None:
        return None
    if x_unit[0] != y_unit[0]:
        return None
    try:
        if not math.isclose(float(x_unit[1]), float(y_unit[1]), rel_tol=1e-12):
            return None
    except (TypeError, ValueError):
        return None
    return x_unit


def axis_limit_unit_values(analysis_options: dict | None, key: str) -> dict[str, dict]:
    """Read stored unit metadata for one axis section."""
    units = (analysis_options or {}).get("axis_limit_units")
    raw = units.get(key) if isinstance(units, dict) else None
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict] = {}
    for side in ("x", "y"):
        entry = raw.get(side)
        if isinstance(entry, dict):
            label = entry.get("label")
            try:
                factor = float(entry.get("factor"))
            except (TypeError, ValueError, OverflowError):
                continue
            if isinstance(label, str) and label and math.isfinite(factor) and factor > 0:
                result[side] = {"label": label, "factor": factor}
                if isinstance(entry.get("dimension"), str):
                    result[side]["dimension"] = entry["dimension"]
    return result


def _convert_limit(
    value: float | None,
    stored: dict | None,
    current: tuple[str, float] | None,
) -> float | None:
    """Convert a stored display-unit limit to the active display unit."""
    if value is None or not stored or current is None:
        return value
    current_factor = float(current[1])
    stored_factor = float(stored.get("factor", 0.0))
    if current_factor <= 0 or stored_factor <= 0:
        return value
    return float(value) * current_factor / stored_factor


def sync_axis_limit_units(figure: Figure, kind: str, options: dict | None) -> list[str]:
    """Convert compatible saved limits, or clear them on a quantity change.

    Legacy ranges with no unit metadata are initially interpreted in the
    currently displayed unit, preserving the historical project behavior.
    """
    if not isinstance(options, dict) or not isinstance(options.get("axis_limits"), dict):
        return []
    limits = options["axis_limits"]
    all_units = options.get("axis_limit_units")
    malformed_all = all_units is not None and not isinstance(all_units, dict)
    if not isinstance(all_units, dict):
        all_units = {}
    missing = object()
    warnings = []
    for axis_spec in plot_axis_specs(kind, figure):
        entry = limits.get(axis_spec.key)
        if not isinstance(entry, dict) or axis_spec.index >= len(figure.axes):
            continue
        ax = figure.axes[axis_spec.index]
        current_units = axis_display_units(ax)
        current_dims = axis_display_dimensions(ax)
        stored_units = all_units.get(axis_spec.key)
        malformed_section = stored_units is not None and not isinstance(stored_units, dict)
        if not isinstance(stored_units, dict):
            stored_units = {}
        for side in ("x", "y"):
            fields = (f"{side}_min", f"{side}_max")
            if not any(field in entry and entry[field] not in (None, "") for field in fields):
                stored_units.pop(side, None)
                continue
            current = current_units.get(side)
            if current is None:
                continue
            label, current_factor = current
            current_dim = current_dims.get(side) or unit_dimension(label)
            stored = stored_units.get(side, missing)
            invalid = False
            if malformed_all or malformed_section:
                invalid = True
            elif stored is not missing:
                try:
                    old_label = str(stored["label"])
                    old_factor = float(stored["factor"])
                    old_dim = stored.get("dimension")
                    if not old_dim:
                        old_dim = current_dim if old_label == label else unit_dimension(old_label)
                    if not (math.isfinite(old_factor) and old_factor > 0 and
                            math.isfinite(current_factor) and current_factor > 0):
                        raise ValueError
                    if old_dim != current_dim or (old_dim is None and old_label != label):
                        raise ValueError
                    ratio = current_factor / old_factor
                    old_scale, new_scale = _unit_scale(old_label), _unit_scale(label)
                    if old_scale is not None and new_scale is not None:
                        if not math.isclose(ratio, new_scale / old_scale, rel_tol=1e-9):
                            raise ValueError
                    elif not math.isclose(ratio, 1.0, rel_tol=1e-9):
                        raise ValueError
                    converted = {}
                    for field in fields:
                        if field in entry and entry[field] not in (None, ""):
                            value = float(entry[field]) * ratio
                            if not math.isfinite(value):
                                raise ValueError
                            converted[field] = value
                    entry.update(converted)
                except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError):
                    invalid = True
            if invalid:
                for field in fields:
                    entry.pop(field, None)
                stored_units.pop(side, None)
                warnings.append(f"{axis_spec.label}：{side.upper()} 轴物理量已改变或单位无法换算，已清空手动范围")
            else:
                stored_units[side] = {"label": label, "factor": current_factor}
                if current_dim is not None:
                    stored_units[side]["dimension"] = current_dim
        if entry:
            limits[axis_spec.key] = entry
        else:
            limits.pop(axis_spec.key, None)
        if stored_units:
            all_units[axis_spec.key] = stored_units
        else:
            all_units.pop(axis_spec.key, None)
    if all_units:
        options["axis_limit_units"] = all_units
    else:
        options.pop("axis_limit_units", None)
    if not limits:
        options.pop("axis_limits", None)
    return warnings


def _limit_value(value: Any) -> tuple[float | None, bool]:
    if value is None or value == "":
        return None, False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, True
    if not math.isfinite(number):
        return None, True
    return number, False


def axis_limit_values(analysis_options: dict | None, key: str) -> dict[str, float | None]:
    """Read one axis section, returning four normalized keys for the UI."""
    limits = (analysis_options or {}).get("axis_limits")
    raw = limits.get(key) if isinstance(limits, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, float | None] = {}
    for field in ("x_min", "x_max", "y_min", "y_max"):
        number, invalid = _limit_value(raw.get(field))
        values[field] = None if invalid else number
    return values


def _entry_has_limits(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return any(
        _limit_value(entry.get(field))[0] is not None
        for field in ("x_min", "x_max", "y_min", "y_max")
    )


def _release_fixed_aspect(ax) -> None:
    """Let explicit limits win over Nyquist's automatic equal aspect."""
    try:
        if ax.get_aspect() != "auto":
            ax.set_aspect("auto")
    except (TypeError, ValueError):
        pass


def _apply_side(
    ax,
    *,
    axis_name: str,
    side: str,
    entry: dict,
    editable: bool,
    axis_label: str,
    warnings: list[str],
    stored_units: dict | None = None,
    current_units: dict[str, tuple[str, float]] | None = None,
) -> None:
    if not editable:
        return
    low_key = f"{side}_min"
    high_key = f"{side}_max"
    low, low_invalid = _limit_value(entry.get(low_key))
    high, high_invalid = _limit_value(entry.get(high_key))
    stored = (stored_units or {}).get(side)
    current = (current_units or {}).get(side)
    low = _convert_limit(low, stored, current)
    high = _convert_limit(high, stored, current)
    if low_invalid:
        warnings.append(f"{axis_label}：{axis_name} 最小值无效，已忽略")
    if high_invalid:
        warnings.append(f"{axis_label}：{axis_name} 最大值无效，已忽略")
    if low is None and high is None:
        return

    categories = getattr(ax, "_cv_scan_rate_categories", ()) if side == "x" else ()
    if categories:
        if low is not None and high is not None and low >= high:
            warnings.append(f"{axis_label}：X 轴范围无效（最小值必须小于最大值），已忽略")
            return
        first = bisect_left(categories, low) if low is not None else 0
        last = bisect_right(categories, high) if high is not None else len(categories)
        if first >= last:
            warnings.append(f"{axis_label}：X 轴范围内没有实测扫速，已忽略")
            return
        current_low, current_high = ax.get_xlim()
        # Start/end between full bar groups instead of clipping any bar.
        ax.set_xlim(
            first - .5 if first > 0 else current_low,
            last - .5 if last < len(categories) else current_high,
        )
        return

    scale = ax.get_xscale() if side == "x" else ax.get_yscale()
    if scale == "log":
        invalid_positive = (
            (low is not None and low <= 0) or (high is not None and high <= 0)
        )
        if invalid_positive:
            warnings.append(
                f"{axis_label}：对数 {axis_name} 轴范围必须为正数，已忽略该设置"
            )
            return

    current_low, current_high = (
        ax.get_xlim() if side == "x" else ax.get_ylim()
    )
    effective_low = low if low is not None else float(current_low)
    effective_high = high if high is not None else float(current_high)
    if not (math.isfinite(effective_low) and math.isfinite(effective_high)):
        warnings.append(f"{axis_label}：{axis_name} 轴范围不是有限数值，已忽略")
        return
    if effective_low >= effective_high:
        warnings.append(
            f"{axis_label}：{axis_name} 轴范围无效（最小值必须小于最大值），已忽略"
        )
        return
    try:
        if side == "x":
            ax.set_xlim(effective_low, effective_high)
        else:
            ax.set_ylim(effective_low, effective_high)
    except (TypeError, ValueError) as exc:
        warnings.append(f"{axis_label}：无法设置 {axis_name} 轴范围（{exc}）")


def apply_axis_limits(
    figure: Figure,
    kind: str,
    analysis_options: dict | None,
) -> list[str]:
    """Synchronize and apply stored manual limits, returning any warnings."""
    warnings = sync_axis_limit_units(figure, kind, analysis_options)
    limits = (analysis_options or {}).get("axis_limits")
    if not isinstance(limits, dict) or not limits:
        return warnings
    for spec in plot_axis_specs(kind, figure):
        entry = limits.get(spec.key)
        if not isinstance(entry, dict) or spec.index >= len(figure.axes):
            continue
        ax = figure.axes[spec.index]
        stored_units = axis_limit_unit_values(analysis_options, spec.key)
        current_units = axis_display_units(ax)
        if _entry_has_limits(entry):
            _release_fixed_aspect(ax)
        _apply_side(
            ax,
            axis_name="X",
            side="x",
            entry=entry,
            editable=spec.editable_x,
            axis_label=spec.label,
            warnings=warnings,
            stored_units=stored_units,
            current_units=current_units,
        )
        _apply_side(
            ax,
            axis_name="Y",
            side="y",
            entry=entry,
            editable=spec.editable_y,
            axis_label=spec.label,
            warnings=warnings,
            stored_units=stored_units,
            current_units=current_units,
        )
    return warnings


__all__ = [
    "PlotAxisSpec",
    "apply_axis_limits",
    "axis_display_dimensions",
    "axis_display_units",
    "axis_limit_unit_values",
    "axis_limit_values",
    "common_axis_display_unit",
    "plot_axis_specs",
    "set_axis_display_units",
    "sync_axis_limit_units",
    "unit_dimension",
]
