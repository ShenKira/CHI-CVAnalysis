"""Capacity percentage and independently selected charge/discharge series."""
import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.cp_renderer import draw_cp_capacity
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


@pytest.mark.parametrize("series,count", [("both", 2), ("charge", 1), ("discharge", 1), ("mean", 1)])
def test_capacity_series_and_reference_cycle(synthetic_cp_run, series, count):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "show_efficiency": False, "capacity_series": series,
        "capacity_percent_mode": "cycle", "capacity_percent_cycle": 1,
    })
    fig = Figure()
    assert not draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert len(fig.axes[0].lines) == count
    if series in ("both", "discharge"):
        assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)
    assert "%" in fig.axes[0].get_ylabel()


def test_missing_reference_cycle_never_silently_uses_another(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "show_efficiency": False, "capacity_percent_mode": "cycle", "capacity_percent_cycle": 999,
    })
    fig = Figure()
    warnings = draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert warnings and not fig.axes[0].lines


def test_skipped_last_run_does_not_change_percent_axis_label(synthetic_cp_run):
    import copy

    first = synthetic_cp_run
    second = copy.deepcopy(first)
    second.run_id = "short_cp"
    second.summary.cycles = second.summary.cycles[:1]
    spec = PlotSpec("cp_capacity", [first.run_id, second.run_id], analysis_options={
        "show_efficiency": False, "capacity_percent_mode": "cycle", "capacity_percent_cycle": 2,
    })
    fig = Figure()
    warnings = draw_cp_capacity(fig, Dataset(cp_runs=[first, second]), spec, BUILTIN_PRESETS["daily"])
    assert warnings and fig.axes[0].lines
    assert "%" in fig.axes[0].get_ylabel()


def test_manual_percent_reference_scales_capacity(synthetic_cp_run):
    run = synthetic_cp_run
    data = Dataset(cp_runs=[run])
    baseline = PlotSpec("cp_capacity", [run.run_id], analysis_options={"show_efficiency": False, "capacity_series": "discharge"})
    first = Figure()
    draw_cp_capacity(first, data, baseline, BUILTIN_PRESETS["daily"])
    reference = first.axes[0].lines[0].get_ydata()[0]
    assert np.isfinite(reference) and reference > 0
    baseline.analysis_options.update(capacity_percent_mode="manual", capacity_percent_reference=reference)
    second = Figure()
    draw_cp_capacity(second, data, baseline, BUILTIN_PRESETS["daily"])
    assert second.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)


def test_capacitance_uses_segment_voltage_and_can_be_percent(synthetic_cp_run):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={
        "show_efficiency": False, "capacity_series": "discharge", "cp_quantity": "capacitance"})
    fig = Figure()
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    cycle = run.summary.cycles[0]
    expected = cycle.discharge_capacity_C / abs(cycle.discharge.potential_V[-1] - cycle.discharge.potential_V[0])
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(expected)
    assert "Capacitance (F)" in fig.axes[0].get_ylabel()
    spec.analysis_options.update(capacity_percent_mode="cycle", capacity_percent_cycle=1)
    percent = Figure()
    draw_cp_capacity(percent, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert percent.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)
    assert "Capacitance (%)" in percent.axes[0].get_ylabel()


@pytest.mark.parametrize("normalization,factor,unit", [("area", 2.0, "F/cm²"), ("mass", 0.004, "F/g")])
def test_capacitance_normalization_units(synthetic_cp_run, normalization, factor, unit):
    run = synthetic_cp_run
    run.params.area_cm2 = 2.0
    run.params.mass_mg = 4.0
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    refresh_analysis(Dataset(cp_runs=[run]), AnalysisSettings(), force=True)
    spec = PlotSpec("cp_capacity", [run.run_id], normalization=normalization, analysis_options={
        "show_efficiency": False, "capacity_series": "discharge", "cp_quantity": "capacitance"})
    fig = Figure()
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    cycle = run.summary.cycles[0]
    expected = cycle.discharge_capacity_C / abs(cycle.discharge.potential_V[-1] - cycle.discharge.potential_V[0]) / factor
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(expected)
    assert unit in fig.axes[0].get_ylabel()


def test_percent_options_apply_and_roundtrip(synthetic_cp_run, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    dataset = Dataset(cp_runs=[run])
    tab = PlotTab(PlotSpec("cp_capacity", [run.run_id]), BUILTIN_PRESETS["daily"], dataset)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    panel.controls["capacity_series"].setCurrentIndex(panel.controls["capacity_series"].findData("mean"))
    panel.controls["capacity_percent_mode"].setCurrentIndex(panel.controls["capacity_percent_mode"].findData("cycle"))
    panel.controls["capacity_percent_cycle"].setText("1")
    panel.apply()
    assert tab.spec.analysis_options["capacity_series"] == "mean"
    assert tab.spec.analysis_options["capacity_percent_cycle"] == 1
    path = tmp_path / "percentage.cvproj"
    save_project(path, dataset, plots=[tab.spec])
    restored = load_project(path).plots[0]
    assert restored.analysis_options["capacity_percent_mode"] == "cycle"
    assert restored.analysis_options["capacity_series"] == "mean"
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()
