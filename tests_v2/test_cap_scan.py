# -*- coding: utf-8 -*-
"""Capacitance-vs-scan-rate fitting, options panel and paper rendering."""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.cv_renderer import draw_cap_scan
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


def test_cap_scan_linear_fit_and_independent_switches(synthetic_cv_runs):
    runs = synthetic_cv_runs
    for run in runs:
        run.summary.mean_capacitance_F = 2 * run.scan_rate + .5
    spec = PlotSpec(
        "cv_cap_scan",
        [r.run_id for r in runs],
        x_log=True,
        analysis_options={"fit_method": "linear", "error_bars": False},
    )
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    fit = next(line for line in ax.lines if line.get_label() == "Fitted Curve")
    assert ax.get_xscale() == "log"
    assert "mF" in ax.get_ylabel()
    assert np.polyfit(fit.get_xdata(), fit.get_ydata(), 1)[0] == pytest.approx(2000)
    np.testing.assert_allclose(fit.get_ydata(), 2000 * fit.get_xdata() + 500)
    assert not ax.containers[0].has_yerr
    spec.analysis_options["fit_line"] = False
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert not any(line.get_label() in {"Fitted Curve", "Fitted Line"} for line in figure.axes[0].lines)
    spec.analysis_options["fit_method"] = "none"
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert not any("R²" in t.get_text() for t in figure.axes[0].texts)


def test_cap_scan_power_fit_keeps_automatic_log_x_for_wide_rate_span(synthetic_cv_runs):
    runs = synthetic_cv_runs
    for run, rate in zip(runs, (.01, .2, .5)):
        run.metadata.scan_rate = rate
        run.summary = None
    spec = PlotSpec(
        "cv_cap_scan",
        [run.run_id for run in runs],
        analysis_options={"fit_method": "power"},
    )
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_xscale() == "log"


@pytest.mark.parametrize(
    ("x_scale", "y_scale"),
    [("linear", "linear"), ("log", "linear"), ("linear", "log"), ("log", "log")],
)
def test_coordinate_straight_fit_is_linear_in_selected_axes(
    synthetic_cv_runs, x_scale, y_scale
):
    runs = synthetic_cv_runs
    rates = (.01, .05, .5)
    values = (.001, .1, 1.0)
    for run, rate, value in zip(runs, rates, values):
        run.summary.scan_rate = rate
        run.summary.mean_capacitance_F = value
    spec = PlotSpec(
        "cv_cap_scan",
        [run.run_id for run in runs],
        analysis_options={
            "fit_method": "coordinate_line",
            "x_axis_scale": x_scale,
            "y_axis_scale": y_scale,
            "error_bars": False,
        },
    )
    figure = Figure()
    FigureCanvasAgg(figure)
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    figure.canvas.draw()
    fit = next(line for line in ax.lines if line.get_label() == "Fitted Line")
    rendered = ax.transData.transform(
        np.column_stack((fit.get_xdata(), fit.get_ydata()))
    )
    r2_screen = np.corrcoef(rendered[:, 0], rendered[:, 1])[0, 1] ** 2
    assert ax.get_xscale() == x_scale
    assert ax.get_yscale() == y_scale
    assert r2_screen == pytest.approx(1.0, abs=1e-10)


def test_cap_scan_auto_scales_update_in_options_panel(tmp_path, synthetic_cv_runs):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    runs = list(synthetic_cv_runs)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cv_runs=runs), [])
    window._request_plot("cv_cap_scan")
    panel = window.options_panel
    tab = window.tabs.currentWidget()
    auto_label = lambda control: control.itemText(control.findData("auto"))
    assert auto_label(panel.controls["x_axis_scale"]) == "自动（线性）"
    assert auto_label(panel.controls["y_axis_scale"]) == "自动（线性）"

    for run, rate, value in zip(runs, (.01, .5, 1.0), (.001, .1, 1.0)):
        run.summary.scan_rate = rate
        run.summary.mean_capacitance_F = value
    tab.redraw()
    assert auto_label(panel.controls["x_axis_scale"]) == "自动（对数）"
    assert auto_label(panel.controls["y_axis_scale"]) == "自动（对数）"
    window.close()
    app.processEvents()


def test_paper_cap_scan_keeps_standardized_fit_legend_label(synthetic_cv_runs):
    runs = synthetic_cv_runs
    spec = PlotSpec(
        "cv_cap_scan",
        [run.run_id for run in runs],
        paper_layout={"enabled": True, "fraction": .25, "text_width_mm": 160, "body_pt": 10},
        analysis_options={
            "fit_method": "coordinate_line",
            "x_axis_scale": "linear",
            "y_axis_scale": "linear",
        },
    )
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["ieee-single"])
    labels = [text.get_text() for text in figure.legends[0].get_texts()]
    assert "Fitted Line" in labels


def test_reusable_dialog_applies_to_current_plot_and_validates(
    tmp_path, synthetic_cv_runs
):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=synthetic_cv_runs), [])
    window._request_plot("cv_cap_scan")
    panel = window.options_panel
    tab = window.tabs.currentWidget()
    panel.controls["fit_method"].setCurrentIndex(
        panel.controls["fit_method"].findData("linear")
    )
    panel.controls["error_bars"].setChecked(False)
    panel.paper_enabled.setChecked(True)
    panel.fraction.setText("0/25")
    panel.legend_placement.setCurrentIndex(
        panel.legend_placement.findData("outside")
    )
    panel.legend_outside_threshold.setValue(.4)
    panel.legend_columns.setCurrentIndex(panel.legend_columns.findData(2))
    panel.apply()
    assert tab.spec.analysis_options == {
        "fit_method": "linear",
        "x_axis_scale": "auto",
        "y_axis_scale": "auto",
        "error_bars": False,
        "fit_line": True,
    }
    assert tab.spec.paper_layout["legend_placement"] == "outside"
    assert tab.spec.paper_layout["legend_outside_threshold"] == .4
    assert tab.spec.paper_layout["legend_columns"] == 2
    assert tab.style.figure_size == tab.base_style.figure_size
    assert not panel.isWindow()
    panel.fraction.setText("0")
    panel.apply()
    assert tab.spec.paper_layout["fraction"] == .25
    window._request_plot("cv_bvalue")
    assert window.options_panel is panel
    assert panel.tab is window.tabs.currentWidget()
    assert "fit_method" not in panel.controls
    window.close()
    app.processEvents()
