# -*- coding: utf-8 -*-
"""Project persistence for the v2 workspace."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from cvanalysis.domain.models import (
    CPMetadata,
    CPRun,
    CVMetadata,
    CVRun,
    Dataset,
    EISMetadata,
    EISRun,
    ElectrodeParams,
    new_id,
)
from cvanalysis.io.registry import load_files
from cvanalysis.plotting.spec import PlotSpec
import numpy as np
from cvanalysis.analysis.fitting import EISFitResult


PROJECT_FORMAT = "cvanalysis-project"
PROJECT_VERSION = 2


@dataclass
class ProjectState:
    dataset: Dataset
    name: str = "未命名项目"
    visible_runs: dict[str, bool] = field(default_factory=dict)
    cycle_selection: dict[str, list[int]] = field(default_factory=dict)
    plots: list[PlotSpec] = field(default_factory=list)
    active_plot: int = 0
    warnings: list[str] = field(default_factory=list)
    analysis_settings: dict = field(default_factory=dict)
    fits: dict = field(default_factory=dict)
    styles: dict = field(default_factory=dict)


def _run_ref(run: CVRun | EISRun | CPRun) -> str:
    source = str(run.source) if run.source else ""
    return f"{source}::{run.run_index}"


def save_project(
    path: str | Path,
    dataset: Dataset,
    *,
    name: str | None = None,
    visible_runs: dict[str, bool] | None = None,
    cycle_selection: dict[str, list[int]] | None = None,
    plots: Iterable[PlotSpec] | None = None,
    active_plot: int = 0,
    analysis_settings: dict | None = None,
    fits: dict | None = None,
    styles: dict | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    visible_runs = visible_runs or {}
    cycle_selection = cycle_selection or {}
    runs_payload: list[dict[str, Any]] = []
    for run in dataset.all_runs():
        embedded = {**getattr(run, "_project_data_extra", {}), **asdict(run)}
        for key in ("summary", "cycles"):
            embedded.pop(key, None)
        embedded["source"] = str(run.source) if run.source else None
        runs_payload.append(
            {
                **getattr(run, "_project_entry_extra", {}),
                "run_id": run.run_id,
                "kind": "cv" if isinstance(run, CVRun) else "cp" if isinstance(run, CPRun) else "eis",
                "source": str(run.source.resolve()) if run.source else "",
                "run_index": run.run_index,
                "name": run.name,
                "visible": bool(visible_runs.get(run.run_id, True)),
                "cycles": list(cycle_selection[run.run_id]) if run.run_id in cycle_selection else None,
                "params": {
                    "area_cm2": run.params.area_cm2,
                    "mass_mg": run.params.mass_mg,
                },
                "legend_template": run.legend_template,
                "data": embedded,
            }
        )
    payload = {
        **getattr(dataset, "_project_extra", {}),
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "name": name or dataset.name,
        "runs": runs_payload,
        "plots": [spec.to_dict() for spec in (plots or [])],
        "active_plot": int(active_plot),
        "analysis_settings": analysis_settings or {},
        "styles": styles or {},
        "fits": {key: {**asdict(value), "z_fit": [value.z_fit.real.tolist(), value.z_fit.imag.tolist()]} for key, value in (fits or {}).items()},
    }
    temp = output.with_name(output.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=lambda value: value.tolist() if isinstance(value, np.ndarray) else str(value)), encoding="utf-8")
    os.replace(temp, output)
    return output


def load_project(path: str | Path) -> ProjectState:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法读取项目文件: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("项目文件顶层必须是 JSON 对象")
    if payload.get("format") != PROJECT_FORMAT:
        raise ValueError("不是 CVAnalysis v2 项目文件")
    try:
        version = int(payload.get("version", 1))
    except (TypeError, ValueError, OverflowError):
        version = 1
    if version > PROJECT_VERSION:
        raise ValueError(f"项目文件版本 {version} 高于当前支持版本 {PROJECT_VERSION}")

    runs_payload = payload.get("runs")
    if not isinstance(runs_payload, list):
        runs_payload = []
    source_map: dict[str, Path] = {}
    for entry in runs_payload:
        source_text = entry.get("source", "")
        if not source_text:
            continue
        source_path = Path(source_text)
        if not source_path.is_absolute():
            source_path = (source.parent / source_path).resolve()
        source_map[source_text] = source_path
    sources = sorted({str(source_map[entry['source']]) for entry in runs_payload if entry.get('source') and not entry.get('data')})
    dataset, issues = load_files(sources)
    warnings = [f"{issue.path.name}: {issue.message}" for issue in issues]
    mapped: dict[tuple[str, int], CVRun | EISRun | CPRun] = {}
    for run in dataset.all_runs():
        key = (str(run.source.resolve()) if run.source else "", run.run_index)
        mapped[key] = run

    old_to_new: dict[str, str] = {}
    visible: dict[str, bool] = {}
    cycle_selection: dict[str, list[int]] = {}
    for entry in runs_payload:
        source_text = entry.get("source", "")
        resolved = source_map.get(source_text)
        key = (str(resolved) if resolved else "", int(entry.get("run_index", 0)))
        run = mapped.get(key)
        if entry.get("data"):
            data = dict(entry["data"])
            kind = entry.get("kind", "cv")
            if kind == "cv":
                cls, metadata_cls = CVRun, CVMetadata
                array_keys = ("potential", "current")
                id_prefix = "cv"
            elif kind == "cp":
                cls, metadata_cls = CPRun, CPMetadata
                array_keys = ("time", "potential", "hold_time", "hold_current")
                id_prefix = "cp"
            else:
                cls, metadata_cls = EISRun, EISMetadata
                array_keys = ("freq", "z_real", "z_imag", "z_mag", "phase")
                id_prefix = "eis"
            data["run_id"] = new_id(id_prefix)
            metadata_payload = data.get("metadata")
            if not isinstance(metadata_payload, dict):
                metadata_payload = {}
            data["metadata"] = metadata_cls(**{
                key: value
                for key, value in metadata_payload.items()
                if key in metadata_cls.__dataclass_fields__
            })
            params_payload = data.get("params")
            if not isinstance(params_payload, dict):
                params_payload = {}
            data["params"] = ElectrodeParams(**{
                key: value
                for key, value in params_payload.items()
                if key in ElectrodeParams.__dataclass_fields__
            })
            data["source"] = resolved
            for array in array_keys:
                value = data.get(array)
                data[array] = (
                    np.asarray(value, dtype=float) if value is not None else None
                )
            run = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            run._project_data_extra = {k: v for k, v in data.items() if k not in cls.__dataclass_fields__}
            dataset.add_runs([run])
        if run is None:
            warnings.append(f"未找到项目中的数据: {entry.get('source', '')}")
            continue
        old_id = entry.get("run_id", "")
        entry_keys = {"run_id", "kind", "source", "run_index", "name", "visible", "cycles", "params", "legend_template", "data"}
        run._project_entry_extra = {k: v for k, v in entry.items() if k not in entry_keys}
        old_to_new[old_id] = run.run_id
        visible[run.run_id] = bool(entry.get("visible", True))
        cycles = entry.get("cycles")
        if cycles is not None:
            cycle_selection[run.run_id] = [int(value) for value in cycles]
        params = entry.get("params") or {}
        run.params = ElectrodeParams(params.get("area_cm2"), params.get("mass_mg"))
        run.legend_template = str(entry.get("legend_template") or "")
        if entry.get("name"):
            run.name = entry["name"]

    plots: list[PlotSpec] = []
    plots_payload = payload.get("plots")
    if not isinstance(plots_payload, list):
        plots_payload = []
    for plot_payload in plots_payload:
        if not isinstance(plot_payload, dict):
            continue
        spec = PlotSpec.from_dict(plot_payload)
        spec.run_ids = [old_to_new[run_id] for run_id in spec.run_ids if run_id in old_to_new]
        spec.cycle_selection = {
            old_to_new[run_id]: cycles
            for run_id, cycles in spec.cycle_selection.items()
            if run_id in old_to_new
        }
        spec.legend_templates = {
            old_to_new[run_id]: template
            for run_id, template in spec.legend_templates.items()
            if run_id in old_to_new
        }
        plots.append(spec)

    dataset.name = payload.get("name", source.stem)
    known = {"format", "version", "name", "runs", "plots", "active_plot", "analysis_settings", "fits", "styles"}
    dataset._project_extra = {k: v for k, v in payload.items() if k not in known}
    restored_fits = {}
    fits_payload = payload.get("fits")
    if not isinstance(fits_payload, dict):
        fits_payload = {}
    for old_id, raw in fits_payload.items():
        if old_id not in old_to_new or not isinstance(raw, dict):
            continue
        data = dict(raw)
        try:
            data["z_fit"] = np.asarray(data["z_fit"][0]) + 1j * np.asarray(data["z_fit"][1])
            for key in ("frequencies", "residual_real", "residual_imag"):
                data[key] = np.asarray(data[key])
        except (KeyError, IndexError, TypeError, ValueError):
            warnings.append(f"拟合结果字段不完整，已跳过: {old_id}")
            continue
        restored_fits[old_to_new[old_id]] = EISFitResult(**{
            key: value
            for key, value in data.items()
            if key in EISFitResult.__dataclass_fields__
        })
    try:
        active_plot = int(payload.get("active_plot", 0))
    except (TypeError, ValueError, OverflowError):
        active_plot = 0
    analysis_settings = payload.get("analysis_settings")
    styles = payload.get("styles")
    return ProjectState(
        dataset=dataset,
        name=dataset.name,
        visible_runs=visible,
        cycle_selection=cycle_selection,
        plots=plots,
        active_plot=active_plot,
        warnings=warnings,
        analysis_settings=analysis_settings if isinstance(analysis_settings, dict) else {},
        fits=restored_fits,
        styles=styles if isinstance(styles, dict) else {},
    )
