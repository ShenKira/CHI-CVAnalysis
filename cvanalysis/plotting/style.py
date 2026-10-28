# -*- coding: utf-8 -*-
"""Plot style model and matplotlib helpers."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

import matplotlib as mpl
import matplotlib.colors as mcolors
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from cvanalysis.domain.units import UnitFamily, choose_unit_for_values


DEFAULT_COLOR_CYCLE = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
)

COLORBLIND_CYCLE = (
    "#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00",
    "#56B4E9", "#F0E442", "#000000",
)

_FLOAT_FIELDS = {
    "font_size", "title_size", "label_size", "tick_size", "legend_size",
    "annotation_size", "line_width", "marker_size", "axes_linewidth",
    "tick_width", "tick_length", "grid_width", "grid_alpha",
}
_ZERO_ALLOWED_FLOATS = {"tick_length"}
_OPTIONAL_FLOAT_FIELDS = {"xlabel_size", "ylabel_size"}
_INT_FIELDS = {"dpi", "save_dpi", "legend_columns"}
_BOOL_FIELDS = {
    "title_bold", "label_bold", "annotation_bold", "minor_ticks",
    "spines_top", "spines_right", "ticks_top", "ticks_right",
    "grid", "legend", "legend_frame",
    "legend_shadow", "annotation", "show_title", "tight_layout",
    "constrained_layout", "nyquist_equal_aspect", "save_bbox_inches",
}
_OPTIONAL_BOOL_FIELDS = {"xlabel_bold", "ylabel_bold"}
_STRING_FIELDS = {
    "name", "label", "marker", "tick_direction", "grid_color", "grid_style",
    "legend_location", "axes_aspect", "math_fontset", "figure_facecolor",
    "axes_facecolor",
}
_COLOR_FIELDS = {"grid_color", "figure_facecolor", "axes_facecolor"}
_ASPECT_VALUES = {"auto", "1:1", "4:3", "16:9"}

_CJK_FONT_CACHE: list[str] | None = None

# Figures use one logical height. Width is derived from the canvas aspect ratio
# so previews and exports share the same geometry.
CANVAS_HEIGHT_IN = 3.2


def canvas_size_for_ratio(aspect_ratio: float) -> tuple[float, float]:
    ratio = float(aspect_ratio)
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("画布宽高比必须为有限正数")
    return (CANVAS_HEIGHT_IN * ratio, CANVAS_HEIGHT_IN)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def _coerce_float(value: Any, *, minimum: float, maximum: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _coerce_int(value: Any, *, minimum: int) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if number < minimum:
        return None
    return number


def _available_cjk_fonts() -> list[str]:
    global _CJK_FONT_CACHE
    if _CJK_FONT_CACHE is not None:
        return _CJK_FONT_CACHE
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
    ]
    _CJK_FONT_CACHE = [name for name in candidates if name in available]
    return _CJK_FONT_CACHE


@dataclass
class PlotStyle:
    name: str = "daily"
    label: str = "日常分析"
    figure_size: tuple[float, float] = canvas_size_for_ratio(4.0 / 3.0)
    dpi: int = 100
    save_dpi: int = 300
    font_family: tuple[str, ...] = ("Times New Roman", "STIXGeneral", "DejaVu Serif")
    font_size: float = 12.0
    title_size: float = 20.0
    label_size: float = 20.0
    xlabel_size: float | None = None
    ylabel_size: float | None = None
    tick_size: float = 14.0
    legend_size: float = 12.0
    annotation_size: float = 14.0
    title_bold: bool = True
    label_bold: bool = True
    xlabel_bold: bool | None = None
    ylabel_bold: bool | None = None
    annotation_bold: bool = False
    line_width: float = 2.0
    marker: str = ""
    marker_size: float = 4.0
    axes_linewidth: float = 1.0
    tick_direction: str = "in"
    tick_width: float = 1.5
    tick_length: float = 6.0
    minor_ticks: bool = False
    spines_top: bool = True
    spines_right: bool = True
    ticks_top: bool = True
    ticks_right: bool = True
    grid: bool = True
    grid_color: str = "#cccccc"
    grid_style: str = "--"
    grid_width: float = 0.8
    grid_alpha: float = 0.3
    legend: bool = True
    legend_frame: bool = True
    legend_shadow: bool = True
    legend_columns: int = 2
    legend_location: str = "best"
    annotation: bool = True
    show_title: bool = False
    tight_layout: bool = True
    constrained_layout: bool = False
    nyquist_equal_aspect: bool = True
    axes_aspect: str = "auto"
    math_fontset: str = "stix"
    figure_facecolor: str = "white"
    axes_facecolor: str = "white"
    color_cycle: tuple[str, ...] = DEFAULT_COLOR_CYCLE
    save_bbox_inches: bool = True

    def __post_init__(self) -> None:
        """Normalize legacy width/height pairs to the shared canvas height.

        Existing project and preset files still carry ``figure_size`` pairs.
        Treat their ratio as the migration input while making the height
        consistent in memory.
        """
        try:
            width, height = (float(value) for value in self.figure_size)
            ratio = width / height
        except (TypeError, ValueError, ZeroDivisionError):
            return
        if math.isfinite(ratio) and ratio > 0:
            self.figure_size = canvas_size_for_ratio(ratio)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, name: str | None = None) -> "PlotStyle":
        known = {field.name for field in fields(cls)}
        defaults = {field.name: field.default for field in fields(cls)}
        values: dict[str, Any] = {}
        for key, value in (data if isinstance(data, dict) else {}).items():
            if key not in known:
                continue
            default = defaults[key]
            try:
                if key == "figure_size":
                    if not isinstance(value, (list, tuple)) or len(value) != 2:
                        continue
                    pair = tuple(float(item) for item in value)
                    if not all(math.isfinite(item) and item > 0 for item in pair):
                        continue
                    values[key] = pair
                elif key == "font_family":
                    items = [value] if isinstance(value, str) else list(value or [])
                    families = tuple(
                        str(item).strip()
                        for item in items
                        if isinstance(item, str) and item.strip()
                    )
                    if families:
                        values[key] = families
                elif key == "color_cycle":
                    items = [value] if isinstance(value, str) else list(value or [])
                    colors: list[str] = []
                    for color in items:
                        try:
                            if isinstance(color, str):
                                if not mcolors.is_color_like(color):
                                    continue
                                colors.append(color)
                            else:
                                colors.append(mcolors.to_hex(color))
                        except (TypeError, ValueError):
                            continue
                    if colors:
                        values[key] = tuple(colors)
                elif key in _FLOAT_FIELDS:
                    minimum = 0.0 if key in _ZERO_ALLOWED_FLOATS else 1e-9
                    maximum = 1.0 if key == "grid_alpha" else None
                    number = _coerce_float(value, minimum=minimum, maximum=maximum)
                    if number is not None:
                        values[key] = number
                elif key in _OPTIONAL_FLOAT_FIELDS:
                    if value is None:
                        values[key] = None
                    else:
                        number = _coerce_float(value, minimum=1e-9)
                        if number is not None:
                            values[key] = number
                elif key in _INT_FIELDS:
                    number = _coerce_int(value, minimum=1)
                    if number is not None:
                        values[key] = number
                elif key in _BOOL_FIELDS:
                    values[key] = _coerce_bool(value, bool(default))
                elif key in _OPTIONAL_BOOL_FIELDS:
                    values[key] = (
                        None if value is None else _coerce_bool(value, bool(default))
                    )
                elif key in _STRING_FIELDS:
                    if value is not None:
                        text = str(value)
                        if key in _COLOR_FIELDS and not mcolors.is_color_like(text):
                            continue
                        if key == "axes_aspect" and text not in _ASPECT_VALUES:
                            continue
                        if key == "tick_direction" and text not in {"in", "out"}:
                            continue
                        values[key] = text
            except (TypeError, ValueError):
                continue
        if name:
            values["name"] = name
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["figure_size"] = list(self.figure_size)
        data["font_family"] = list(self.font_family)
        data["color_cycle"] = list(self.color_cycle)
        return data

    def with_overrides(self, overrides: dict[str, Any] | None) -> "PlotStyle":
        if not overrides:
            return replace(self)
        return self.from_dict({**self.to_dict(), **(overrides or {})})

    def effective_xlabel_size(self) -> float:
        return self.xlabel_size if self.xlabel_size is not None else self.label_size

    def effective_ylabel_size(self) -> float:
        return self.ylabel_size if self.ylabel_size is not None else self.label_size

    def effective_xlabel_bold(self) -> bool:
        return self.xlabel_bold if self.xlabel_bold is not None else self.label_bold

    def effective_ylabel_bold(self) -> bool:
        return self.ylabel_bold if self.ylabel_bold is not None else self.label_bold

    def effective_ticks_top(self) -> bool:
        return self.spines_top and self.ticks_top

    def effective_ticks_right(self) -> bool:
        return self.spines_right and self.ticks_right

    def rc(self) -> dict[str, Any]:
        families = list(self.font_family)
        return {
            "font.family": families,
            "font.serif": families,
            "font.sans-serif": families,
            "font.size": self.font_size,
            "mathtext.fontset": self.math_fontset,
            "axes.unicode_minus": False,
            "figure.facecolor": self.figure_facecolor,
            "axes.facecolor": self.axes_facecolor,
            "savefig.facecolor": self.figure_facecolor,
        }

    def apply(self, figure: Figure) -> None:
        figure.set_facecolor(self.figure_facecolor)
        for ax in figure.axes:
            self.apply_axes(ax)

    def apply_axes(self, ax: Axes) -> None:
        ax.set_facecolor(self.axes_facecolor)
        for spine in ax.spines.values():
            spine.set_linewidth(self.axes_linewidth)
        ax.spines["top"].set_visible(self.spines_top)
        ax.spines["right"].set_visible(self.spines_right)
        ticks_top = self.effective_ticks_top()
        ticks_right = self.effective_ticks_right()
        ax.tick_params(
            axis="both",
            which="major",
            direction=self.tick_direction,
            width=self.tick_width,
            length=self.tick_length,
            labelsize=self.tick_size,
            top=ticks_top,
            right=ticks_right,
        )
        if self.minor_ticks:
            ax.minorticks_on()
            ax.tick_params(
                axis="both",
                which="minor",
                direction=self.tick_direction,
                width=max(0.4, self.tick_width * 0.6),
                length=max(1.0, self.tick_length * 0.55),
                top=ticks_top,
                right=ticks_right,
            )
        if self.grid:
            ax.grid(
                True,
                color=self.grid_color,
                linestyle=self.grid_style,
                linewidth=self.grid_width,
                alpha=self.grid_alpha,
            )
            ax.set_axisbelow(True)
        else:
            ax.grid(False)
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontfamily(self.font_family)
            label.set_fontsize(self.tick_size)

    def style_legend(self, legend):
        if legend is None:
            return
        legend.set_frame_on(self.legend_frame)
        legend.shadow = self.legend_shadow
        families = list(self.font_family)
        for name in _available_cjk_fonts():
            if name not in families:
                families.append(name)
        for text in legend.get_texts():
            text.set_fontfamily(families)
            text.set_fontsize(self.legend_size)
        if legend.legend_handles:
            for handle in legend.legend_handles:
                try:
                    handle.set_linewidth(self.line_width)
                except Exception:
                    pass


def font_kwargs(
    style: PlotStyle,
    *,
    size: float | None = None,
    bold: bool | None = None,
    axis: str | None = None,
) -> dict[str, Any]:
    if size is None:
        if axis == "x":
            size = style.effective_xlabel_size()
        elif axis == "y":
            size = style.effective_ylabel_size()
        else:
            size = style.label_size
    if bold is None:
        if axis == "x":
            bold = style.effective_xlabel_bold()
        elif axis == "y":
            bold = style.effective_ylabel_bold()
        else:
            bold = style.label_bold
    return {
        "fontfamily": style.font_family,
        "fontsize": size,
        "fontweight": "bold" if bold else "normal",
    }


def auto_axis_unit(values, family: UnitFamily, *, use_max: bool = True):
    return choose_unit_for_values(family, values, use_max=use_max)


def apply_axis_style_to_figure(figure: Figure, style: PlotStyle) -> None:
    with mpl.rc_context(style.rc()):
        style.apply(figure)


def get_colors(style: PlotStyle, count: int) -> list[str]:
    if count <= 0:
        return []
    colors = list(style.color_cycle) or list(DEFAULT_COLOR_CYCLE)
    if len(colors) >= count:
        return colors[:count]
    repeats = (count + len(colors) - 1) // len(colors)
    return (colors * repeats)[:count]


def clear_figure(figure: Figure) -> None:
    figure.clear()
    figure.set_facecolor("white")


def finalize_figure(figure: Figure, style: PlotStyle) -> None:
    if style.constrained_layout:
        try:
            figure.set_layout_engine("constrained")
        except Exception:
            pass
    elif style.tight_layout:
        try:
            figure.tight_layout()
        except Exception:
            pass
    style.apply(figure)
    aspect_ratio = {"1:1": 1.0, "4:3": 3.0 / 4.0, "16:9": 9.0 / 16.0}.get(style.axes_aspect)
    if aspect_ratio is not None and len(figure.axes) == 1:
        try:
            figure.axes[0].set_box_aspect(aspect_ratio)
        except Exception:
            pass
