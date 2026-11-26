# -*- coding: utf-8 -*-
import json
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["plots"][0]["follow_dataset"] = True  # old v2 project
    payload["plots"][0]["future_option"] = "preserved"
    path.write_text(json.dumps(payload), encoding="utf-8")
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
    assert "follow_dataset" not in state.plots[0].to_dict()
    assert state.plots[0].to_dict()["future_option"] == "preserved"


def test_plot_tab_name_project_round_trip_and_copy(synthetic_cv_runs, tmp_path):
    run = synthetic_cv_runs[0]
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id],
        cycle_selection={run.run_id: [2]},
        title="Scientific title",
        tab_name="电极 A · 第 2 次",
        analysis_options={"nested": {"values": [1, 2]}},
    )
    duplicate = spec.copy()
    assert duplicate.tab_name == spec.tab_name
    duplicate.tab_name = "另一个标签"
    duplicate.analysis_options["nested"]["values"].append(3)
    assert spec.tab_name == "电极 A · 第 2 次"
    assert spec.analysis_options["nested"]["values"] == [1, 2]

    project = tmp_path / "tab-names.cvproj"
    save_project(project, Dataset(cv_runs=[run]), plots=[spec, duplicate])
    state = load_project(project)
    assert [plot.tab_name for plot in state.plots] == ["电极 A · 第 2 次", "另一个标签"]
    assert all(plot.title == "Scientific title" for plot in state.plots)
    loaded_run = state.dataset.cv_runs[0]
    assert state.plots[0].cycle_selection == {loaded_run.run_id: [2]}
    assert state.plots[0].run_ids == [loaded_run.run_id]

    saved = json.loads(project.read_text(encoding="utf-8"))
    saved["plots"][0].pop("tab_name")
    saved["plots"][1]["tab_name"] = {"invalid": "name"}
    project.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    legacy = load_project(project)
    assert [plot.tab_name for plot in legacy.plots] == ["", ""]
    assert [plot.label for plot in legacy.plots] == [spec.label, spec.label]


def test_project_embedded_preset_is_available_and_saved_without_modifying_global_presets(tmp_path, synthetic_cv_runs):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    style = BUILTIN_PRESETS["ieee-single"].to_dict()
    style.update(name="project-only", label="Project style", custom_future_field="keep")
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs], preset="project-only")
    source = tmp_path / "embedded.cvproj"
    save_project(source, Dataset(cv_runs=list(synthetic_cv_runs)), plots=[spec], styles={"project-only": style})
    expected_style = json.loads(source.read_text(encoding="utf-8"))["styles"]["project-only"]
    state = load_project(source)
    refresh_analysis(state.dataset)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window.show()
    window._apply_project(state, source)
    QTest.qWait(30)
    assert window.preset_combo.currentData() == "project-only"
    assert "project-only" not in window.settings_service.user_presets
    menu = window._active_plot_tab()._build_settings_menu()
    presets = next(action.menu() for action in menu.actions() if action.text() == "绘图预设")
    assert any(action.isChecked() and action.text() == "Project style" for action in presets.actions())
    output = tmp_path / "roundtrip.cvproj"
    assert window._write_project(output)
    assert json.loads(output.read_text(encoding="utf-8"))["styles"]["project-only"] == expected_style
    menu.deleteLater()
    window.close()
    app.processEvents()


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
