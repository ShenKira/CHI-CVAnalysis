# -*- coding: utf-8 -*-
"""CV plot renderers (GUI canvas and headless export use the same code)."""

from __future__ import annotations

from typing import Iterable

import matplotlib.ticker as mticker
import numpy as np
from matplotlib.figure import Figure

from cvanalysis.analysis.cv import (
    BValueResult,
    CVRunSummary,
    ScanRatePoint,
    analyze_cv_run,
    collect_scan_rate_points,
    dunn_analysis,
    dunn_fraction_vs_scan_rate,
    fit_b_value,
    scan_window_warning,
    trasatti_analysis,
)
from cvanalysis.domain.errors import AnalysisError
from cvanalysis.domain.models import CVRun, Dataset
from cvanalysis.domain.units import (
    AREAL_CAPACITANCE,
    CAPACITANCE,
    CURRENT,
    CURRENT_DENSITY,
    SPECIFIC_CAPACITANCE,
    SPECIFIC_CURRENT,
    charge_family,
    choose_unit,
    choose_unit_for_values,
    current_family,
    normalize_capacitance,
    normalize_charge,
    normalize_current,
    resolve_unit,
    unit_factor,
)
from cvanalysis.plotting.axis_limits import set_axis_display_units
from cvanalysis.plotting.colors import resolve_color_cycle
from cvanalysis.plotting.legend import dataset_file_numbers, effective_template, preview_label, template_uses_cycle
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure, font_kwargs


def _option_float(options: dict, key: str, default: float, low: float, high: float) -> float:
    try:
        value = float(options.get(key, default))
    except (TypeError, ValueError):
        return default
    if not np.isfinite(value):
        return default
    return min(max(value, low), high)


_CJK_FONT_CACHE: list[str] | None = None


def _cjk_fonts() -> list[str]:
    global _CJK_FONT_CACHE
    if _CJK_FONT_CACHE is not None:
        return _CJK_FONT_CACHE
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"]
    _CJK_FONT_CACHE = [name for name in candidates if name in available] or ["DejaVu Sans"]
    return _CJK_FONT_CACHE


def _message(figure: Figure, style: PlotStyle, text: str, *, color: str = "#888888") -> None:
    figure.clear()
    ax = figure.add_subplot(111)
    ax.text(
        0.5,
        0.5,
        text,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=max(10, style.font_size),
        color=color,
        fontfamily=_cjk_fonts(),
        wrap=True,
    )
    ax.set_axis_off()
    style.apply(figure)


def _selected_cycles(run: CVRun, spec: PlotSpec) -> list:
    if run.run_id in spec.cycle_selection:
        selected_set = set(spec.cycle_selection[run.run_id])
        return [cycle for cycle in run.cycles if cycle.index in selected_set]
    return list(run.cycles)


def _selected_cv_runs(dataset: Dataset, spec: PlotSpec) -> list[CVRun]:
    if not spec.run_ids:
        return []
    selected = set(spec.run_ids)
    return [run for run in dataset.cv_runs if run.run_id in selected]


def _ensure_summaries(runs: Iterable[CVRun]) -> None:
    for run in runs:
        if run.summary is None:
            analyze_cv_run(run)


def _normalization_available(runs: Iterable[CVRun], normalization: str) -> bool:
    runs = list(runs)
    if normalization == "none":
        return True
    if normalization == "area":
        return all(run.params.has_area() for run in runs)
    if normalization == "mass":
        return all(run.params.has_mass() for run in runs)
    return False


def _unit_override(spec: PlotSpec, key: str) -> str | None:
    overrides = spec.analysis_options.get("unit_overrides")
    if not isinstance(overrides, dict):
        return None
    value = overrides.get(key)
    if not value or str(value) == "auto":
        return None
    return str(value)


def _resolve_current_unit(
    spec: PlotSpec,
    values: Iterable[float] | None,
    normalization: str,
    warnings: list[str],
    *,
    use_max: bool = True,
) -> tuple[str, float]:
    family = current_family(normalization)
    override = _unit_override(spec, "current")
    unit, factor = resolve_unit(family, values, override, use_max=use_max)
    if override and unit_factor(family, override) is None:
        warnings.append(
            f"电流单位 {override} 不适用于当前归一化方式，已自动选择 {unit}"
        )
    return unit, factor


def _current_unit_and_factor(
    runs: Iterable[CVRun],
    normalization: str,
    spec: PlotSpec,
    warnings: list[str],
) -> tuple[str, float, list[float]]:
    values: list[float] = []
    for run in runs:
        for cycle in run.cycles:
            if not cycle.valid:
                continue
            current = normalize_current(
                cycle.current,
                normalization,
                area_cm2=run.params.area_cm2,
                mass_mg=run.params.mass_mg,
            )
            values.extend(np.asarray(current, dtype=float).tolist())
    unit, factor = _resolve_current_unit(
        spec, values, normalization, warnings, use_max=True
    )
    return unit, factor, values


def _cap_unit_and_factor(runs: Iterable[CVRun], normalization: str) -> tuple[str, float]:
    family = (
        AREAL_CAPACITANCE
        if normalization == "area"
        else SPECIFIC_CAPACITANCE
        if normalization == "mass"
        else CAPACITANCE
    )
    values = []
    for run in runs:
        if run.summary and run.summary.mean_capacitance_F:
            value = normalize_capacitance(
                run.summary.mean_capacitance_F,
                normalization,
                area_cm2=run.params.area_cm2,
                mass_mg=run.params.mass_mg,
            )
            if value is not None:
                values.append(value)
    unit, factor = choose_unit_for_values(family, values, use_max=False)
    return unit, factor


def _can_normalize_point(point: ScanRatePoint, normalization: str) -> bool:
    if normalization == "none":
        return True
    if normalization == "area":
        return point.area_cm2 is not None and point.area_cm2 > 0
    if normalization == "mass":
        return point.mass_mg is not None and point.mass_mg > 0
    return False


def _point_capacitance(point: ScanRatePoint, normalization: str) -> float | None:
    if not _can_normalize_point(point, normalization):
        return None
    value = normalize_capacitance(
        point.capacitance_F,
        normalization,
        area_cm2=point.area_cm2,
        mass_mg=point.mass_mg,
    )
    return value


def _point_capacitance_sd(point: ScanRatePoint, normalization: str) -> float | None:
    if not _can_normalize_point(point, normalization):
        return None
    return normalize_capacitance(
        point.capacitance_sd_F,
        normalization,
        area_cm2=point.area_cm2,
        mass_mg=point.mass_mg,
    )


def _point_current(point: ScanRatePoint, normalization: str, key: str = "up") -> float | None:
    value = point.current_up_A if key == "up" else point.current_down_A
    if value is None or not np.isfinite(value):
        return None
    if not _can_normalize_point(point, normalization):
        return None
    if normalization == "area":
        return value / point.area_cm2
    if normalization == "mass":
        return value / (point.mass_mg * 1e-3)
    return value


def _set_labels(ax, style: PlotStyle, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(xlabel, **font_kwargs(style, axis="x"))
    ax.set_ylabel(ylabel, **font_kwargs(style, axis="y"))


def _annotate(ax, style: PlotStyle, text: str, *, color: str = "#333333") -> None:
    ax.text(
        0.98,
        0.04,
        text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=style.annotation_size,
        fontfamily=style.font_family,
        fontweight="bold" if style.annotation_bold else "normal",
        color=color,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8e6", edgecolor="#d9c89e", alpha=0.9),
    )


def _title(ax, style: PlotStyle, title: str) -> None:
    if title and style.show_title:
        ax.set_title(
            title,
            fontsize=style.title_size,
            fontfamily=style.font_family,
            fontweight="bold" if style.title_bold else "normal",
        )


def _finish(figure: Figure, style: PlotStyle, spec: PlotSpec) -> None:
    if not spec.show_axes:
        for ax in figure.axes:
            ax.tick_params(labelbottom=False, labelleft=False, labelright=False, labeltop=False)
            if ax.xaxis.label:
                ax.xaxis.label.set_visible(False)
            if ax.yaxis.label:
                ax.yaxis.label.set_visible(False)
    if getattr(figure, "_defer_final_layout", False):
        return
    finalize_figure(figure, style)
    from cvanalysis.plotting.paper import finish_paper
    finish_paper(figure, spec, style)


def draw_cv_overlay(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    warnings: list[str] = []
    normalization = spec.normalization
    if not _normalization_available(runs, normalization):
        warnings.append("部分数据缺少面积/质量参数，已回退为原始电流")
        normalization = "none"

    unit, factor, _ = _current_unit_and_factor(
        runs, normalization, spec, warnings
    )
    figure.clear()
    ax = figure.add_subplot(111)
    color_by_run = spec.color_by == "run" or (spec.color_by == "auto" and len(runs) > 1)
    colors = resolve_color_cycle(style, max(sum(len(_selected_cycles(run, spec)) for run in runs), len(runs)), color_config)
    color_index = 0
    labeled_runs: set[int] = set()
    line_handles: list[tuple[str, str]] = []
    legend_warnings: set[str] = set()
    file_numbers = dataset_file_numbers(dataset)

    for run_index, run in enumerate(runs):
        cycles = [cycle for cycle in _selected_cycles(run, spec) if cycle.valid]
        if not cycles:
            warnings.append(f"{run.display_name} 没有可绘制的有效循环")
            continue
        template = effective_template(run, spec)
        per_cycle_template = template_uses_cycle(template)
        run_display_index = 0
        for cycle in cycles:
            current = normalize_current(
                cycle.current,
                normalization,
                area_cm2=run.params.area_cm2,
                mass_mg=run.params.mass_mg,
            )
            if color_by_run:
                color = colors[run_index % len(colors)]
            else:
                color = colors[color_index % len(colors)]
            color_index += 1
            run_display_index += 1
            cycle_label = run_display_index if spec.renumber_cycles else cycle.index
            rate = run.metadata.scan_rate
            if template:
                if per_cycle_template:
                    label, unknown = preview_label(
                        run,
                        template,
                        cycle=cycle,
                        cycle_number=cycle_label,
                        file_number=file_numbers.get(run.run_id),
                        fallback=f"Cycle {cycle_label}",
                    )
                    for token in unknown:
                        legend_warnings.add(f"图例模板包含未知字段: {{{token}}}")
                elif run_index in labeled_runs:
                    label = None
                else:
                    label, unknown = preview_label(
                        run,
                        template,
                        cycle=cycles[0],
                        cycle_number=cycles[0].index,
                        file_number=file_numbers.get(run.run_id),
                        fallback=run.legend_name,
                    )
                    for token in unknown:
                        legend_warnings.add(f"图例模板包含未知字段: {{{token}}}")
                    labeled_runs.add(run_index)
            elif color_by_run:
                if run_index in labeled_runs:
                    label = None
                else:
                    label = run.legend_name
                    if rate:
                        label += f" ({rate:g} V/s)"
                    labeled_runs.add(run_index)
            elif len(runs) > 1:
                label = f"{run.legend_name} C{cycle_label}"
            else:
                label = f"Cycle {cycle_label}"
            ax.plot(
                cycle.potential,
                np.asarray(current) * factor,
                color=color,
                linewidth=style.line_width,
                marker=style.marker or None,
                markersize=style.marker_size,
                alpha=_option_float(spec.analysis_options, "line_alpha", 0.9, 0.05, 1.0),
                label=label,
            )
            if label is not None:
                line_handles.append((label, color))
    if legend_warnings:
        warnings.extend(sorted(legend_warnings))

    ylabel = "Current (A)"
    if normalization == "area":
        ylabel = f"Current density ({unit})"
    elif normalization == "mass":
        ylabel = f"Specific current ({unit})"
    else:
        ylabel = f"Current ({unit})"
    _set_labels(ax, style, "Potential (V)", ylabel)
    set_axis_display_units(ax, x=("V", 1.0), y=(unit, factor))
    _title(ax, style, spec.title)

    if style.legend and spec.show_legend and line_handles:
        columns = style.legend_columns if len(line_handles) > 8 else 1
        legend = ax.legend(
            loc=style.legend_location,
            fontsize=style.legend_size,
            frameon=style.legend_frame,
            shadow=style.legend_shadow,
            ncol=columns,
        )
        style.style_legend(legend)

    if style.annotation and spec.annotations:
        if len(runs) == 1:
            run = runs[0]
            selected_cycles = [cycle for cycle in _selected_cycles(run, spec) if cycle.valid]
            capacities = [
                cycle.capacitance_F
                for cycle in selected_cycles
                if np.isfinite(cycle.capacitance_F)
            ]
            if capacities:
                cap_unit, cap_factor = _cap_unit_and_factor(runs, normalization)
                mean_cap = float(np.mean(capacities))
                sd_cap = float(np.std(capacities, ddof=1)) if len(capacities) > 1 else 0.0
                mean_value = normalize_capacitance(
                    mean_cap,
                    normalization,
                    area_cm2=run.params.area_cm2,
                    mass_mg=run.params.mass_mg,
                )
                sd_value = normalize_capacitance(
                    sd_cap,
                    normalization,
                    area_cm2=run.params.area_cm2,
                    mass_mg=run.params.mass_mg,
                )
                if mean_value is not None:
                    text = f"Mean C = {mean_value * cap_factor:.4g} {cap_unit}"
                    if sd_value is not None and np.isfinite(sd_value):
                        text += f"\nSD = {sd_value * cap_factor:.4g} {cap_unit}"
                    text += f"\nN = {len(selected_cycles)}"
                    _annotate(ax, style, text)
        else:
            total_cycles = sum(len(_selected_cycles(run, spec)) for run in runs)
            _annotate(ax, style, f"{len(runs)} runs\n{total_cycles} cycles")
    if warnings:
        ax.text(
            0.02,
            0.98,
            "\n".join(warnings[:3]),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=max(8, style.annotation_size - 1),
            color="#a33",
            fontfamily=_cjk_fonts(),
        )
    _finish(figure, style, spec)
    return warnings


def _fit_power_law(rates: np.ndarray, values: np.ndarray) -> tuple[float, float, float]:
    x = np.log10(rates)
    y = np.log10(values)
    slope, intercept = np.polyfit(x, y, 1)
    prediction = slope * x + intercept
    ss_res = float(np.sum((y - prediction) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return float(slope), float(intercept), float(r2)


def _resolve_scan_axis_scale(requested, values, *, lower_bounds=None) -> tuple[str, str | None]:
    """Resolve linear/log/auto display scale and reject invalid log data."""
    requested = requested if requested in {"auto", "linear", "log"} else "auto"
    values = np.asarray(values, dtype=float)
    finite_positive = values.size > 0 and np.all(np.isfinite(values) & (values > 0))
    if lower_bounds is not None:
        lower_bounds = np.asarray(lower_bounds, dtype=float)
        finite_positive = finite_positive and np.all(np.isfinite(lower_bounds) & (lower_bounds > 0))
    if requested == "linear":
        return "linear", None
    if requested == "log":
        if finite_positive:
            return "log", None
        return "linear", "对数坐标要求数据及误差棒下界均为正数，已回退为线性坐标"
    if finite_positive and np.max(values) / np.min(values) >= 20:
        return "log", None
    return "linear", None


def draw_cap_scan(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    warnings: list[str] = []
    normalization = spec.normalization
    if not _normalization_available(runs, normalization):
        warnings.append("部分数据缺少面积/质量参数，已回退为原始电容")
        normalization = "none"
    points = collect_scan_rate_points(runs, cycle_selection=spec.cycle_selection)
    window_warning = scan_window_warning(points)
    if window_warning:
        warnings.append(window_warning)
    usable = [
        (point, _point_capacitance(point, normalization), _point_capacitance_sd(point, normalization))
        for point in points
    ]
    usable = [
        (point, value, sd)
        for point, value, sd in usable
        if value is not None and np.isfinite(value) and value > 0
    ]
    if not usable:
        _message(figure, style, "没有可用于电容-扫速曲线的数据")
        return warnings + ["没有可用于电容-扫速曲线的数据"]

    rates = np.asarray([point.scan_rate for point, _, _ in usable], dtype=float)
    values = np.asarray([value for _, value, _ in usable], dtype=float)
    errors = np.asarray(
        [sd if sd is not None and np.isfinite(sd) else 0.0 for _, _, sd in usable],
        dtype=float,
    )
    family = (
        AREAL_CAPACITANCE
        if normalization == "area"
        else SPECIFIC_CAPACITANCE
        if normalization == "mass"
        else CAPACITANCE
    )
    unit, factor = choose_unit_for_values(family, values, use_max=False)
    colors = resolve_color_cycle(style, 2, color_config)

    figure.clear()
    ax = figure.add_subplot(111)
    options = spec.analysis_options
    fit_method = options.get("fit_method", "power")
    if fit_method not in {"linear", "coordinate_line", "power", "none"}:
        fit_method = "power"
    x_request = options.get("x_axis_scale")
    if x_request is None:
        # Older projects only had this boolean. False historically meant
        # automatic range-based scaling; True explicitly requested log X.
        x_request = "log" if spec.x_log else "auto"
    y_request = options.get("y_axis_scale", "auto")
    x_scale, x_warning = _resolve_scan_axis_scale(x_request, rates)
    lower_bounds = values - errors if options.get("error_bars", True) else None
    y_scale, y_warning = _resolve_scan_axis_scale(
        y_request, values, lower_bounds=lower_bounds
    )
    warnings.extend(message for message in (x_warning, y_warning) if message)
    ax.set_xscale(x_scale)
    ax.set_yscale(y_scale)
    ax.errorbar(
        rates,
        values * factor,
        yerr=errors * factor if options.get("error_bars", True) else None,
        fmt="o",
        color=colors[0],
        markersize=max(4.0, style.marker_size + 2),
        linewidth=style.line_width,
        capsize=3,
        label="Measured",
    )
    if fit_method != "none" and np.unique(np.round(rates, 12)).size >= 2:
        if x_scale == "log":
            fit_x = np.geomspace(float(np.min(rates)), float(np.max(rates)), 100)
        else:
            fit_x = np.linspace(float(np.min(rates)), float(np.max(rates)), 100)
        if fit_method == "linear":
            # Raw-data first-degree fit: its coefficients do not depend on the
            # selected display scales, so it can appear curved on log axes.
            slope, intercept = np.polyfit(rates, values, 1)
            prediction = slope * rates + intercept
            total = float(np.sum((values - np.mean(values)) ** 2))
            r2 = 1 - float(np.sum((values - prediction) ** 2)) / total if total > 0 else float("nan")
            fit_y = (slope * fit_x + intercept) * factor
            equation = f"C = {slope * factor:.4g} v + {intercept * factor:.4g} {unit}"
        elif fit_method == "coordinate_line":
            # Fit a line in the coordinates the viewer sees, then invert each
            # transform so Matplotlib draws a straight line on the selected axes.
            displayed_values = values * factor
            x_data = np.log10(rates) if x_scale == "log" else rates
            y_data = np.log10(displayed_values) if y_scale == "log" else displayed_values
            slope, intercept = np.polyfit(x_data, y_data, 1)
            predicted = slope * x_data + intercept
            total = float(np.sum((y_data - np.mean(y_data)) ** 2))
            r2 = 1 - float(np.sum((y_data - predicted) ** 2)) / total if total > 0 else float("nan")
            fit_x_data = np.linspace(float(np.min(x_data)), float(np.max(x_data)), 100)
            fit_x = 10**fit_x_data if x_scale == "log" else fit_x_data
            fit_y_data = slope * fit_x_data + intercept
            fit_y = 10**fit_y_data if y_scale == "log" else fit_y_data
            x_term = "log10(v)" if x_scale == "log" else "v"
            y_term = "log10(C)" if y_scale == "log" else "C"
            equation = f"{y_term} = {slope:.4g}·{x_term} + {intercept:.4g}"
        else:
            slope, intercept, r2 = _fit_power_law(rates, values)
            fit_y = (10**intercept) * fit_x**slope * factor
            equation = f"C = {10**intercept * factor:.4g} v^{slope:.3f}"
        fit_is_straight = (
            fit_method == "coordinate_line"
            or (fit_method == "linear" and x_scale == "linear" and y_scale == "linear")
            or (fit_method == "power" and x_scale == "log" and y_scale == "log")
        )
        fit_label = "Fitted Line" if fit_is_straight else "Fitted Curve"
        if fit_method == "linear" and y_scale == "log" and np.any(fit_y <= 0):
            warnings.append("一次函数在部分扫速处预测值非正，纵轴为对数时该段拟合线不可见")
            fit_y = np.where(fit_y > 0, fit_y, np.nan)
        if options.get("fit_line", True):
            ax.plot(fit_x, fit_y, "--", color=colors[1], linewidth=style.line_width, label=fit_label)
        if style.annotation and spec.annotations:
            compact = spec.paper_layout.get("enabled") and spec.paper_layout.get("fraction", 1) * spec.paper_layout.get("text_width_mm", 160) <= 85
            compact_text = f"n={slope:.2f}; R²={r2:.3f}" if fit_method == "power" else f"R²={r2:.3f}"
            _annotate(ax, style, compact_text if compact else f"{equation}\nR² = {r2:.4f}")
    if x_scale == "log":
        ax.xaxis.set_major_formatter(mticker.LogFormatterSciNotation())
    _set_labels(ax, style, "Scan rate (V/s)", f"Capacitance ({unit})")
    if spec.paper_layout.get("enabled") and spec.paper_layout.get("fraction", 1) * spec.paper_layout.get("text_width_mm", 160) <= 85:
        _set_labels(ax, style, "v (V/s)", f"C ({unit})")
    _title(ax, style, spec.title or "Capacitance vs scan rate")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size, frameon=style.legend_frame, shadow=style.legend_shadow)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top", fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_current_scan(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    warnings: list[str] = []
    normalization = spec.normalization
    if not _normalization_available(runs, normalization):
        warnings.append("部分数据缺少面积/质量参数，已回退为原始电流")
        normalization = "none"
    target = spec.target_voltage
    if target is None:
        window = [run.voltage_window for run in runs if run.voltage_window]
        if not window:
            _message(figure, style, "请先在分析面板输入目标电位")
            return ["缺少目标电位"]
        low = max(float(np.nanmin(run.potential)) for run in runs)
        high = min(float(np.nanmax(run.potential)) for run in runs)
        target = (low + high) / 2.0
    points = collect_scan_rate_points(runs, target_voltage=target, current_mode="absolute", cycle_selection=spec.cycle_selection)
    usable = []
    for point in points:
        up = _point_current(point, normalization, "up")
        down = _point_current(point, normalization, "down")
        if (up is not None and np.isfinite(up)) or (down is not None and np.isfinite(down)):
            usable.append((point, up, down))
    if not usable:
        _message(figure, style, f"在 {target:g} V 处没有可用的电流数据")
        return warnings + ["没有可用的固定电位电流"]

    all_values = [abs(value) for _, up, down in usable for value in (up, down) if value is not None and np.isfinite(value)]
    unit, factor = _resolve_current_unit(spec, all_values, normalization, warnings)
    rates = np.asarray([point.scan_rate for point, _, _ in usable], dtype=float)
    up_values = np.asarray([up if up is not None else np.nan for _, up, _ in usable], dtype=float)
    down_values = np.asarray([down if down is not None else np.nan for _, _, down in usable], dtype=float)
    colors = resolve_color_cycle(style, 2, color_config)

    figure.clear()
    ax = figure.add_subplot(111)
    ax.plot(rates, np.abs(up_values) * factor, "o-", color=colors[0], linewidth=style.line_width, markersize=style.marker_size + 1, label="Forward |i|")
    ax.plot(rates, np.abs(down_values) * factor, "s--", color=colors[1], linewidth=style.line_width, markersize=style.marker_size, label="Reverse |i|")
    if spec.x_log or (np.max(rates) / max(np.min(rates), 1e-30) >= 20):
        ax.set_xscale("log")
    if normalization == "area":
        ylabel = f"Current density ({unit})"
    elif normalization == "mass":
        ylabel = f"Specific current ({unit})"
    else:
        ylabel = f"Current ({unit})"
    _set_labels(ax, style, "Scan rate (V/s)", ylabel)
    set_axis_display_units(ax, x=("V/s", 1.0), y=(unit, factor))
    _title(ax, style, spec.title or f"Current at {target:g} V")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size, frameon=style.legend_frame, shadow=style.legend_shadow)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top", fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_b_value(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    warnings: list[str] = []
    normalization = spec.normalization
    if not _normalization_available(runs, normalization):
        warnings.append("部分数据缺少面积/质量参数，已回退为原始电流")
        normalization = "none"
    target = spec.target_voltage
    if target is None:
        low = max(float(np.nanmin(run.potential)) for run in runs)
        high = min(float(np.nanmax(run.potential)) for run in runs)
        target = (low + high) / 2.0
    current_mode = spec.analysis_options.get("b_current_mode", "absolute")
    if current_mode not in {"absolute", "up", "down"}:
        current_mode = "absolute"
    points = collect_scan_rate_points(
        runs,
        target_voltage=target,
        current_mode=current_mode,
        cycle_selection=spec.cycle_selection,
    )
    rates = []
    currents = []
    labels = []
    for point in points:
        value = point.current_abs_A
        if value is None or not np.isfinite(value):
            continue
        normalized = normalize_current(
            value,
            normalization,
            area_cm2=point.area_cm2,
            mass_mg=point.mass_mg,
        )
        normalized = float(np.asarray(normalized, dtype=float))
        if not np.isfinite(normalized) or normalized <= 0:
            continue
        rates.append(point.scan_rate)
        currents.append(normalized)
        labels.append(point.label)
    if len(rates) < 2:
        _message(figure, style, "b 值分析至少需要两个不同扫速下的有效电流")
        return warnings + ["b 值分析数据不足"]
    rates_arr = np.asarray(rates, dtype=float)
    currents_arr = np.asarray(currents, dtype=float)
    slope, intercept, r2 = _fit_power_law(rates_arr, currents_arr)
    unit, factor = _resolve_current_unit(spec, currents_arr, normalization, warnings)
    colors = resolve_color_cycle(style, 3, color_config)

    figure.clear()
    ax = figure.add_subplot(111)
    ax.loglog(rates_arr, currents_arr * factor, "o", color=colors[0], markersize=style.marker_size + 2, label="Measured")
    fit_x = np.geomspace(float(np.min(rates_arr)), float(np.max(rates_arr)), 100)
    ax.loglog(fit_x, (10**intercept) * fit_x**slope * factor, "-", color=colors[0], linewidth=style.line_width, label="Fitted Line")
    for guide, guide_color in ((0.5, "#999999"), (1.0, "#bbbbbb")):
        ax.loglog(fit_x, fit_x**guide * (currents_arr[0] / rates_arr[0] ** 0.5) * factor, ":", color=guide_color, linewidth=0.9, label=f"b = {guide:g}")
    if normalization == "area":
        ylabel = f"|Current density| ({unit})"
    elif normalization == "mass":
        ylabel = f"|Specific current| ({unit})"
    else:
        ylabel = f"|Current| ({unit})"
    _set_labels(ax, style, "Scan rate (V/s)", ylabel)
    set_axis_display_units(ax, x=("V/s", 1.0), y=(unit, factor))
    _title(ax, style, spec.title or f"b-value at {target:g} V")
    # This is a log/log chart. Keep decade labels and suppress the minor
    # scientific-notation labels that collide when the scan-rate range is
    # narrow (a common case with only a few selected runs).
    ax.xaxis.set_major_formatter(mticker.LogFormatterSciNotation(labelOnlyBase=True))
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    if style.annotation and spec.annotations:
        _annotate(ax, style, f"b = {slope:.3f}\nR² = {r2:.4f}\nN = {len(rates)}")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size, frameon=style.legend_frame, shadow=style.legend_shadow)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top", fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_contribution(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    try:
        result = dunn_analysis(
            runs,
            normalization=spec.normalization,
            selected_scan_rate=spec.selected_scan_rate,
            cycle_selection=spec.cycle_selection,
        )
    except AnalysisError as exc:
        _message(figure, style, str(exc))
        return [str(exc)]

    warnings = list(result.warnings)
    unit, factor = _resolve_current_unit(
        spec, result.total_current, result.normalization, warnings
    )
    colors = resolve_color_cycle(style, 3, color_config)
    figure.clear()
    ax = figure.add_subplot(111)
    x = result.potential
    total = result.total_current * factor
    capacitive = result.capacitive_current * factor
    diffusive = result.diffusive_current * factor
    ax.plot(x, total, color="#222222", linewidth=style.line_width, label="Total")
    ax.plot(x, capacitive, color=colors[0], linewidth=style.line_width, label="Capacitive")
    ax.plot(x, diffusive, color=colors[1], linewidth=style.line_width, label="Diffusive")
    ax.fill_between(
        x,
        capacitive,
        total,
        color=colors[0],
        alpha=_option_float(spec.analysis_options, "fill_alpha", 0.12, 0.0, 1.0),
    )
    if result.normalization == "area":
        ylabel = f"Current density ({unit})"
    elif result.normalization == "mass":
        ylabel = f"Specific current ({unit})"
    else:
        ylabel = f"Current ({unit})"
    _set_labels(ax, style, "Potential (V)", ylabel)
    set_axis_display_units(ax, x=("V", 1.0), y=(unit, factor))
    _title(ax, style, spec.title or f"Dunn current decomposition at {result.scan_rate:g} V/s")
    if style.annotation and spec.annotations:
        _annotate(ax, style, f"Capacitive = {result.capacitive_fraction * 100:.1f}%\nMean R² = {result.mean_r2:.3f}")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size, frameon=style.legend_frame, shadow=style.legend_shadow)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top", fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_trasatti(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    warnings: list[str] = []
    normalization = spec.normalization
    if not _normalization_available(runs, normalization):
        warnings.append("部分数据缺少面积/质量参数，已回退为原始电荷")
        normalization = "none"
    points = collect_scan_rate_points(runs, cycle_selection=spec.cycle_selection)
    xs: list[float] = []
    charges: list[float] = []
    for point in points:
        width = (
            point.integration_width_V
            if point.integration_width_V is not None
            and np.isfinite(point.integration_width_V)
            and point.integration_width_V > 0
            else point.voltage_window
        )
        if (
            point.capacitance_F is None
            or width is None
            or not np.isfinite(width)
            or width <= 0
            or point.scan_rate <= 0
            or not np.isfinite(point.capacitance_F)
        ):
            continue
        charge = normalize_charge(
            point.capacitance_F * width,
            normalization,
            area_cm2=point.area_cm2,
            mass_mg=point.mass_mg,
        )
        if charge is None or not np.isfinite(charge):
            continue
        xs.append(1.0 / np.sqrt(point.scan_rate))
        charges.append(float(charge))
    if len(xs) < 2:
        _message(figure, style, "Trasatti 分析至少需要两个不同扫速")
        return warnings + ["Trasatti 分析数据不足"]
    try:
        warnings.extend(trasatti_analysis(points).warnings)
    except AnalysisError:
        pass
    x_values = np.asarray(xs, dtype=float)
    y_values = np.asarray(charges, dtype=float)
    slope, intercept = np.polyfit(x_values, y_values, 1)
    predicted = intercept + slope * x_values
    ss_res = float(np.sum((y_values - predicted) ** 2))
    ss_tot = float(np.sum((y_values - np.mean(y_values)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    q_low = float(y_values[np.argmax(x_values)])
    fraction = intercept / q_low if q_low else float("nan")
    unit, factor = choose_unit_for_values(charge_family(normalization), y_values, use_max=False)
    colors = resolve_color_cycle(style, 2, color_config)

    figure.clear()
    ax = figure.add_subplot(111)
    ax.plot(x_values, y_values * factor, "o", color=colors[0], markersize=style.marker_size + 2, label="Measured")
    fit_x = np.linspace(float(np.min(x_values)), float(np.max(x_values)), 100)
    ax.plot(fit_x, (intercept + slope * fit_x) * factor, "-", color=colors[0], linewidth=style.line_width, label="Fitted Line")
    if normalization == "area":
        ylabel = f"Charge density ({unit})"
    elif normalization == "mass":
        ylabel = f"Specific charge ({unit})"
    else:
        ylabel = f"Charge ({unit})"
    _set_labels(ax, style, r"$v^{-1/2}$ (V/s)$^{-1/2}$", ylabel)
    _title(ax, style, spec.title or "Trasatti charge separation")
    if style.annotation and spec.annotations:
        _annotate(
            ax,
            style,
            f"q_cap = {intercept * factor:.4g} {unit}\n"
            f"Capacitive fraction = {fraction * 100:.1f}%\nR? = {r2:.4f}",
        )
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size, frameon=style.legend_frame, shadow=style.legend_shadow)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top", fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_contribution_vs_rate(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_cv_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CV 数据")
        return ["没有选择 CV 数据"]
    _ensure_summaries(runs)
    try:
        result = dunn_fraction_vs_scan_rate(
            runs,
            normalization=spec.normalization,
            cycle_selection=spec.cycle_selection,
        )
    except AnalysisError as exc:
        _message(figure, style, str(exc))
        return [str(exc)]

    if result.scan_rates.size == 0:
        _message(figure, style, "没有可用于贡献占比分析的扫速")
        return ["没有可用于贡献占比分析的扫速"]

    rates = result.scan_rates
    capacitive = result.capacitive_fraction * 100.0
    diffusive = result.diffusive_fraction * 100.0
    positions = np.arange(len(rates), dtype=float)
    colors = resolve_color_cycle(style, 2, color_config)

    figure.clear()
    ax = figure.add_subplot(111)
    bar_width = _option_float(spec.analysis_options, "bar_width", 0.72, 0.1, 1.0)
    bar_alpha = _option_float(spec.analysis_options, "bar_alpha", 1.0, 0.05, 1.0)
    ax.bar(positions, capacitive, width=bar_width, alpha=bar_alpha, color=colors[0], label="Capacitive")
    ax.bar(positions, diffusive, bottom=capacitive, width=bar_width, alpha=bar_alpha, color=colors[1], label="Diffusive")
    ax.set_xticks(positions)
    ax.set_xticklabels([f"{rate:g}" for rate in rates])
    ax.set_ylim(0.0, 100.0)
    if len(rates) > 6:
        ax.tick_params(axis="x", labelrotation=45)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")
    _set_labels(ax, style, "Scan rate (V/s)", "Contribution (%)")
    _title(ax, style, spec.title or "Contribution vs scan rate")

    if style.annotation and spec.annotations:
        for position, cap_value, diff_value in zip(positions, capacitive, diffusive):
            if np.isfinite(cap_value):
                ax.text(
                    position,
                    cap_value / 2.0,
                    f"{cap_value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=max(6.0, style.annotation_size - 1),
                    color="white" if cap_value > 18 else "#263238",
                    fontfamily=style.font_family,
                )
            if np.isfinite(diff_value) and diff_value > 18:
                ax.text(
                    position,
                    cap_value + diff_value / 2.0,
                    f"{diff_value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=max(6.0, style.annotation_size - 1),
                    color="white",
                    fontfamily=style.font_family,
                )
        _annotate(ax, style, f"N = {len(rates)} rates\nMean R² = {result.mean_r2:.3f}")

    if style.legend and spec.show_legend:
        legend = ax.legend(
            loc=style.legend_location,
            fontsize=style.legend_size,
            frameon=style.legend_frame,
            shadow=style.legend_shadow,
        )
        style.style_legend(legend)
    if result.warnings:
        ax.text(
            0.02,
            0.98,
            "\n".join(result.warnings[:3]),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=max(8, style.annotation_size - 1),
            color="#a33",
            fontfamily=_cjk_fonts(),
        )
    _finish(figure, style, spec)
    return list(result.warnings)


def draw(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict | None = None,
    metrics: dict | None = None,
) -> list[str]:
    if spec.kind == "cv_overlay":
        return draw_cv_overlay(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_cap_scan":
        return draw_cap_scan(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_current_scan":
        return draw_current_scan(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_bvalue":
        return draw_b_value(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_contribution":
        return draw_contribution(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_contribution_vs_rate":
        return draw_contribution_vs_rate(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cv_trasatti":
        return draw_trasatti(figure, dataset, spec, style, color_config=color_config)
    _message(figure, style, f"未知绘图类型: {spec.kind}")
    return [f"未知绘图类型: {spec.kind}"]
