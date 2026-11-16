# -*- coding: utf-8 -*-
"""Chronopotentiometry / GCD plot renderers (no Qt imports)."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import matplotlib.colors as mcolors
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from cvanalysis.analysis.cp import CPRunSummary, analyze_cp_run, completed_cp_series
from cvanalysis.analysis.cp_series import (
    CPConcatEntry,
    cp_concat_entries,
    cp_cycle_values,
    resolve_cp_unified_reference,
)
from cvanalysis.domain.models import CPRun, Dataset
from cvanalysis.domain.units import CURRENT, canonical_unit, cp_plot_units, resolve_unit
from cvanalysis.plotting.axis_limits import set_axis_display_units
from cvanalysis.plotting.colors import resolve_color_cycle
from cvanalysis.plotting.legend import (
    dataset_file_numbers,
    dataset_runs,
    effective_template,
    is_blank_legend_template,
    preview_label,
    remember_legend_sources,
    resolve_legend_labels,
)
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure, font_kwargs
from cvanalysis.plotting.texts import axis_label_override, axis_text, plot_text, safe_format
from cvanalysis.plotting.template_format import DisplayValue


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


def _message(figure: Figure, style: PlotStyle, text: str) -> None:
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
        color="#888888",
        fontfamily=_cjk_fonts(),
        wrap=True,
    )
    ax.set_axis_off()
    style.apply(figure)


def _selected_runs(dataset: Dataset, spec: PlotSpec) -> list[CPRun]:
    if not spec.run_ids:
        return []
    selected = set(spec.run_ids)
    return [run for run in getattr(dataset, "cp_runs", []) if run.run_id in selected]


def _summary(run: CPRun) -> CPRunSummary:
    return analyze_cp_run(run)


def cp_automatic_unit(summaries, quantity: str, normalization: str, include_holds: bool = False) -> str:
    """Choose one unit for all selected runs from their median finite magnitude."""
    values = []
    for run, summary in summaries:
        divisor = (run.params.area_cm2 if normalization == "area" else
                   run.params.mass_mg * 1e-3 if normalization == "mass" else 1.0)
        if not divisor or not np.isfinite(divisor) or divisor <= 0:
            continue
        for cycle in summary.cycles:
            for segment, charge in ((cycle.charge, cycle.charge_capacity_with_holds_C if include_holds else cycle.charge_capacity_C),
                                    (cycle.discharge, cycle.discharge_capacity_with_holds_C if include_holds else cycle.discharge_capacity_C)):
                if not np.isfinite(charge):
                    continue
                value = abs(charge) / divisor / 3.6
                if quantity == "capacitance":
                    potential = np.asarray(segment.potential_V, dtype=float)
                    delta = abs(float(potential[-1] - potential[0])) if potential.size >= 2 else 0.0
                    if not np.isfinite(delta) or delta <= 0:
                        continue
                    value = value * 3.6 / delta
                if value > 0 and np.isfinite(value):
                    values.append(value)
    units = dict(cp_plot_units(quantity, normalization))
    suffix = "/cm²" if normalization == "area" else "/g" if normalization == "mass" else ""
    names = ("F", "mF", "µF", "nF", "pF") if quantity == "capacitance" else ("Ah", "mAh", "µAh", "nAh", "pAh", "pC")
    if not values:
        return next(iter(units))
    representative = float(np.median(values))
    return next((name + suffix for name in names if representative * units[name + suffix] >= 1), names[-1] + suffix)


def _labels(ax, style: PlotStyle, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(xlabel, **font_kwargs(style, axis="x"))
    ax.set_ylabel(ylabel, **font_kwargs(style, axis="y"))


def _annotate(
    ax,
    style: PlotStyle,
    text: str,
    *,
    x: float = 0.02,
    y: float = 0.04,
    ha: str = "left",
    va: str = "bottom",
    size: float | None = None,
) -> None:
    if not text:
        return
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha=ha,
        va=va,
        fontsize=size if size is not None else style.annotation_size,
        fontfamily=style.text_font_family(),
        fontweight="bold" if style.annotation_bold else "normal",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8e6", edgecolor="#d9c89e", alpha=0.9),
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

    legend_style = style
    if spec.kind == "cp_capacity" and spec.show_legend and not style.legend:
        legend_style = style.with_overrides({"legend": True})
    finish_paper(figure, spec, legend_style)


def _option_float(options: dict, key: str, default: float, low: float, high: float) -> float:
    try:
        value = float(options.get(key, default))
    except (TypeError, ValueError):
        return default
    if not np.isfinite(value):
        return default
    return min(max(value, low), high)


def _current_override(spec: PlotSpec) -> str | None:
    overrides = spec.analysis_options.get("unit_overrides")
    if not isinstance(overrides, dict):
        return None
    value = overrides.get("current")
    if not value or str(value) == "auto":
        return None
    return str(value)


def _current_text(current: float | None, override: str | None = None) -> DisplayValue:
    if current is None or not np.isfinite(current):
        return DisplayValue(None, "—")
    unit, factor = resolve_unit(CURRENT, [current], override)
    value = float(current * factor)
    return DisplayValue(value, f"{value:.3g} {unit}", f" {unit}")


def _legend_label(
    run: CPRun,
    spec: PlotSpec,
    *,
    file_number: int | None,
    warnings: list[str],
    include_current: bool = True,
    default_label: str | None = None,
    manual_alias: bool = False,
) -> str:
    fallback = default_label or run.legend_name
    template = effective_template(run, spec)
    if is_blank_legend_template(template):
        return ""
    alias_used = False
    if template:
        label, unknown = preview_label(
            run,
            template,
            file_number=file_number,
            fallback=fallback,
        )
        for token in unknown:
            message = f"图例模板包含未知字段: {{{token}}}"
            if message not in warnings:
                warnings.append(message)
    else:
        label = fallback
        alias_used = manual_alias or (
            default_label is None and bool(run.legend_alias.strip())
        )
    current = run.applied_current_A
    if include_current and current is not None and not alias_used:
        label = plot_text(
            spec,
            "legend.cp_current_suffix",
            label=label,
            current=_current_text(current, _current_override(spec)),
        )
    return label


def _append_warnings(target: list[str], messages: Iterable[str]) -> None:
    for message in messages:
        if message and message not in target:
            target.append(message)


def _capacity_legend_text(spec, role, *, run, label, fallback, quantity, unit, multiple):
    """CP capacity legends describe plotted series even if the run label is blank."""
    custom = spec.analysis_options.get(f"cp_legend_{role}")
    if isinstance(custom, str) and custom.strip():
        if is_blank_legend_template(custom):
            return ""
        return safe_format(custom, {
            "label": label or fallback,
            "name": run.display_name,
            "quantity": "Capacitance" if quantity == "capacitance" else "Capacity",
            "unit": unit,
        }).strip()
    if role == "mean":
        if label:
            return f"{label} (Charge/Discharge Mean)"
        name = "Capacitance" if quantity == "capacitance" else "Capacity"
        return f"{fallback} {name}" if multiple else name
    if role == "efficiency" and not label:
        return f"{fallback} CE" if multiple else "CE"
    prefix = label or (fallback if multiple else "")
    return plot_text(spec, f"legend.cp_{role}", label=prefix).strip()


def _concat_capacity_legend_text(spec, role, *, run, quantity, unit):
    """Legend text for the single merged series drawn in concatenation mode."""
    custom = spec.analysis_options.get(f"cp_legend_{role}")
    if isinstance(custom, str) and custom.strip():
        if is_blank_legend_template(custom):
            return ""
        return safe_format(custom, {
            "label": "拼接",
            "name": run.display_name if run is not None else "",
            "quantity": "Capacitance" if quantity == "capacitance" else "Capacity",
            "unit": unit,
        }).strip()
    return {
        "charge": "拼接 Charge",
        "discharge": "拼接 Discharge",
        "mean": "拼接 Mean",
        "efficiency": "拼接 CE",
    }[role]


def _cp_range_bounds(raw) -> tuple[int, int] | None:
    """Parse a saved concatenation range without silently accepting nonsense."""
    if isinstance(raw, dict):
        start, end = raw.get("start"), raw.get("end")
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        start, end = raw[0], raw[1]
    else:
        return None
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    try:
        return int(start), int(end)
    except (TypeError, ValueError, OverflowError):
        return None


def _warn_concat_ranges(runs, summaries, options, warnings: list[str]) -> None:
    """Warn about saved ranges that cannot describe a usable cycle interval."""
    ranges = options.get("cp_concat_ranges")
    if not isinstance(ranges, dict):
        return
    for run, summary in zip(runs, summaries):
        raw = ranges.get(run.run_id)
        if raw is None:
            continue
        bounds = _cp_range_bounds(raw)
        if bounds is None:
            message = f"{run.display_name}: 拼接循环范围无效，已使用全部循环"
        elif bounds[0] < 1 or bounds[1] < 1 or bounds[0] > bounds[1]:
            message = f"{run.display_name}: 拼接循环范围无效，已使用全部循环"
        elif not summary.cycles:
            message = f"{run.display_name}: 没有可拼接的完整循环，已跳过"
        elif bounds[0] > len(summary.cycles) or bounds[1] > len(summary.cycles):
            message = f"{run.display_name}: 拼接循环范围超出可用循环，已裁剪"
        else:
            continue
        _append_warnings(warnings, [message])


def draw_gcd_curve(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CP 数据")
        return ["没有选择 CP 数据"]
    warnings: list[str] = []
    complete_holds = bool(spec.analysis_options.get("complete_holds", True))
    figure.clear()
    ax = figure.add_subplot(111)
    colors = resolve_color_cycle(style, len(runs), color_config)
    file_numbers = dataset_file_numbers(dataset)
    resolved_labels = resolve_legend_labels(
        dataset_runs(dataset), spec=spec, file_numbers=file_numbers
    )
    handles: list[str] = []
    for index, run in enumerate(runs):
        summary = _summary(run)
        series = completed_cp_series(
            run,
            complete_holds=complete_holds,
            segments=summary.segments,
            holds=summary.holds,
            warnings=summary.warnings,
        )
        _append_warnings(warnings, series.warnings)
        show_annotation = len(runs) == 1 and style.annotation and spec.annotations
        resolved = resolved_labels.get(run.run_id)
        label = _legend_label(
            run,
            spec,
            file_number=file_numbers.get(run.run_id),
            warnings=warnings,
            include_current=not show_annotation,
            default_label=resolved.label if resolved is not None else None,
            manual_alias=bool(
                resolved.manual if resolved is not None else run.legend_alias.strip()
            ),
        )
        color = colors[index % len(colors)]
        ax.plot(
            series.time_s,
            series.potential_V,
            color=color,
            linewidth=style.line_width,
            marker=style.marker or None,
            markersize=style.marker_size,
            alpha=_option_float(spec.analysis_options, "line_alpha", 0.9, 0.05, 1.0),
            label=label,
        )
        if label:
            handles.append(label)
        if show_annotation:
            lines = [
                plot_text(
                    spec,
                    "annotation.cp_gcd.current",
                    current=_current_text(run.applied_current_A, _current_override(spec)),
                ),
                plot_text(spec, "annotation.cp_gcd.cycles", n=summary.cycle_count),
            ]
            if np.isfinite(summary.mean_specific_capacity_mAh_g):
                lines.append(
                    plot_text(
                        spec,
                        "annotation.cp_gcd.q_specific",
                        value=summary.mean_specific_capacity_mAh_g,
                    )
                )
            elif np.isfinite(summary.mean_discharge_capacity_C):
                lines.append(
                    plot_text(
                        spec,
                        "annotation.cp_gcd.q",
                        value=summary.mean_discharge_capacity_C,
                    )
                )
            if np.isfinite(summary.mean_coulombic_efficiency_pct):
                lines.append(
                    plot_text(
                        spec,
                        "annotation.cp_gcd.ce",
                        value=summary.mean_coulombic_efficiency_pct,
                    )
                )
            if np.isfinite(summary.mean_ir_drop_V):
                lines.append(
                    plot_text(spec, "annotation.cp_gcd.ir", value=summary.mean_ir_drop_V)
                )
            if complete_holds and series.completed:
                lines.append(plot_text(spec, "annotation.cp_gcd.holds_completed"))
            _annotate(
                ax,
                style,
                "\n".join(line for line in lines if line),
                x=0.98,
                y=0.96,
                ha="right",
                va="top",
                size=max(9.0, style.annotation_size * 0.85),
            )
    _labels(
        ax,
        style,
        axis_text(spec, "main", "x"),
        axis_text(spec, "main", "y"),
    )
    set_axis_display_units(ax, x=("s", 1.0), y=("V", 1.0))
    title = safe_format(spec.title, {}) or plot_text(spec, "title.cp_gcd")
    if title and style.show_title:
        ax.set_title(
            title,
            fontsize=style.title_size,
            fontfamily=style.text_font_family(),
            fontweight="bold" if style.title_bold else "normal",
        )
    if style.legend and spec.show_legend and handles:
        location = style.legend_location
        if location in {"", "best"}:
            location = "upper left"
        legend = ax.legend(
            loc=location,
            fontsize=style.legend_size,
            frameon=style.legend_frame,
            shadow=style.legend_shadow,
            ncol=style.legend_columns if len(handles) > 5 else 1,
        )
        style.style_legend(legend)
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


def _draw_concat_capacity_lines(
    ax,
    ax2,
    spec: PlotSpec,
    style: PlotStyle,
    entries: list[CPConcatEntry],
    values_by_run,
    *,
    series: str,
    percentage: str,
    unified_reference,
    quantity: str,
    unit: str,
    display_factor: float,
    units: dict,
    reference_unit: str,
    invalid_unit: bool,
    invalid_reference_unit: bool,
    colors,
    efficiency_colors,
    warnings: list[str],
    handles: list,
    labels: list[str],
) -> None:
    """Draw the merged, single-curve concatenated capacity/capacitance plot."""
    options = spec.analysis_options
    cumulative = options.get("cp_concat_cycle_mode", "sequential") == "cumulative"
    legend_unit = "%" if percentage != "absolute" else unit

    manual_reference = None
    manual_skip = False
    if percentage == "manual":
        if invalid_unit or invalid_reference_unit:
            manual_skip = True
        else:
            try:
                exponent = int(options.get("capacity_percent_reference_exponent", 0))
                if not -12 <= exponent <= 6:
                    raise ValueError("invalid reference scale")
                manual_reference = (
                    float(options.get("capacity_percent_reference")) * 10.0 ** exponent
                )
                if reference_unit:
                    manual_reference *= display_factor / units[reference_unit]
                if not np.isfinite(manual_reference) or manual_reference <= 0:
                    raise ValueError("invalid reference")
            except (TypeError, ValueError, OverflowError):
                manual_skip = True
                _append_warnings(warnings, ["手动 100% 参考容量无效，已跳过百分比绘制"])

    cycle_reference = None
    cycle_skip = False
    if percentage == "cycle":
        try:
            cycle_reference = int(options.get("capacity_percent_cycle", 1))
        except (TypeError, ValueError, OverflowError):
            cycle_skip = True
            _append_warnings(warnings, ["百分比参考循环无效，已跳过百分比绘制"])

    branch_x = {"charge": [], "discharge": [], "mean": []}
    branch_y = {"charge": [], "discharge": [], "mean": []}
    efficiency_x: list[float] = []
    efficiency_y: list[float] = []
    sequential_x = 1

    for entry in entries:
        values = [
            value
            for value in values_by_run.get(entry.run_id, ())
            if entry.start <= value.index <= entry.end
        ]
        if not values:
            continue
        charge_ref = discharge_ref = mean_ref = None
        if percentage == "manual":
            if manual_skip:
                continue
            charge_ref = discharge_ref = mean_ref = manual_reference
        elif percentage == "cycle":
            if cycle_skip:
                continue
            # Per-file cycle mode may use a reference cycle outside the
            # displayed range; only the plotted cycles are range-filtered.
            reference_value = next(
                (
                    value
                    for value in values_by_run.get(entry.run_id, ())
                    if value.index == cycle_reference
                ),
                None,
            )
            if reference_value is None:
                _append_warnings(
                    warnings,
                    [
                        f"{entry.run.display_name}: 百分比参考循环 "
                        f"{cycle_reference} 不存在，已跳过"
                    ],
                )
                continue
            charge_ref = reference_value.charge * display_factor
            discharge_ref = reference_value.discharge * display_factor
            mean_ref = reference_value.mean * display_factor
        elif percentage == "unified":
            if unified_reference is None:
                continue
            charge_ref = unified_reference.charge
            discharge_ref = unified_reference.discharge
            mean_ref = unified_reference.mean

        if percentage != "absolute":
            required = {
                "charge": (charge_ref,),
                "discharge": (discharge_ref,),
                "both": (charge_ref, discharge_ref),
                "mean": (mean_ref,),
            }[series]
            if any(not np.isfinite(value) or value <= 0 for value in required):
                _append_warnings(
                    warnings,
                    [f"{entry.run.display_name}: 百分比参考容量无效，已跳过"],
                )
                continue

        for value in values:
            x_value = entry.offset + value.index if cumulative else sequential_x
            if percentage == "absolute":
                charge = value.charge * display_factor
                discharge = value.discharge * display_factor
                mean = value.mean * display_factor
            elif percentage == "unified":
                charge = value.charge / charge_ref * 100
                discharge = value.discharge / discharge_ref * 100
                mean = value.mean / mean_ref * 100
            else:
                charge = value.charge * display_factor / charge_ref * 100
                discharge = value.discharge * display_factor / discharge_ref * 100
                mean = value.mean * display_factor / mean_ref * 100
            if series in {"both", "discharge"}:
                branch_x["discharge"].append(x_value)
                branch_y["discharge"].append(discharge)
            if series in {"both", "charge"}:
                branch_x["charge"].append(x_value)
                branch_y["charge"].append(charge)
            if series == "mean":
                branch_x["mean"].append(x_value)
                branch_y["mean"].append(mean)
            efficiency_x.append(x_value)
            efficiency_y.append(value.efficiency_pct)
            if not cumulative:
                sequential_x += 1

    if percentage == "manual" and not manual_skip:
        plotted = []
        if series in {"both", "discharge"}:
            plotted.extend(branch_y["discharge"])
        if series in {"both", "charge"}:
            plotted.extend(branch_y["charge"])
        if series == "mean":
            plotted.extend(branch_y["mean"])
        finite = [abs(value) for value in plotted if np.isfinite(value) and value != 0]
        if finite and (max(finite) < .01 or min(finite) > 100000):
            warnings.append("百分比远离 100%，请检查参考值单位和数量级")

    legend_run = entries[0].run if entries else None
    main_color = colors[0]

    def add_main_line(role: str, marker: str) -> None:
        if not branch_x[role]:
            return
        label = _concat_capacity_legend_text(
            spec,
            role,
            run=legend_run,
            quantity=quantity,
            unit=legend_unit,
        )
        if role == "charge":
            line = ax.plot(
                branch_x[role],
                branch_y[role],
                marker,
                color=main_color,
                linewidth=max(1.0, style.line_width * 0.8),
                markersize=style.marker_size * 0.85,
                markerfacecolor="white",
                markeredgecolor=main_color,
                alpha=0.8,
                label=label or "_nolegend_",
            )
        else:
            line = ax.plot(
                branch_x[role],
                branch_y[role],
                marker,
                color=main_color,
                linewidth=style.line_width,
                markersize=style.marker_size,
                markerfacecolor=main_color,
                label=label or "_nolegend_",
            )
        if label:
            handles.extend(line)
            labels.append(label)

    if series in {"both", "discharge"}:
        add_main_line("discharge", "o-")
    if series in {"both", "charge"}:
        add_main_line("charge", "o--")
    if series == "mean":
        add_main_line("mean", "o-")

    if ax2 is not None and efficiency_x and any(np.isfinite(value) for value in efficiency_y):
        efficiency_label = _concat_capacity_legend_text(
            spec,
            "efficiency",
            run=legend_run,
            quantity=quantity,
            unit="%",
        )
        efficiency_color = efficiency_colors[0] if efficiency_colors else "#d97706"
        if any(mcolors.same_color(efficiency_color, used) for used in colors):
            candidates = ("#d97706", "#16836b", "#9a36b5", "#d03455", "#2878b5")
            efficiency_color = next(
                (
                    candidate
                    for candidate in candidates
                    if not any(mcolors.same_color(candidate, used) for used in colors)
                ),
                "#111111",
            )
        line = ax2.plot(
            efficiency_x,
            efficiency_y,
            "s:",
            color=efficiency_color,
            linewidth=max(1.0, style.line_width * 0.7),
            markersize=style.marker_size * 0.8,
            alpha=0.75,
            label=efficiency_label or "_nolegend_",
        )
        if efficiency_label:
            handles.extend(line)
            labels.append(efficiency_label)


def draw_cp_capacity(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
) -> list[str]:
    runs = _selected_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 CP 数据")
        return ["没有选择 CP 数据"]
    warnings: list[str] = []
    options = spec.analysis_options
    include_holds = bool(options.get("include_holds", False))
    show_charge = bool(options.get("show_charge", True))
    series = options.get("capacity_series", "both" if show_charge else "discharge")
    if series not in {"both", "charge", "discharge", "mean"}:
        series = "both" if show_charge else "discharge"
    percentage = options.get("capacity_percent_mode", "absolute")
    if percentage not in {"absolute", "manual", "cycle", "unified"}:
        percentage = "absolute"
    quantity = options.get("cp_quantity", "capacity")
    show_efficiency = bool(options.get("show_efficiency", True))
    concat_enabled = bool(options.get("cp_concat_enabled", False))
    if concat_enabled:
        # Concatenation follows the saved order, then the plot's run order for
        # any newly selected files.  Dataset ordering alone is not enough.
        selected = {run.run_id: run for run in runs}
        ordered: list[CPRun] = []
        seen: set[str] = set()
        for run_id in spec.run_ids:
            run = selected.get(str(run_id))
            if run is not None and run.run_id not in seen:
                ordered.append(run)
                seen.add(run.run_id)
        runs = ordered or runs
    normalization = spec.normalization
    if normalization in {"mass", "area"}:
        available = all(
            (run.params.has_mass() if normalization == "mass" else run.params.has_area())
            for run in runs
        )
        if not available:
            warnings.append("部分数据缺少面积/质量参数，已回退为总容量")
            normalization = "none"

    summaries = [(run, _summary(run)) for run in runs]
    if not any(summary.cycles for _, summary in summaries):
        _message(figure, style, "没有完整的 GCD 循环")
        return warnings + ["没有完整的 GCD 循环"]
    summary_by_id = {run.run_id: summary for run, summary in summaries}

    entries: list[CPConcatEntry] = []
    if concat_enabled or percentage == "unified":
        entries = cp_concat_entries(
            runs,
            summary_by_id,
            order=options.get("cp_concat_order") if concat_enabled else None,
            ranges=options.get("cp_concat_ranges") if concat_enabled else None,
        )
    if concat_enabled:
        _warn_concat_ranges(
            [run for run, _ in summaries],
            [summary for _, summary in summaries],
            options,
            warnings,
        )
        for entry in entries:
            if entry.included_count <= 0:
                message = (
                    f"{entry.run.display_name}: 当前拼接范围内没有可显示的循环，已跳过"
                    if entry.summary.cycles
                    else f"{entry.run.display_name}: 没有可拼接的完整循环，已跳过"
                )
                _append_warnings(warnings, [message])

    values_by_run = {}
    if concat_enabled or percentage == "unified":
        values_by_run = {
            run.run_id: cp_cycle_values(
                run,
                summary,
                quantity=quantity,
                normalization=normalization,
                include_holds=include_holds,
            )
            for run, summary in summaries
        }

    unified_reference = None
    if percentage == "unified":
        unified_reference, error = resolve_cp_unified_reference(
            entries,
            values_by_run,
            options.get("capacity_percent_reference_run_id"),
            options.get("capacity_percent_reference_cycle"),
            require_displayed=True,
        )
        if unified_reference is None:
            _append_warnings(
                warnings,
                [f"{error or '统一 100% 参考无效'}；已回退为实际容量/电容值"],
            )
            percentage = "absolute"
        else:
            required = {
                "charge": (unified_reference.charge,),
                "discharge": (unified_reference.discharge,),
                "both": (unified_reference.charge, unified_reference.discharge),
                "mean": (unified_reference.mean,),
            }[series]
            if any(not np.isfinite(value) or value <= 0 for value in required):
                _append_warnings(
                    warnings,
                    [
                        f"统一 100% 参考 {unified_reference.run_id} "
                        f"Cycle {unified_reference.cycle_index} 的参考值缺失或非正；"
                        "已回退为实际容量/电容值"
                    ],
                )
                percentage = "absolute"
                unified_reference = None

    figure.clear()
    ax = figure.add_subplot(111)
    ax2 = ax.twinx() if show_efficiency else None
    colors = resolve_color_cycle(style, len(runs), color_config)
    efficiency_colors = resolve_color_cycle(style, max(2, len(runs) * 2), color_config)[len(runs):]
    file_numbers = dataset_file_numbers(dataset)
    resolved_labels = resolve_legend_labels(
        dataset_runs(dataset), spec=spec, file_numbers=file_numbers
    )
    handles = []
    labels = []
    units = dict(cp_plot_units(quantity, normalization))
    requested_unit = canonical_unit(options.get("cp_display_unit"))
    invalid_unit = bool(requested_unit and requested_unit != "auto" and requested_unit not in units)
    selected_unit = (cp_automatic_unit(summaries, quantity, normalization, include_holds)
                     if requested_unit == "auto" else requested_unit if requested_unit in units else next(iter(units)))
    unit = selected_unit
    display_factor = units[selected_unit]
    ax._cv_cp_physical_unit = (selected_unit, display_factor)
    if (percentage == "manual" and not invalid_unit
            and options.get("capacity_percent_reference") is not None
            and not options.get("capacity_percent_reference_unit")):
        # Older projects saved only a number. Preserve its original displayed
        # unit before any later automatic-prefix or normalization change.
        options["capacity_percent_reference_unit"] = selected_unit
    if invalid_unit:
        message = (
            f"显示单位 {requested_unit} 与当前量或归一化方式不兼容，"
            f"已回退到 {unit}"
        )
        if percentage == "manual":
            message += "；请重新确认手动参考值"
        warnings.append(message)
    reference_unit = canonical_unit(options.get("capacity_percent_reference_unit"))
    invalid_reference_unit = bool(reference_unit and reference_unit not in units)
    if percentage == "manual" and invalid_reference_unit:
        warnings.append(f"手动参考值单位 {reference_unit} 与当前量或归一化方式不兼容，请重新填写参考值。")

    if concat_enabled:
        _draw_concat_capacity_lines(
            ax,
            ax2,
            spec,
            style,
            entries,
            values_by_run,
            series=series,
            percentage=percentage,
            unified_reference=unified_reference,
            quantity=quantity,
            unit=unit,
            display_factor=display_factor,
            units=units,
            reference_unit=reference_unit,
            invalid_unit=invalid_unit,
            invalid_reference_unit=invalid_reference_unit,
            colors=colors,
            efficiency_colors=efficiency_colors,
            warnings=warnings,
            handles=handles,
            labels=labels,
        )
    for index, (run, summary) in enumerate(() if concat_enabled else summaries):
        if not summary.cycles:
            continue
        color = colors[index % len(colors)]
        cycles = summary.cycles
        discharge: list[float] = []
        charge: list[float] = []
        if normalization == "mass":
            unit = "mAh/g"
            for cycle in cycles:
                discharge.append(
                    cycle.specific_capacity_with_holds_mAh_g
                    if include_holds
                    else cycle.specific_capacity_mAh_g
                )
                charge.append(
                    (
                        cycle.charge_capacity_with_holds_C
                        if include_holds
                        else cycle.charge_capacity_C
                    )
                    / (run.params.mass_mg * 1e-3)
                    / 3.6
                    if run.params.mass_mg
                    else float("nan")
                )
        elif normalization == "area":
            unit = "mAh/cm²"
            for cycle in cycles:
                discharge.append(
                    cycle.areal_capacity_with_holds_mAh_cm2
                    if include_holds
                    else cycle.areal_capacity_mAh_cm2
                )
                charge.append(
                    (
                        cycle.charge_capacity_with_holds_C
                        if include_holds
                        else cycle.charge_capacity_C
                    )
                    / run.params.area_cm2
                    / 3.6
                    if run.params.area_cm2
                    else float("nan")
                )
        else:
            unit = "mAh"
            for cycle in cycles:
                discharge.append(
                    (
                        cycle.discharge_capacity_with_holds_C
                        if include_holds
                        else cycle.discharge_capacity_C
                    )
                    / 3.6
                )
                charge.append(
                    (
                        cycle.charge_capacity_with_holds_C
                        if include_holds
                        else cycle.charge_capacity_C
                    )
                    / 3.6
                )
        if quantity == "capacitance":
            def capacitance(capacity, segment):
                potential = np.asarray(segment.potential_V, dtype=float)
                if potential.size < 2:
                    return float("nan")
                delta = abs(float(potential[-1] - potential[0]))
                return capacity * 3.6 / delta if np.isfinite(delta) and delta > 0 else float("nan")
            charge = [capacitance(value, cycle.charge) for value, cycle in zip(charge, cycles)]
            discharge = [capacitance(value, cycle.discharge) for value, cycle in zip(discharge, cycles)]
            unit = {"mass": "F/g", "area": "F/cm²"}.get(normalization, "F")
        unit = selected_unit
        charge = [value * display_factor for value in charge]
        discharge = [value * display_factor for value in discharge]
        x = [cycle.index for cycle in cycles]
        mean_values = [(a + b) / 2 if np.isfinite(a) and np.isfinite(b) else float("nan")
                       for a, b in zip(charge, discharge)]
        if percentage != "absolute":
            if percentage == "manual" and (invalid_unit or invalid_reference_unit):
                continue
            try:
                if percentage == "manual":
                    exponent = int(spec.analysis_options.get("capacity_percent_reference_exponent", 0))
                    if not -12 <= exponent <= 6:
                        raise ValueError("invalid reference scale")
                    reference = float(spec.analysis_options.get("capacity_percent_reference")) * 10.0 ** exponent
                    if reference_unit:
                        reference *= display_factor / units[reference_unit]
                    charge_ref = discharge_ref = mean_ref = reference
                elif percentage == "unified":
                    if unified_reference is None:
                        raise ValueError("missing unified reference")
                    charge_ref = unified_reference.charge * display_factor
                    discharge_ref = unified_reference.discharge * display_factor
                    mean_ref = unified_reference.mean * display_factor
                else:
                    reference_cycle = int(spec.analysis_options.get("capacity_percent_cycle", 1))
                    ref_index = x.index(reference_cycle)
                    charge_ref, discharge_ref, mean_ref = charge[ref_index], discharge[ref_index], mean_values[ref_index]
                required = {"charge": (charge_ref,), "discharge": (discharge_ref,),
                            "both": (charge_ref, discharge_ref), "mean": (mean_ref,)}[series]
                if any(not np.isfinite(reference) or reference <= 0 for reference in required):
                    raise ValueError("invalid reference")
            except (TypeError, ValueError, OverflowError, IndexError):
                warnings.append(f"{run.display_name}: 百分比参考容量无效或参考循环不存在，已跳过")
                continue
            if series in {"both", "discharge"}:
                discharge = [value / discharge_ref * 100 for value in discharge]
            if series in {"both", "charge"}:
                charge = [value / charge_ref * 100 for value in charge]
            if series == "mean":
                mean_values = [value / mean_ref * 100 for value in mean_values]
            if percentage == "manual":
                plotted = {"both": charge + discharge, "charge": charge,
                           "discharge": discharge, "mean": mean_values}[series]
                finite = [abs(v) for v in plotted if np.isfinite(v) and v != 0]
                if finite and (max(finite) < .01 or min(finite) > 100000):
                    warnings.append(f"{run.display_name}: 百分比远离 100%，请检查参考值单位和数量级")
            unit = "%"
        resolved = resolved_labels.get(run.run_id)
        fallback = resolved.label if resolved is not None else run.legend_name
        label, unknown = preview_label(run, effective_template(run, spec),
                                       file_number=file_numbers.get(run.run_id), fallback=fallback)
        for token in unknown:
            warnings.append(f"图例模板包含未知字段: {{{token}}}")
        legend_context = {"run": run, "label": label, "fallback": fallback,
                          "quantity": quantity, "unit": unit, "multiple": len(runs) > 1}
        discharge_label = _capacity_legend_text(spec, "discharge", **legend_context)
        charge_label = _capacity_legend_text(spec, "charge", **legend_context)
        if series in {"both", "discharge"}:
            line = ax.plot(
                x,
                discharge,
                "o-",
                color=color,
                linewidth=style.line_width,
                markersize=style.marker_size,
                markerfacecolor=color,
                label=discharge_label or "_nolegend_",
            )
            if discharge_label:
                handles.extend(line)
                labels.append(discharge_label)
        if series in {"both", "charge"}:
            line = ax.plot(
                x,
                charge,
                "o--",
                color=color,
                linewidth=max(1.0, style.line_width * 0.8),
                markersize=style.marker_size * 0.85,
                markerfacecolor="white",
                markeredgecolor=color,
                alpha=0.8,
                label=charge_label or "_nolegend_",
            )
            if charge_label:
                handles.extend(line)
                labels.append(charge_label)
        if series == "mean":
            mean_label = _capacity_legend_text(spec, "mean", **legend_context)
            line = ax.plot(x, mean_values, "o-", color=color, linewidth=style.line_width,
                           markersize=style.marker_size, label=mean_label or "_nolegend_")
            if mean_label:
                handles.extend(line)
                labels.append(mean_label)
        if ax2 is not None:
            efficiencies = [
                cycle.coulombic_efficiency_with_holds_pct
                if include_holds
                else cycle.coulombic_efficiency_pct
                for cycle in cycles
            ]
            if any(np.isfinite(value) for value in efficiencies):
                efficiency_label = _capacity_legend_text(spec, "efficiency", **{**legend_context, "unit": "%"})
                efficiency_color = efficiency_colors[index % len(efficiency_colors)]
                if any(mcolors.same_color(efficiency_color, used) for used in colors):
                    candidates = ("#d97706", "#16836b", "#9a36b5", "#d03455", "#2878b5")
                    efficiency_color = next((candidate for candidate in candidates
                                             if not any(mcolors.same_color(candidate, used) for used in colors)), "#111111")
                line = ax2.plot(
                    x,
                    efficiencies,
                    "s:",
                    color=efficiency_color,
                    linewidth=max(1.0, style.line_width * 0.7),
                    markersize=style.marker_size * 0.8,
                    alpha=0.75,
                    label=efficiency_label or "_nolegend_",
                )
                if efficiency_label:
                    handles.extend(line)
                    labels.append(efficiency_label)

    if percentage != "absolute":
        unit = "%"
        # Show a magnitude on each tick instead of a detached 1e−N offset;
        # otherwise tiny percentages can appear to be values around 0–1%.
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.4g}"))
        set_axis_display_units(ax, x=("Cycle", 1.0), y=("%", 1.0),
                               dimensions={"y": f"cp_{quantity}_{normalization}_percentage"})
    else:
        set_axis_display_units(ax, x=("Cycle", 1.0), y=(unit, display_factor))
    if ax2 is not None:
        set_axis_display_units(ax2, y=("%", 1.0))
    _labels(
        ax,
        style,
        axis_text(spec, "capacity", "x"),
        axis_text(spec, "capacity", "y", unit=unit),
    )
    if quantity == "capacitance" and axis_label_override(spec, "capacity", "y") is None:
        ax.set_ylabel(f"Capacitance ({unit})", **font_kwargs(style, axis="y"))
    if ax2 is not None:
        ax2.set_ylabel(
            axis_text(spec, "efficiency", "y"),
            **font_kwargs(style, axis="y"),
        )
        ax2.set_ylim(0, 110)
        ax2.tick_params(axis="y", labelsize=style.tick_size, colors="#546e7a")
        ax2.yaxis.label.set_color("#546e7a")
    ax.xaxis.set_major_locator(MaxNLocator(nbins="auto", integer=True))
    title = safe_format(spec.title, {}) or plot_text(spec, "title.cp_capacity")
    if title and style.show_title:
        ax.set_title(
            title,
            fontsize=style.title_size,
            fontfamily=style.text_font_family(),
            fontweight="bold" if style.title_bold else "normal",
        )
    if spec.show_legend and handles:
        legend = ax.legend(
            handles,
            labels,
            loc=style.legend_location,
            fontsize=style.legend_size,
            frameon=style.legend_frame,
            shadow=style.legend_shadow,
            ncol=style.legend_columns if len(handles) > 5 else 1,
        )
        remember_legend_sources(legend, handles, labels)
        style.style_legend(legend)
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
    if spec.kind == "cp_gcd":
        return draw_gcd_curve(figure, dataset, spec, style, color_config=color_config)
    if spec.kind == "cp_capacity":
        return draw_cp_capacity(figure, dataset, spec, style, color_config=color_config)
    _message(figure, style, f"未知 CP 绘图类型: {spec.kind}")
    return [f"未知 CP 绘图类型: {spec.kind}"]


__all__ = ["draw", "draw_cp_capacity", "draw_gcd_curve"]
