# -*- coding: utf-8 -*-
"""EIS plot renderers."""

from __future__ import annotations

from typing import Iterable

import matplotlib.lines as mlines
import numpy as np
from matplotlib.figure import Figure

from cvanalysis.analysis.eis import EISMetrics, analyze_eis, filter_eis_run
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import Dataset, EISRun
from cvanalysis.domain.units import (
    CAPACITANCE,
    IMPEDANCE,
    IMPEDANCE_AREA,
    format_with_unit,
    normalize_impedance,
    resolve_unit,
    unit_factor,
)
from cvanalysis.plotting.axis_limits import set_axis_display_units
from cvanalysis.plotting.colors import resolve_color_cycle
from cvanalysis.plotting.legend import dataset_file_numbers, effective_template, preview_label
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle, finalize_figure, font_kwargs


_CJK_FONT_CACHE: list[str] | None = None
_EQUAL_ASPECT_MAX_SPAN_RATIO = 4.0


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
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha="center", va="center",
            fontsize=max(10, style.font_size), color="#888888", fontfamily=_cjk_fonts())
    ax.set_axis_off()
    style.apply(figure)


def _selected_runs(dataset: Dataset, spec: PlotSpec) -> list[EISRun]:
    if not spec.run_ids:
        return []
    selected = set(spec.run_ids)
    return [run for run in dataset.eis_runs if run.run_id in selected]


def _filtered_runs(runs: Iterable[EISRun], spec: PlotSpec) -> list[EISRun]:
    low = spec.frequency_low
    high = spec.frequency_high
    if low is None and high is None:
        return list(runs)
    return [filter_eis_run(run, low, high) for run in runs]


def _equal_aspect_reasonable(x_values: list[np.ndarray], y_values: list[np.ndarray]) -> bool:
    """Keep equal aspect only when it will not leave mostly empty axes.

    A high-frequency-only Nyquist slice can span several hundred ohms in
    -Z'' but only a few ohms in Z'. Forcing equal units then expands Z' to
    the much larger span and fills the plot with blank space (often into
    negative values). In that case independent automatic ranges are more
    readable; normal semicircles still use equal aspect.
    """
    if not x_values or not y_values:
        return True
    x = np.concatenate([np.asarray(values, dtype=float).ravel() for values in x_values])
    y = np.concatenate([np.asarray(values, dtype=float).ravel() for values in y_values])
    x = x[np.isfinite(x)]
    y = y[np.isfinite(y)]
    if x.size == 0 or y.size == 0:
        return True
    x_span = float(np.ptp(x))
    y_span = float(np.ptp(y))
    if x_span <= 0 or y_span <= 0:
        return True
    return max(x_span, y_span) / min(x_span, y_span) <= _EQUAL_ASPECT_MAX_SPAN_RATIO


def _resolve_normalization(
    runs: Iterable[EISRun],
    normalization: str,
    warnings: list[str],
) -> str:
    runs = list(runs)
    if normalization == "mass":
        warnings.append("EIS 阻抗不支持质量归一化，已使用原始阻抗")
        return "none"
    if normalization == "area" and not all(run.params.has_area() for run in runs):
        warnings.append("部分数据缺少电极面积，已回退为原始阻抗")
        return "none"
    return normalization


def _legend_label(run: EISRun, spec: PlotSpec, warnings: list[str], *, file_number=None) -> str:
    template = effective_template(run, spec)
    if not template:
        return run.legend_name
    label, unknown = preview_label(run, template, file_number=file_number, fallback=run.legend_name)
    for token in unknown:
        message = f"图例模板包含未知字段: {{{token}}}"
        if message not in warnings:
            warnings.append(message)
    return label


def _z_values(run: EISRun, normalization: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    real = normalize_impedance(run.z_real, normalization, area_cm2=run.params.area_cm2)
    imag = normalize_impedance(run.z_imag, normalization, area_cm2=run.params.area_cm2)
    mag = normalize_impedance(run.z_mag, normalization, area_cm2=run.params.area_cm2)
    return real, imag, mag


def _unit_override(spec: PlotSpec, key: str) -> str | None:
    overrides = spec.analysis_options.get("unit_overrides")
    if not isinstance(overrides, dict):
        return None
    value = overrides.get(key)
    if not value or str(value) == "auto":
        return None
    return str(value)


def _unit_for_impedance(
    runs: Iterable[EISRun],
    normalization: str,
    *,
    override: str | None = None,
    warnings: list[str] | None = None,
) -> tuple[str, float]:
    values: list[float] = []
    for run in runs:
        real, imag, mag = _z_values(run, normalization)
        values.extend(np.abs(real).tolist())
        values.extend(np.abs(imag).tolist())
        values.extend(np.abs(mag).tolist())
    family = IMPEDANCE_AREA if normalization == "area" else IMPEDANCE
    unit, factor = resolve_unit(family, values, override)
    if (
        warnings is not None
        and override
        and override != "auto"
        and unit_factor(family, override) is None
    ):
        warnings.append(
            f"阻抗单位 {override} 不适用于当前归一化方式，已自动选择 {unit}"
        )
    return unit, factor


def _format_metric_with_unit(
    value: float | None,
    family,
    override: str | None,
    *,
    digits: int = 3,
) -> str:
    factor = unit_factor(family, override)
    if value is None or not np.isfinite(value):
        return "—"
    if factor is None:
        return format_with_unit(value, family, digits=digits)
    return f"{value * factor:.{digits}g} {override}"


def _impedance_metric(
    value: float | None,
    run: EISRun,
    normalization: str,
) -> tuple[float | None, object]:
    if value is None or not np.isfinite(value):
        return value, IMPEDANCE
    if normalization == "area" and run.params.has_area():
        return float(value) * float(run.params.area_cm2), IMPEDANCE_AREA
    return float(value), IMPEDANCE


def _format_metrics(
    run: EISRun,
    metrics: EISMetrics | None,
    fit: EISFitResult | None,
    *,
    impedance_override: str | None = None,
    normalization: str = "none",
) -> str:
    if fit is not None:
        parameters = fit.parameters
        rs = parameters.get("Rs_ohm")
        if metrics is not None and metrics.rs_ohm is not None and (
            rs is None or rs < max(1e-9, 1e-4 * metrics.rs_ohm)
        ):
            rs = metrics.rs_ohm
        rct = parameters.get("Rct_ohm")
        if rct is None and metrics is not None:
            rct = metrics.rct_ohm
        c_eff = parameters.get("C_eff_F")
        if c_eff is None and metrics is not None:
            c_eff = metrics.cdl_F
        rs, rs_family = _impedance_metric(rs, run, normalization)
        rct, rct_family = _impedance_metric(rct, run, normalization)
        lines = [
            fit.model_label,
            f"Rs = {_format_metric_with_unit(rs, rs_family, impedance_override)}",
            f"Rct = {_format_metric_with_unit(rct, rct_family, impedance_override)}",
        ]
        if c_eff:
            lines.append(f"Ceff = {format_with_unit(c_eff, CAPACITANCE, digits=3)}")
        lines.append(f"R² = {fit.r2:.4f}")
        return "\n".join(lines)
    if metrics is not None:
        rs, rs_family = _impedance_metric(metrics.rs_ohm, run, normalization)
        lines = [
            f"Rs = {_format_metric_with_unit(rs, rs_family, impedance_override)}"
        ]
        if metrics.rct_ohm:
            rct, rct_family = _impedance_metric(metrics.rct_ohm, run, normalization)
            lines.append(
                f"Rct ≈ {_format_metric_with_unit(rct, rct_family, impedance_override)}"
            )
        if metrics.cdl_F:
            lines.append(f"Cdl ≈ {format_with_unit(metrics.cdl_F, CAPACITANCE, digits=3)}")
        if metrics.f_peak_hz:
            lines.append(f"f0 ≈ {metrics.f_peak_hz:.3g} Hz")
        return "\n".join(lines)
    return ""


def _annotate(ax, style: PlotStyle, text: str) -> None:
    if not text:
        return
    ax.text(0.02, 0.04, text, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=style.annotation_size, fontfamily=style.font_family,
            fontweight="bold" if style.annotation_bold else "normal",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff8e6", edgecolor="#d9c89e", alpha=0.9))


def _labels(ax, style: PlotStyle, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(xlabel, **font_kwargs(style, axis="x"))
    ax.set_ylabel(ylabel, **font_kwargs(style, axis="y"))


def _finish(figure: Figure, style: PlotStyle, spec: PlotSpec) -> None:
    if not spec.show_axes:
        for ax in figure.axes:
            ax.tick_params(labelbottom=False, labelleft=False, labelright=False, labeltop=False)
            if ax.xaxis.label:
                ax.xaxis.label.set_visible(False)
            if ax.yaxis.label:
                ax.yaxis.label.set_visible(False)
    for ax in figure.axes:
        legend = ax.get_legend()
        if legend and len(legend.get_texts()) > 8:
            handles, labels = ax.get_legend_handles_labels()
            legend.remove()
            legend = ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.02, 1),
                               fontsize=style.legend_size, frameon=style.legend_frame)
            style.style_legend(legend)
    if getattr(figure, "_defer_final_layout", False):
        return
    finalize_figure(figure, style)
    from cvanalysis.plotting.paper import finish_paper
    finish_paper(figure, spec, style)


def draw_nyquist(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> list[str]:
    runs = _selected_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 EIS 数据")
        return ["没有选择 EIS 数据"]
    warnings: list[str] = []
    normalization = _resolve_normalization(runs, spec.normalization, warnings)
    runs = _filtered_runs(runs, spec)
    runs = [run for run in runs if len(run.freq) >= 1]
    if not runs:
        _message(figure, style, "所选频率范围内无数据")
        return warnings + ["所选频率范围内无数据"]

    impedance_override = _unit_override(spec, "impedance")
    unit, factor = _unit_for_impedance(
        runs, normalization, override=impedance_override, warnings=warnings
    )
    colors = resolve_color_cycle(style, len(runs) + len(fits or {}), color_config)
    figure.clear()
    ax = figure.add_subplot(111)
    fits = fits or {}
    metrics = metrics or {}

    file_numbers = dataset_file_numbers(dataset)
    x_series: list[np.ndarray] = []
    y_series: list[np.ndarray] = []
    for index, run in enumerate(runs):
        real, imag, _ = _z_values(run, normalization)
        color = colors[index % len(colors)]
        label = _legend_label(run, spec, warnings, file_number=file_numbers.get(run.run_id))
        x_display = real * factor
        y_display = -imag * factor
        x_series.append(x_display)
        y_series.append(y_display)
        ax.plot(x_display, y_display, "o-", color=color,
                markerfacecolor=color, markersize=style.marker_size,
                linewidth=style.line_width, label=label)
        fit = fits.get(run.run_id)
        if spec.fit_enabled and fit is not None:
            fit_real = normalize_impedance(fit.z_fit.real, normalization, area_cm2=run.params.area_cm2)
            fit_imag = normalize_impedance(fit.z_fit.imag, normalization, area_cm2=run.params.area_cm2)
            x_fit = fit_real * factor
            y_fit = -fit_imag * factor
            x_series.append(x_fit)
            y_series.append(y_fit)
            ax.plot(x_fit, y_fit, "--", color=color,
                    linewidth=max(1.0, style.line_width), alpha=0.9,
                    label=f"{label} fit")
        if style.annotation and spec.annotations and len(runs) == 1:
            text = _format_metrics(
                run,
                metrics.get(run.run_id),
                fit if spec.fit_enabled else None,
                impedance_override=impedance_override,
                normalization=normalization,
            )
            _annotate(ax, style, text)

    _labels(ax, style, f"Z' ({unit})", f"-Z'' ({unit})")
    set_axis_display_units(ax, x=(unit, factor), y=(unit, factor))
    if spec.title and style.show_title:
        ax.set_title(spec.title, fontsize=style.title_size, fontfamily=style.font_family,
                     fontweight="bold" if style.title_bold else "normal")
    if style.nyquist_equal_aspect and _equal_aspect_reasonable(x_series, y_series):
        ax.set_aspect("equal", adjustable="datalim")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size,
                           frameon=style.legend_frame, shadow=style.legend_shadow,
                           ncol=style.legend_columns)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top",
                fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_bode(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> list[str]:
    runs = _selected_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 EIS 数据")
        return ["没有选择 EIS 数据"]
    warnings: list[str] = []
    normalization = _resolve_normalization(runs, spec.normalization, warnings)
    runs = _filtered_runs(runs, spec)
    runs = [run for run in runs if len(run.freq) >= 2]
    if not runs:
        _message(figure, style, "所选频率范围内无数据")
        return warnings + ["所选频率范围内无数据"]

    impedance_override = _unit_override(spec, "impedance")
    unit, factor = _unit_for_impedance(
        runs, normalization, override=impedance_override, warnings=warnings
    )
    colors = resolve_color_cycle(style, len(runs), color_config)
    figure.clear()
    ax_phase = figure.add_subplot(2, 1, 1)
    ax_mag = figure.add_subplot(2, 1, 2)
    metrics = metrics or {}

    file_numbers = dataset_file_numbers(dataset)
    for index, run in enumerate(runs):
        order = np.argsort(run.freq)
        freq = run.freq[order]
        phase = run.phase[order]
        _, _, mag = _z_values(run, normalization)
        color = colors[index % len(colors)]
        label = _legend_label(run, spec, warnings, file_number=file_numbers.get(run.run_id))
        ax_phase.semilogx(freq, phase, "-", color=color, linewidth=style.line_width, label=label)
        ax_mag.loglog(freq, mag[order] * factor, "-", color=color, linewidth=style.line_width, label=label)
        metric = metrics.get(run.run_id)
        if metric and metric.f_peak_hz:
            ax_phase.axvline(metric.f_peak_hz, color=color, linestyle=":", linewidth=0.9, alpha=0.8)
            ax_mag.axvline(metric.f_peak_hz, color=color, linestyle=":", linewidth=0.9, alpha=0.8)

    phase_label = "Phase (°)" if spec.paper_layout.get("enabled") else "Phase angle (°)"
    _labels(ax_phase, style, "", phase_label)
    _labels(ax_mag, style, "Frequency (Hz)", f"|Z| ({unit})")
    set_axis_display_units(ax_phase, x=("Hz", 1.0), y=("°", 1.0))
    set_axis_display_units(ax_mag, x=("Hz", 1.0), y=(unit, factor))
    if spec.title and style.show_title:
        ax_phase.set_title(spec.title, fontsize=style.title_size, fontfamily=style.font_family,
                           fontweight="bold" if style.title_bold else "normal")
    if style.legend and spec.show_legend:
        legend = ax_phase.legend(loc=style.legend_location, fontsize=style.legend_size,
                                 frameon=style.legend_frame, shadow=style.legend_shadow,
                                 ncol=style.legend_columns)
        style.style_legend(legend)
    if warnings:
        ax_phase.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax_phase.transAxes, ha="left", va="top",
                      fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw_fit(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> list[str]:
    runs = _selected_runs(dataset, spec)
    if not runs:
        _message(figure, style, "没有选择 EIS 数据")
        return ["没有选择 EIS 数据"]
    fits = fits or {}
    available = [run for run in runs if run.run_id in fits]
    if not available:
        _message(figure, style, "请先点击“拟合”生成结果")
        return ["没有拟合结果"]
    warnings: list[str] = []
    normalization = _resolve_normalization(available, spec.normalization, warnings)
    impedance_override = _unit_override(spec, "impedance")
    unit, factor = _unit_for_impedance(
        available, normalization, override=impedance_override, warnings=warnings
    )
    colors = resolve_color_cycle(style, len(available), color_config)
    metrics = metrics or {}

    figure.clear()
    ax = figure.add_subplot(2, 1, 1)
    ax_res = figure.add_subplot(2, 1, 2)
    file_numbers = dataset_file_numbers(dataset)
    x_series: list[np.ndarray] = []
    y_series: list[np.ndarray] = []
    for index, run in enumerate(available):
        fit = fits[run.run_id]
        real, imag, _ = _z_values(run, normalization)
        color = colors[index % len(colors)]
        label = _legend_label(run, spec, warnings, file_number=file_numbers.get(run.run_id))
        x_display = real * factor
        y_display = -imag * factor
        x_series.append(x_display)
        y_series.append(y_display)
        ax.plot(x_display, y_display, "o", color=color, markersize=style.marker_size,
                label=label)
        fit_real = normalize_impedance(fit.z_fit.real, normalization, area_cm2=run.params.area_cm2)
        fit_imag = normalize_impedance(fit.z_fit.imag, normalization, area_cm2=run.params.area_cm2)
        x_fit = fit_real * factor
        y_fit = -fit_imag * factor
        x_series.append(x_fit)
        y_series.append(y_fit)
        ax.plot(x_fit, y_fit, "-", color=color, linewidth=style.line_width,
                label=f"{label} fit")
        ax_res.semilogx(fit.frequencies, fit.residual_real * factor, "o", color=color,
                        markersize=max(2, style.marker_size - 2), label="Real residual")
        ax_res.semilogx(fit.frequencies, fit.residual_imag * factor, "x", color=color,
                        markersize=max(2, style.marker_size - 1), label="Imag residual")
        if style.annotation and spec.annotations and len(available) == 1:
            _annotate(
                ax,
                style,
                _format_metrics(
                    run,
                    metrics.get(run.run_id),
                    fit,
                    impedance_override=impedance_override,
                    normalization=normalization,
                ),
            )
    _labels(ax, style, f"Z' ({unit})", f"-Z'' ({unit})")
    _labels(ax_res, style, "Frequency (Hz)", f"Residual ({unit})")
    set_axis_display_units(ax, x=(unit, factor), y=(unit, factor))
    set_axis_display_units(ax_res, x=("Hz", 1.0), y=(unit, factor))
    ax_res.axhline(0.0, color="#666666", linewidth=0.8)
    if style.nyquist_equal_aspect and _equal_aspect_reasonable(x_series, y_series):
        ax.set_aspect("equal", adjustable="datalim")
    if style.legend and spec.show_legend:
        legend = ax.legend(loc=style.legend_location, fontsize=style.legend_size,
                           frameon=style.legend_frame, shadow=style.legend_shadow,
                           ncol=style.legend_columns)
        style.style_legend(legend)
    if warnings:
        ax.text(0.02, 0.98, "\n".join(warnings[:3]), transform=ax.transAxes, ha="left", va="top",
                fontsize=max(8, style.annotation_size - 1), color="#a33", fontfamily=_cjk_fonts())
    _finish(figure, style, spec)
    return warnings


def draw(
    figure: Figure,
    dataset: Dataset,
    spec: PlotSpec,
    style: PlotStyle,
    *,
    color_config: dict | None = None,
    fits: dict[str, EISFitResult] | None = None,
    metrics: dict[str, EISMetrics] | None = None,
) -> list[str]:
    if spec.kind == "eis_nyquist":
        return draw_nyquist(figure, dataset, spec, style, color_config=color_config, fits=fits, metrics=metrics)
    if spec.kind == "eis_bode":
        return draw_bode(figure, dataset, spec, style, color_config=color_config, fits=fits, metrics=metrics)
    if spec.kind == "eis_fit":
        return draw_fit(figure, dataset, spec, style, color_config=color_config, fits=fits, metrics=metrics)
    _message(figure, style, f"未知 EIS 绘图类型: {spec.kind}")
    return [f"未知 EIS 绘图类型: {spec.kind}"]
