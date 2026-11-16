# -*- coding: utf-8 -*-
"""LSV/I-T reference-area and reference-capacitance display modes."""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.axis_limits import axis_display_dimensions
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


def _it_run(run_id: str = "it_ref", current=None) -> SweepRun:
    return SweepRun(
        run_id,
        "sample",
        "it",
        np.array([0.0, 1.0, 2.0]),
        np.array([1e-6, 2e-6, 4e-6]) if current is None else current,
        SweepMetadata("test", {}),
    )


def _lsv_run(run_id: str = "lsv_ref", current=None) -> SweepRun:
    return SweepRun(
        run_id,
        "sample",
        "lsv",
        np.array([0.0, 0.5, 1.0]),
        np.array([1e-6, 2e-6, 4e-6]) if current is None else current,
        SweepMetadata("test", {}),
    )


def _render(spec: PlotSpec, data: Dataset):
    figure = Figure()
    warnings = render_plot(figure, data, spec, STYLE)
    return figure, warnings


@pytest.mark.parametrize("kind,run_factory", [("it", _it_run), ("lsv", _lsv_run)])
def test_reference_area_scales_current_and_uses_density_units(kind, run_factory):
    run = run_factory()
    spec = PlotSpec(
        f"{kind}_curve",
        [run.run_id],
        analysis_options={
            f"{kind}_current_display": "reference_area",
            f"{kind}_reference_area_cm2": 2.0,
            "unit_overrides": {"current": "auto"},
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]) if kind == "it" else Dataset(lsv_runs=[run]))
    assert not warnings
    axis = figure.axes[0]
    np.testing.assert_allclose(axis.lines[0].get_ydata(), [0.5, 1.0, 2.0])
    assert "µA/cm²" in axis.get_ylabel()
    assert axis_display_dimensions(axis)["y"] == "current_area"


@pytest.mark.parametrize("kind,run_factory", [("it", _it_run), ("lsv", _lsv_run)])
def test_reference_capacitance_scales_current_and_uses_af_units(kind, run_factory):
    run = run_factory()
    spec = PlotSpec(
        f"{kind}_curve",
        [run.run_id],
        analysis_options={
            f"{kind}_current_display": "reference_capacitance",
            f"{kind}_reference_capacitance_f": 2.0,
            "unit_overrides": {"current": "auto"},
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]) if kind == "it" else Dataset(lsv_runs=[run]))
    assert not warnings
    axis = figure.axes[0]
    np.testing.assert_allclose(axis.lines[0].get_ydata(), [0.5, 1.0, 2.0])
    assert "µA/F" in axis.get_ylabel()
    assert axis_display_dimensions(axis)["y"] == "current_per_capacitance"


def test_reference_capacitance_denominator_follows_reference_unit():
    run = _it_run("it-unit", np.array([2e-6, 2e-6, 2e-6]))
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        analysis_options={
            "it_current_display": "reference_capacitance",
            "it_reference_capacitance_f": 1e-6,
            "it_reference_capacitance_unit": "µF",
            "it_reference_time": 1.0,
            "it_reference_current_unit": "nA",
            "it_reference_label_mode": "current",
            "unit_overrides": {"current": "nA/F"},
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]))
    assert not warnings
    axis = figure.axes[0]
    np.testing.assert_allclose(axis.lines[0].get_ydata(), [2000, 2000, 2000])
    assert "nA/µF" in axis.get_ylabel()
    assert "nA/µF" in axis.texts[0].get_text()
    assert axis_display_dimensions(axis)["y"] == "current_per_capacitance"


def test_reference_area_is_shared_by_all_it_runs():
    first = _it_run("it1", np.array([1e-6, 2e-6, 4e-6]))
    second = _it_run("it2", np.array([2e-6, 4e-6, 8e-6]))
    spec = PlotSpec(
        "it_curve",
        [first.run_id, second.run_id],
        analysis_options={
            "it_current_display": "reference_area",
            "it_reference_area_cm2": 2.0,
            "unit_overrides": {"current": "µA/cm²"},
        },
    )
    figure, warnings = _render(
        spec, Dataset(it_runs=[first, second])
    )
    assert not warnings
    axis = figure.axes[0]
    np.testing.assert_allclose(axis.lines[0].get_ydata(), [0.5, 1.0, 2.0])
    np.testing.assert_allclose(axis.lines[1].get_ydata(), [1.0, 2.0, 4.0])
    assert "µA/cm²" in axis.get_ylabel()


def test_reference_modes_ignore_global_area_normalization():
    run = _it_run()
    run.params.area_cm2 = 10.0
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        normalization="area",
        analysis_options={
            "it_current_display": "reference_area",
            "it_reference_area_cm2": 2.0,
            "unit_overrides": {"current": "auto"},
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]))
    assert not warnings
    np.testing.assert_allclose(
        figure.axes[0].lines[0].get_ydata(), [0.5, 1.0, 2.0]
    )


def test_it_reference_annotation_uses_capacitance_suffix():
    run = _it_run()
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        analysis_options={
            "it_current_display": "reference_capacitance",
            "it_reference_capacitance_f": 2.0,
            "it_reference_time": 1.0,
            "it_reference_current_unit": "pA",
            "it_reference_label_mode": "current",
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]))
    assert not warnings
    assert "pA/F" in figure.axes[0].texts[0].get_text()


def test_invalid_reference_falls_back_to_raw_current():
    run = _it_run()
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        analysis_options={
            "it_current_display": "reference_area",
            "it_reference_area_cm2": 0,
            "unit_overrides": {"current": "auto"},
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]))
    assert warnings and "参考面积" in warnings[0]
    np.testing.assert_allclose(
        figure.axes[0].lines[0].get_ydata(), [1.0, 2.0, 4.0]
    )
    assert "µA" in figure.axes[0].get_ylabel()


@pytest.mark.parametrize("kind,run_factory", [("it", _it_run), ("lsv", _lsv_run)])
def test_reference_display_panel_roundtrip_and_unit_conversion(
    kind, run_factory, tmp_path
):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    run = run_factory()
    data = Dataset(it_runs=[run]) if kind == "it" else Dataset(lsv_runs=[run])
    spec = PlotSpec(f"{kind}_curve", [run.run_id])
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        mode = panel.controls[f"{kind}_current_display"]
        area = panel.controls[f"{kind}_reference_area_cm2"]
        cap = panel.controls[f"{kind}_reference_capacitance"]
        cap_unit = panel.controls[f"{kind}_reference_capacitance_unit"]
        assert mode.findData("reference_area") >= 0
        assert mode.findData("reference_capacitance") >= 0

        mode.setCurrentIndex(mode.findData("reference_area"))
        area.setText("2")
        panel.apply()
        assert "已应用" in panel.error.text()
        assert spec.analysis_options[f"{kind}_current_display"] == "reference_area"
        assert spec.analysis_options[f"{kind}_reference_area_cm2"] == pytest.approx(2.0)

        mode.setCurrentIndex(mode.findData("reference_capacitance"))
        cap_unit.setCurrentIndex(cap_unit.findData("µF"))
        cap.setText("1500")
        cap_unit.setCurrentIndex(cap_unit.findData("mF"))
        assert float(cap.text()) == pytest.approx(1.5)
        panel.apply()
        assert spec.analysis_options[f"{kind}_current_display"] == "reference_capacitance"
        assert spec.analysis_options[f"{kind}_reference_capacitance_f"] == pytest.approx(
            0.0015
        )
        assert spec.analysis_options[f"{kind}_reference_capacitance_unit"] == "mF"

        path = tmp_path / f"{kind}-reference.cvproj"
        save_project(path, data, plots=[spec])
        restored = load_project(path).plots[0]
        assert restored.analysis_options[f"{kind}_current_display"] == "reference_capacitance"
        assert restored.analysis_options[f"{kind}_reference_capacitance_f"] == pytest.approx(
            0.0015
        )
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_reference_display_axis_dimensions_and_range_clear():
    from cvanalysis.plotting.axis_limits import sync_axis_limit_units, unit_dimension

    assert unit_dimension("µA/F") == "current_per_capacitance"
    assert unit_dimension("mA/cm²") == "current_area"
    run = _it_run()
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        analysis_options={
            "it_current_display": "reference_capacitance",
            "it_reference_capacitance_f": 2.0,
            "unit_overrides": {"current": "auto"},
            "axis_limits": {"main": {"y_min": 0.0, "y_max": 1.0}},
            "axis_limit_units": {
                "main": {
                    "y": {"label": "µA", "factor": 1e6, "dimension": "current"}
                }
            },
        },
    )
    figure, warnings = _render(spec, Dataset(it_runs=[run]))
    assert any("清空" in warning or "范围" in warning for warning in warnings)
    limits = spec.analysis_options.get("axis_limits", {}).get("main", {})
    assert "y_min" not in limits


def test_reference_panel_sanitizes_incompatible_unit_override():
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    run = _it_run()
    spec = PlotSpec(
        "it_curve",
        [run.run_id],
        analysis_options={"unit_overrides": {"current": "µA"}},
    )
    tab = PlotTab(spec, STYLE, Dataset(it_runs=[run]))
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        mode = panel.controls["it_current_display"]
        mode.setCurrentIndex(mode.findData("reference_capacitance"))
        panel.controls["it_reference_capacitance"].setText("2")
        panel.apply()
        assert spec.analysis_options["unit_overrides"]["current"] == "µA/F"
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_reference_panel_requires_positive_active_value():
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    run = _it_run()
    spec = PlotSpec("it_curve", [run.run_id])
    tab = PlotTab(spec, STYLE, Dataset(it_runs=[run]))
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        mode = panel.controls["it_current_display"]
        mode.setCurrentIndex(mode.findData("reference_area"))
        panel.controls["it_reference_area_cm2"].setText("")
        panel.apply()
        assert "参考面积" in panel.error.text()
        assert "it_current_display" not in spec.analysis_options
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()
