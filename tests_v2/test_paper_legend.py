from __future__ import annotations

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from cvanalysis.plotting.paper import finish_paper, paper_legend_settings, paper_linewidth_factor, paper_overrides
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


def _paper_style(layout):
    base = BUILTIN_PRESETS["ieee-single"]
    return base.with_overrides(paper_overrides(layout, base))


def test_paper_font_compensation_matrix():
    style = BUILTIN_PRESETS["daily"].with_overrides(
        {"figure_size": (160 / 25.4, 3.2)}
    )
    full = dict(enabled=True, text_width_mm=160, fraction=1, body_pt=10)
    baseline = paper_overrides(full, style)
    half = paper_overrides({**full, "fraction": .5}, style)
    quarter = paper_overrides({**full, "fraction": .25}, style)
    assert baseline["title_size"] == pytest.approx(10)
    assert half["title_size"] == pytest.approx(20)
    assert quarter["title_size"] == pytest.approx(32)
    assert half["annotation_size"] * .5 == pytest.approx(7.5)
    assert quarter["annotation_size"] * .25 == pytest.approx(6.0)
    custom = paper_overrides({**full, "fraction": .5, "body_pt": 12}, style)
    assert custom["annotation_size"] * .5 == pytest.approx(9)
    assert custom["xlabel_size"] * .5 == pytest.approx(10.8)

    base_layout = dict(enabled=True, text_width_mm=160, body_pt=10)
    below = paper_overrides({**base_layout, "fraction": .329}, style)
    at_boundary = paper_overrides({**base_layout, "fraction": .33}, style)
    below_scale = 160 * .329 / (style.figure_size[0] * 25.4)
    boundary_scale = 160 * .33 / (style.figure_size[0] * 25.4)
    assert below["title_size"] * below_scale == pytest.approx(8.0)
    assert below["xlabel_size"] * below_scale == pytest.approx(7.2)
    assert at_boundary["title_size"] * boundary_scale == pytest.approx(10.0)
    assert at_boundary["xlabel_size"] * boundary_scale == pytest.approx(9.0)


@pytest.mark.parametrize("fraction", [.5, .33, .25])
def test_paper_line_widths_follow_insertion_size(synthetic_cv_runs, fraction):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_plot, render_to_new_figure

    base = BUILTIN_PRESETS["daily"].with_overrides({
        "figure_size": (160 / 25.4, 3.2), "line_width": 1.6,
        "axes_linewidth": .8, "tick_width": .6, "grid_width": .4, "grid": True,
    })
    spec = PlotSpec("cv_cap_scan", [r.run_id for r in synthetic_cv_runs],
                    paper_layout={"enabled": True, "fraction": fraction, "text_width_mm": 160,
                                  "compensate_linewidths": True, "linewidth_mode": "full"})
    data = Dataset(cv_runs=synthetic_cv_runs)
    figure = render_to_new_figure(data, spec, base)
    ax = figure.axes[0]
    assert ax.lines[0].get_linewidth() * fraction == pytest.approx(1.6)
    assert ax.spines["left"].get_linewidth() * fraction == pytest.approx(.8)
    assert ax.xaxis.get_major_ticks()[0].tick1line.get_markeredgewidth() * fraction == pytest.approx(.6)
    assert ax.get_xgridlines()[0].get_linewidth() * fraction == pytest.approx(.4)
    assert ax.lines[0].get_markersize() == pytest.approx(max(4., base.marker_size + 2))
    widths = ax.collections[0].get_linewidths()
    assert widths.size and widths[0] * fraction == pytest.approx(1.6)
    # Render again on the same figure using the production pipeline.
    styled = base.with_overrides(paper_overrides(spec.paper_layout, base))
    render_plot(figure, data, spec, styled)
    assert figure.axes[0].lines[0].get_linewidth() * fraction == pytest.approx(1.6)


def test_paper_line_width_setting_is_saved_and_old_projects_default_off(synthetic_cv_runs, tmp_path):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_to_new_figure
    from cvanalysis.services.project_service import load_project, save_project

    base = BUILTIN_PRESETS["daily"]
    data = Dataset(cv_runs=synthetic_cv_runs)
    spec = PlotSpec("cv_overlay", [r.run_id for r in synthetic_cv_runs],
                    paper_layout={"enabled": True, "fraction": .25, "text_width_mm": 160})
    old = render_to_new_figure(data, spec, base)
    assert old.axes[0].lines[0].get_linewidth() == pytest.approx(base.line_width)
    spec.paper_layout["compensate_linewidths"] = True
    spec.paper_layout["linewidth_mode"] = "manual"
    spec.paper_layout["linewidth_coefficient"] = .72
    path = tmp_path / "paper.cvproj"
    save_project(path, data, plots=[spec])
    restored = load_project(path)
    assert restored.plots[0].paper_layout["compensate_linewidths"] is True
    assert restored.plots[0].paper_layout["linewidth_mode"] == "manual"
    assert restored.plots[0].paper_layout["linewidth_coefficient"] == pytest.approx(.72)
    assert spec.copy().paper_layout == spec.paper_layout


def test_compensation_preserves_auxiliary_strokes_in_svg(synthetic_eis_run):
    from cvanalysis.analysis.eis import analyze_eis
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_to_new_figure, render_svg_bytes

    base = BUILTIN_PRESETS["daily"].with_overrides({"figure_size": (160 / 25.4, 3.2)})
    data = Dataset(eis_runs=[synthetic_eis_run])
    metrics = {synthetic_eis_run.run_id: analyze_eis(synthetic_eis_run)}
    layout = {"enabled": True, "fraction": .25, "text_width_mm": 160,
              "compensate_linewidths": True, "linewidth_mode": "half"}
    spec = PlotSpec("eis_bode", [synthetic_eis_run.run_id], paper_layout=layout)
    figure = render_to_new_figure(data, spec, base, metrics=metrics)
    for ax in figure.axes:
        assert ax.lines[0].get_linewidth() == pytest.approx(base.line_width * .60 / .25)
        assert ax.lines[1].get_linewidth() == pytest.approx(.9 * .60 / .25)
        assert ax.spines["left"].get_linewidth() == pytest.approx(base.axes_linewidth * .60 / .25)
    data_bytes = render_svg_bytes(data, spec, base, metrics=metrics)
    assert b"<svg" in data_bytes
    assert b"stroke-width: 2.16" in data_bytes


@pytest.mark.parametrize("fraction,settings,expected", [
    (.5, {"linewidth_mode": "auto"}, 1.0),
    (.499, {"linewidth_mode": "auto"}, .60),
    (.33, {}, .60),
    (.25, {"linewidth_mode": "full"}, 1.0),
    (.5, {"linewidth_mode": "half"}, .60),
    (.33, {"linewidth_mode": "manual", "linewidth_coefficient": .45}, .45),
    (.33, {"linewidth_mode": "manual", "linewidth_coefficient": float("nan")}, .60),
])
def test_paper_linewidth_modes_at_insertion_size(fraction, settings, expected):
    base = BUILTIN_PRESETS["daily"].with_overrides({"figure_size": (160 / 25.4, 3.2)})
    layout = {"enabled": True, "fraction": fraction, "text_width_mm": 160,
              "compensate_linewidths": True, **settings}
    assert paper_linewidth_factor(layout, base) * fraction == pytest.approx(expected)
    assert paper_linewidth_factor({**layout, "compensate_linewidths": False}, base) == 1.0


def test_paper_export_dimensions_and_final_fonts(synthetic_cv_runs, tmp_path):
    from io import BytesIO

    from PIL import Image

    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import export_figure, render_to_new_figure

    style = BUILTIN_PRESETS["daily"]
    layout = dict(enabled=True, fraction=.5, text_width_mm=160, body_pt=10)
    overrides = paper_overrides(layout, style)
    scale = 160 * .5 / (style.figure_size[0] * 25.4)
    assert overrides["annotation_size"] * scale == pytest.approx(7.5)
    assert overrides["tick_size"] * scale == pytest.approx(8)
    spec = PlotSpec(
        "cv_cap_scan",
        [r.run_id for r in synthetic_cv_runs],
        paper_layout=layout,
    )
    figure = render_to_new_figure(Dataset(cv_runs=synthetic_cv_runs), spec, style)
    assert tuple(figure.get_size_inches()) == pytest.approx(style.figure_size)
    assert figure.axes[0].xaxis.label.get_fontsize() * scale == pytest.approx(9)
    assert paper_overrides(layout, style.with_overrides(overrides)) == overrides
    assert not overrides["save_bbox_inches"]
    output = BytesIO()
    figure.savefig(output, format="png", dpi=300)
    output.seek(0)
    with Image.open(output) as exported:
        assert exported.size == (
            round(style.figure_size[0] * 300),
            round(style.figure_size[1] * 300),
        )
    path = tmp_path / "paper.png"
    export_figure(figure, path, style)
    with Image.open(path) as exported:
        assert exported.size == (
            round(style.figure_size[0] * style.save_dpi),
            round(style.figure_size[1] * style.save_dpi),
        )
    with pytest.raises(ValueError):
        paper_overrides({**layout, "fraction": 0}, style)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(.49, "outside"), (.5, "inside"), (.51, "inside")],
)
def test_auto_paper_legend_threshold_is_strict(fraction, expected):
    layout = {"legend_placement": "auto", "legend_outside_threshold": .5}
    placement, threshold, columns = paper_legend_settings(layout, fraction=fraction)
    assert placement == expected
    assert threshold == .5
    assert columns == "auto"


def test_paper_legend_manual_placement_overrides_threshold():
    layout = {"legend_placement": "inside", "legend_outside_threshold": .9, "legend_columns": 2}
    placement, threshold, columns = paper_legend_settings(layout, fraction=.1)
    assert (placement, threshold, columns) == ("inside", .9, 2)
    layout["legend_placement"] = "outside"
    assert paper_legend_settings(layout, fraction=.99)[0] == "outside"


def test_single_axes_auto_columns_use_short_labels_and_reserve_tight_margin():
    layout = {"enabled": True, "fraction": .33, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "auto", "legend_outside_threshold": .5, "legend_columns": "auto"}
    style = _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot(111)
    for index, label in enumerate(("A", "B", "C")):
        ax.plot([0, 1], [index, index + 1], label=label)
    ax.legend(loc=style.legend_location)

    finish_paper(figure, PlotSpec("cv_overlay", paper_layout=layout), style)
    figure.canvas.draw()

    assert ax.get_legend() is None
    assert len(figure.legends) == 1
    legend = figure.legends[0]
    assert legend._ncols >= 2
    legend_bbox = legend.get_window_extent(figure.canvas.get_renderer()).transformed(figure.transFigure.inverted())
    assert legend_bbox.y1 < ax.get_position().y0
    xlabel_bbox = ax.xaxis.label.get_window_extent(figure.canvas.get_renderer()).transformed(figure.transFigure.inverted())
    assert xlabel_bbox.y0 > legend_bbox.y1
    assert ax.xaxis.labelpad == pytest.approx(2.0)
    assert ax.yaxis.labelpad == pytest.approx(2.0)
    assert ax.get_position().height > .25


def test_paper_contribution_chart_uses_compact_left_margin(synthetic_cv_runs):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_to_new_figure

    layout = {"enabled": True, "fraction": .33, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "outside", "legend_columns": "auto"}
    style = BUILTIN_PRESETS["ieee-single"].with_overrides({"figure_size": (3.2, 3.2)})
    spec = PlotSpec("cv_contribution_vs_rate", [run.run_id for run in synthetic_cv_runs], paper_layout=layout)
    figure = render_to_new_figure(Dataset(cv_runs=synthetic_cv_runs), spec, style)
    FigureCanvasAgg(figure)
    figure.canvas.draw()

    ylabel = figure.axes[0].yaxis.label.get_window_extent(figure.canvas.get_renderer())
    assert 0 < ylabel.x0 < figure.bbox.width * .08


def test_inside_position_honors_manual_columns():
    layout = {"enabled": True, "fraction": .5, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "inside", "legend_outside_threshold": .5, "legend_columns": 2}
    style = _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot(111)
    for index, label in enumerate(("Measured", "Fit", "Reference")):
        ax.plot([0, 1], [index, index + 1], label=label)
    ax.legend(loc=style.legend_location)

    finish_paper(figure, PlotSpec("cv_cap_scan", paper_layout=layout), style)

    assert not figure.legends
    assert ax.get_legend() is not None
    assert ax.get_legend()._ncols == 2


def test_multi_axes_external_legend_combines_unique_series_at_top():
    layout = {"enabled": True, "fraction": .33, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "outside", "legend_columns": "auto"}
    style = _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    upper = figure.add_subplot(211)
    lower = figure.add_subplot(212)
    for index, label in enumerate(("R1", "R1 fit", "R2", "R2 fit")):
        upper.plot([0, 1], [index, index + 1], label=label)
    lower.plot([1, 10], [0, 1], label="Real residual")
    lower.plot([1, 10], [1, 0], label="Imag residual")
    upper.legend(loc=style.legend_location)

    finish_paper(figure, PlotSpec("eis_fit", paper_layout=layout), style)
    figure.canvas.draw()

    assert all(ax.xaxis.labelpad == pytest.approx(2.0) for ax in figure.axes)
    assert all(ax.yaxis.labelpad == pytest.approx(2.0) for ax in figure.axes)
    assert upper.get_legend() is None
    assert lower.get_legend() is None
    assert len(figure.legends) == 1
    legend = figure.legends[0]
    labels = [text.get_text() for text in legend.get_texts()]
    assert labels == ["R1", "R1 fit", "R2", "R2 fit", "Real residual", "Imag residual"]
    bbox = legend.get_window_extent(figure.canvas.get_renderer()).transformed(figure.transFigure.inverted())
    assert bbox.x0 > max(ax.get_position().x1 for ax in figure.axes)


def test_inside_fit_plot_keeps_primary_legend_and_adds_residual_key():
    layout = {"enabled": True, "fraction": .5, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "inside", "legend_columns": "auto"}
    style = _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    upper = figure.add_subplot(211)
    lower = figure.add_subplot(212)
    upper.plot([0, 1], [0, 1], label="Measured")
    upper.plot([0, 1], [0, 1.1], label="Fit")
    lower.plot([1, 10], [0, 1], label="Real residual")
    lower.plot([1, 10], [1, 0], label="Imag residual")
    upper.legend(loc=style.legend_location)

    finish_paper(figure, PlotSpec("eis_fit", paper_layout=layout), style)

    assert not figure.legends
    assert upper.get_legend() is not None
    assert lower.get_legend() is not None
    assert [text.get_text() for text in lower.get_legend().get_texts()] == ["Real residual", "Imag residual"]


def test_small_external_fit_legend_keeps_large_ylabel_inside_canvas(synthetic_eis_run):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from cvanalysis.analysis.fitting import fit_eis_model
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_to_new_figure

    layout = {"enabled": True, "fraction": .25, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "auto", "legend_outside_threshold": .5}
    style = BUILTIN_PRESETS["ieee-single"]
    run = synthetic_eis_run
    fit = fit_eis_model(run.freq, run.z_real, run.z_imag, model="rct_c")
    figure = render_to_new_figure(
        Dataset(eis_runs=[run]),
        PlotSpec("eis_fit", [run.run_id], fit_enabled=True, paper_layout=layout),
        style,
        fits={run.run_id: fit},
    )
    FigureCanvasAgg(figure)
    figure.canvas.draw()

    ylabel = figure.axes[0].yaxis.label.get_window_extent(figure.canvas.get_renderer())
    assert ylabel.x0 >= 0


def test_bvalue_log_axis_hides_colliding_minor_labels(synthetic_cv_runs):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.export import render_to_new_figure

    layout = {"enabled": True, "fraction": .25, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "auto", "legend_outside_threshold": .5}
    style = BUILTIN_PRESETS["ieee-single"]
    figure = render_to_new_figure(
        Dataset(cv_runs=synthetic_cv_runs),
        PlotSpec("cv_bvalue", [run.run_id for run in synthetic_cv_runs], target_voltage=.5, paper_layout=layout),
        style,
    )
    FigureCanvasAgg(figure)
    figure.canvas.draw()

    minor_labels = [tick.get_text() for tick in figure.axes[0].get_xticklabels(minor=True) if tick.get_visible()]
    assert all(not label for label in minor_labels)

def test_auto_legend_columns_cache_reuses_result(monkeypatch):
    import cvanalysis.plotting.paper as paper

    layout = {"enabled": True, "fraction": .33, "text_width_mm": 160, "body_pt": 10,
              "legend_placement": "inside", "legend_columns": "auto"}
    style = _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot(111)
    for index, label in enumerate(("A", "B", "C", "D")):
        ax.plot([0, 1], [index, index + 1], label=label)
    handles, labels = ax.get_legend_handles_labels()

    calls = []
    original = paper._legend_bbox_in_figure

    def counted(fig, legend):
        calls.append(1)
        return original(fig, legend)

    monkeypatch.setattr(paper, "_legend_bbox_in_figure", counted)
    first = paper._choose_columns(figure, handles, labels, style, "auto", axis=ax)
    first_calls = len(calls)
    assert first_calls > 0

    second = paper._choose_columns(figure, handles, labels, style, "auto", axis=ax)
    assert second == first
    assert len(calls) == first_calls

    changed = paper._choose_columns(
        figure, handles + [handles[0]], labels + ["E"], style, "auto", axis=ax
    )
    assert len(calls) > first_calls
    assert changed >= 1
