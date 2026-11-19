# -*- coding: utf-8 -*-
"""Unified plot rendering, export and clipboard helpers."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

import matplotlib as mpl
from matplotlib.figure import Figure

from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting import cp_renderer, cv_renderer, eis_renderer, sweep_renderer
from cvanalysis.plotting.axis_limits import apply_axis_limits
from cvanalysis.plotting.colors import apply_color_overrides, apply_rebuilt_legend_text_overrides
from cvanalysis.plotting.legend import dataset_runs, effective_template, is_blank_legend_template
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure
from cvanalysis.plotting.paper import finish_paper, fit_standard_legends, paper_overrides
from cvanalysis.plotting.texts import plot_text_context
from cvanalysis.plotting.ticks import apply_log_tick_formats, apply_unified_ticks
from cvanalysis.plotting.template_format import collect_template_warnings


def _finish_layout(figure: Figure, spec: PlotSpec, style: PlotStyle) -> None:
    """Run the one and only final layout pass after limits and tick changes."""
    if not figure.axes:
        return
    if all(not getattr(ax, "axison", True) for ax in figure.axes):
        return
    finalize_figure(figure, style)
    if spec.paper_layout.get("enabled"):
        finish_paper(figure, spec, style)
    else:
        fit_standard_legends(figure, spec, style)


def render_plot(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
    text_values: dict | None = None,
) -> list[str]:
    """Draw a plot into an existing figure and return warnings."""
    color_overrides = spec.analysis_options.get("color_overrides")
    role_color_overrides = spec.analysis_options.get("color_overrides_by_role")
    if not spec.kind.startswith(("cv_", "eis_", "cp_", "lsv_", "it_")):
        figure.clear()
        figure.add_subplot(111).set_axis_off()
        apply_color_overrides(figure, color_overrides, role_color_overrides)
        return [f"未知绘图类型: {spec.kind}"]

    figure._defer_final_layout = True
    try:
        with collect_template_warnings() as text_warnings, plot_text_context(spec, text_values):
            with mpl.rc_context(style.rc()):
                if spec.kind.startswith("cv_"):
                    warnings = cv_renderer.draw(
                        figure,
                        dataset,
                        spec,
                        style,
                        color_config=color_config,
                        fits=fits,
                        metrics=metrics,
                    )
                elif spec.kind.startswith("eis_"):
                    warnings = eis_renderer.draw(
                        figure,
                        dataset,
                        spec,
                        style,
                        color_config=color_config,
                        fits=fits,
                        metrics=metrics,
                    )
                elif spec.kind.startswith("cp_"):
                    warnings = cp_renderer.draw(
                        figure,
                        dataset,
                        spec,
                        style,
                        color_config=color_config,
                        fits=fits,
                        metrics=metrics,
                    )
                else:
                    warnings = sweep_renderer.draw(figure, dataset, spec, style, color_config=color_config)
        warnings.extend(text_warnings)
    finally:
        figure._defer_final_layout = False

    apply_color_overrides(figure, color_overrides, role_color_overrides)
    warnings.extend(apply_axis_limits(figure, spec.kind, spec.analysis_options))
    warnings.extend(apply_unified_ticks(figure, spec.kind, spec.analysis_options))
    apply_log_tick_formats(figure, spec.analysis_options)
    selected_ids = set(spec.run_ids)
    selected_runs = [run for run in dataset_runs(dataset) if run.run_id in selected_ids]
    for run in selected_runs:
        diagnostics = dict.fromkeys([*run.warnings, *getattr(getattr(run, "summary", None), "warnings", ())])
        warnings.extend(f"{run.display_name}：{message}" for message in diagnostics if message not in warnings)
    blank_legend = spec.kind != "cp_capacity" and bool(selected_runs) and all(
        is_blank_legend_template(effective_template(run, spec)) for run in selected_runs
    )
    if blank_legend and spec.kind == "it_curve":
        blank_legend = not any(
            line.get_gid() == "it_manual_y_reference" and getattr(line, "_it_reference_legend_text", None)
            for ax in figure.axes for line in ax.lines
        )
    if blank_legend:
        for legend in list(figure.legends):
            legend.remove()
        for ax in figure.axes:
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()
    layout_style = style
    if spec.kind == "cp_capacity" and spec.show_legend and not style.legend:
        layout_style = style.with_overrides({"legend": True})
    _finish_layout(figure, replace(spec, show_legend=False) if blank_legend else spec, layout_style)
    apply_rebuilt_legend_text_overrides(figure, color_overrides, role_color_overrides)
    return list(dict.fromkeys(warnings))


def render_to_new_figure(
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
    text_values: dict | None = None,
    diagnostics: list[str] | None = None,
) -> Figure:
    """Render a fresh figure with the preset's print size (for export)."""
    style = style.with_overrides(paper_overrides(spec.paper_layout, style))
    figure = Figure(figsize=style.figure_size, dpi=style.save_dpi)
    figure._paper_layout_enabled = bool(spec.paper_layout.get("enabled"))
    messages = render_plot(
        figure,
        dataset,
        spec,
        style,
        color_config=color_config,
        fits=fits,
        metrics=metrics,
        text_values=text_values,
    )
    if diagnostics is not None:
        diagnostics.extend(messages)
    return figure


def render_svg_bytes(
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
    text_values: dict | None = None,
    diagnostics: list[str] | None = None,
) -> bytes:
    """Render a plot as SVG bytes for vector clipboard/export workflows."""
    figure = render_to_new_figure(
        dataset,
        spec,
        style,
        color_config=color_config,
        fits=fits,
        metrics=metrics,
        text_values=text_values,
        diagnostics=diagnostics,
    )
    buffer = BytesIO()
    figure.savefig(buffer, format="svg", facecolor=figure.get_facecolor())
    return buffer.getvalue()


def export_figure(
    figure: Figure,
    path: str | Path,
    style: PlotStyle,
    *,
    format: str | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fmt = (format or output.suffix.lstrip(".") or "png").lower()
    save_kwargs = {
        "dpi": style.save_dpi,
        "facecolor": figure.get_facecolor(),
        "format": fmt,
    }
    if style.save_bbox_inches and not getattr(figure, "_paper_layout_enabled", False):
        save_kwargs["bbox_inches"] = "tight"
    figure.savefig(output, **save_kwargs)
    return output
