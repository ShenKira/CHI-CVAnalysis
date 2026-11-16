"""Production LSV and amperometric i-t rendering."""
from __future__ import annotations

import math
import numpy as np
from matplotlib.text import Annotation
from matplotlib.path import Path
from matplotlib.transforms import Bbox

from cvanalysis.domain.units import (
    CAPACITANCE,
    CURRENT,
    CURRENT_DENSITY,
    canonical_unit,
    resolve_unit,
    sweep_current_family,
    unit_factor,
)
from cvanalysis.plotting.axis_limits import _unit_scale, set_axis_display_units, unit_dimension
from cvanalysis.plotting.colors import resolve_color_cycle
from cvanalysis.plotting.cp_renderer import _finish
from cvanalysis.plotting.legend import dataset_file_numbers, dataset_runs, effective_template, preview_label, resolve_legend_labels
from cvanalysis.plotting.style import font_kwargs
from cvanalysis.plotting.texts import axis_text, safe_format
from cvanalysis.plotting.template_format import DisplayValue, TemplateError, format_template, literal_fallback
from cvanalysis.plotting.it_references import references_from_options
from matplotlib.colors import is_color_like


class _AutoReferenceAnnotation(Annotation):
    """Lay out reference labels together once the final axes geometry is known."""

    def draw(self, renderer):
        if not self.get_visible() or not self._check_xy(renderer):
            return
        _layout_reference_annotations(self.axes, renderer)
        super().draw(renderer)


def _layout_reference_annotations(axes, renderer):
    labels = [text for text in axes.texts
              if isinstance(text, _AutoReferenceAnnotation) and text.get_visible()
              and np.isfinite(text.xy).all()]
    if not labels:
        return
    bounds = axes.get_window_extent(renderer)
    legend = axes.get_legend()
    if legend is not None and not legend.get_visible():
        legend = None
    lines = [line for line in axes.lines
             if line.get_visible() and line.get_linestyle() not in ("None", "none", "", " ")]
    other_texts = [text for text in axes.texts
                   if not isinstance(text, _AutoReferenceAnnotation) and text.get_visible()]
    signature = (
        type(renderer), getattr(renderer, "dpi", None), tuple(bounds.bounds),
        tuple(axes.get_xlim()), tuple(axes.get_ylim()), axes.get_xscale(), axes.get_yscale(),
        tuple((id(label), label.get_text(), tuple(label.xy), str(label.get_fontproperties()),
               label.get_rotation()) for label in labels),
        (id(legend), legend.stale, str(legend._loc)) if legend is not None else None,
        tuple((id(text), text.get_text(), tuple(text.get_position()), str(text.get_fontproperties()),
               text.get_ha(), text.get_va(), text.get_rotation()) for text in other_texts),
        tuple((line.get_path(), line.get_transform().get_affine().get_matrix().tobytes())
              for line in lines),
    )
    if getattr(axes, "_reference_layout_signature", None) == signature:
        return

    obstacles = [text.get_window_extent(renderer) for text in other_texts]
    if legend is not None:
        obstacles.append(legend.get_window_extent(renderer))
    paths = []
    for line in lines:
        vertices = line.get_xydata()
        if len(vertices) < 2:
            continue
        if len(vertices) > 1200:
            vertices = vertices[np.linspace(0, len(vertices) - 1, 1200, dtype=int)]
        paths.append(Path(line.get_transform().transform(vertices)))

    # Sorting by displayed current (not dataset order or screen direction)
    # also keeps larger values above smaller values on an inverted y axis.
    labels.sort(key=lambda label: label.xy[1])
    sizes = []
    points = []
    for label in labels:
        label.set_ha("left")
        label.set_va("bottom")
        box = label.get_window_extent(renderer)
        sizes.append((box.width, box.height))
        points.append(label._get_xy(renderer, label.xy, label.xycoords))

    pad = 3.0
    left, right = bounds.x0 + pad, bounds.x1 - pad
    bottom, top = bounds.y0 + pad, bounds.y1 - pad
    width = max(size[0] for size in sizes)
    # When the labels fit, keep a small gap. For an overfull axes the same
    # ordering is retained with overlapping labels rather than moving them out.
    heights = [size[1] for size in sizes]
    available = max(0., top - bottom)
    gap = min(3., max(0., (available - sum(heights)) / max(1, len(labels) - 1)))
    feasible = sum(heights) + gap * (len(labels) - 1) <= available
    x_max = max(left, right - width)
    xs = np.linspace(left, x_max, 25) if x_max > left else [left]
    shifts = np.linspace(-available, available, 17) if feasible else [0.]
    best = None
    for shift in shifts:
        if feasible:
            ys = []
            for point, height in zip(points, heights):
                desired = min(max(point[1] + 8 + shift, bottom), top - height)
                ys.append(max(desired, ys[-1] + heights[len(ys) - 1] + gap) if ys else desired)
            if ys[-1] + heights[-1] > top:
                ys[-1] = top - heights[-1]
                for index in range(len(ys) - 2, -1, -1):
                    ys[index] = min(ys[index], ys[index + 1] - gap - heights[index])
        else:
            # More labels than fit: preserve center ordering and clip to axes.
            centers = np.linspace(bottom, top, len(labels) + 2)[1:-1]
            ys = [min(max(center - height / 2, bottom), max(bottom, top - height))
                  for center, height in zip(centers, heights)]
        for x in xs:
            boxes = [Bbox.from_bounds(x, y, w, h)
                     for y, (w, h) in zip(ys, sizes)]
            overlap = 0.
            for box in boxes:
                for obstacle in obstacles:
                    intersection = Bbox.intersection(box, obstacle)
                    if intersection is not None:
                        overlap += intersection.width * intersection.height
            crossings = sum(path.intersects_bbox(box, filled=False) for path in paths for box in boxes)
            distance = sum(abs(x - point[0]) + abs(y - point[1])
                           for point, y in zip(points, ys))
            score = overlap * 10 + crossings * 1000 + distance * .01
            if best is None or score < best[0]:
                best = (score, x, ys)
    _, x, ys = best
    pixel_per_point = renderer.points_to_pixels(1.)
    for label, point, y in zip(labels, points, ys):
        label.set_position(((x - point[0]) / pixel_per_point,
                            (y - point[1]) / pixel_per_point))
        label.set_clip_on(True)
        label.set_clip_path(axes.patch)
    axes._reference_layout_signature = signature


def _reference_text(options, time, value, family, run, *, axis_unit=None, axis_factor=1., suffix=""):
    """Format annotation values without changing the plotted current."""
    requested = options.get("it_reference_current_unit", "axis")
    if requested == "axis" and axis_unit is not None:
        unit, factor = axis_unit, axis_factor
    elif requested == "auto":
        unit, factor = resolve_unit(family, [value])
    else:
        requested = canonical_unit(requested)
        override = requested + suffix
        factor = {"A": 1., "mA": 1e3, "µA": 1e6, "nA": 1e9, "pA": 1e12}.get(requested)
        unit, factor = (override, factor) if factor is not None else (family.units[0][0], 1.)
    try:
        digits = max(0, min(10, int(options.get("it_reference_digits", 4))))
    except (TypeError, ValueError, OverflowError):
        digits = 4
    number_format = options.get("it_reference_number_format", "auto")
    code = {"fixed": f".{digits}f", "scientific": f".{digits}e",
            "significant": f"#.{max(1, digits)}g"}.get(number_format, ".4g")
    time_text, current_text = format(time, code), format(value * factor, code)
    mode = options.get("it_reference_label_mode", "time_current")
    if mode == "current":
        return f"I={current_text} {unit}"
    if mode == "custom":
        template = str(options.get("it_reference_label_text", ""))
        values = {"time": DisplayValue(float(time), time_text),
                  "current": DisplayValue(float(value * factor), current_text),
                  "unit": unit, "name": run.display_name}
        try:
            return format_template(template, values)
        except TemplateError:
            return literal_fallback(template)

    return f"t={time_text} s, I={current_text} {unit}"


def _reference_annotation(ax, text, point, options, style, color, run_id):
    if options.get("it_reference_position", "auto") == "manual":
        try:
            positions = options.get("it_reference_positions", {})
            position = positions.get(run_id, (75., 85.)) if isinstance(positions, dict) else (75., 85.)
            x, y = float(position[0]), float(position[1])
            if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 100 and 0 <= y <= 100):
                raise ValueError
        except (ValueError, TypeError, OverflowError, IndexError, KeyError):
            x, y = 75., 85.
        arrow = {"arrowstyle": "-", "color": color, "linewidth": .8,
                 "shrinkA": 3, "shrinkB": 3} if options.get("it_reference_leader", False) else None
        annotation = ax.annotate(text, point, xytext=(x / 100, y / 100),
                                 textcoords="axes fraction", ha="center", va="center",
                                 fontsize=style.annotation_size, fontfamily=style.text_font_family(), arrowprops=arrow)
    else:
        annotation = _AutoReferenceAnnotation(text, point, xytext=(8, 8),
                                               textcoords="offset points", fontsize=style.annotation_size,
                                               fontfamily=style.text_font_family())
        ax.add_artist(annotation)
    annotation.set_in_layout(False)
    return annotation


def _manual_y_reference(ax, reference, style, unit, factor, warnings):
    raw = reference.get("value")
    if raw is None:
        return
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError
        saved = reference.get("unit")
        if saved is not None:
            if not isinstance(saved, dict):
                raise ValueError
            old_unit = saved.get("label")
            old_factor = float(saved.get("factor"))
            expected = _unit_scale(old_unit) if isinstance(old_unit, str) else None
            dimension = unit_dimension(unit)
            if (expected is None or not math.isfinite(old_factor) or old_factor <= 0
                    or not math.isclose(old_factor, expected, rel_tol=1e-9)
                    or saved.get("dimension") != dimension
                    or unit_dimension(old_unit) != dimension):
                raise ValueError
            value *= factor / old_factor
        if not math.isfinite(value):
            raise ValueError
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        warnings.append("手动 Y 参考线的数值或单位与当前纵轴不兼容，请重新设置")
        return
    label_visible = reference.get("label_visible", True) is not False
    mode = reference.get("legend_mode", "hidden")
    label = ""
    if label_visible or mode == "label":
        template = str(reference.get("label") or "I = {value:.4g} {unit}")
        try:
            label = format_template(template, {"value": value, "unit": unit})
        except TemplateError:
            label = f"I = {value:.4g} {unit}"
            warnings.append("手动 Y 参考线的图注格式无效，已使用默认文字")
    color = reference.get("color", "#666666")
    if not isinstance(color, str) or not is_color_like(color):
        color = "#666666"
        warnings.append("手动 Y 参考线颜色无效，已使用灰色")
    legend_label = None
    if mode == "label":
        legend_label = label
    elif mode == "custom":
        try:
            legend_label = format_template(str(reference.get("legend_label") or ""),
                                           {"value": value, "unit": unit}) or None
        except TemplateError:
            warnings.append("手动 Y 参考线图例格式无效，已隐藏图例项")
    line = ax.axhline(value, color=color, linestyle="--",
                      linewidth=max(0.8, style.line_width * .7), label=legend_label or "_nolegend_")
    line.set_gid("it_manual_y_reference")
    line._it_reference_id = str(reference.get("id", ""))
    line._it_reference_legend_text = legend_label
    if not label_visible:
        return
    manual_position = None
    if reference.get("label_position_mode", "auto") == "manual":
        try:
            position = reference.get("label_position", [75., 85.])
            x, y = float(position[0]), float(position[1])
            if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 100 and 0 <= y <= 100):
                raise ValueError
            manual_position = (x / 100, y / 100)
        except (TypeError, ValueError, OverflowError, IndexError, KeyError):
            warnings.append("手动 Y 参考线的标签坐标无效，已使用自动排版")
    if manual_position is not None:
        annotation = ax.annotate(label, (.5, value), xycoords=("axes fraction", "data"),
                                 xytext=manual_position, textcoords="axes fraction",
                                 ha="center", va="center", color=color,
                                 fontsize=style.annotation_size,
                                 fontfamily=style.text_font_family())
        annotation.set_clip_on(True)
        annotation.set_clip_path(ax.patch)
    else:
        # Auto labels share the reference-point layout and reflow on redraw.
        annotation = _AutoReferenceAnnotation(label, (.5, value),
                                               xycoords=("axes fraction", "data"),
                                               xytext=(8, 8), textcoords="offset points",
                                               color=color, fontsize=style.annotation_size,
                                               fontfamily=style.text_font_family())
        ax.add_artist(annotation)
    annotation.set_gid("it_manual_y_reference_label")
    annotation._it_reference_id = str(reference.get("id", ""))
    annotation.set_in_layout(False)


def draw(figure, dataset, spec, style, *, color_config=None):
    kind = "lsv" if spec.kind == "lsv_curve" else "it"
    source = dataset.lsv_runs if kind == "lsv" else dataset.it_runs
    selected = set(spec.run_ids)
    runs = [run for run in source if run.run_id in selected]
    figure.clear()
    ax = figure.add_subplot(111)
    warnings = []
    prefix = "lsv" if kind == "lsv" else "it"
    display_mode = str(
        spec.analysis_options.get(f"{prefix}_current_display", "follow")
        or "follow"
    )
    if display_mode not in {
        "follow",
        "reference_area",
        "reference_capacitance",
    }:
        display_mode = "follow"
    normalization = spec.normalization
    constant_divisor: float | None = None
    suffix = ""
    text_mode = normalization
    if display_mode == "reference_area":
        try:
            reference_area = float(
                spec.analysis_options.get(f"{prefix}_reference_area_cm2")
            )
        except (TypeError, ValueError, OverflowError):
            reference_area = float("nan")
        if not np.isfinite(reference_area) or reference_area <= 0:
            warnings.append("参考面积无效，已回退为原始电流")
            display_mode = "raw"
            constant_divisor = 1.0
            family = CURRENT
            suffix = ""
            text_mode = "none"
        else:
            constant_divisor = reference_area
            family = CURRENT_DENSITY
            suffix = "/cm²"
            text_mode = "reference_area"
    elif display_mode == "reference_capacitance":
        try:
            reference_capacitance = float(
                spec.analysis_options.get(
                    f"{prefix}_reference_capacitance_f"
                )
            )
        except (TypeError, ValueError, OverflowError):
            reference_capacitance = float("nan")
        if (
            not np.isfinite(reference_capacitance)
            or reference_capacitance <= 0
        ):
            warnings.append("参考电容无效，已回退为原始电流")
            display_mode = "raw"
            constant_divisor = 1.0
            family = CURRENT
            suffix = ""
            text_mode = "none"
        else:
            constant_divisor = reference_capacitance
            cap_unit = canonical_unit(
                spec.analysis_options.get(
                    f"{prefix}_reference_capacitance_unit"
                )
                or "F"
            )
            if unit_factor(CAPACITANCE, cap_unit) is None:
                cap_unit = "F"
            family = sweep_current_family(
                "reference_capacitance", normalization, cap_unit
            )
            suffix = f"/{cap_unit}"
            text_mode = "reference_capacitance"
    elif display_mode == "raw":
        constant_divisor = 1.0
        family = CURRENT
        suffix = ""
        text_mode = "none"
    else:
        display_mode = "follow"
        if normalization == "area" and not all(run.params.has_area() for run in runs):
            normalization = "none"
            warnings.append("部分数据缺少电极面积，已回退为原始电流")
        if normalization == "mass" and not all(run.params.has_mass() for run in runs):
            normalization = "none"
            warnings.append("部分数据缺少活性物质质量，已回退为原始电流")
        family = sweep_current_family("follow", normalization)
        suffix = "/cm²" if normalization == "area" else "/g" if normalization == "mass" else ""
        text_mode = normalization
    colors = resolve_color_cycle(style, len(runs), color_config)
    clip_negative = kind == "lsv" and bool(spec.analysis_options.get("lsv_clip_negative", False))
    overrides = spec.analysis_options.get("unit_overrides")
    requested = overrides.get("current") if isinstance(overrides, dict) else None
    if requested:
        normalized = []
        for run in runs:
            divisor = (
                constant_divisor
                if constant_divisor is not None
                else run.params.area_cm2
                if normalization == "area"
                else run.params.mass_mg * 1e-3
                if normalization == "mass"
                else 1.0
            )
            current = np.asarray(run.current, dtype=float)
            if clip_negative:
                current = np.maximum(current, 0.0)
            finite = current[np.isfinite(current)]
            if finite.size:
                normalized.append(float(np.max(np.abs(finite))) / divisor)
        override = None if requested == "auto" else requested
        if (
            override
            and unit_factor(family, override) is None
            and display_mode == "reference_capacitance"
        ):
            prefix_unit = str(override).split("/", 1)[0]
            candidate = f"{prefix_unit}/{cap_unit}"
            if unit_factor(family, candidate) is not None:
                override = candidate
        unit, factor = resolve_unit(family, normalized, override)
        if override and unit_factor(family, override) is None:
            warnings.append(f"电流单位 {override} 不适用于当前归一化方式，已自动选择 {unit}")
    else:
        unit, factor = family.units[0]
    labels = resolve_legend_labels(dataset_runs(dataset), spec=spec, file_numbers=dataset_file_numbers(dataset))
    for index, run in enumerate(runs):
        divisor = (
            constant_divisor
            if constant_divisor is not None
            else run.params.area_cm2
            if normalization == "area"
            else run.params.mass_mg * 1e-3
            if normalization == "mass"
            else 1.0
        )
        current = run.current / divisor
        if clip_negative:
            current = np.maximum(current, 0.0)
        fallback = labels[run.run_id].label if run.run_id in labels else run.legend_name
        label, unknown = preview_label(run, effective_template(run, spec),
                                       file_number=dataset_file_numbers(dataset).get(run.run_id), fallback=fallback)
        if unknown:
            warnings.append(f"{run.display_name}: 未知图例字段 {', '.join(unknown)}")
        ax.plot(run.x, current * factor, color=colors[index], linewidth=style.line_width, label=label or "_nolegend_")
        reference = spec.analysis_options.get("it_reference_time") if kind == "it" else None
        if reference is not None:
            try:
                time = float(reference)
                if not math.isfinite(time) or time < np.min(run.x) or time > np.max(run.x):
                    raise ValueError
                nearest = int(np.argmin(np.abs(run.x - time)))
                value = float(current[nearest])
                ax.axhline(value * factor, color=colors[index], linestyle="--", linewidth=max(0.8, style.line_width * .7))
                ax.plot([run.x[nearest]], [value * factor], "o", color=colors[index], markersize=style.marker_size)
                visibility = spec.analysis_options.get("it_reference_label_visibility", {})
                visible = (spec.analysis_options.get("it_reference_show_labels", True) is not False
                           and (not isinstance(visibility, dict) or visibility.get(run.run_id, True) is not False))
                if visible:
                    label_text = _reference_text(spec.analysis_options, float(run.x[nearest]), value, family, run,
                                                 axis_unit=unit, axis_factor=factor, suffix=suffix)
                    if label_text:
                        _reference_annotation(ax, label_text, (run.x[nearest], value * factor), spec.analysis_options, style, colors[index], run.run_id)
            except (TypeError, ValueError, OverflowError):
                warnings.append(f"{run.display_name}: 参考时间不在测量范围内，未绘制参考线")
    if kind == "it":
        for reference in references_from_options(spec.analysis_options):
            _manual_y_reference(ax, reference, style, unit, factor, warnings)
    if kind == "lsv":
        low, high = spec.analysis_options.get("lsv_window_low"), spec.analysis_options.get("lsv_window_high")
        if low is not None and high is not None:
            try:
                low, high = sorted((float(low), float(high)))
                if not math.isfinite(low) or not math.isfinite(high) or low == high:
                    raise ValueError
                ax.axvspan(low, high, color="tab:blue", alpha=.12)
                ax.axvline(low, linestyle="--", color="tab:blue", linewidth=1)
                ax.axvline(high, linestyle="--", color="tab:blue", linewidth=1)
                ax.text(.5, .97, f"ΔV = {high-low:.4g} V", transform=ax.transAxes,
                        ha="center", va="top", fontsize=style.annotation_size)
            except (TypeError, ValueError, OverflowError):
                warnings.append("LSV 电压窗口无效，未绘制窗口")
    x_unit = "V" if kind == "lsv" else "s"
    ax.set_xlabel(axis_text(spec, "main", "x", unit=x_unit), **font_kwargs(style, axis="x"))
    ax.set_ylabel(
        axis_text(spec, "main", "y", unit=unit, normalization=text_mode),
        **font_kwargs(style, axis="y"),
    )
    set_axis_display_units(ax, x=(x_unit, 1.0), y=(unit, factor))
    if spec.title and style.show_title:
        ax.set_title(safe_format(spec.title, {}), fontsize=style.title_size)
    if style.legend and spec.show_legend:
        handles, legend_labels = ax.get_legend_handles_labels()
        for line in ax.lines:
            explicit = getattr(line, "_it_reference_legend_text", None)
            if explicit and explicit.startswith("_"):
                handles.append(line)
                legend_labels.append(explicit)
        if handles:
            ax.legend(handles, legend_labels)
    style.apply(figure)
    _finish(figure, style, spec)
    return warnings
