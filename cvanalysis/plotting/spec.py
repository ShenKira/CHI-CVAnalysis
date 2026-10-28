# -*- coding: utf-8 -*-
"""Serializable description of a plot document."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    follow_dataset: bool = False
    analysis_options: dict[str, Any] = field(default_factory=dict)
    paper_layout: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

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
            follow_dataset=self.follow_dataset,
            analysis_options=dict(self.analysis_options),
            paper_layout=dict(self.paper_layout),
            extra=dict(self.extra),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra,
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
            "preset": self.preset,
            "overrides": dict(self.overrides),
            "color_by": self.color_by,
            "x_log": self.x_log,
            "renumber_cycles": self.renumber_cycles,
            "legend_templates": dict(self.legend_templates),
            "follow_dataset": self.follow_dataset,
            "analysis_options": dict(self.analysis_options),
            "paper_layout": dict(self.paper_layout),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlotSpec":
        allowed = set(cls.__dataclass_fields__)
        values = {key: value for key, value in data.items() if key in allowed}
        values["extra"] = {**values.get("extra", {}), **{key: value for key, value in data.items() if key not in allowed}}
        return cls(**values)
