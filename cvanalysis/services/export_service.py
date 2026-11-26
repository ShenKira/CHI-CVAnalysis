# -*- coding: utf-8 -*-
"""CSV export of analysis tables and plot-specific Dunn results."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import pandas as pd
except Exception:  # pragma: no cover - pandas is an explicit v2 dependency
    pd = None

from cvanalysis.analysis.cp import CPRunSummary
from cvanalysis.analysis.cv import (
    CVRunSummary,
    analyze_cv_run,
    dunn_analysis,
    dunn_fraction_vs_scan_rate,
    dunn_input_coverage,
)
from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.errors import AnalysisError
from cvanalysis.domain.models import Dataset
from cvanalysis.domain.units import charge_family, current_family
from cvanalysis.plotting.spec import PlotSpec, dunn_potential_window


def cv_summary_frame(dataset: Dataset) -> pd.DataFrame:
    rows = []
    for run in dataset.cv_runs:
        summary = run.summary if isinstance(run.summary, CVRunSummary) else None
        rows.append(
            {
                "file": run.display_name,
                "source": str(run.source) if run.source else "",
                "scan_rate_V_s": run.scan_rate,
                "voltage_window_V": run.voltage_window,
                "cycles_total": summary.total_cycles if summary else len(run.cycles),
                "cycles_valid": summary.valid_cycles if summary else None,
                "mean_capacitance_F": summary.mean_capacitance_F if summary else None,
                "sd_capacitance_F": summary.sd_capacitance_F if summary else None,
                "cv_percent": summary.cv_percent if summary else None,
                "mean_cap_per_area_F_cm2": summary.mean_cap_per_area if summary else None,
                "mean_cap_per_mass_F_g": summary.mean_cap_per_mass if summary else None,
                "area_cm2": run.params.area_cm2,
                "mass_mg": run.params.mass_mg,
                "warnings": "; ".join(summary.warnings) if summary else "",
                "method": summary.method if summary else "",
                "method_version": summary.method_version if summary else None,
            }
        )
    return pd.DataFrame(rows)


def cv_cycles_frame(dataset: Dataset) -> pd.DataFrame:
    rows = []
    for run in dataset.cv_runs:
        for cycle in run.cycles:
            rows.append(
                {
                    "file": run.display_name,
                    "source": str(run.source) if run.source else "",
                    "cycle": cycle.index,
                    "integral_area_A_V": cycle.integral_area_A_V,
                    "loop_charge_C": cycle.integral_area_A_V / run.scan_rate if run.scan_rate and run.scan_rate > 0 else None,
                    "capacitance_F": cycle.capacitance_F,
                    "valid": cycle.valid,
                    "included_in_statistics": cycle.valid and (run.summary is None or cycle.index not in run.summary.outlier_cycles),
                    "outlier_reason": cycle.outlier_reason or "",
                    "warning": cycle.warning or "",
                }
            )
    return pd.DataFrame(rows)


def eis_metrics_frame(dataset: Dataset) -> pd.DataFrame:
    rows = []
    for run in dataset.eis_runs:
        metrics = run.summary if isinstance(run.summary, EISMetrics) else None
        rows.append(
            {
                "file": run.display_name,
                "source": str(run.source) if run.source else "",
                "points": len(run.freq),
                "high_freq_Hz": run.metadata.high_freq,
                "low_freq_Hz": run.metadata.low_freq,
                "Rs_ohm": metrics.rs_ohm if metrics else None,
                "Rct_ohm": metrics.rct_ohm if metrics else None,
                "f_peak_Hz": metrics.f_peak_hz if metrics else None,
                "Cdl_F": metrics.cdl_F if metrics else None,
                "effective_capacitance_F": metrics.effective_capacitance_F if metrics else None,
                "fit_model": metrics.fit_model if metrics else None,
                "fit_frequency_low_Hz": metrics.fit_frequency_range_hz[0] if metrics and metrics.fit_frequency_range_hz else None,
                "fit_frequency_high_Hz": metrics.fit_frequency_range_hz[1] if metrics and metrics.fit_frequency_range_hz else None,
                "tau_s": metrics.tau_s if metrics else None,
                "phase_at_1Hz_deg": metrics.phase_at_1hz_deg if metrics else None,
                "mag_at_1Hz_ohm": metrics.mag_at_1hz_ohm if metrics else None,
                "low_freq_mag_ohm": metrics.low_freq_mag_ohm if metrics else None,
                "warnings": "; ".join(metrics.warnings) if metrics else "",
                "method": metrics.method if metrics else "",
                "method_version": metrics.method_version if metrics else None,
            }
        )
    return pd.DataFrame(rows)


def eis_fits_frame(fits: dict[str, EISFitResult]) -> pd.DataFrame:
    rows = []
    for run_id, fit in fits.items():
        row = {
            "run_id": run_id,
            "model": fit.model,
            "model_label": fit.model_label,
            "rmse_ohm": fit.rmse_ohm,
            "r2": fit.r2,
            "warnings": "; ".join(fit.warnings),
            "method_version": fit.method_version,
        }
        for key, value in fit.parameters.items():
            row[f"param_{key}"] = value
        for key, value in fit.stderr.items():
            row[f"stderr_{key}"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def cp_summary_frame(dataset: Dataset) -> pd.DataFrame:
    rows = []
    for run in dataset.cp_runs:
        summary = run.summary if isinstance(run.summary, CPRunSummary) else None
        rows.append(
            {
                "file": run.display_name,
                "source": str(run.source) if run.source else "",
                "applied_current_A": run.applied_current_A,
                "high_E_V": run.metadata.high_e,
                "low_E_V": run.metadata.low_e,
                "high_hold_s": run.metadata.high_hold_s,
                "low_hold_s": run.metadata.low_hold_s,
                "cycles": summary.cycle_count if summary else None,
                "has_hold_data": summary.has_hold_data if summary else run.has_hold_data,
                "completed_holds": summary.completed_hold_count if summary else None,
                "mean_discharge_capacity_C": summary.mean_discharge_capacity_C if summary else None,
                "mean_specific_capacity_mAh_g": summary.mean_specific_capacity_mAh_g if summary else None,
                "mean_areal_capacity_mAh_cm2": summary.mean_areal_capacity_mAh_cm2 if summary else None,
                "mean_areal_capacity_with_holds_C_cm2": (
                    summary.mean_areal_capacity_with_holds_C_cm2 if summary else None
                ),
                "mean_areal_capacity_with_holds_mAh_cm2": (
                    summary.mean_areal_capacity_with_holds_mAh_cm2 if summary else None
                ),
                "mean_coulombic_efficiency_pct": summary.mean_coulombic_efficiency_pct if summary else None,
                "mean_ir_drop_V": summary.mean_ir_drop_V if summary else None,
                "mean_specific_energy_Wh_kg": summary.mean_specific_energy_Wh_kg if summary else None,
                "mean_power_W_kg": summary.mean_power_W_kg if summary else None,
                "area_cm2": run.params.area_cm2,
                "mass_mg": run.params.mass_mg,
                "warnings": "; ".join(summary.warnings) if summary else "",
            }
        )
    return pd.DataFrame(rows)


def cp_cycles_frame(dataset: Dataset) -> pd.DataFrame:
    rows = []
    for run in dataset.cp_runs:
        summary = run.summary if isinstance(run.summary, CPRunSummary) else None
        if summary is None:
            continue
        for cycle in summary.cycles:
            rows.append(
                {
                    "file": run.display_name,
                    "source": str(run.source) if run.source else "",
                    "cycle": cycle.index,
                    "charge_capacity_C": cycle.charge_capacity_C,
                    "discharge_capacity_C": cycle.discharge_capacity_C,
                    "charge_capacity_with_holds_C": cycle.charge_capacity_with_holds_C,
                    "discharge_capacity_with_holds_C": cycle.discharge_capacity_with_holds_C,
                    "coulombic_efficiency_pct": cycle.coulombic_efficiency_pct,
                    "specific_capacity_C_g": cycle.specific_capacity_C_g,
                    "specific_capacity_mAh_g": cycle.specific_capacity_mAh_g,
                    "areal_capacity_mAh_cm2": cycle.areal_capacity_mAh_cm2,
                    "areal_capacity_with_holds_C_cm2": cycle.areal_capacity_with_holds_C_cm2,
                    "areal_capacity_with_holds_mAh_cm2": cycle.areal_capacity_with_holds_mAh_cm2,
                    "discharge_energy_Wh": cycle.discharge_energy_Wh,
                    "specific_energy_Wh_kg": cycle.specific_energy_Wh_kg,
                    "power_W_kg": cycle.power_W_kg,
                    "mean_discharge_potential_V": cycle.mean_discharge_potential_V,
                    "ir_drop_V": cycle.ir_drop_V,
                    "completeness": cycle.completeness,
                    "cycle_warning": cycle.cycle_warning,
                    "time_grid_status": run.time_grid_status,
                    "timing_method": cycle.timing_method,
                    "charge_duration_s": cycle.charge_duration_s,
                    "discharge_duration_s": cycle.discharge_duration_s,
                    "sampled_ce_pct": cycle.sampled_ce_pct,
                    "ce_lower_pct": cycle.ce_lower_pct,
                    "ce_upper_pct": cycle.ce_upper_pct,
                }
            )
    return pd.DataFrame(rows)


def plot_specs_frame(specs: Iterable[PlotSpec]) -> pd.DataFrame:
    rows = []
    for index, spec in enumerate(specs, start=1):
        rows.append(
            {
                "plot_index": index,
                "kind": spec.kind,
                "label": spec.label,
                "run_ids": "; ".join(spec.run_ids),
                "normalization": spec.normalization,
                "target_voltage": spec.target_voltage,
                "selected_scan_rate": spec.selected_scan_rate,
                "fit_model": spec.fit_model,
                "frequency_low": spec.frequency_low,
                "frequency_high": spec.frequency_high,
                "preset": spec.preset,
            }
        )
    return pd.DataFrame(rows)


def _dunn_frames(
    dataset: Dataset, specs: list[PlotSpec], warnings: list[str],
) -> dict[str, pd.DataFrame]:
    summary_rows = []
    input_rows = []
    point_frames = []
    for index, spec in enumerate(specs, start=1):
        if spec.kind not in {"cv_contribution", "cv_contribution_vs_rate"}:
            continue
        selected = set(spec.run_ids)
        runs = [run for run in dataset.cv_runs if run.run_id in selected]
        for run in runs:
            if run.summary is None:
                analyze_cv_run(run)
        branch = spec.analysis_options.get("dunn_branch", "up")
        basis = spec.analysis_options.get("dunn_fraction_basis", "fitted")
        window = dunn_potential_window(spec)
        requested_low, requested_high = window if isinstance(window, (tuple, list)) and len(window) == 2 else (None, None)
        context = {
            "plot_index": index,
            "plot_kind": spec.kind,
            "plot_title": spec.title or spec.label,
            "branch": branch,
            "fraction_basis": basis,
            "normalization_requested": spec.normalization,
            "window_source": "common" if window is None else "manual",
            "requested_window_low_V": requested_low,
            "requested_window_high_V": requested_high,
            "requested_scan_rate_V_s": spec.selected_scan_rate if spec.kind == "cv_contribution" else None,
        }
        fit_options = {
            "normalization": spec.normalization,
            "cycle_selection": spec.cycle_selection,
            "branch": branch,
            "fraction_basis": basis,
            "potential_window": window,
        }
        try:
            if spec.kind == "cv_contribution":
                result = dunn_analysis(runs, selected_scan_rate=spec.selected_scan_rate, **fit_options)
                sweeps = (
                    (result.diagnostic, result.capacitive_fraction, result.diffusive_fraction, result.measured_current),
                )
            else:
                result = dunn_fraction_vs_scan_rate(runs, **fit_options)
                sweeps = zip(result.diagnostics, result.capacitive_fraction, result.diffusive_fraction, result.fit.measured)
        except AnalysisError as exc:
            messages = [str(exc)]
            summary_rows.append({**context, "status": "unavailable", "warnings": str(exc)})
            try:
                inputs = dunn_input_coverage(runs, cycle_selection=spec.cycle_selection, branch=branch).inputs
            except AnalysisError:
                inputs = ()
        else:
            fit = result.fit
            messages = result.warnings
            inputs = fit.inputs
            current_unit = current_family(fit.normalization).units[0][0]
            charge_unit = charge_family(fit.normalization).units[0][0]
            common_low, common_high = fit.common_window
            context.update(
                method="dunn",
                method_version=result.method_version,
                normalization=fit.normalization,
                common_window_low_V=common_low,
                common_window_high_V=common_high,
                effective_window_low_V=fit.grid[0],
                effective_window_high_V=fit.grid[-1],
                distinct_fit_scan_rates=len(fit.rates),
            )
            for diagnostic, capacitive_fraction, diffusive_fraction, measured in sweeps:
                rate = diagnostic.scan_rate
                summary_rows.append({
                    **context,
                    "scan_rate_V_s": rate,
                    "is_prediction": measured is None,
                    "status": diagnostic.status,
                    "charge_unit": charge_unit,
                    "q_capacitive": diagnostic.q_capacitive,
                    "q_diffusive": diagnostic.q_diffusive,
                    "q_fitted": diagnostic.q_fitted,
                    "q_measured": diagnostic.q_measured,
                    "q_residual_fitted_minus_measured": diagnostic.q_residual,
                    "capacitive_pct": 100 * capacitive_fraction,
                    "diffusive_pct": 100 * diffusive_fraction,
                    "charge_closure_error_pct": 100 * diagnostic.closure_error,
                    "relative_current_rmse_pct": 100 * diagnostic.relative_rmse,
                    "fitted_net_to_absolute_charge_ratio": diagnostic.fitted_net_ratio,
                    "measured_net_to_absolute_charge_ratio": diagnostic.measured_net_ratio,
                    "mean_transformed_r2": result.mean_r2,
                    "warnings": "\n".join(messages),
                })
                capacitive = fit.k1 * rate
                diffusive = fit.k2 * np.sqrt(rate)
                fitted = capacitive + diffusive
                point_frames.append(pd.DataFrame({
                    "plot_index": index,
                    "scan_rate_V_s": rate,
                    "potential_V": fit.grid,
                    "current_unit": current_unit,
                    "k1_unit": f"{current_unit}/(V/s)",
                    "k2_unit": f"{current_unit}/√(V/s)",
                    "k1": fit.k1,
                    "k2": fit.k2,
                    "current_capacitive": capacitive,
                    "current_diffusive": diffusive,
                    "current_fitted": fitted,
                    "current_measured": measured if measured is not None else np.nan,
                    "current_residual_fitted_minus_measured": fitted - measured if measured is not None else np.nan,
                }))
        warnings.extend(f"图 {index} · {spec.label} · {message}" for message in messages)
        sources = {run.run_id: run for run in runs}
        for item in inputs:
            low, high = item.potential_window or (None, None)
            run = sources[item.run_id]
            requested_cycles = spec.cycle_selection.get(item.run_id)
            input_rows.append({
                "plot_index": index,
                "run_id": item.run_id,
                "file": item.label,
                "source": str(run.source or ""),
                "scan_rate_V_s": item.scan_rate,
                "requested_cycles": (
                    "all" if requested_cycles is None else "; ".join(str(cycle) for cycle in requested_cycles)
                ),
                "included_cycles": "; ".join(str(cycle) for cycle in item.cycle_indices),
                "partial_cycles": "; ".join(str(cycle) for cycle in item.partial_cycle_indices),
                "excluded_cycles": "; ".join(str(cycle) for cycle in item.excluded_cycle_indices),
                "input_window_low_V": low,
                "input_window_high_V": high,
                "area_cm2": run.params.area_cm2,
                "mass_mg": run.params.mass_mg,
                "reason": item.reason,
            })
    if not summary_rows:
        return {}
    # Replace stale files when a subsequent export has only invalid Dunn plots.
    points = pd.concat(point_frames, ignore_index=True) if point_frames else pd.DataFrame(columns=[
        "plot_index", "scan_rate_V_s", "potential_V", "current_unit", "k1_unit", "k2_unit", "k1", "k2",
        "current_capacitive", "current_diffusive", "current_fitted", "current_measured",
        "current_residual_fitted_minus_measured",
    ])
    inputs = pd.DataFrame(input_rows, columns=[
        "plot_index", "run_id", "file", "source", "scan_rate_V_s", "requested_cycles", "included_cycles",
        "partial_cycles", "excluded_cycles", "input_window_low_V", "input_window_high_V", "area_cm2", "mass_mg", "reason",
    ])
    return {
        "dunn_summary.csv": pd.DataFrame(summary_rows),
        "dunn_points.csv": points,
        "dunn_inputs.csv": inputs,
    }


def export_analysis_csv(
    dataset: Dataset,
    directory: str | Path,
    *,
    fits: dict[str, EISFitResult] | None = None,
    plots: Iterable[PlotSpec] | None = None,
    warnings: list[str] | None = None,
) -> list[Path]:
    if pd is None:
        raise RuntimeError("当前环境缺少 pandas，无法导出 CSV")
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    specs = list(plots or ())
    dunn_tables = _dunn_frames(dataset, specs, warnings if warnings is not None else [])
    written: list[Path] = []
    tables = {
        "cv_summary.csv": cv_summary_frame(dataset),
        "cv_cycles.csv": cv_cycles_frame(dataset),
        "eis_metrics.csv": eis_metrics_frame(dataset),
        "eis_fits.csv": eis_fits_frame(fits or {}),
        "cp_summary.csv": cp_summary_frame(dataset),
        "cp_cycles.csv": cp_cycles_frame(dataset),
        "plots.csv": plot_specs_frame(specs),
        **dunn_tables,
    }
    for kind, runs in (("lsv", dataset.lsv_runs), ("it", dataset.it_runs)):
        if runs:
            x_name = "potential_V" if kind == "lsv" else "time_s"
            tables[f"{kind}_points.csv"] = pd.DataFrame(
                {"file": run.display_name, "source": str(run.source or ""),
                 "point": index + 1, x_name: float(x), "current_A": float(current)}
                for run in runs for index, (x, current) in enumerate(zip(run.x, run.current))
            )
    for name, frame in tables.items():
        if frame.empty and name not in dunn_tables:
            continue
        path = output / name
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        written.append(path)
    return written
