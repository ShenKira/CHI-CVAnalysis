# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from matplotlib.figure import Figure

from cvanalysis.domain.models import Dataset, EISMetadata, EISRun, ElectrodeParams
from cvanalysis.plotting.axis_limits import plot_axis_specs
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.paper import finish_paper, paper_overrides
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import fit_eis_runs


ALL_KINDS = (
    "cv_overlay",
    "cv_cap_scan",
    "cv_current_scan",
    "cv_bvalue",
    "cv_contribution",
    "cv_contribution_vs_rate",
    "cv_trasatti",
    "eis_nyquist",
    "eis_bode",
    "eis_fit",
    "cp_gcd",
    "cp_capacity",
)


def _dataset(synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run):
    synthetic_cp_run.params = ElectrodeParams(area_cm2=1.0, mass_mg=1.0)
    return Dataset(
        cv_runs=list(synthetic_cv_runs),
        eis_runs=[synthetic_eis_run],
        cp_runs=[synthetic_cp_run],
    )


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_axis_limits_apply_to_every_plot_kind(
    kind, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run
):
    dataset = _dataset(synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run)
    fits = fit_eis_runs(dataset, [synthetic_eis_run.run_id], model="rct_c")
    specs = plot_axis_specs(kind)
    limits = {}
    for spec in specs:
        entry = {}
        if spec.editable_x:
            entry["x_min"] = 0.2
            entry["x_max"] = 20.0
        if spec.editable_y:
            entry["y_min"] = 0.2
            entry["y_max"] = 20.0
        limits[spec.key] = entry
    run_ids = [
        run.run_id
        for run in (
            dataset.cv_runs
            if kind.startswith("cv_")
            else dataset.eis_runs
            if kind.startswith("eis_")
            else dataset.cp_runs
        )
    ]
    plot = PlotSpec(kind, run_ids, analysis_options={"axis_limits": limits})
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(
        figure,
        dataset,
        plot,
        BUILTIN_PRESETS["daily"],
        fits=fits,
    )
    assert not [warning for warning in warnings if "轴范围" in warning]
    for spec in plot_axis_specs(kind, figure):
        if spec.index >= len(figure.axes):
            continue
        axis = figure.axes[spec.index]
        if spec.editable_x:
            assert axis.get_xlim() == pytest.approx((0.2, 20.0))
        if spec.editable_y:
            assert axis.get_ylim() == pytest.approx((0.2, 20.0))


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_manual_limits_layout_is_stable_for_every_plot_kind(
    kind, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run
):
    dataset = _dataset(synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run)
    fits = fit_eis_runs(dataset, [synthetic_eis_run.run_id], model="rct_c")
    specs = plot_axis_specs(kind)
    limits = {}
    for axis_spec in specs:
        entry = {}
        if axis_spec.editable_x:
            entry["x_min"] = 0.2
            entry["x_max"] = 20.0
        if axis_spec.editable_y:
            entry["y_min"] = 0.2
            entry["y_max"] = 20.0
        limits[axis_spec.key] = entry
    run_ids = [
        run.run_id
        for run in (
            dataset.cv_runs
            if kind.startswith("cv_")
            else dataset.eis_runs
            if kind.startswith("eis_")
            else dataset.cp_runs
        )
    ]
    paper = {
        "enabled": True,
        "fraction": 0.33,
        "text_width_mm": 160.0,
        "body_pt": 10.0,
        "legend_placement": "auto",
        "legend_outside_threshold": 0.5,
        "legend_columns": "auto",
    }
    base = BUILTIN_PRESETS["ieee-single"]
    style = base.with_overrides(paper_overrides(paper, base))
    plot = PlotSpec(
        kind,
        run_ids,
        show_legend=False,
        analysis_options={"axis_limits": limits},
        paper_layout=paper,
    )
    figure = Figure(figsize=style.figure_size, dpi=100)
    figure._paper_layout_enabled = True
    render_plot(figure, dataset, plot, style, fits=fits)
    figure.canvas.draw()
    before = [tuple(axis.get_position().bounds) for axis in figure.axes]
    finish_paper(figure, plot, style)
    figure.canvas.draw()
    for axis, expected in zip(figure.axes, before):
        assert tuple(axis.get_position().bounds) == pytest.approx(
            expected, abs=1e-6
        )


def test_nyquist_balanced_data_keeps_equal_aspect(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec("eis_nyquist", [synthetic_eis_run.run_id])
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    figure.canvas.draw()
    assert figure.axes[0].get_aspect() == 1.0


def test_nyquist_manual_limits_override_equal_aspect(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        analysis_options={
            "axis_limits": {"main": {"y_min": 0.0, "y_max": 1000.0}}
        },
    )
    figure = Figure(figsize=(3.2, 3.2))
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    figure.canvas.draw()
    axis = figure.axes[0]
    assert not [warning for warning in warnings if "轴范围" in warning]
    assert axis.get_ylim() == pytest.approx((0.0, 1000.0))
    assert axis.get_aspect() == "auto"
    # Auto X must follow the data, not expand to the forced equal-aspect span.
    assert axis.get_xlim()[1] - axis.get_xlim()[0] < 300.0


def test_nyquist_extreme_span_uses_independent_auto_ranges():
    frequency = np.logspace(5, 6, 30)
    z_real = np.linspace(2.0, 132.0, frequency.size)
    z_imag = -np.linspace(88.0, 922.0, frequency.size)
    run = EISRun(
        run_id="eis_extreme",
        name="extreme_hf",
        freq=frequency,
        z_real=z_real,
        z_imag=z_imag,
        z_mag=np.hypot(z_real, z_imag),
        phase=np.degrees(np.arctan2(z_imag, z_real)),
        metadata=EISMetadata(high_freq=float(frequency.max()), low_freq=float(frequency.min())),
    )
    spec = PlotSpec("eis_nyquist", [run.run_id])
    figure = Figure(figsize=(3.2, 3.2))
    render_plot(figure, Dataset(eis_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    figure.canvas.draw()
    axis = figure.axes[0]
    assert axis.get_aspect() == "auto"
    x_span = axis.get_xlim()[1] - axis.get_xlim()[0]
    y_span = axis.get_ylim()[1] - axis.get_ylim()[0]
    assert x_span < 300.0
    assert y_span > 700.0


def test_log_axis_limits_reject_non_positive_values(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec(
        "eis_bode",
        [synthetic_eis_run.run_id],
        analysis_options={
            "axis_limits": {
                "phase": {"x_min": 0.0, "x_max": 10.0},
                "magnitude": {"y_min": -1.0, "y_max": 10.0},
            }
        },
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert any("对数" in warning for warning in warnings)
    # The invalid sides are ignored instead of crashing or creating inverted axes.
    assert figure.axes[0].get_xlim()[0] > 0
    assert figure.axes[1].get_ylim()[0] > 0


def test_axis_limit_ui_sections_and_apply(
    tmp_path, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run
):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(
        _dataset(synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run), []
    )
    app.processEvents()

    window._request_plot("cv_overlay")
    app.processEvents()
    assert set(window.options_panel.axis_controls) == {"main"}

    window._request_plot("eis_bode")
    app.processEvents()
    assert set(window.options_panel.axis_controls) == {"phase", "magnitude"}
    phase = window.options_panel.axis_controls["phase"]
    phase["x_min"].setText("0.2")
    phase["x_max"].setText("20")
    phase["y_min"].setText("-45")
    phase["y_max"].setText("45")
    magnitude = window.options_panel.axis_controls["magnitude"]
    magnitude["x_min"].setText("0.5")
    magnitude["x_max"].setText("50")
    magnitude["y_min"].setText("0.1")
    magnitude["y_max"].setText("100")
    window.options_panel.apply()
    tab = window.tabs.currentWidget()
    assert window.options_panel.error.text() == "已应用"
    assert tab.spec.analysis_options["axis_limits"]["phase"]["x_min"] == 0.2
    assert tab.figure.axes[0].get_xlim() == pytest.approx((0.2, 20.0))
    assert tab.figure.axes[0].get_ylim() == pytest.approx((-45.0, 45.0))
    assert tab.figure.axes[1].get_xlim() == pytest.approx((0.5, 50.0))
    assert tab.figure.axes[1].get_ylim() == pytest.approx((0.1, 100.0))

    window._request_plot("cp_capacity")
    app.processEvents()
    assert set(window.options_panel.axis_controls) == {"capacity", "efficiency"}
    capacity = window.options_panel.axis_controls["capacity"]
    efficiency = window.options_panel.axis_controls["efficiency"]
    assert "x_min" not in efficiency
    capacity["y_min"].setText("0.001")
    capacity["y_max"].setText("0.02")
    efficiency["y_min"].setText("50")
    efficiency["y_max"].setText("100")
    window.options_panel.apply()
    tab = window.tabs.currentWidget()
    assert tab.figure.axes[0].get_ylim() == pytest.approx((0.001, 0.02))
    assert tab.figure.axes[1].get_ylim() == pytest.approx((50.0, 100.0))

    window._request_plot("eis_bode")
    app.processEvents()
    window.options_panel.axis_controls["phase"]["x_min"].setText("0")
    window.options_panel.axis_controls["phase"]["x_max"].setText("10")
    before = dict(window.tabs.currentWidget().spec.analysis_options.get("axis_limits", {}))
    window.options_panel.apply()
    assert "正数" in window.options_panel.error.text()
    after = window.tabs.currentWidget().spec.analysis_options.get("axis_limits", {})
    assert after == before
    window.close()


def test_nyquist_axis_limit_ui_disables_equal_aspect(tmp_path, synthetic_eis_run):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(eis_runs=[synthetic_eis_run]), [])
    app.processEvents()
    window._request_plot("eis_nyquist")
    app.processEvents()
    assert set(window.options_panel.axis_controls) == {"main"}
    main = window.options_panel.axis_controls["main"]
    main["y_min"].setText("0")
    main["y_max"].setText("1000")
    window.options_panel.apply()
    tab = window.tabs.currentWidget()
    assert window.options_panel.error.text() == "已应用"
    axis = tab.figure.axes[0]
    assert axis.get_ylim() == pytest.approx((0.0, 1000.0))
    assert axis.get_aspect() == "auto"
    assert axis.get_xlim()[1] - axis.get_xlim()[0] < 300.0
    window.close()


def test_axis_limits_project_round_trip(tmp_path, synthetic_cv_runs):
    from cvanalysis.services.project_service import load_project, save_project

    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id for run in synthetic_cv_runs],
        analysis_options={"axis_limits": {"main": {"x_min": -0.2, "x_max": 1.2}}},
    )
    path = tmp_path / "axis-limits.cvproj"
    save_project(path, dataset, plots=[spec])
    state = load_project(path)
    assert state.plots[0].analysis_options["axis_limits"]["main"]["x_min"] == -0.2
    assert state.plots[0].analysis_options["axis_limits"]["main"]["x_max"] == 1.2
