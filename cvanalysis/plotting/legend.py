# -*- coding: utf-8 -*-
"""Legend label templates shared by renderers and UI previews."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from cvanalysis.domain.models import CPRun, CVRun, EISRun, abbreviate_name
from cvanalysis.plotting.texts import text_from_values


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
    LegendToken("Alias", "图例别名", "手动设置的图例别名；未设置时为空"),
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

DEFAULT_CYCLE_LEGEND_LIMIT = 10


@dataclass(frozen=True)
class CycleLegendGroup:
    """A contiguous group of CV cycles represented by one legend entry."""

    cycles: tuple
    start: int
    end: int


def cycle_legend_limit(spec) -> int:
    """Return the active per-run cycle legend limit.

    ``0`` disables merging, which is useful for users who explicitly want one
    legend entry per cycle.  Invalid values fall back to the safe default.
    """
    options = getattr(spec, "analysis_options", None) or {}
    raw = options.get("legend_cycle_limit", DEFAULT_CYCLE_LEGEND_LIMIT)
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_CYCLE_LEGEND_LIMIT
    return max(0, value)


def cycle_legend_groups(
    cycles,
    limit: int,
    *,
    renumber: bool = False,
) -> list[CycleLegendGroup] | None:
    """Split selected cycles into at most ``limit`` balanced legend groups.

    Returns ``None`` when no grouping is needed, so callers can keep the
    original per-cycle path unchanged.  Labels use the displayed sequence
    number when ``renumber`` is true, otherwise the original cycle index.
    """
    ordered = list(cycles)
    if limit <= 0 or len(ordered) <= limit:
        return None
    base, extra = divmod(len(ordered), limit)
    groups: list[CycleLegendGroup] = []
    start = 0
    for group_index in range(limit):
        size = base + (1 if group_index < extra else 0)
        if size <= 0:
            continue
        chunk = tuple(ordered[start : start + size])
        first = start + 1 if renumber else int(chunk[0].index)
        last = start + size if renumber else int(chunk[-1].index)
        groups.append(CycleLegendGroup(chunk, first, last))
        start += size
    return groups


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


def dataset_runs(dataset) -> list[CVRun | EISRun | CPRun]:
    """All runs from a Dataset or a lightweight duck-typed test dataset."""
    return [
        *getattr(dataset, "cv_runs", []),
        *getattr(dataset, "eis_runs", []),
        *getattr(dataset, "cp_runs", []),
    ]


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
        "alias": str(getattr(run, "legend_alias", "") or "").strip(),
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


@dataclass(frozen=True)
class ResolvedLegendLabel:
    """The automatic default label for one run/legend entry."""

    label: str
    manual: bool = False
    auto: bool = False
    compact: bool = False


def default_filename_label(run: CVRun | EISRun | CPRun) -> str:
    """Default filename label, before any similarity-aware compaction."""
    return abbreviate_name(run.display_name, 26)


def _longest_common_prefix(values: Iterable[str]) -> str:
    items = [str(value or "") for value in values]
    if not items:
        return ""
    prefix = items[0]
    for value in items[1:]:
        while prefix and not value.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            break
    return prefix


def _similar_names(first: str, second: str) -> bool:
    first = str(first or "")
    second = str(second or "")
    if not first or not second:
        return False
    shorter = min(len(first), len(second))
    if shorter < 6:
        return False
    prefix = _longest_common_prefix([first, second])
    if len(prefix) >= max(10, int(0.4 * shorter)):
        return True
    return SequenceMatcher(None, first, second).ratio() >= 0.82


def similar_name_families(
    runs: Iterable[CVRun | EISRun | CPRun],
) -> list[list[CVRun | EISRun | CPRun]]:
    """Group same-kind runs whose file names share a meaningful stem."""
    ordered = list(runs)
    parents = list(range(len(ordered)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(ordered)):
        for right in range(left + 1, len(ordered)):
            if type(ordered[left]) is not type(ordered[right]):
                continue
            if _similar_names(ordered[left].display_name, ordered[right].display_name):
                union(left, right)

    families: dict[int, list[CVRun | EISRun | CPRun]] = {}
    for index, run in enumerate(ordered):
        families.setdefault(find(index), []).append(run)
    return list(families.values())


def _family_needs_compact(family: Iterable[CVRun | EISRun | CPRun]) -> bool:
    runs = list(family)
    if len(runs) < 2:
        return False
    names = [run.display_name for run in runs]
    if max((len(name) for name in names), default=0) > 24:
        return True
    labels = [default_filename_label(run) for run in runs]
    return len(set(labels)) < len(labels)


def _compact_template_key(run: CVRun | EISRun | CPRun) -> str:
    if isinstance(run, CVRun):
        return "legend.cv_compact"
    if isinstance(run, CPRun):
        return "legend.cp_compact"
    return "legend.eis_compact"


def _compact_label(
    run: CVRun | EISRun | CPRun,
    *,
    spec=None,
    file_number: int | None = None,
    text_values: dict | None = None,
) -> str:
    values = text_values
    if values is None and spec is not None:
        values = getattr(spec, "_cv_text_values", None)
    template = text_from_values(values, _compact_template_key(run))
    label, unknown = render_legend_template(
        template,
        run,
        file_number=file_number,
    )
    if unknown or not label.strip():
        return default_filename_label(run)
    return label.strip()


def resolve_legend_labels(
    runs: Iterable[CVRun | EISRun | CPRun],
    *,
    spec=None,
    file_numbers: dict[str, int] | None = None,
    text_values: dict | None = None,
) -> dict[str, ResolvedLegendLabel]:
    """Resolve automatic labels for a group of runs.

    Rules, in order: manual alias, similar-name compact mode, long-filename
    abbreviation, plain filename. Duplicate automatic labels receive a short
    file/run suffix so a legend never silently collapses two series.
    """
    ordered = list(runs)
    if not ordered:
        return {}
    numbers = file_numbers if file_numbers is not None else file_numbers_for_runs(ordered)
    compact_ids: set[str] = set()
    for family in similar_name_families(ordered):
        if _family_needs_compact(family):
            compact_ids.update(run.run_id for run in family)

    result: dict[str, ResolvedLegendLabel] = {}
    for run in ordered:
        alias = str(getattr(run, "legend_alias", "") or "").strip()
        if alias:
            result[run.run_id] = ResolvedLegendLabel(alias, manual=True)
        elif run.run_id in compact_ids:
            result[run.run_id] = ResolvedLegendLabel(
                _compact_label(
                    run,
                    spec=spec,
                    file_number=numbers.get(run.run_id),
                    text_values=text_values,
                ),
                auto=True,
                compact=True,
            )
        else:
            label = default_filename_label(run)
            result[run.run_id] = ResolvedLegendLabel(
                label,
                auto=len(run.display_name) > 26,
            )

    # Seed manual aliases first so an automatic label cannot take a manual
    # alias's exact text depending on dataset order.  Manual aliases themselves
    # are left verbatim; users are responsible for making them unique.
    used: set[str] = {
        decision.label for decision in result.values() if decision.manual
    }
    for run in ordered:
        decision = result[run.run_id]
        label = decision.label
        if label in used and not decision.manual:
            file_number = numbers.get(run.run_id)
            suffix = f" #{file_number}" if file_number is not None else f" #{run.run_index + 1}"
            candidate = label + suffix
            counter = 2
            while candidate in used:
                candidate = f"{label}{suffix} ({counter})"
                counter += 1
            result[run.run_id] = ResolvedLegendLabel(
                candidate,
                manual=decision.manual,
                auto=True,
                compact=decision.compact,
            )
            label = candidate
        used.add(label)
    return result
