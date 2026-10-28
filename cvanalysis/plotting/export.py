# -*- coding: utf-8 -*-
"""Unified plot rendering, export and clipboard helpers."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import matplotlib as mpl
from matplotlib.figure import Figure

from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting import cp_renderer, cv_renderer, eis_renderer
from cvanalysis.plotting.axis_limits import apply_axis_limits
from cvanalysis.plotting.colors import apply_color_overrides
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure
from cvanalysis.plotting.paper import finish_paper, paper_overrides
from cvanalysis.plotting.ticks import apply_log_tick_formats, apply_unified_ticks


def _finish_layout(figure: Figure, spec: PlotSpec, style: PlotStyle) -> None:
    """Run the one and only final layout pass after limits and tick changes."""
    if not figure.axes:
        return
    if all(not getattr(ax, "axison", True) for ax in figure.axes):
        return
    finalize_figure(figure, style)
    if spec.paper_layout.get("enabled"):
        finish_paper(figure, spec, style)


def render_plot(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> list[str]:
    """Draw a plot into an existing figure and return warnings."""
    color_overrides = spec.analysis_options.get("color_overrides")
    if not spec.kind.startswith(("cv_", "eis_", "cp_")):
        figure.clear()
        ax = figure.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            f"未知绘图类型: {spec.kind}",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
        ax.set_axis_off()
        apply_color_overrides(figure, color_overrides)
        return [f"未知绘图类型: {spec.kind}"]

    figure._defer_final_layout = True
    try:
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
            else:
                warnings = cp_renderer.draw(
                    figure,
                    dataset,
                    spec,
                    style,
                    color_config=color_config,
                    fits=fits,
                    metrics=metrics,
                )
    finally:
        figure._defer_final_layout = False

    apply_color_overrides(figure, color_overrides)
    warnings.extend(apply_axis_limits(figure, spec.kind, spec.analysis_options))
    warnings.extend(apply_unified_ticks(figure, spec.kind, spec.analysis_options))
    apply_log_tick_formats(figure, spec.analysis_options)
    _finish_layout(figure, spec, style)
    return warnings


def render_to_new_figure(
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> Figure:
    """Render a fresh figure with the preset's print size (for export)."""
    style = style.with_overrides(paper_overrides(spec.paper_layout, style))
    figure = Figure(figsize=style.figure_size, dpi=style.save_dpi)
    figure._paper_layout_enabled = bool(spec.paper_layout.get("enabled"))
    render_plot(
        figure,
        dataset,
        spec,
        style,
        color_config=color_config,
        fits=fits,
        metrics=metrics,
    )
    return figure


def render_svg_bytes(
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> bytes:
    """Render a plot as SVG bytes for vector clipboard/export workflows."""
    figure = render_to_new_figure(
        dataset,
        spec,
        style,
        color_config=color_config,
        fits=fits,
        metrics=metrics,
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
