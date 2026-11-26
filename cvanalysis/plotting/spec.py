# -*- coding: utf-8 -*-
"""Serializable description of a plot document."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


DUNN_CATEGORY_INDEX_UNIT = "类别索引"
DUNN_CATEGORY_INDEX_DIMENSION = "category_index"


def _dunn_axis_limit_options(options: Any, *, legacy: bool) -> Any:
    """Tag an unqualified Dunn X range with its saved coordinate convention."""
    if not isinstance(options, dict):
        return options
    limits = options.get("axis_limits")
    main = limits.get("main") if isinstance(limits, dict) else None
    if not isinstance(main, dict) or not any(
        main.get(key) not in (None, "") for key in ("x_min", "x_max")
    ):
        return options
    units = options.get("axis_limit_units")
    if units is not None and not isinstance(units, dict):
        return options
    main_units = (units or {}).get("main")
    if main_units is not None and (not isinstance(main_units, dict) or "x" in main_units):
        return options
    x_unit = {
        "label": DUNN_CATEGORY_INDEX_UNIT if legacy else "V/s",
        "factor": 1.0,
        "dimension": DUNN_CATEGORY_INDEX_DIMENSION if legacy else "scan_rate",
    }
    return {
        **options,
        "axis_limit_units": {**(units or {}), "main": {**(main_units or {}), "x": x_unit}},
    }


PLOT_KINDS = {
    "cv_overlay": "CV 叠加图",
    "cv_cap_scan": "电容-扫速",
    "cv_current_scan": "固定电位电流-扫速",
    "cv_bvalue": "b 值分析",
    "cv_contribution": "Dunn 电流分解",
    "cv_contribution_vs_rate": "贡献占比-扫速",
    "cv_trasatti": "Trasatti 电荷分解",
    "eis_nyquist": "EIS Nyquist",
    "eis_bode": "EIS Bode",
    "eis_fit": "EIS 拟合",
    "cp_gcd": "CP / GCD 电位-时间",
    "cp_capacity": "GCD 容量-循环",
    "lsv_curve": "LSV 电流-电位",
    "it_curve": "I-T 电流-时间",
}


@dataclass
class PlotSpec:
    kind: str
    run_ids: list[str] = field(default_factory=list)
    cycle_selection: dict[str, list[int]] = field(default_factory=dict)
    normalization: str = "none"
    target_voltage: float | None = None
    selected_scan_rate: float | None = None
    fit_model: str = "rct_cpe"
    fit_enabled: bool = False
    frequency_low: float | None = None
    frequency_high: float | None = None
    show_legend: bool = True
    show_axes: bool = True
    annotations: bool = True
    title: str = ""
    preset: str = "daily"
    overrides: dict[str, Any] = field(default_factory=dict)
    color_by: str = "auto"
    x_log: bool = False
    renumber_cycles: bool = False
    legend_templates: dict[str, str] = field(default_factory=dict)
    analysis_options: dict[str, Any] = field(default_factory=dict)
    paper_layout: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    tab_name: str = ""

    @property
    def label(self) -> str:
        return PLOT_KINDS.get(self.kind, self.kind)

    def copy(self) -> "PlotSpec":
        return PlotSpec(
            kind=self.kind,
            run_ids=list(self.run_ids),
            cycle_selection={key: list(value) for key, value in self.cycle_selection.items()},
            normalization=self.normalization,
            target_voltage=self.target_voltage,
            selected_scan_rate=self.selected_scan_rate,
            fit_model=self.fit_model,
            fit_enabled=self.fit_enabled,
            frequency_low=self.frequency_low,
            frequency_high=self.frequency_high,
            show_legend=self.show_legend,
            show_axes=self.show_axes,
            annotations=self.annotations,
            title=self.title,
            preset=self.preset,
            overrides=dict(self.overrides),
            color_by=self.color_by,
            x_log=self.x_log,
            renumber_cycles=self.renumber_cycles,
            legend_templates=dict(self.legend_templates),
            analysis_options=deepcopy(self.analysis_options),
            paper_layout=dict(self.paper_layout),
            extra=dict(self.extra),
            tab_name=self.tab_name,
        )

    def to_dict(self) -> dict[str, Any]:
        options = dict(self.analysis_options)
        if self.kind == "cv_contribution_vs_rate":
            options = _dunn_axis_limit_options(options, legacy=False)
        return {
            **{key: value for key, value in self.extra.items() if key != "follow_dataset"},
            "kind": self.kind,
            "run_ids": list(self.run_ids),
            "cycle_selection": {key: list(value) for key, value in self.cycle_selection.items()},
            "normalization": self.normalization,
            "target_voltage": self.target_voltage,
            "selected_scan_rate": self.selected_scan_rate,
            "fit_model": self.fit_model,
            "fit_enabled": self.fit_enabled,
            "frequency_low": self.frequency_low,
            "frequency_high": self.frequency_high,
            "show_legend": self.show_legend,
            "show_axes": self.show_axes,
            "annotations": self.annotations,
            "title": self.title,
            "tab_name": self.tab_name,
            "preset": self.preset,
            "overrides": dict(self.overrides),
            "color_by": self.color_by,
            "x_log": self.x_log,
            "renumber_cycles": self.renumber_cycles,
            "legend_templates": dict(self.legend_templates),
            "analysis_options": options,
            "paper_layout": dict(self.paper_layout),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlotSpec":
        data = dict(data)
        data.pop("follow_dataset", None)
        allowed = set(cls.__dataclass_fields__)
        values = {key: value for key, value in data.items() if key in allowed}
        values["extra"] = {**values.get("extra", {}), **{key: value for key, value in data.items() if key not in allowed}}
        values["extra"].pop("follow_dataset", None)
        if not isinstance(values.get("tab_name", ""), str):
            values["tab_name"] = ""
        if values.get("kind") == "cv_contribution_vs_rate" and "analysis_options" in values:
            # Older projects stored the raw Matplotlib category indices.
            values["analysis_options"] = _dunn_axis_limit_options(values["analysis_options"], legacy=True)
        return cls(**values)


def dunn_potential_window(spec: PlotSpec) -> Any:
    """Read the active branch's ROI; the analysis layer validates the value."""
    ranges = spec.analysis_options.get("dunn_roi_by_branch")
    if isinstance(ranges, dict):
        branch = spec.analysis_options.get("dunn_branch", "up")
        return ranges.get(branch) if isinstance(branch, str) else None
    return ranges
