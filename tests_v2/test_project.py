# -*- coding: utf-8 -*-
import numpy as np
import pytest

from cvanalysis.domain.models import Dataset, ElectrodeParams
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
from cvanalysis.services.project_service import load_project, save_project


def test_project_round_trip(synthetic_cv_runs, tmp_path):
    dataset = Dataset(name="test project", cv_runs=list(synthetic_cv_runs))
    run = synthetic_cv_runs[0]
    run.params = ElectrodeParams(0.5, 2.0)
    run.legend_template = "{CV_Voltage}-{Cycle_Number}"
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id],
        cycle_selection={run.run_id: [1, 2]},
        normalization="area",
        target_voltage=0.5,
        overrides={"line_width": 3.0, "label_size": 11.0},
        legend_templates={run.run_id: "{Scan_Rate}"},
        follow_dataset=True,
    )
    path = tmp_path / "project.cvproj"
    save_project(
        path,
        dataset,
        name="test project",
        visible_runs={run.run_id: False},
        cycle_selection={run.run_id: [1, 2]},
        plots=[spec],
    )
    state = load_project(path)
    assert len(state.dataset.cv_runs) == 3
    loaded = next(run for run in state.dataset.cv_runs if run.params.area_cm2 == 0.5)
    assert state.visible_runs[loaded.run_id] is False
    assert state.cycle_selection[loaded.run_id] == [1, 2]
    assert state.plots[0].normalization == "area"
    assert state.plots[0].run_ids == [loaded.run_id]
    assert state.plots[0].overrides["line_width"] == 3.0
    assert loaded.legend_template == "{CV_Voltage}-{Cycle_Number}"
    assert state.plots[0].legend_templates == {loaded.run_id: "{Scan_Rate}"}
    assert state.plots[0].follow_dataset is True


def test_project_round_trip_preserves_new_analysis_options(tmp_path, synthetic_cv_runs):
    run_ids = [run.run_id for run in synthetic_cv_runs]
    spec = PlotSpec(
        "cv_bvalue",
        run_ids,
        target_voltage=0.5,
        analysis_options={"b_current_mode": "up"},
    )
    path = tmp_path / "new-options.cvproj"
    save_project(
        path,
        Dataset(cv_runs=list(synthetic_cv_runs)),
        plots=[spec],
        analysis_settings={"outlier_method": "zscore", "outlier_z": 2.5},
    )
    state = load_project(path)
    assert state.plots[0].analysis_options["b_current_mode"] == "up"
    assert state.analysis_settings["outlier_method"] == "zscore"
    assert state.analysis_settings["outlier_z"] == 2.5


def test_project_round_trip_preserves_plot_color_and_style_options(tmp_path, synthetic_cv_runs):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.services.project_service import load_project, save_project

    run_ids = [run.run_id for run in synthetic_cv_runs]
    spec = PlotSpec(
        "cv_contribution_vs_rate",
        run_ids,
        analysis_options={
            "bar_width": 0.4,
            "bar_alpha": 0.8,
            "color_overrides": {"#1f77b4": "#ff0000"},
        },
    )
    path = tmp_path / "plot-options.cvproj"
    save_project(path, Dataset(cv_runs=list(synthetic_cv_runs)), plots=[spec])
    state = load_project(path)
    loaded = state.plots[0]
    assert loaded.analysis_options["bar_width"] == 0.4
    assert loaded.analysis_options["bar_alpha"] == 0.8
    assert loaded.analysis_options["color_overrides"] == {"#1f77b4": "#ff0000"}
    assert len(state.dataset.cv_runs) == len(synthetic_cv_runs)


def test_project_round_trip_preserves_axis_unit_and_tick_options(
    tmp_path, synthetic_eis_run
):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    cases = {
        "axis": {"axis_limits": {"main": {"x_min": -0.2, "x_max": 1.2}}},
        "units": {
            "unit_overrides": {"impedance": "kΩ"},
            "axis_limits": {"main": {"y_min": 0.0, "y_max": 0.1}},
            "axis_limit_units": {"main": {"y": {"label": "kΩ", "factor": 1e-3}}},
            "unified_xy_ticks": True,
            "unified_tick_interval": 0.1,
            "unified_tick_interval_unit": {"label": "kΩ", "factor": 1e-3},
            "log_tick_formats": {"x": "decimal", "y": "scientific"},
        },
    }
    for name, options in cases.items():
        spec = PlotSpec("eis_nyquist", [synthetic_eis_run.run_id], analysis_options=options)
        path = tmp_path / f"{name}-options.cvproj"
        save_project(path, dataset, plots=[spec])
        restored = load_project(path).plots[0].analysis_options
        for key, value in options.items():
            assert restored[key] == value


def test_project_load_ignores_unknown_fit_and_metadata_fields(tmp_path, synthetic_eis_run):
    import json

    from cvanalysis.domain.models import Dataset
    from cvanalysis.services.dataset_service import fit_eis_runs
    from cvanalysis.services.project_service import load_project, save_project

    dataset = Dataset(eis_runs=[synthetic_eis_run])
    fits = fit_eis_runs(dataset, [synthetic_eis_run.run_id], model="rct_c")
    path = tmp_path / "future-fields.cvproj"
    save_project(path, dataset, fits=fits)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runs"][0]["data"]["metadata"]["future_meta"] = 123
    old_id = payload["runs"][0]["run_id"]
    payload["fits"][old_id]["future_fit"] = 456
    payload["analysis_settings"] = "bad"
    payload["styles"] = "bad"
    path.write_text(json.dumps(payload), encoding="utf-8")

    state = load_project(path)
    assert len(state.dataset.eis_runs) == 1
    assert state.fits
    assert state.analysis_settings == {}
    assert state.styles == {}


def test_portable_project_fits_settings_and_unknown_fields(
    tmp_path, synthetic_cv_runs, synthetic_eis_run
):
    import json

    from cvanalysis.services.dataset_service import fit_eis_runs

    dataset = Dataset(cv_runs=synthetic_cv_runs, eis_runs=[synthetic_eis_run])
    fits = fit_eis_runs(dataset, [synthetic_eis_run.run_id], model="rct_c")
    spec = PlotSpec.from_dict(
        {
            "kind": "cv_cap_scan",
            "run_ids": [synthetic_cv_runs[0].run_id],
            "future": {"x": 1},
            "analysis_options": {"fit_method": "linear"},
            "paper_layout": {"enabled": True, "fraction": .25},
        }
    )
    path = tmp_path / "portable.cvproj"
    save_project(
        path,
        dataset,
        plots=[spec],
        fits=fits,
        analysis_settings={"outlier_count": 0},
    )
    for run in synthetic_cv_runs:
        run.source.unlink()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["future_project"] = 123
    path.write_text(json.dumps(payload), encoding="utf-8")
    state = load_project(path)
    assert not state.warnings
    assert len(state.dataset.cv_runs) == 3
    assert state.analysis_settings["outlier_count"] == 0
    np.testing.assert_allclose(
        next(iter(state.fits.values())).z_fit,
        fits[synthetic_eis_run.run_id].z_fit,
    )
    assert state.plots[0].to_dict()["future"] == {"x": 1}
    assert state.plots[0].analysis_options["fit_method"] == "linear"
    save_project(path, state.dataset, plots=state.plots)
    assert json.loads(path.read_text(encoding="utf-8"))["future_project"] == 123


def test_csv_export(synthetic_cv_runs, synthetic_eis_run, tmp_path):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis
    from cvanalysis.services.export_service import cv_cycles_frame, export_analysis_csv
    from cvanalysis.analysis.eis import analyze_eis

    dataset = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run])
    refresh_analysis(dataset, AnalysisSettings())
    synthetic_eis_run.summary = analyze_eis(synthetic_eis_run)
    written = export_analysis_csv(dataset, tmp_path)
    names = {path.name for path in written}
    assert "cv_summary.csv" in names
    assert "cv_cycles.csv" in names
    assert "eis_metrics.csv" in names
    for path in written:
        assert path.exists() and path.stat().st_size > 0

    frame = cv_cycles_frame(dataset)
    assert "area_C" not in frame.columns
    row = frame.iloc[0]
    assert row["loop_charge_C"] == pytest.approx(
        row["integral_area_A_V"] / synthetic_cv_runs[0].scan_rate
    )
    assert "included_in_statistics" in frame.columns
