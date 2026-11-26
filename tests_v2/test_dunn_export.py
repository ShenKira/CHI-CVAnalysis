import numpy as np
import pandas as pd
import pytest

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.export_service import export_analysis_csv


def test_dunn_csv_uses_each_plot_roi_and_records_inputs(tmp_path, synthetic_cv_runs):
    dataset = Dataset(cv_runs=synthetic_cv_runs)
    run_ids = [run.run_id for run in synthetic_cv_runs]
    cycles = {run_id: [2] for run_id in run_ids}
    for run in synthetic_cv_runs:
        run.params.area_cm2 = .5
    percentage = PlotSpec(
        "cv_contribution_vs_rate", run_ids,
        cycle_selection=cycles, normalization="area",
        analysis_options={
            "dunn_branch": "up",
            "dunn_fraction_basis": "measured",
            "dunn_roi_by_branch": {"up": [.13, .71], "down": [.17, .81]},
        },
    )
    prediction = PlotSpec(
        "cv_contribution", run_ids, selected_scan_rate=.03,
        analysis_options={"dunn_fraction_basis": "measured", "dunn_roi_by_branch": {"up": [.21, .84]}},
    )
    warnings = []
    written = export_analysis_csv(
        dataset, tmp_path, plots=(plot for plot in [PlotSpec("cv_overlay"), percentage, prediction]),
        warnings=warnings,
    )
    assert {"dunn_summary.csv", "dunn_points.csv", "dunn_inputs.csv"} <= {path.name for path in written}
    summary = pd.read_csv(tmp_path / "dunn_summary.csv")
    points = pd.read_csv(tmp_path / "dunn_points.csv")
    inputs = pd.read_csv(tmp_path / "dunn_inputs.csv", dtype={"included_cycles": str})
    stats = summary[summary.plot_index == 2]
    np.testing.assert_allclose(stats.scan_rate_V_s, [.01, .02, .05])
    np.testing.assert_allclose(stats.effective_window_low_V, .13)
    np.testing.assert_allclose(stats.effective_window_high_V, .71)
    assert set(stats.charge_unit) == {"C/cm²"}
    assert set(stats.method_version) == {5}
    np.testing.assert_allclose(stats.capacitive_pct, 100, atol=.01)
    subset = points[points.plot_index == 2]
    assert set(subset.current_unit) == {"A/cm²"}
    for rate, sweep in subset.groupby("scan_rate_V_s"):
        assert sweep.potential_V.min() == pytest.approx(.13)
        integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
        q_measured = integrate(sweep.current_measured, sweep.potential_V) / rate
        assert q_measured == pytest.approx(stats[stats.scan_rate_V_s == rate].q_measured.iloc[0])
        np.testing.assert_allclose(
            sweep.current_fitted, sweep.current_capacitive + sweep.current_diffusive, atol=1e-12,
        )
    assert set(inputs[inputs.plot_index == 2].run_id) == set(run_ids)
    assert set(inputs[inputs.plot_index == 2].included_cycles) == {"2"}

    predicted = summary[summary.plot_index == 3].iloc[0]
    assert predicted.scan_rate_V_s == .03
    assert predicted.is_prediction
    assert pd.isna(predicted.q_measured)
    assert pd.isna(predicted.diffusive_pct)
    assert points[points.plot_index == 3].current_measured.isna().all()
    assert any("图 3" in message and "无实测" in message for message in warnings)


def test_dunn_csv_reports_invalid_roi_without_blocking_other_tables(tmp_path, synthetic_cv_runs):
    dataset = Dataset(cv_runs=synthetic_cv_runs)
    spec = PlotSpec(
        "cv_contribution", [run.run_id for run in synthetic_cv_runs],
    )
    export_analysis_csv(dataset, tmp_path, plots=[spec])
    assert not pd.read_csv(tmp_path / "dunn_points.csv").empty
    spec.analysis_options["dunn_roi_by_branch"] = {"up": [.13, 9.0]}
    warnings = []
    written = export_analysis_csv(dataset, tmp_path, plots=[spec], warnings=warnings)
    assert {"cv_summary.csv", "dunn_summary.csv"} <= {path.name for path in written}
    assert pd.read_csv(tmp_path / "dunn_points.csv").empty
    summary = pd.read_csv(tmp_path / "dunn_summary.csv")
    assert summary.loc[0, "status"] == "unavailable"
    assert summary.loc[0, "requested_window_high_V"] == 9.0
    assert len(warnings) == 1
    assert "图 1" in warnings[0]
