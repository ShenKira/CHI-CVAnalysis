# -*- coding: utf-8 -*-
"""Central catalog and formatting helpers for in-plot text."""

from __future__ import annotations

import string
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

TEXT_CATEGORIES = ("axis", "title", "annotation", "legend")

DEFAULT_TEXT_PRESET_NAME = "default"
DEFAULT_TEXT_PRESET_LABEL = "默认图内文字（英文）"

_STRING_SAMPLES = {
    "unit": "unit",
    "label": "Sample",
    "model": "Rs-CPE",
    "x_term": "x",
    "y_term": "y",
    "current": "1 mA",
}

_MISSING = object()


@dataclass(frozen=True)
class TextField:
    key: str
    category: str
    group: str
    label: str
    default: str
    placeholders: tuple[str, ...] = ()


def _axis(group: str, suffix: str, label: str, default: str, placeholders: tuple[str, ...] = ()) -> TextField:
    return TextField(f"axis.{suffix}", "axis", group, label, default, placeholders)


def _title(key: str, group: str, default: str, placeholders: tuple[str, ...] = ()) -> TextField:
    return TextField(f"title.{key}", "title", group, "默认标题", default, placeholders)


def _annotation(group: str, key: str, label: str, default: str, placeholders: tuple[str, ...] = ()) -> TextField:
    return TextField(f"annotation.{key}", "annotation", group, label, default, placeholders)


def _legend(key: str, label: str, default: str, placeholders: tuple[str, ...] = ()) -> TextField:
    return TextField(f"legend.{key}", "legend", "固定图例与后缀", label, default, placeholders)


_CV_OVERLAY = "CV 叠加图"
_CV_CAP_SCAN = "电容-扫速"
_CV_CURRENT_SCAN = "固定电位电流-扫速"
_CV_BVALUE = "b 值分析"
_CV_CONTRIBUTION = "Dunn 电流分解"
_CV_CONTRIBUTION_VS_RATE = "贡献占比-扫速"
_CV_TRASATTI = "Trasatti 电荷分解"
_EIS_NYQUIST = "EIS Nyquist"
_EIS_BODE = "EIS Bode"
_EIS_FIT = "EIS 拟合"
_CP_GCD = "CP / GCD"
_CP_CAPACITY = "GCD 容量-循环"


TEXT_FIELDS: tuple[TextField, ...] = (
    _axis(_CV_OVERLAY, "cv_overlay.x", "X 轴标签", "Potential (V)"),
    _axis(_CV_OVERLAY, "cv_overlay.y_none", "Y 轴标签（原始电流）", "Current ({unit})", ("unit",)),
    _axis(_CV_OVERLAY, "cv_overlay.y_area", "Y 轴标签（面积归一化）", "Current density ({unit})", ("unit",)),
    _axis(_CV_OVERLAY, "cv_overlay.y_mass", "Y 轴标签（质量归一化）", "Specific current ({unit})", ("unit",)),
    _axis(_CV_CAP_SCAN, "cv_cap_scan.x", "X 轴标签", "Scan rate (V/s)"),
    _axis(_CV_CAP_SCAN, "cv_cap_scan.x_paper", "X 轴标签（论文紧凑）", "v (V/s)"),
    _axis(_CV_CAP_SCAN, "cv_cap_scan.y", "Y 轴标签", "Capacitance ({unit})", ("unit",)),
    _axis(_CV_CAP_SCAN, "cv_cap_scan.y_paper", "Y 轴标签（论文紧凑）", "C ({unit})", ("unit",)),
    _axis(_CV_CURRENT_SCAN, "cv_current_scan.x", "X 轴标签", "Scan rate (V/s)"),
    _axis(_CV_CURRENT_SCAN, "cv_current_scan.y_none", "Y 轴标签（原始电流）", "Current ({unit})", ("unit",)),
    _axis(_CV_CURRENT_SCAN, "cv_current_scan.y_area", "Y 轴标签（面积归一化）", "Current density ({unit})", ("unit",)),
    _axis(_CV_CURRENT_SCAN, "cv_current_scan.y_mass", "Y 轴标签（质量归一化）", "Specific current ({unit})", ("unit",)),
    _axis(_CV_BVALUE, "cv_bvalue.x", "X 轴标签", "Scan rate (V/s)"),
    _axis(_CV_BVALUE, "cv_bvalue.y_none", "Y 轴标签（原始电流）", "|Current| ({unit})", ("unit",)),
    _axis(_CV_BVALUE, "cv_bvalue.y_area", "Y 轴标签（面积归一化）", "|Current density| ({unit})", ("unit",)),
    _axis(_CV_BVALUE, "cv_bvalue.y_mass", "Y 轴标签（质量归一化）", "|Specific current| ({unit})", ("unit",)),
    _axis(_CV_CONTRIBUTION, "cv_contribution.x", "X 轴标签", "Potential (V)"),
    _axis(_CV_CONTRIBUTION, "cv_contribution.y_none", "Y 轴标签（原始电流）", "Current ({unit})", ("unit",)),
    _axis(_CV_CONTRIBUTION, "cv_contribution.y_area", "Y 轴标签（面积归一化）", "Current density ({unit})", ("unit",)),
    _axis(_CV_CONTRIBUTION, "cv_contribution.y_mass", "Y 轴标签（质量归一化）", "Specific current ({unit})", ("unit",)),
    _axis(_CV_CONTRIBUTION_VS_RATE, "cv_contribution_vs_rate.x", "X 轴标签", "Scan rate (V/s)"),
    _axis(_CV_CONTRIBUTION_VS_RATE, "cv_contribution_vs_rate.y", "Y 轴标签", "Contribution (%)"),
    _axis(_CV_TRASATTI, "cv_trasatti.x", "X 轴标签", "$v^{-1/2}$ (V/s)$^{-1/2}$"),
    _axis(_CV_TRASATTI, "cv_trasatti.y_none", "Y 轴标签（原始电荷）", "Charge ({unit})", ("unit",)),
    _axis(_CV_TRASATTI, "cv_trasatti.y_area", "Y 轴标签（面积归一化）", "Charge density ({unit})", ("unit",)),
    _axis(_CV_TRASATTI, "cv_trasatti.y_mass", "Y 轴标签（质量归一化）", "Specific charge ({unit})", ("unit",)),
    _axis(_EIS_NYQUIST, "eis_nyquist.x", "X 轴标签", "Z' ({unit})", ("unit",)),
    _axis(_EIS_NYQUIST, "eis_nyquist.y", "Y 轴标签", "-Z'' ({unit})", ("unit",)),
    _axis(_EIS_BODE, "eis_bode.phase_x", "相位图 X 轴标签", ""),
    _axis(_EIS_BODE, "eis_bode.phase_y", "相位图 Y 轴标签", "Phase angle (°)"),
    _axis(_EIS_BODE, "eis_bode.phase_y_paper", "相位图 Y 轴标签（论文紧凑）", "Phase (°)"),
    _axis(_EIS_BODE, "eis_bode.magnitude_x", "模量图 X 轴标签", "Frequency (Hz)"),
    _axis(_EIS_BODE, "eis_bode.magnitude_y", "模量图 Y 轴标签", "|Z| ({unit})", ("unit",)),
    _axis(_EIS_FIT, "eis_fit.nyquist_x", "Nyquist X 轴标签", "Z' ({unit})", ("unit",)),
    _axis(_EIS_FIT, "eis_fit.nyquist_y", "Nyquist Y 轴标签", "-Z'' ({unit})", ("unit",)),
    _axis(_EIS_FIT, "eis_fit.residual_x", "残差图 X 轴标签", "Frequency (Hz)"),
    _axis(_EIS_FIT, "eis_fit.residual_y", "残差图 Y 轴标签", "Residual ({unit})", ("unit",)),
    _axis(_CP_GCD, "cp_gcd.x", "X 轴标签", "Time (s)"),
    _axis(_CP_GCD, "cp_gcd.y", "Y 轴标签", "Potential (V)"),
    _axis(_CP_CAPACITY, "cp_capacity.x", "X 轴标签", "Cycle"),
    _axis(_CP_CAPACITY, "cp_capacity.y", "左轴 Y 标签", "Capacity ({unit})", ("unit",)),
    _axis(_CP_CAPACITY, "cp_capacity.efficiency_y", "右轴 Y 标签", "Coulombic efficiency (%)"),
    _title("cv_overlay", _CV_OVERLAY, ""),
    _title("cv_cap_scan", _CV_CAP_SCAN, "Capacitance vs scan rate"),
    _title("cv_current_scan", _CV_CURRENT_SCAN, "Current at {target:g} V", ("target",)),
    _title("cv_bvalue", _CV_BVALUE, "b-value at {target:g} V", ("target",)),
    _title("cv_contribution", _CV_CONTRIBUTION, "Dunn current decomposition at {scan_rate:g} V/s", ("scan_rate",)),
    _title("cv_contribution_vs_rate", _CV_CONTRIBUTION_VS_RATE, "Contribution vs scan rate"),
    _title("cv_trasatti", _CV_TRASATTI, "Trasatti charge separation"),
    _title("eis_nyquist", _EIS_NYQUIST, ""),
    _title("eis_bode", _EIS_BODE, ""),
    _title("eis_fit", _EIS_FIT, ""),
    _title("cp_gcd", _CP_GCD, ""),
    _title("cp_capacity", _CP_CAPACITY, ""),
    _annotation(_CV_OVERLAY, "cv_overlay.mean", "均值行", "Mean C = {mean:.4g} {unit}", ("mean", "unit")),
    _annotation(_CV_OVERLAY, "cv_overlay.sd", "标准差行", "SD = {sd:.4g} {unit}", ("sd", "unit")),
    _annotation(_CV_OVERLAY, "cv_overlay.n", "循环数行", "N = {n}", ("n",)),
    _annotation(_CV_OVERLAY, "cv_overlay.multi_runs", "多数据行数", "{runs} runs", ("runs",)),
    _annotation(_CV_OVERLAY, "cv_overlay.multi_cycles", "多数据循环数", "{cycles} cycles", ("cycles",)),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.equation_linear", "线性拟合方程", "C = {slope:.4g} v + {intercept:.4g} {unit}", ("slope", "intercept", "unit")),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.equation_coordinate", "坐标直线拟合方程", "{y_term} = {slope:.4g}·{x_term} + {intercept:.4g}", ("y_term", "slope", "x_term", "intercept")),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.equation_power", "幂律拟合方程", "C = {a:.4g} v^{n:.3f}", ("a", "n")),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.r2", "R² 行", "R² = {r2:.4f}", ("r2",)),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.compact_power", "紧凑幂律注释", "n={n:.2f}; R²={r2:.3f}", ("n", "r2")),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.compact_r2", "紧凑 R² 注释", "R²={r2:.3f}", ("r2",)),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.term_y_linear", "纵向变量（线性）", "C"),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.term_y_log", "纵向变量（对数）", "log10(C)"),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.term_x_linear", "横向变量（线性）", "v"),
    _annotation(_CV_CAP_SCAN, "cv_cap_scan.term_x_log", "横向变量（对数）", "log10(v)"),
    _annotation(_CV_BVALUE, "cv_bvalue.b", "b 值行", "b = {b:.3f}", ("b",)),
    _annotation(_CV_BVALUE, "cv_bvalue.r2", "R² 行", "R² = {r2:.4f}", ("r2",)),
    _annotation(_CV_BVALUE, "cv_bvalue.n", "数据数行", "N = {n}", ("n",)),
    _annotation(_CV_CONTRIBUTION, "cv_contribution.capacitive", "电容占比行", "Capacitive = {pct:.1f}%", ("pct",)),
    _annotation(_CV_CONTRIBUTION, "cv_contribution.mean_r2", "平均 R² 行", "Mean R² = {r2:.3f}", ("r2",)),
    _annotation(_CV_CONTRIBUTION_VS_RATE, "cv_contribution_vs_rate.n", "扫速数行", "N = {n} rates", ("n",)),
    _annotation(_CV_CONTRIBUTION_VS_RATE, "cv_contribution_vs_rate.mean_r2", "平均 R² 行", "Mean R² = {r2:.3f}", ("r2",)),
    _annotation(_CV_CONTRIBUTION_VS_RATE, "cv_contribution_vs_rate.bar_pct", "柱内百分比", "{pct:.0f}%", ("pct",)),
    _annotation(_CV_TRASATTI, "cv_trasatti.q_cap", "q_cap 行", "q_cap = {q_cap:.4g} {unit}", ("q_cap", "unit")),
    _annotation(_CV_TRASATTI, "cv_trasatti.fraction", "电容占比行", "Capacitive fraction = {pct:.1f}%", ("pct",)),
    _annotation(_CV_TRASATTI, "cv_trasatti.r2", "R² 行", "R² = {r2:.4f}", ("r2",)),
    _annotation(_EIS_NYQUIST, "eis.model", "拟合模型行", "{model}", ("model",)),
    _annotation(_EIS_NYQUIST, "eis.rs", "Rs 行", "Rs = {value}", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.rct", "Rct 行", "Rct = {value}", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.rct_approx", "Rct 估算行", "Rct ≈ {value}", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.ceff", "Ceff 行", "Ceff = {value}", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.cdl_approx", "Cdl 估算行", "Cdl ≈ {value}", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.f0", "f0 行", "f0 ≈ {value:.3g} Hz", ("value",)),
    _annotation(_EIS_NYQUIST, "eis.r2", "R² 行", "R² = {value:.4f}", ("value",)),
    _annotation(_CP_GCD, "cp_gcd.current", "电流行", "I = {current}", ("current",)),
    _annotation(_CP_GCD, "cp_gcd.cycles", "循环数行", "{n} GCD cycles", ("n",)),
    _annotation(_CP_GCD, "cp_gcd.q_specific", "比容量行", "Q_dis = {value:.4g} mAh/g", ("value",)),
    _annotation(_CP_GCD, "cp_gcd.q", "容量行", "Q_dis = {value:.4g} C", ("value",)),
    _annotation(_CP_GCD, "cp_gcd.ce", "库仑效率行", "CE = {value:.2f}%", ("value",)),
    _annotation(_CP_GCD, "cp_gcd.ir", "IR 降行", "IR drop = {value:.3g} V", ("value",)),
    _annotation(_CP_GCD, "cp_gcd.holds_completed", "保持段补全行", "Holds completed"),
    _legend("measured", "测量曲线", "Measured"),
    _legend("fitted_line", "拟合直线", "Fitted Line"),
    _legend("fitted_curve", "拟合曲线", "Fitted Curve"),
    _legend("total", "总电流", "Total"),
    _legend("capacitive", "电容分量", "Capacitive"),
    _legend("diffusive", "扩散分量", "Diffusive"),
    _legend("forward_current", "正扫电流", "Forward |i|"),
    _legend("reverse_current", "反扫电流", "Reverse |i|"),
    _legend("guide_b", "b 值参考线", "b = {guide:g}", ("guide",)),
    _legend("real_residual", "实部残差", "Real residual"),
    _legend("imag_residual", "虚部残差", "Imag residual"),
    _legend("eis_fit_suffix", "EIS 拟合后缀", "{label} fit", ("label",)),
    _legend("cp_current_suffix", "CP 电流后缀", "{label} ({current})", ("label", "current")),
    _legend("cp_discharge", "CP 放电", "{label} Discharge", ("label",)),
    _legend("cp_charge", "CP 充电", "{label} Charge", ("label",)),
    _legend("cp_efficiency", "CP 库仑效率", "{label} CE", ("label",)),
    _legend("cv_cycle", "CV 循环标签", "Cycle {cycle}", ("cycle",)),
    _legend("cv_cycle_range", "CV 循环范围标签", "Cycle {start}-{end}", ("start", "end")),
    _legend("cv_run_rate", "CV 扫速后缀", "{label} ({rate:g} V/s)", ("label", "rate")),
    _legend("cv_run_cycle", "CV 多数据循环标签", "{label} C{cycle}", ("label", "cycle")),
    _legend(
        "cv_run_cycle_range",
        "CV 多数据循环范围标签",
        "{label} C{start}-{end}",
        ("label", "start", "end"),
    ),
)

DEFAULT_TEXTS: dict[str, str] = {field.key: field.default for field in TEXT_FIELDS}
TEXT_FIELD_MAP: dict[str, TextField] = {field.key: field for field in TEXT_FIELDS}


def _sample_context(field: TextField) -> dict[str, Any]:
    return {
        name: _STRING_SAMPLES.get(name, 1.0)
        for name in field.placeholders
    }


def safe_format(template: str, context: Mapping[str, Any]) -> str:
    """Format known placeholders while preserving mathtext braces."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError:
        return template
    output: list[str] = []
    for literal, field_name, format_spec, conversion in parts:
        output.append(literal)
        if field_name is None:
            continue
        if field_name in context:
            value: Any = context[field_name]
            if conversion == "r":
                value = repr(value)
            elif conversion == "s":
                value = str(value)
            elif conversion == "a":
                value = ascii(value)
            output.append(format(value, format_spec or ""))
            continue
        token = "{" + field_name
        if conversion:
            token += "!" + conversion
        if format_spec:
            token += ":" + format_spec
        token += "}"
        output.append(token)
    return "".join(output)


def validate_text_template(key: str, template: str) -> tuple[bool, str]:
    field = TEXT_FIELD_MAP.get(key)
    if field is None:
        return True, ""
    if not isinstance(template, str):
        return False, "必须是字符串"
    if template == "" or template.strip() == "":
        return True, ""
    try:
        safe_format(template, _sample_context(field))
    except (ValueError, KeyError) as exc:
        return False, str(exc)
    return True, ""


def invalid_text_values(values: Mapping[str, Any] | None) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, Mapping):
        return ["文本预设 values 不是对象"]
    warnings: list[str] = []
    for key, value in values.items():
        if key not in TEXT_FIELD_MAP:
            continue
        if not isinstance(value, str):
            warnings.append(f"文本预设 {key} 不是字符串，已使用默认文字")
            continue
        valid, message = validate_text_template(key, value)
        if not valid:
            warnings.append(f"文本预设 {key} 格式无效，已使用默认文字: {message}")
    return warnings


def resolve_text_values(values: Mapping[str, Any] | None) -> dict[str, str]:
    result = dict(DEFAULT_TEXTS)
    if not isinstance(values, Mapping):
        return result
    for key, value in values.items():
        if key not in TEXT_FIELD_MAP or not isinstance(value, str) or value == "":
            continue
        valid, _ = validate_text_template(key, value)
        if valid:
            result[key] = value
    return result


def _template_from(values: Mapping[str, Any] | None, key: str) -> str:
    if isinstance(values, Mapping):
        value = values.get(key)
        if isinstance(value, str) and value != "":
            return value
    return DEFAULT_TEXTS.get(key, "")


def _format_from_values(values: Mapping[str, Any] | None, key: str, context: Mapping[str, Any]) -> str:
    template = _template_from(values, key)
    if template.strip() == "":
        return ""
    try:
        return safe_format(template, context)
    except (ValueError, KeyError):
        fallback = DEFAULT_TEXTS.get(key, "")
        if template == fallback:
            return fallback
        try:
            return safe_format(fallback, context)
        except (ValueError, KeyError):
            return fallback


def plot_text(spec, key: str, **context: Any) -> str:
    values = getattr(spec, "_cv_text_values", None)
    return _format_from_values(values if isinstance(values, Mapping) else None, key, context)


def text_from_values(values: Mapping[str, Any] | None, key: str, **context: Any) -> str:
    return _format_from_values(values, key, context)


@contextmanager
def plot_text_context(spec, values: Mapping[str, Any] | None) -> Iterator[None]:
    previous = getattr(spec, "_cv_text_values", _MISSING)
    spec._cv_text_values = resolve_text_values(values)
    try:
        yield
    finally:
        if previous is _MISSING:
            try:
                delattr(spec, "_cv_text_values")
            except AttributeError:
                pass
        else:
            spec._cv_text_values = previous


def axis_label_override(spec, section: str, side: str) -> str | None:
    options = getattr(spec, "analysis_options", None)
    labels = options.get("axis_labels") if isinstance(options, Mapping) else None
    entry = labels.get(section) if isinstance(labels, Mapping) else None
    if not isinstance(entry, Mapping) or side not in entry:
        return None
    value = entry.get(side)
    if not isinstance(value, str) or value == "":
        return None
    if value.strip() == "":
        return ""
    return value


def axis_text_key(
    kind: str,
    section: str,
    side: str,
    *,
    normalization: str = "none",
    compact: bool = False,
) -> str | None:
    if kind in {"cv_overlay", "cv_current_scan", "cv_bvalue", "cv_contribution"}:
        if side == "x":
            return f"axis.{kind}.x"
        if side == "y":
            mode = normalization if normalization in {"none", "area", "mass"} else "none"
            return f"axis.{kind}.y_{mode}"
        return None
    if kind == "cv_cap_scan":
        suffix = "_paper" if compact else ""
        return f"axis.cv_cap_scan.{side}{suffix}" if side in {"x", "y"} else None
    if kind == "cv_contribution_vs_rate":
        return f"axis.cv_contribution_vs_rate.{side}" if side in {"x", "y"} else None
    if kind == "cv_trasatti":
        if side == "x":
            return "axis.cv_trasatti.x"
        if side == "y":
            mode = normalization if normalization in {"none", "area", "mass"} else "none"
            return f"axis.cv_trasatti.y_{mode}"
        return None
    if kind == "eis_nyquist":
        return f"axis.eis_nyquist.{side}" if side in {"x", "y"} else None
    if kind == "eis_bode":
        suffix = "_paper" if compact and section == "phase" and side == "y" else ""
        return f"axis.eis_bode.{section}_{side}{suffix}"
    if kind == "eis_fit":
        return f"axis.eis_fit.{section}_{side}"
    if kind == "cp_gcd":
        return f"axis.cp_gcd.{side}" if side in {"x", "y"} else None
    if kind == "cp_capacity":
        if section == "efficiency":
            return "axis.cp_capacity.efficiency_y" if side == "y" else None
        return f"axis.cp_capacity.{side}" if side in {"x", "y"} else None
    return None


def compact_text_enabled(spec) -> bool:
    layout = getattr(spec, "paper_layout", None)
    if not isinstance(layout, Mapping) or not layout.get("enabled"):
        return False
    try:
        width = float(layout.get("fraction", 0.5)) * float(layout.get("text_width_mm", 160))
    except (TypeError, ValueError):
        return False
    return width <= 85


def axis_text(
    spec,
    section: str,
    side: str,
    *,
    normalization: str | None = None,
    compact: bool | None = None,
    **context: Any,
) -> str:
    override = axis_label_override(spec, section, side)
    if override is not None:
        return override
    mode = normalization if normalization is not None else getattr(spec, "normalization", "none")
    if compact is None:
        compact = compact_text_enabled(spec)
    key = axis_text_key(getattr(spec, "kind", ""), section, side, normalization=mode, compact=compact)
    if key is None:
        return ""
    return plot_text(spec, key, **context)


def default_axis_text(
    spec,
    section: str,
    side: str,
    values: Mapping[str, Any] | None,
    *,
    normalization: str | None = None,
    compact: bool | None = None,
    **context: Any,
) -> str:
    mode = normalization if normalization is not None else getattr(spec, "normalization", "none")
    if compact is None:
        compact = compact_text_enabled(spec)
    key = axis_text_key(getattr(spec, "kind", ""), section, side, normalization=mode, compact=compact)
    if key is None:
        return ""
    return text_from_values(values, key, **context)


def category_fields(category: str) -> list[TextField]:
    return [field for field in TEXT_FIELDS if field.category == category]


__all__ = [
    "DEFAULT_TEXTS",
    "DEFAULT_TEXT_PRESET_LABEL",
    "DEFAULT_TEXT_PRESET_NAME",
    "TEXT_CATEGORIES",
    "TEXT_FIELDS",
    "TEXT_FIELD_MAP",
    "TextField",
    "axis_label_override",
    "axis_text",
    "axis_text_key",
    "category_fields",
    "compact_text_enabled",
    "default_axis_text",
    "invalid_text_values",
    "plot_text",
    "plot_text_context",
    "resolve_text_values",
    "safe_format",
    "text_from_values",
    "validate_text_template",
]
