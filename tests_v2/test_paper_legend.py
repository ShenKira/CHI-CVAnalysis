from __future__ import annotations

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from cvanalysis.plotting.paper import finish_paper, paper_legend_settings, paper_overrides
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


def _paper_style(layout):
    base = BUILTIN_PRESETS["ieee-single"]
    return base.with_overrides(paper_overrides(layout, base))


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

