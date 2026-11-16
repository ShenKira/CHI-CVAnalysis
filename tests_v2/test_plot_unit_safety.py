"""Physical units, persisted manual ranges and display-unit transitions."""
import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.analysis.fitting import fit_eis_model
from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.axis_limits import axis_display_units
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


@pytest.mark.parametrize("normalization,area,unit,scale", [
    ("none", None, "Ω", 1.), ("area", 2., "Ω·cm²", 2.),
    ("area", .5, "kΩ·cm²", .5e-3),
])
def test_eis_fit_residual_uses_same_area_and_prefix_as_plot(synthetic_eis_run, normalization, area, unit, scale):
    run = synthetic_eis_run
    run.params.area_cm2 = area
    fit = fit_eis_model(run.freq, run.z_real, run.z_imag, model="rct_c")
    original = fit.residual_real.copy()
    spec = PlotSpec("eis_fit", [run.run_id], normalization=normalization,
                    analysis_options={"unit_overrides": {"impedance": unit}})
    fig = Figure()
    render_plot(fig, Dataset(eis_runs=[run]), spec, STYLE, fits={run.run_id: fit})
    assert unit in fig.axes[1].get_ylabel()
    np.testing.assert_allclose(fig.axes[1].lines[0].get_ydata(), fit.residual_real * scale)
    np.testing.assert_allclose(fig.axes[1].lines[1].get_ydata(), fit.residual_imag * scale)
    np.testing.assert_array_equal(original, fit.residual_real)


def test_cp_percentage_transition_clears_only_left_y_range(synthetic_cp_run):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"cp_display_unit": "µAh", "show_efficiency": False,
        "axis_limits": {"capacity": {"x_min": .5, "x_max": 3, "y_min": 0, "y_max": 1}}})
    tab = PlotTab(spec, STYLE, Dataset(cp_runs=[run]))
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    mode = panel.controls["capacity_percent_mode"]
    mode.setCurrentIndex(mode.findData("cycle"))
    panel.controls["capacity_percent_cycle"].setText("1")
    panel.apply()
    entry = spec.analysis_options["axis_limits"]["capacity"]
    assert entry == {"x_min": .5, "x_max": 3.}
    assert panel.axis_controls["capacity"]["y_max"].text() == ""
    assert tab.figure.axes[0].get_ylim()[1] >= 100
    panel.axis_controls["capacity"]["y_min"].setText("80")
    panel.axis_controls["capacity"]["y_max"].setText("120")
    panel.apply()
    mode.setCurrentIndex(mode.findData("absolute"))
    panel.apply()
    assert spec.analysis_options["axis_limits"]["capacity"] == {"x_min": .5, "x_max": 3.}
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("kind,old_unit,new_unit,ratio", [
    ("cv_cap_scan", "µF", "mF", .001),
    ("cv_trasatti", "µC", "mC", .001),
])
def test_capacitance_and_charge_ranges_follow_unit_changes(synthetic_cv_runs, kind, old_unit, new_unit, ratio):
    runs = list(synthetic_cv_runs)
    data = Dataset(cv_runs=runs)
    key = "capacitance" if kind == "cv_cap_scan" else "charge"
    spec = PlotSpec(kind, [run.run_id for run in runs], analysis_options={
        "unit_overrides": {key: old_unit}, "axis_limits": {"main": {"y_min": 0., "y_max": 100.}}})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    assert old_unit in fig.axes[0].get_ylabel()
    spec.analysis_options["unit_overrides"][key] = new_unit
    render_plot(fig, data, spec, STYLE)
    assert new_unit in fig.axes[0].get_ylabel()
    assert fig.axes[0].get_ylim() == pytest.approx((0., 100 * ratio))
    assert spec.analysis_options["axis_limits"]["main"]["y_max"] == pytest.approx(100 * ratio)


def test_cv_automatic_capacitance_prefix_converts_existing_limits(synthetic_cv_runs):
    runs = list(synthetic_cv_runs)
    spec = PlotSpec("cv_cap_scan", [run.run_id for run in runs],
                    analysis_options={"axis_limits": {"main": {"y_min": 0., "y_max": 100.}}})
    data = Dataset(cv_runs=runs)
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    old_unit, old_factor = axis_display_units(fig.axes[0])["y"]
    for run in runs:
        run.summary.mean_capacitance_F *= 1000
        run.summary.sd_capacitance_F *= 1000
        for cycle in run.cycles:
            cycle.capacitance_F *= 1000
    render_plot(fig, data, spec, STYLE)
    new_unit, new_factor = axis_display_units(fig.axes[0])["y"]
    assert old_unit != new_unit
    assert fig.axes[0].get_ylim() == pytest.approx((0, 100 * new_factor / old_factor))


@pytest.mark.parametrize("method,field", [("power", "annotation.cv_cap_scan.equation_power"),
                                           ("coordinate_line", "annotation.cv_cap_scan.equation_coordinate")])
def test_fit_text_template_can_reference_current_unit(synthetic_cv_runs, method, field):
    runs = list(synthetic_cv_runs)
    spec = PlotSpec("cv_cap_scan", [run.run_id for run in runs], analysis_options={
        "fit_method": method, "unit_overrides": {"capacitance": "nF"}})
    fig = Figure()
    render_plot(fig, Dataset(cv_runs=runs), spec, STYLE, text_values={field: "Unit: {unit}"})
    assert any("Unit: nF" in text.get_text() for text in fig.axes[0].texts)


def test_legacy_range_kept_then_cleared_when_normalization_changes(synthetic_cv_runs):
    runs = list(synthetic_cv_runs)
    for run in runs:
        run.params.area_cm2 = 2.
    spec = PlotSpec("cv_overlay", [run.run_id for run in runs], analysis_options={
        "axis_limits": {"main": {"x_min": 0., "x_max": 1., "y_min": -2., "y_max": 2.}}})
    fig = Figure()
    data = Dataset(cv_runs=runs)
    render_plot(fig, data, spec, STYLE)
    assert fig.axes[0].get_ylim() == pytest.approx((-2, 2))
    spec.normalization = "area"
    warnings = render_plot(fig, data, spec, STYLE)
    assert spec.analysis_options["axis_limits"]["main"] == {"x_min": 0., "x_max": 1.}
    assert any("清空" in warning for warning in warnings)


@pytest.mark.parametrize("bad_factor", [0, 123.])
def test_bad_limit_unit_metadata_clears_instead_of_guessing(synthetic_cv_runs, bad_factor):
    runs = list(synthetic_cv_runs)
    spec = PlotSpec("cv_cap_scan", [run.run_id for run in runs], analysis_options={
        "axis_limits": {"main": {"x_max": 1., "y_min": 0., "y_max": 100.}},
        "axis_limit_units": {"main": {"y": {"label": "µF", "factor": bad_factor}}}})
    fig = Figure()
    warnings = render_plot(fig, Dataset(cv_runs=runs), spec, STYLE)
    assert spec.analysis_options["axis_limits"]["main"] == {"x_max": 1.}
    assert any("清空" in warning for warning in warnings)


def test_copy_keeps_unit_and_range_updates_independent(synthetic_cv_runs):
    runs = list(synthetic_cv_runs)
    original = PlotSpec("cv_cap_scan", [run.run_id for run in runs], analysis_options={
        "unit_overrides": {"capacitance": "µF"}, "axis_limits": {"main": {"y_min": 0., "y_max": 100.}}})
    fig = Figure()
    data = Dataset(cv_runs=runs)
    render_plot(fig, data, original, STYLE)
    duplicate = original.copy()
    duplicate.analysis_options["unit_overrides"]["capacitance"] = "mF"
    render_plot(fig, data, duplicate, STYLE)
    assert duplicate.analysis_options["axis_limits"]["main"]["y_max"] == pytest.approx(.1)
    assert original.analysis_options["axis_limits"]["main"]["y_max"] == pytest.approx(100.)
    assert original.analysis_options["unit_overrides"]["capacitance"] == "µF"


def test_cp_capacity_and_capacitance_do_not_convert_each_others_limits(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"show_efficiency": False,
        "axis_limits": {"capacity": {"y_min": 0., "y_max": 1.}}})
    fig = Figure()
    data = Dataset(cp_runs=[run])
    render_plot(fig, data, spec, STYLE)
    spec.analysis_options.update(cp_quantity="capacitance", cp_display_unit="nF")
    warnings = render_plot(fig, data, spec, STYLE)
    assert "axis_limits" not in spec.analysis_options
    assert any("清空" in warning for warning in warnings)


def test_legacy_percentage_limits_are_preserved_and_gain_quantity_metadata(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"show_efficiency": False,
        "capacity_percent_mode": "cycle", "capacity_percent_cycle": 1,
        "axis_limits": {"capacity": {"y_min": 80., "y_max": 120.}},
        "axis_limit_units": {"capacity": {"y": {"label": "%", "factor": 1.}}}})
    fig = Figure()
    render_plot(fig, Dataset(cp_runs=[run]), spec, STYLE)
    assert fig.axes[0].get_ylim() == pytest.approx((80., 120.))
    assert spec.analysis_options["axis_limit_units"]["capacity"]["y"]["dimension"] == "cp_capacity_none_percentage"


def test_sweep_axis_unit_and_reference_can_follow_axis():
    run = SweepRun("it", "sample", "it", np.array([0., 1., 2.]),
                   np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    data = Dataset(it_runs=[run])
    spec = PlotSpec("it_curve", [run.run_id], analysis_options={"it_reference_time": 1.,
        "unit_overrides": {"current": "auto"}, "it_reference_current_unit": "axis",
        "axis_labels": {"main": {"x": "Time [{unit}]", "y": "I [{unit}]"}}})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    assert fig.axes[0].get_xlabel() == "Time [s]"
    assert fig.axes[0].get_ylabel() == "I [µA]"
    assert fig.axes[0].lines[0].get_ydata()[1] == pytest.approx(2.)
    assert fig.axes[0].texts[0].get_text() == "t=1 s, I=2 µA"
    spec.analysis_options["unit_overrides"]["current"] = "nA"
    render_plot(fig, data, spec, STYLE)
    assert fig.axes[0].get_ylabel() == "I [nA]"
    assert fig.axes[0].texts[0].get_text() == "t=1 s, I=2000 nA"
    assert fig.axes[0].lines[0].get_ydata()[1] == pytest.approx(2000.)


def test_new_sweep_defaults_to_auto_and_old_graph_retains_raw_unit(tmp_path):
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    run = SweepRun("it", "sample", "it", np.array([0., 1., 2.]),
                   np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    data = Dataset(it_runs=[run])
    old = PlotSpec("it_curve", [run.run_id], analysis_options={"it_reference_time": 1})
    fig = Figure()
    render_plot(fig, data, old, STYLE)
    assert fig.axes[0].get_ylabel() == "Current (A)"
    assert fig.axes[0].lines[0].get_ydata()[1] == pytest.approx(2e-6)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(data, [])
    window._request_plot("it_curve", run_ids=[run.run_id])
    app.processEvents()
    tab = window._active_plot_tab()
    assert tab.spec.analysis_options["unit_overrides"]["current"] == "auto"
    assert tab.figure.axes[0].get_ylabel() == "Current (µA)"
    assert window.options_panel.controls["it_reference_current_unit"].currentData() == "axis"
    window._mark_clean()
    window.close()
    app.processEvents()


def test_cp_auto_unit_keeps_manual_reference_physical_value(synthetic_cp_run):
    from cvanalysis.analysis.cp import analyze_cp_run
    run = synthetic_cp_run
    data = Dataset(cp_runs=[run])
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"cp_display_unit": "auto",
        "capacity_series": "discharge", "show_efficiency": False})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    original_unit, original_factor = fig.axes[0]._cv_cp_physical_unit
    initial_value = float(fig.axes[0].lines[0].get_ydata()[0])
    spec.analysis_options.update(capacity_percent_mode="manual", capacity_percent_reference=initial_value,
                                 capacity_percent_reference_unit=original_unit)
    warnings = render_plot(fig, data, spec, STYLE)
    assert fig.axes[0].lines, (warnings, original_unit, initial_value, spec.analysis_options)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100.)
    run.metadata.cathodic_current_A *= 1000
    run.metadata.anodic_current_A *= 1000
    analyze_cp_run(run, force=True)
    render_plot(fig, data, spec, STYLE)
    assert fig.axes[0]._cv_cp_physical_unit[1] != original_factor
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100000.)


def test_legacy_cp_reference_cannot_silently_cross_normalizations(synthetic_cp_run):
    run = synthetic_cp_run
    run.params.area_cm2 = 2.
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"show_efficiency": False,
        "capacity_percent_mode": "manual", "capacity_percent_reference": 1.})
    fig = Figure()
    data = Dataset(cp_runs=[run])
    render_plot(fig, data, spec, STYLE)
    assert spec.analysis_options["capacity_percent_reference_unit"] == "mAh"
    spec.normalization = "area"
    warnings = render_plot(fig, data, spec, STYLE)
    assert not fig.axes[0].lines
    assert any("参考值单位" in warning for warning in warnings)


def test_auto_capacitance_reference_and_template_with_area(synthetic_cp_run):
    from cvanalysis.analysis.cp import analyze_cp_run
    run = synthetic_cp_run
    run.params.area_cm2 = 2.
    analyze_cp_run(run, force=True)
    data = Dataset(cp_runs=[run])
    spec = PlotSpec("cp_capacity", [run.run_id], normalization="area", analysis_options={
        "cp_quantity": "capacitance", "cp_display_unit": "auto", "capacity_series": "discharge",
        "show_efficiency": False, "axis_labels": {"capacity": {"y": "Capacitance [{unit}]"}}})
    fig = Figure()
    render_plot(fig, data, spec, STYLE)
    unit, _factor = fig.axes[0]._cv_cp_physical_unit
    reference = float(fig.axes[0].lines[0].get_ydata()[0])
    assert unit.endswith("/cm²")
    assert fig.axes[0].get_ylabel() == f"Capacitance [{unit}]"
    spec.analysis_options.update(capacity_percent_mode="manual", capacity_percent_reference=reference,
                                 capacity_percent_reference_unit=unit)
    render_plot(fig, data, spec, STYLE)
    assert fig.axes[0].get_ylabel() == "Capacitance [%]"
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100.)


def test_cp_auto_reference_is_converted_in_panel_and_project(synthetic_cp_run, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    data = Dataset(cp_runs=[run])
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"cp_display_unit": "nC",
        "capacity_percent_mode": "manual", "capacity_percent_reference": 1000., "show_efficiency": False})
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    combo = panel.controls["cp_display_unit"]
    combo.setCurrentIndex(combo.findData("auto"))
    selected = panel._cp_reference_unit_state["unit"]
    assert selected != "auto"
    converted = float(panel.controls["capacity_percent_reference"].text())
    panel.apply()
    assert spec.analysis_options["cp_display_unit"] == "auto"
    assert spec.analysis_options["capacity_percent_reference_unit"] == selected
    assert spec.analysis_options["capacity_percent_reference"] == pytest.approx(converted)
    path = tmp_path / "auto-unit.cvproj"
    save_project(path, data, plots=[spec])
    restored = load_project(path).plots[0]
    assert restored.analysis_options["capacity_percent_reference_unit"] == selected
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_normalization_change_clears_unsaved_y_range_in_active_panel(synthetic_cp_run, tmp_path):
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    run.params.area_cm2 = 2.
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cp_runs=[run]), [])
    window._request_plot("cp_capacity")
    app.processEvents()
    tab = window._active_plot_tab()
    panel = window.options_panel
    controls = panel.axis_controls["capacity"]
    controls["x_max"].setText("4")
    controls["y_min"].setText("0")
    controls["y_max"].setText("100")
    tab.spec.normalization = "area"
    tab.redraw()
    app.processEvents()
    assert controls["x_max"].text() == "4"
    assert controls["y_min"].text() == "" and controls["y_max"].text() == ""
    assert "/cm²" in panel._axis_range_labels["capacity"]["y"].text()
    panel.apply()
    assert "y_max" not in tab.spec.analysis_options.get("axis_limits", {}).get("capacity", {})
    window._mark_clean()
    window.close()
    app.processEvents()


def test_unit_selector_follows_effective_normalization(synthetic_cv_runs, tmp_path):
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    run = synthetic_cv_runs[0]
    run.params.area_cm2 = 2.
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cv_runs=[run]), [])
    window._request_plot("cv_overlay")
    app.processEvents()
    tab = window._active_plot_tab()
    panel = window.options_panel
    assert panel.unit_controls["current"].findData("µA") >= 0
    tab.spec.normalization = "area"
    tab.redraw()
    app.processEvents()
    assert panel.unit_controls["current"].findData("µA/cm²") >= 0
    assert panel.unit_controls["current"].findData("µA") < 0
    run.params.area_cm2 = None
    tab.redraw()
    app.processEvents()
    assert panel.unit_controls["current"].findData("µA") >= 0
    window._mark_clean()
    window.close()
    app.processEvents()


def test_cp_auto_reference_input_follows_dataset_change(synthetic_cp_run, tmp_path):
    import copy
    from cvanalysis.analysis.cp import analyze_cp_run
    from cvanalysis.domain.units import cp_plot_units
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = copy.deepcopy(first)
    second.run_id = "larger-cp"
    second.metadata.cathodic_current_A *= 1000
    second.metadata.anodic_current_A *= 1000
    analyze_cp_run(second, force=True)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cp_runs=[first, second]), [])
    window._request_plot("cp_capacity", run_ids=[first.run_id])
    app.processEvents()
    tab = window._active_plot_tab()
    panel = window.options_panel
    mode = panel.controls["capacity_percent_mode"]
    mode.setCurrentIndex(mode.findData("manual"))
    panel.controls["capacity_percent_reference"].setText("2")
    panel.apply()
    old_unit = panel._cp_reference_unit_state["unit"]
    tab.spec.run_ids = [second.run_id]
    tab.redraw()
    app.processEvents()
    new_unit = panel._cp_reference_unit_state["unit"]
    factors = dict(cp_plot_units("capacity", "none"))
    assert old_unit != new_unit
    assert float(panel.controls["capacity_percent_reference"].text()) == pytest.approx(2 * factors[new_unit] / factors[old_unit])
    assert new_unit in panel.controls["cp_display_unit"].currentText()
    window._mark_clean()
    window.close()
    app.processEvents()
