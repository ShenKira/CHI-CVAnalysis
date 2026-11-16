"""Regression tests for legend suppression, reference labels and CP display units."""
import copy

import numpy as np
import pytest
from matplotlib.colors import same_color
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.cp_renderer import draw_cp_capacity
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.legend import preview_label, render_legend_template
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


@pytest.mark.parametrize("kind", ["cv_overlay", "cv_cap_scan", "cv_current_scan", "cv_bvalue",
    "cv_contribution", "cv_contribution_vs_rate", "cv_trasatti", "eis_nyquist", "eis_bode",
    "cp_gcd", "cp_capacity", "lsv_curve", "it_curve"])
def test_blank_legend_for_each_analysis(kind, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run):
    sweep_kind = "lsv" if kind == "lsv_curve" else "it"
    sweep = SweepRun("sweep", "sample", sweep_kind, np.array([0., 1., 2.]),
                     np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    data = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run],
                   cp_runs=[synthetic_cp_run], lsv_runs=[sweep] if sweep_kind == "lsv" else [],
                   it_runs=[sweep] if sweep_kind == "it" else [])
    runs = (data.cv_runs if kind.startswith("cv_") else data.eis_runs if kind.startswith("eis_")
            else data.cp_runs if kind.startswith("cp_") else [sweep])
    for run in runs:
        assert render_legend_template("{ }", run) == ("", [])
        assert preview_label(run, "{ }", fallback="fallback") == ("", [])
    spec = PlotSpec(kind, [r.run_id for r in runs], legend_templates={r.run_id: "{ }" for r in runs})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    if kind == "cp_capacity":
        assert fig.legends or any(ax.get_legend() is not None for ax in fig.axes)
    else:
        assert not fig.legends
        assert all(ax.get_legend() is None for ax in fig.axes)
    assert any(ax.lines or ax.patches or ax.collections for ax in fig.axes)


@pytest.mark.parametrize("kind", ["cv_overlay", "eis_nyquist", "eis_bode", "cp_gcd", "cp_capacity"])
def test_blank_legend_hides_only_its_run(kind, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run):
    first = synthetic_cv_runs[0] if kind.startswith("cv_") else synthetic_eis_run if kind.startswith("eis_") else synthetic_cp_run
    second = copy.deepcopy(first)
    second.run_id = "second"
    second.name = "visible run"
    data = Dataset(**({"cv_runs": [first, second]} if kind.startswith("cv_") else
                      {"eis_runs": [first, second]} if kind.startswith("eis_") else {"cp_runs": [first, second]}))
    spec = PlotSpec(kind, [first.run_id, second.run_id],
                    legend_templates={first.run_id: "{ }", second.run_id: "VISIBLE"})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    legends = [ax.get_legend() for ax in fig.axes if ax.get_legend()] + list(fig.legends)
    texts = [text.get_text() for legend in legends for text in legend.get_texts()]
    if kind == "cp_capacity":
        assert any("VISIBLE" in text for text in texts)
        assert any("VISIBLE" not in text for text in texts)
    else:
        assert texts and all("VISIBLE" in text for text in texts)
    assert sum(len(ax.lines) for ax in fig.axes) >= 2


def test_blank_legend_in_eis_fit_preserves_measured_and_fit_curves(synthetic_eis_run):
    from cvanalysis.analysis.fitting import fit_eis_model
    run = synthetic_eis_run
    fit = fit_eis_model(run.freq, run.z_real, run.z_imag, model="rct_c")
    spec = PlotSpec("eis_fit", [run.run_id], fit_enabled=True, legend_templates={run.run_id: "{ }"})
    fig = Figure()
    render_plot(fig, Dataset(eis_runs=[run]), spec, STYLE, fits={run.run_id: fit})
    assert len(fig.axes[0].lines) >= 2
    assert not fig.legends and all(ax.get_legend() is None for ax in fig.axes)


@pytest.mark.parametrize("kind", ["cv_overlay", "cv_cap_scan", "eis_fit", "cp_capacity"])
def test_blank_legend_is_not_rebuilt_by_paper_layout(kind, synthetic_cv_runs, synthetic_eis_run, synthetic_cp_run):
    from cvanalysis.analysis.fitting import fit_eis_model
    runs = (list(synthetic_cv_runs) if kind.startswith("cv_") else
            [synthetic_eis_run] if kind.startswith("eis_") else [synthetic_cp_run])
    data = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run], cp_runs=[synthetic_cp_run])
    spec = PlotSpec(kind, [run.run_id for run in runs], fit_enabled=True,
                    legend_templates={run.run_id: "{ }" for run in runs},
                    paper_layout={"enabled": True, "fraction": .34, "text_width_mm": 160, "body_pt": 10})
    fits = {}
    if kind == "eis_fit":
        run = synthetic_eis_run
        fits[run.run_id] = fit_eis_model(run.freq, run.z_real, run.z_imag, model="rct_c")
    fig = Figure()
    render_plot(fig, data, spec, STYLE, fits=fits)
    if kind == "cp_capacity":
        assert fig.legends or any(ax.get_legend() is not None for ax in fig.axes)
    else:
        assert not fig.legends and all(ax.get_legend() is None for ax in fig.axes)
    assert spec.show_legend


@pytest.mark.parametrize("mode,expected", [("time_current", "t=1 s, I=2e-06 A"),
                                             ("current", "I=2e-06 A"), ("custom", "reference point")])
def test_it_reference_annotation_modes(mode, expected):
    run = SweepRun("it", "sample", "it", np.array([0., 1., 2.]),
                   np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    spec = PlotSpec("it_curve", [run.run_id], analysis_options={"it_reference_time": 1,
                    "it_reference_label_mode": mode, "it_reference_label_text": "reference point"})
    fig = Figure()
    render_plot(fig, Dataset(it_runs=[run]), spec, STYLE)
    assert [text.get_text() for text in fig.axes[0].texts] == [expected]
    assert fig.axes[0].lines[1].get_ydata()[0] == pytest.approx(2e-6)


def test_it_custom_annotation_options_roundtrip(tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = SweepRun("it", "sample", "it", np.array([0., 1., 2.]),
                   np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    data = Dataset(it_runs=[run])
    tab = PlotTab(PlotSpec("it_curve", [run.run_id]), STYLE, data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    mode = panel.controls["it_reference_label_mode"]
    custom = panel.controls["it_reference_label_text"]
    assert not custom.isEnabled()
    mode.setCurrentIndex(mode.findData("custom"))
    assert custom.isEnabled()
    custom.setText("chosen point")
    panel.controls["it_reference_time"].setText("1")
    panel.apply()
    path = tmp_path / "it-reference.cvproj"
    save_project(path, data, plots=[tab.spec])
    restored = load_project(path)
    fig = Figure()
    render_plot(fig, restored.dataset, restored.plots[0], STYLE)
    assert [text.get_text() for text in fig.axes[0].texts] == ["chosen point"]
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("quantity,unit,factor", [("capacity", "nC", 1e9),
    ("capacity", "µAh", 1e3 / 3.6), ("capacitance", "nF", 1e9)])
def test_cp_units_apply_to_plot_and_manual_reference(synthetic_cp_run, quantity, unit, factor):
    run = synthetic_cp_run
    cycle = run.summary.cycles[0]
    expected = cycle.discharge_capacity_C * factor
    if quantity == "capacitance":
        expected /= abs(cycle.discharge.potential_V[-1] - cycle.discharge.potential_V[0])
    options = {"cp_quantity": quantity, "cp_display_unit": unit, "capacity_series": "discharge", "show_efficiency": False}
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options=options)
    fig = Figure()
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(expected)
    assert unit in fig.axes[0].get_ylabel()
    spec.analysis_options.update(capacity_percent_mode="manual", capacity_percent_reference=expected)
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)


def test_cp_efficiency_has_a_different_default_color(synthetic_cp_run):
    run = synthetic_cp_run
    fig = Figure()
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), PlotSpec("cp_capacity", [run.run_id]), STYLE)
    assert fig.axes[0].lines and fig.axes[1].lines
    assert not same_color(fig.axes[0].lines[0].get_color(), fig.axes[1].lines[0].get_color())


@pytest.mark.parametrize("normalization,divisor,suffix", [("area", 2., "/cm²"), ("mass", .004, "/g")])
def test_normalized_cp_units_and_reference(synthetic_cp_run, normalization, divisor, suffix):
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    run = synthetic_cp_run
    run.params.area_cm2 = 2.
    run.params.mass_mg = 4.
    data = Dataset(cp_runs=[run])
    refresh_analysis(data, AnalysisSettings(), force=True)
    expected = run.summary.cycles[0].discharge_capacity_C * 1e9 / divisor
    spec = PlotSpec("cp_capacity", [run.run_id], normalization=normalization, analysis_options={
        "cp_display_unit": "nC" + suffix, "capacity_series": "discharge", "show_efficiency": False})
    fig = Figure()
    draw_cp_capacity(fig, data, spec, STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(expected)
    assert "nC" + suffix in fig.axes[0].get_ylabel()
    spec.analysis_options.update(capacity_percent_mode="manual", capacity_percent_reference=expected)
    draw_cp_capacity(fig, data, spec, STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)


def test_incompatible_manual_unit_does_not_silently_compute(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"cp_quantity": "capacitance",
        "cp_display_unit": "nC", "capacity_percent_mode": "manual", "capacity_percent_reference": 2})
    fig = Figure()
    warnings = draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, STYLE)
    assert warnings and not fig.axes[0].lines


def test_cp_axis_limits_follow_unit_change(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "cp_display_unit": "nC", "show_efficiency": False,
        "axis_limits": {"capacity": {"y_min": 0, "y_max": 0.001}},
        "axis_limit_units": {"capacity": {"y": {"label": "mAh", "factor": 1}}},
    })
    fig = Figure()
    render_plot(fig, Dataset(cp_runs=[run]), spec, STYLE)
    assert fig.axes[0].get_ylim() == pytest.approx((0, 3.6e6))


def test_changing_cp_quantity_requires_reference_confirmation(synthetic_cp_run):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    tab = PlotTab(PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "cp_quantity": "capacity", "capacity_percent_mode": "manual", "capacity_percent_reference": 1}),
        STYLE, Dataset(cp_runs=[run]))
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    quantity = panel.controls["cp_quantity"]
    quantity.setCurrentIndex(quantity.findData("capacitance"))
    panel.apply()
    assert panel.error.text()
    assert tab.spec.analysis_options["cp_quantity"] == "capacity"
    panel.controls["capacity_percent_reference"].textEdited.emit("1")
    panel.apply()
    assert tab.spec.analysis_options["cp_quantity"] == "capacitance"
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_cp_unit_change_preserves_reference_and_roundtrips(synthetic_cp_run, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    data = Dataset(cp_runs=[run])
    tab = PlotTab(PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "cp_display_unit": "nC", "capacity_percent_mode": "manual", "capacity_percent_reference": 1000}), STYLE, data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    combo = panel.controls["cp_display_unit"]
    combo.setCurrentIndex(combo.findData("µC"))
    assert float(panel.controls["capacity_percent_reference"].text()) == pytest.approx(1)
    panel.apply()
    assert tab.spec.analysis_options["cp_display_unit"] == "µC"
    assert tab.spec.analysis_options["capacity_percent_reference"] == pytest.approx(1)
    path = tmp_path / "units.cvproj"
    save_project(path, data, plots=[tab.spec])
    restored = load_project(path).plots[0]
    assert restored.analysis_options["cp_display_unit"] == "µC"
    assert restored.analysis_options["capacity_percent_reference"] == pytest.approx(1)
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()
