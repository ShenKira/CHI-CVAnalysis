# -*- coding: utf-8 -*-
"""Dataset-level orchestration (no Qt dependencies)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cvanalysis.analysis.cp import analyze_cp_run
from cvanalysis.analysis.cv import analyze_cv_run
from cvanalysis.analysis.eis import EISMetrics, analyze_eis, filter_eis_run
from cvanalysis.analysis.fitting import EISFitResult, fit_eis_model
from cvanalysis.domain.models import CVRun, Dataset, EISRun, ElectrodeParams


@dataclass
class AnalysisSettings:
    outlier_count: int = 1
    sensitivity_factor: float = 10.0
    segmentation: str = "robust"
    outlier_method: str = "trim"
    outlier_z: float = 3.0


def refresh_analysis(dataset: Dataset, settings: AnalysisSettings | None = None, *, force: bool = False) -> list[str]:
    settings = settings or AnalysisSettings()
    warnings: list[str] = []
    for run in dataset.cv_runs:
        try:
            summary = analyze_cv_run(
                run,
                sensitivity_factor=settings.sensitivity_factor,
                outlier_count=settings.outlier_count,
                outlier_z=(
                    settings.outlier_z
                    if settings.outlier_method == "zscore"
                    else None
                ),
                segmentation=settings.segmentation,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001 - one bad run must not abort the batch
            message = f"{run.display_name}: CV 分析失败: {exc}"
            run.summary = None
            run.add_warning(message)
            warnings.append(message)
            continue
        warnings.extend(f"{run.display_name}: {message}" for message in summary.warnings)
    for run in dataset.eis_runs:
        try:
            run.summary = analyze_eis(run)
        except Exception as exc:  # noqa: BLE001 - keep importing other files
            message = f"{run.display_name}: EIS 分析失败: {exc}"
            run.summary = None
            run.add_warning(message)
            warnings.append(message)
    for run in dataset.cp_runs:
        try:
            summary = analyze_cp_run(run, force=force)
            warnings.extend(f"{run.display_name}: {message}" for message in summary.warnings)
        except Exception as exc:  # noqa: BLE001 - keep importing other files
            message = f"{run.display_name}: CP 分析失败: {exc}"
            run.summary = None
            run.add_warning(message)
            warnings.append(message)
    return warnings


def apply_params(
    dataset: Dataset,
    params: ElectrodeParams,
    run_ids: Iterable[str] | None = None,
    settings: AnalysisSettings | None = None,
) -> None:
    settings = settings or AnalysisSettings()
    selected = set(run_ids) if run_ids is not None else None
    dataset.apply_params(params, run_ids=run_ids)
    for run in dataset.cv_runs:
        if run.summary is None or (selected is not None and run.run_id not in selected):
            continue
        # Recompute summaries (normalized values) without re-segmentation.
        analyze_cv_run(
            run,
            sensitivity_factor=settings.sensitivity_factor,
            outlier_count=settings.outlier_count,
            outlier_z=(
                settings.outlier_z
                if settings.outlier_method == "zscore"
                else None
            ),
            segmentation=settings.segmentation,
            force=False,
        )
    for run in dataset.cp_runs:
        if run.summary is None or (selected is not None and run.run_id not in selected):
            continue
        # CP capacity normalization is stored in the summary, so it must be
        # rebuilt even though the parsed raw arrays are unchanged.
        analyze_cp_run(run, force=True)


def fit_eis_runs(
    dataset: Dataset,
    run_ids: Iterable[str],
    *,
    model: str = "rct_cpe",
    frequency_low: float | None = None,
    frequency_high: float | None = None,
) -> dict[str, EISFitResult]:
    fits: dict[str, EISFitResult] = {}
    for run_id in run_ids:
        run = dataset.find_eis(run_id)
        if run is None:
            continue
        selected = filter_eis_run(run, frequency_low, frequency_high)
        model_for_run = model
        if model == "auto":
            model_for_run = analyze_eis(selected).recommended_model
        fits[run_id] = fit_eis_model(selected.freq, selected.z_real, selected.z_imag, model=model_for_run)
    return fits


def eis_metrics(dataset: Dataset) -> dict[str, EISMetrics]:
    metrics: dict[str, EISMetrics] = {}
    for run in dataset.eis_runs:
        if isinstance(run.summary, EISMetrics):
            metrics[run.run_id] = run.summary
        else:
            metrics[run.run_id] = analyze_eis(run)
    return metrics
