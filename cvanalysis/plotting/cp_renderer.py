# -*- coding: utf-8 -*-
"""Chronopotentiometry / GCD plot renderers (no Qt imports)."""

from __future__ import annotations

from typing import Iterable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from cvanalysis.analysis.cp import CPRunSummary, analyze_cp_run, completed_cp_series
from cvanalysis.domain.models import CPRun, Dataset
from cvanalysis.domain.units import CURRENT, resolve_unit
from cvanalysis.plotting.colors import resolve_color_cycle
from cvanalysis.plotting.legend import (
    dataset_file_numbers,
    dataset_runs,
    effective_template,
    preview_label,
    resolve_legend_labels,
)
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure, font_kwargs
from cvanalysis.plotting.texts import axis_text, plot_text


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

    finish_paper(figure, spec, style)


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


def _current_text(current: float | None, override: str | None = None) -> str:
    if current is None or not np.isfinite(current):
        return "—"
    unit, factor = resolve_unit(CURRENT, [current], override)
    return f"{current * factor:.3g} {unit}"


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
    title = spec.title or plot_text(spec, "title.cp_gcd")
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
    include_holds = bool(spec.analysis_options.get("include_holds", False))
    show_charge = bool(spec.analysis_options.get("show_charge", True))
    show_efficiency = bool(spec.analysis_options.get("show_efficiency", True))
    normalization = spec.normalization
    if normalization in {"mass", "area"}:
        available = all(
            (run.params.mass_mg if normalization == "mass" else run.params.area_cm2)
            for run in runs
        )
        if not available:
            warnings.append("部分数据缺少面积/质量参数，已回退为总容量")
            normalization = "none"

    summaries = [(run, _summary(run)) for run in runs]
    if not any(summary.cycles for _, summary in summaries):
        _message(figure, style, "没有完整的 GCD 循环")
        return warnings + ["没有完整的 GCD 循环"]

    figure.clear()
    ax = figure.add_subplot(111)
    ax2 = ax.twinx() if show_efficiency else None
    colors = resolve_color_cycle(style, len(runs), color_config)
    file_numbers = dataset_file_numbers(dataset)
    resolved_labels = resolve_legend_labels(
        dataset_runs(dataset), spec=spec, file_numbers=file_numbers
    )
    handles = []
    labels = []
    unit = "mAh"

    for index, (run, summary) in enumerate(summaries):
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
        x = [cycle.index for cycle in cycles]
        resolved = resolved_labels.get(run.run_id)
        label = resolved.label if resolved is not None else run.legend_name
        discharge_label = plot_text(spec, "legend.cp_discharge", label=label)
        charge_label = plot_text(spec, "legend.cp_charge", label=label)
        line = ax.plot(
            x,
            discharge,
            "o-",
            color=color,
            linewidth=style.line_width,
            markersize=style.marker_size,
            markerfacecolor=color,
            label=discharge_label,
        )
        handles.extend(line)
        labels.append(discharge_label)
        if show_charge:
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
                label=charge_label,
            )
            handles.extend(line)
            labels.append(charge_label)
        if ax2 is not None:
            efficiencies = [
                cycle.coulombic_efficiency_with_holds_pct
                if include_holds
                else cycle.coulombic_efficiency_pct
                for cycle in cycles
            ]
            if any(np.isfinite(value) for value in efficiencies):
                efficiency_label = plot_text(spec, "legend.cp_efficiency", label=label)
                line = ax2.plot(
                    x,
                    efficiencies,
                    "s:",
                    color=color,
                    linewidth=max(1.0, style.line_width * 0.7),
                    markersize=style.marker_size * 0.8,
                    alpha=0.75,
                    label=efficiency_label,
                )
                handles.extend(line)
                labels.append(efficiency_label)

    _labels(
        ax,
        style,
        axis_text(spec, "capacity", "x"),
        axis_text(spec, "capacity", "y", unit=unit),
    )
    if ax2 is not None:
        ax2.set_ylabel(
            axis_text(spec, "efficiency", "y"),
            **font_kwargs(style, axis="y"),
        )
        ax2.set_ylim(0, 110)
        ax2.tick_params(axis="y", labelsize=style.tick_size, colors="#546e7a")
        ax2.yaxis.label.set_color("#546e7a")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    title = spec.title or plot_text(spec, "title.cp_capacity")
    if title and style.show_title:
        ax.set_title(
            title,
            fontsize=style.title_size,
            fontfamily=style.text_font_family(),
            fontweight="bold" if style.title_bold else "normal",
        )
    if style.legend and spec.show_legend and handles:
        legend = ax.legend(
            handles,
            labels,
            loc=style.legend_location,
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
