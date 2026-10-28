# -*- coding: utf-8 -*-
"""CSV export of analysis tables (summary, cycles, EIS metrics, fits)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:
    import pandas as pd
except Exception:  # pragma: no cover - pandas is an explicit v2 dependency
    pd = None

from cvanalysis.analysis.cp import CPRunSummary
from cvanalysis.analysis.cv import CVRunSummary
from cvanalysis.analysis.eis import EISMetrics
from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec


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
                }
            )
    return pd.DataFrame(rows)


def plot_specs_frame(specs: Iterable[PlotSpec]) -> pd.DataFrame:
    rows = []
    for spec in specs:
        rows.append(
            {
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


def export_analysis_csv(
    dataset: Dataset,
    directory: str | Path,
    *,
    fits: dict[str, EISFitResult] | None = None,
    plots: Iterable[PlotSpec] | None = None,
) -> list[Path]:
    if pd is None:
        raise RuntimeError("当前环境缺少 pandas，无法导出 CSV")
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    tables = {
        "cv_summary.csv": cv_summary_frame(dataset),
        "cv_cycles.csv": cv_cycles_frame(dataset),
        "eis_metrics.csv": eis_metrics_frame(dataset),
        "eis_fits.csv": eis_fits_frame(fits or {}),
        "cp_summary.csv": cp_summary_frame(dataset),
        "cp_cycles.csv": cp_cycles_frame(dataset),
        "plots.csv": plot_specs_frame(plots or []),
    }
    for name, frame in tables.items():
        if frame.empty:
            continue
        path = output / name
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        written.append(path)
    return written
