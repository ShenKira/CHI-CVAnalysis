"""Paper-size font compensation and legend layout helpers."""

from __future__ import annotations

import math
import warnings

from matplotlib.backends.backend_agg import RendererAgg


PAPER_LEGEND_PLACEMENTS = {"auto", "inside", "outside"}
MAX_PAPER_LEGEND_COLUMNS = 8
SMALL_FIGURE_THRESHOLD = 0.33
SMALL_FIGURE_FONT_SCALE = 0.8
PAPER_AXIS_LABEL_PAD_PT = 2.0
PAPER_SINGLE_AXIS_LEFT_BOUNDARY = 0.04


def paper_overrides(layout, style):
    if not layout or not layout.get("enabled"):
        return {}
    fraction = float(layout.get("fraction", 0.5))
    page_mm = float(layout.get("text_width_mm", 160))
    body = float(layout.get("body_pt", 10))
    if not all(math.isfinite(v) for v in (fraction, page_mm, body)) or not (0 < fraction <= 1 and 50 <= page_mm <= 400 and 5 <= body <= 30):
        raise ValueError("论文占比须在 0–1 之间，版心宽度须为 50–400 mm，正文字号须为 5–30 pt")
    source_width_mm = style.figure_size[0] * 25.4
    scale = page_mm * fraction / source_width_mm
    size_scale = SMALL_FIGURE_FONT_SCALE if fraction < SMALL_FIGURE_THRESHOLD else 1.0
    # Source points × placement scale = final points in the paper.
    # Derive this from the unchanging canvas, never from an already-scaled font.
    return dict(font_size=body * .8 / scale * size_scale,
                title_size=body / scale * size_scale, label_size=body * .9 / scale * size_scale, xlabel_size=body * .9 / scale * size_scale,
                ylabel_size=body * .9 / scale * size_scale, tick_size=body * .8 / scale * size_scale,
                legend_size=body * .8 / scale * size_scale, annotation_size=body * .75 / scale * size_scale,
                save_bbox_inches=False, tight_layout=False)


def paper_legend_settings(layout: dict, *, fraction: float | None = None) -> tuple[str, float, int | str]:
    """Return resolved placement, auto threshold and requested column count.

    Invalid or missing project fields fall back safely for backwards
    compatibility. The threshold comparison is intentionally strict (<).
    """
    mode = layout.get("legend_placement", "auto")
    if not isinstance(mode, str) or mode not in PAPER_LEGEND_PLACEMENTS:
        mode = "auto"
    try:
        threshold = float(layout.get("legend_outside_threshold", 0.5))
    except (TypeError, ValueError):
        threshold = 0.5
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        threshold = 0.5
    columns = layout.get("legend_columns", "auto")
    if columns != "auto":
        try:
            columns = int(columns)
        except (TypeError, ValueError, OverflowError):
            columns = "auto"
        if columns != "auto" and not 1 <= columns <= MAX_PAPER_LEGEND_COLUMNS:
            columns = "auto"
    if mode == "auto":
        try:
            current_fraction = float(fraction if fraction is not None else layout.get("fraction", 0.5))
        except (TypeError, ValueError):
            current_fraction = 0.5
        mode = "outside" if math.isfinite(current_fraction) and current_fraction < threshold else "inside"
    return mode, threshold, columns


def _renderer_for(figure):
    dpi = max(1.0, float(figure.dpi))
    width = max(1, int(round(figure.get_figwidth() * dpi)))
    height = max(1, int(round(figure.get_figheight() * dpi)))
    return RendererAgg(width, height, dpi)


def _legend_bbox_in_figure(figure, legend):
    renderer = _renderer_for(figure)
    figure.draw(renderer)
    return legend.get_window_extent(renderer).transformed(figure.transFigure.inverted())


def _unique_legend_items(axes):
    handles: list = []
    labels: list[str] = []
    seen: set[str] = set()
    for ax in axes:
        axis_handles, axis_labels = ax.get_legend_handles_labels()
        for handle, label in zip(axis_handles, axis_labels):
            if not label or label.startswith("_") or label in seen:
                continue
            seen.add(label)
            handles.append(handle)
            labels.append(label)
    return handles, labels


def _make_legend(figure, handles, labels, style, *, ncols, axis=None, loc="best", anchor=None):
    common = dict(
        fontsize=style.legend_size,
        frameon=False,
        ncols=ncols,
        handlelength=1.4,
        handletextpad=0.45,
        columnspacing=0.9,
        labelspacing=0.25,
        borderpad=0.15,
        borderaxespad=0.0,
    )
    if axis is not None:
        legend = axis.legend(handles, labels, loc=loc, **common)
    else:
        legend = figure.legend(
            handles,
            labels,
            loc=loc,
            bbox_to_anchor=anchor,
            **common,
        )
    style.style_legend(legend)
    return legend


def _choose_columns(figure, handles, labels, style, requested, *, axis=None, loc="best", anchor=None,
                    usable_width_fraction: float = 0.92):
    if not labels:
        return 1
    if requested != "auto":
        return min(max(1, int(requested)), len(labels))

    container_width = axis.bbox.width if axis is not None else figure.bbox.width
    max_columns = min(len(labels), MAX_PAPER_LEGEND_COLUMNS)
    for ncols in range(max_columns, 0, -1):
        legend = _make_legend(
            figure,
            handles,
            labels,
            style,
            ncols=ncols,
            axis=axis,
            loc=loc,
            anchor=anchor,
        )
        bbox = _legend_bbox_in_figure(figure, legend)
        legend.remove()
        if container_width > 0 and bbox.width * figure.bbox.width <= container_width * usable_width_fraction:
            return ncols
    return 1


def _tight_layout(figure, *, rect=None, pad=0.7, h_pad=0.7) -> bool:
    """Run tight_layout and detect its "could not fit" warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        try:
            figure.tight_layout(pad=pad, h_pad=h_pad, rect=rect)
        except (RuntimeError, ValueError):
            return False
    if any("Tight layout not applied" in str(item.message) for item in caught):
        # tight_layout installs a placeholder engine; clear it before applying
        # the manual fallback, otherwise subplots_adjust is ignored.
        figure.set_layout_engine(None)
        return False
    return True


def _rebuild_inside_legends(figure, spec, style, requested_columns):
    """Apply paper-mode automatic/custom column counts to axes legends."""
    for ax in figure.axes:
        old = ax.get_legend()
        if old is None:
            continue
        handles, labels = ax.get_legend_handles_labels()
        old.remove()
        if not labels:
            continue
        columns = _choose_columns(
            figure,
            handles,
            labels,
            style,
            requested_columns,
            axis=ax,
            loc=style.legend_location,
        )
        _make_legend(
            figure,
            handles,
            labels,
            style,
            ncols=columns,
            axis=ax,
            loc=style.legend_location,
        )

    # The fit plot has two meaningful legend groups. The lower panel has no
    # legend today, so show its two residual series when the legend is inside.
    if spec.kind == "eis_fit" and len(figure.axes) > 1 and figure.axes[1].get_legend() is None:
        residual_ax = figure.axes[1]
        handles, labels = _unique_legend_items([residual_ax])
        if handles:
            columns = _choose_columns(
                figure,
                handles,
                labels,
                style,
                requested_columns,
                axis=residual_ax,
                loc="best",
            )
            _make_legend(figure, handles, labels, style, ncols=columns, axis=residual_ax, loc="best")


def _finish_inside(figure, spec, style, requested_columns):
    _rebuild_inside_legends(figure, spec, style, requested_columns)
    if not _tight_layout(figure, pad=0.8, h_pad=0.8):
        # Keep a deterministic fallback for artists/layouts that tight_layout
        # cannot measure, while preserving the fixed Figure dimensions.
        figure.set_layout_engine(None)
        figure.subplots_adjust(left=0.16, right=0.96, bottom=0.18, top=0.94, hspace=0.5)


def _finish_outside(figure, handles, labels, style, requested_columns, spec):
    if not labels:
        if not _tight_layout(figure, pad=0.8, h_pad=0.8):
            figure.set_layout_engine(None)
            figure.subplots_adjust(left=0.16, right=0.96, bottom=0.18, top=0.94, hspace=0.5)
        return

    multi_axes = len(figure.axes) > 1
    fit_legend_on_right = spec.kind == "eis_fit" and multi_axes
    if fit_legend_on_right:
        loc, anchor, usable_width = "center right", (0.985, 0.5), 0.46
    elif multi_axes:
        loc, anchor, usable_width = "upper center", (0.5, 0.99), 0.92
    else:
        loc, anchor, usable_width = "lower center", (0.5, 0.025), 0.92
    columns = _choose_columns(
        figure,
        handles,
        labels,
        style,
        requested_columns,
        loc=loc,
        anchor=anchor,
        usable_width_fraction=usable_width,
    )
    legend = _make_legend(
        figure,
        handles,
        labels,
        style,
        ncols=columns,
        loc=loc,
        anchor=anchor,
    )
    bbox = _legend_bbox_in_figure(figure, legend)
    if fit_legend_on_right:
        right = max(0.48, bbox.x0 - 0.025)
        rect = (0.08, 0.08, right, 0.94)
    elif multi_axes:
        top = max(0.55, bbox.y0 - 0.025)
        rect = (0.08, 0.08, 0.96, top)
    else:
        # rect is the full area for axes and their labels. tight_layout accounts
        # for the label band, so only reserve the measured legend plus a gap.
        bottom = min(0.72, max(0.08, bbox.y1 + 0.02))
        rect = (PAPER_SINGLE_AXIS_LEFT_BOUNDARY, bottom, 0.96, 0.95)
    layout_ok = _tight_layout(figure, pad=0.55, h_pad=0.65, rect=rect)
    if not layout_ok:
        figure.set_layout_engine(None)
        if multi_axes and not fit_legend_on_right:
            figure.subplots_adjust(left=0.13, right=0.96, bottom=0.12, top=rect[3], hspace=0.42)
        elif not fit_legend_on_right:
            figure.subplots_adjust(left=0.14, right=0.96, bottom=max(0.15, rect[1]), top=0.95)
    if fit_legend_on_right:
        figure.set_layout_engine(None)
        # The combined fit legend leaves less width for the plot axes. Preserve
        # enough room for the large compensated Y labels, especially below
        # the small-figure font threshold where source labels are enlarged.
        figure.subplots_adjust(left=0.18, right=rect[2], bottom=0.12, top=0.94, hspace=0.42)


def finish_paper(figure, spec, style):
    """Apply paper legend placement and compact margins after each renderer.

    Single-axis plots place external legends below the axes. Bode plots use a
    shared Figure legend above their axes; fit plots reserve a right-side lane
    for their larger combined legend. Preview and export both call this
    function, so placement and column decisions stay consistent.
    """
    layout = spec.paper_layout
    if not layout.get("enabled"):
        return
    if not figure.axes:
        return

    # This function is called once while drawing and again after manual axis
    # limits/ticks are applied. Clear figure-level legends so the second pass
    # replaces them instead of stacking duplicates.
    for legend in list(getattr(figure, "legends", [])):
        legend.remove()

    fraction = float(layout.get("fraction", 0.5))
    placement, _threshold, requested_columns = paper_legend_settings(layout, fraction=fraction)
    # Matplotlib's default 4 pt label pad becomes conspicuous after paper font
    # compensation enlarges the labels. Keep both axis titles closer to their
    # tick labels across every paper-sized chart.
    for ax in figure.axes:
        ax.xaxis.labelpad = PAPER_AXIS_LABEL_PAD_PT
        ax.yaxis.labelpad = PAPER_AXIS_LABEL_PAD_PT
    has_legend = bool(style.legend and spec.show_legend)
    if not has_legend:
        if not _tight_layout(figure, pad=0.8, h_pad=0.8):
            figure.set_layout_engine(None)
            figure.subplots_adjust(left=0.16, right=0.96, bottom=0.18, top=0.94, hspace=0.5)
        return

    if placement == "inside":
        _finish_inside(figure, spec, style, requested_columns)
        return

    handles, labels = _unique_legend_items(figure.axes)
    for ax in figure.axes:
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()
    _finish_outside(figure, handles, labels, style, requested_columns, spec)
