# -*- coding: utf-8 -*-
"""Legend label templates shared by renderers and UI previews."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from cvanalysis.domain.models import CPRun, CVRun, EISRun


@dataclass(frozen=True)
class LegendToken:
    token: str
    label: str
    description: str
    kinds: str = "all"

    @property
    def placeholder(self) -> str:
        return "{" + self.token + "}"


LEGEND_TOKENS: tuple[LegendToken, ...] = (
    LegendToken("file_n", "文件序号", "数据集中当前文件顺序，从 1 开始；同一源文件共用序号"),
    LegendToken("cycle_n", "文件内循环号", "当前 CV 文件内的原始循环号，不受循环重编号影响", "cv"),
    LegendToken("File_Name", "文件名", "源文件名（不含扩展名）"),
    LegendToken("Sample_Name", "数据名称", "导入时显示的数据名称"),
    LegendToken("Run_Index", "序号", "同一文件内数据的序号，从 1 开始"),
    LegendToken("CV_Voltage", "CV 上限电位", "CV 上限电位，例如 1.5V", "cv"),
    LegendToken("CV_Low", "CV 下限电位", "CV 下限电位", "cv"),
    LegendToken("CV_High", "CV 上限电位", "CV 上限电位", "cv"),
    LegendToken("CV_Window", "CV 电压窗口", "上限减下限", "cv"),
    LegendToken("Scan_Rate", "扫速", "CV 扫速，例如 0.01V/s", "cv"),
    LegendToken("Cycle_Number", "循环号", "循环序号；勾选重编号时使用显示序号", "cv"),
    LegendToken("High_Freq", "高频", "EIS 最高频率", "eis"),
    LegendToken("Low_Freq", "低频", "EIS 最低频率", "eis"),
    LegendToken("Points", "点数", "数据点数", "eis"),
    LegendToken("Current", "CP 电流", "CP 施加电流，自动选择 A/mA/µA 单位", "cp"),
    LegendToken("CP_Window", "CP 电位窗口", "CP 高电位减低压", "cp"),
    LegendToken("Hold_Time", "保持时间", "CP 高/低电位保持时间；无记录时为空", "cp"),
    LegendToken("Area_cm2", "电极面积", "电极面积，例如 0.5cm²"),
    LegendToken("Mass_mg", "活性物质质量", "活性物质质量，例如 2mg"),
)

_TOKEN_LOOKUP = {token.token.lower(): token for token in LEGEND_TOKENS}
_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")


def legend_tokens(kind: str | None = None) -> list[LegendToken]:
    if kind is None:
        return list(LEGEND_TOKENS)
    return [token for token in LEGEND_TOKENS if token.kinds in {"all", kind}]


def _normalize_token(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip().lower())


def template_uses_cycle(template: str) -> bool:
    template = str(template or "")
    if not template:
        return False
    return any(_normalize_token(match.group(1)) in {"cycle_number", "cycle_n"} for match in _TOKEN_PATTERN.finditer(template))


def file_numbers_for_runs(runs: Iterable[CVRun | EISRun | CPRun]) -> dict[str, int]:
    """Number source files by their first appearance in the dataset tree."""
    numbers = {}
    sources = {}
    for run in runs:
        key = ("source", run.source.resolve()) if run.source else ("run", run.run_id)
        if key not in sources:
            sources[key] = len(sources) + 1
        numbers[run.run_id] = sources[key]
    return numbers


def dataset_file_numbers(dataset) -> dict[str, int]:
    return file_numbers_for_runs(
        [
            *getattr(dataset, "cv_runs", []),
            *getattr(dataset, "eis_runs", []),
            *getattr(dataset, "cp_runs", []),
        ]
    )


def _format_number(value: float | None, unit: str = "") -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not (number == number):
        return ""
    return f"{number:g}{unit}"


def _context(run: CVRun | EISRun | CPRun, cycle=None, cycle_number: int | None = None,
             file_number: int | None = None) -> dict[str, str]:
    source_name = run.source.stem if run.source else run.display_name
    values: dict[str, str] = {
        "file_name": source_name,
        "sample_name": run.display_name,
        "run_index": str(run.run_index + 1),
        "file_n": str(file_number) if file_number is not None else "",
        "area_cm2": _format_number(run.params.area_cm2, "cm²"),
        "mass_mg": _format_number(run.params.mass_mg, "mg"),
    }
    if isinstance(run, CVRun):
        high = run.metadata.high_e
        low = run.metadata.low_e
        if high is None and run.potential.size:
            high = float(max(run.potential))
        if low is None and run.potential.size:
            low = float(min(run.potential))
        window = run.metadata.voltage_window
        if window is None and high is not None and low is not None:
            window = abs(high - low)
        values.update(
            {
                "cv_voltage": _format_number(high, "V"),
                "cv_low": _format_number(low, "V"),
                "cv_high": _format_number(high, "V"),
                "cv_window": _format_number(window, "V"),
                "scan_rate": _format_number(run.metadata.scan_rate, "V/s"),
                "cycle_number": str(cycle_number if cycle_number is not None else (cycle.index if cycle is not None else "")),
                "cycle_n": str(cycle.index) if cycle is not None else "",
                "points": str(len(run.potential)),
            }
        )
    elif isinstance(run, EISRun):
        values.update(
            {
                "high_freq": _format_number(run.metadata.high_freq, "Hz"),
                "low_freq": _format_number(run.metadata.low_freq, "Hz"),
                "points": str(len(run.freq)),
            }
        )
    else:
        values.update(
            {
                "current": _format_number(run.applied_current_A, "A"),
                "cp_window": _format_number(run.voltage_window, "V"),
                "hold_time": _format_number(run.metadata.hold_duration_s, "s"),
                "points": str(len(run.time)),
            }
        )
    return values


def render_legend_template(
    template: str,
    run: CVRun | EISRun | CPRun,
    *,
    cycle=None,
    cycle_number: int | None = None,
    file_number: int | None = None,
) -> tuple[str, list[str]]:
    """Expand a legend template.

    Unknown placeholders are kept verbatim and reported so the caller can show
    a warning instead of silently producing a misleading legend.
    """
    template = str(template or "")
    if not template:
        return "", []
    values = _context(run, cycle=cycle, cycle_number=cycle_number, file_number=file_number)
    unknown: list[str] = []

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        key = _normalize_token(raw)
        if key not in _TOKEN_LOOKUP:
            if raw not in unknown:
                unknown.append(raw)
            return match.group(0)
        value = values.get(key, "")
        return value

    return _TOKEN_PATTERN.sub(replace, template), unknown


def effective_template(run: CVRun | EISRun | CPRun, spec) -> str:
    """Resolve the per-plot override, then the data-level template."""
    overrides = getattr(spec, "legend_templates", None) or {}
    if run.run_id in overrides:
        return str(overrides[run.run_id] or "")
    return str(getattr(run, "legend_template", "") or "")


def default_run_label(run: CVRun | EISRun | CPRun) -> str:
    return run.legend_name


def preview_label(
    run: CVRun | EISRun | CPRun,
    template: str,
    *,
    cycle=None,
    cycle_number: int | None = None,
    file_number: int | None = None,
    fallback: str | None = None,
) -> tuple[str, list[str]]:
    if template:
        rendered, unknown = render_legend_template(
            template,
            run,
            cycle=cycle,
            cycle_number=cycle_number,
            file_number=file_number,
        )
        if rendered.strip():
            return rendered, unknown
        if fallback is not None:
            return fallback, unknown
    return (fallback if fallback is not None else default_run_label(run)), []
