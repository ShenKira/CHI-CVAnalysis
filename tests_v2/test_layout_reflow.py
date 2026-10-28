# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from cvanalysis.domain.models import Dataset, EISMetadata, EISRun
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.paper import finish_paper, paper_overrides
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


def _large_eis_run():
    frequency = np.logspace(5, -2, 80)
    z_real = np.linspace(5.0, 100000.0, frequency.size)
    z_imag = -np.linspace(100.0, 100000.0, frequency.size)
    return EISRun(
        run_id="eis_large",
        name="large_impedance",
        freq=frequency,
        z_real=z_real,
        z_imag=z_imag,
        z_mag=np.hypot(z_real, z_imag),
        phase=np.degrees(np.arctan2(z_imag, z_real)),
        metadata=EISMetadata(
            high_freq=float(frequency.max()), low_freq=float(frequency.min())
        ),
    )


def _paper_layout(fraction=0.33):
    return {
        "enabled": True,
        "fraction": fraction,
        "text_width_mm": 160.0,
        "body_pt": 10.0,
        "legend_placement": "auto",
        "legend_outside_threshold": 0.5,
        "legend_columns": "auto",
    }


def _paper_style(layout):
    style = BUILTIN_PRESETS["ieee-single"].with_overrides(
        {"figure_size": (3.2, 3.2)}
    )
    return style.with_overrides(paper_overrides(layout, style))


def _render(run, *, layout=None, show_legend=False):
    dataset = Dataset(eis_runs=[run])
    spec = PlotSpec(
        "eis_nyquist",
        [run.run_id],
        show_legend=show_legend,
        analysis_options={
            "unit_overrides": {"impedance": "Ω"},
            "axis_limits": {
                "main": {"x_min": -10.0, "x_max": 400.0, "y_min": 0.0, "y_max": 400.0}
            },
            "unified_xy_ticks": True,
        },
        paper_layout=layout or {},
    )
    style = BUILTIN_PRESETS["daily"] if layout is None else _paper_style(layout)
    figure = Figure(figsize=style.figure_size, dpi=100)
    figure.canvas = FigureCanvasAgg(figure)
    figure._paper_layout_enabled = bool(layout)
    warnings = render_plot(figure, dataset, spec, style)
    figure.canvas.draw()
    return figure, spec, style, warnings


def test_manual_limits_reflow_compacts_paper_left_margin():
    layout = _paper_layout()
    figure, spec, style, warnings = _render(_large_eis_run(), layout=layout)
    assert not warnings
    ax = figure.axes[0]
    renderer = figure.canvas.get_renderer()
    assert ax.get_position().x0 < 0.25
    assert figure.get_tightbbox(renderer).x0 < 0.20
    assert ax.get_xlim() == pytest.approx((-10.0, 400.0))
    assert ax.get_ylim() == pytest.approx((0.0, 400.0))


def test_manual_limits_reflow_compacts_daily_left_margin():
    figure, _spec, _style, warnings = _render(_large_eis_run())
    assert not warnings
    ax = figure.axes[0]
    renderer = figure.canvas.get_renderer()
    assert ax.get_position().x0 < 0.24
    assert figure.get_tightbbox(renderer).x0 < 0.30
    assert ax.get_xlim() == pytest.approx((-10.0, 400.0))


def test_paper_outside_legend_reflow_has_no_duplicates():
    layout = _paper_layout(fraction=0.33)
    figure, spec, style, _warnings = _render(
        _large_eis_run(), layout=layout, show_legend=True
    )
    assert len(figure.legends) == 1
    positions = [tuple(ax.get_position().bounds) for ax in figure.axes]

    finish_paper(figure, spec, style)
    figure.canvas.draw()
    assert len(figure.legends) == 1
    assert all(
        tuple(ax.get_position().bounds) == pytest.approx(before, abs=1e-6)
        for ax, before in zip(figure.axes, positions)
    )


def test_paper_inside_legend_reflow_has_no_duplicates():
    layout = _paper_layout(fraction=0.5)
    figure, spec, style, _warnings = _render(
        _large_eis_run(), layout=layout, show_legend=True
    )
    legends = [ax.get_legend() for ax in figure.axes]
    assert sum(legend is not None for legend in legends) == 1

    finish_paper(figure, spec, style)
    figure.canvas.draw()
    legends = [ax.get_legend() for ax in figure.axes]
    assert sum(legend is not None for legend in legends) == 1
