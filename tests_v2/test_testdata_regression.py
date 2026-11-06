# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from cvanalysis.io.registry import load_files
from cvanalysis.plotting.export import render_plot, render_to_new_figure
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis


TESTDATA = Path(__file__).resolve().parents[1] / "testdata"


@pytest.mark.skipif(not TESTDATA.exists(), reason="testdata directory is not present")
def test_multi_cv_testdata_overlay_geometry():
    paths = sorted(str(path) for path in TESTDATA.glob("*_CV_*.txt"))[:9]
    if len(paths) < 2:
        pytest.skip("not enough CV testdata files")
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    assert len(dataset.cv_runs) == len(paths)
    style = BUILTIN_PRESETS["daily"]
    spec = PlotSpec("cv_overlay", [run.run_id for run in dataset.cv_runs])
    figure = Figure(figsize=style.figure_size, dpi=100)
    FigureCanvasAgg(figure)
    render_plot(figure, dataset, spec, style)
    ax = figure.axes[0]
    legend = ax.get_legend()
    assert legend is not None
    labels = [text.get_text() for text in legend.get_texts()]
    assert len(labels) == len(dataset.cv_runs)
    assert len(set(labels)) == len(labels)
    assert labels[0].startswith("#1 ")
    renderer = figure.canvas.get_renderer()
    bbox = legend.get_window_extent(renderer).transformed(figure.transFigure.inverted())
    assert bbox.x0 >= -0.01 and bbox.x1 <= 1.01
    assert bbox.y0 >= -0.01 and bbox.y1 <= 1.01
    figure.canvas.draw()
    xlabel = ax.xaxis.label.get_window_extent(renderer).transformed(
        figure.transFigure.inverted()
    )
    assert xlabel.y1 <= bbox.y0 + 0.005 or xlabel.y0 >= bbox.y1 - 0.005
    # A duplicated per-cycle legend used to squeeze this below 0.5.
    assert ax.get_position().width > 0.6


@pytest.mark.skipif(not TESTDATA.exists(), reason="testdata directory is not present")
def test_long_names_paper_outside_legend_keeps_all_entries():
    paths = sorted(str(path) for path in TESTDATA.glob("*_CV_*.txt"))[:9]
    if len(paths) < 2:
        pytest.skip("not enough CV testdata files")
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    layout = {
        "enabled": True,
        "fraction": 0.34,
        "text_width_mm": 160,
        "body_pt": 10,
    }
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id for run in dataset.cv_runs],
        paper_layout=layout,
    )
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    FigureCanvasAgg(figure)
    assert figure.legends
    legend = figure.legends[0]
    assert len(legend.get_texts()) == len(dataset.cv_runs)
    renderer = figure.canvas.get_renderer()
    bbox = legend.get_window_extent(renderer).transformed(figure.transFigure.inverted())
    assert bbox.x0 >= -0.01 and bbox.x1 <= 1.01
    assert bbox.y0 >= -0.01 and bbox.y1 <= 1.01
