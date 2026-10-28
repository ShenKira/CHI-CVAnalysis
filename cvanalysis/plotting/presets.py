# -*- coding: utf-8 -*-
"""Built-in plot presets and preset resolution."""

from __future__ import annotations

from cvanalysis.plotting.style import (
    CANVAS_HEIGHT_IN,
    COLORBLIND_CYCLE,
    DEFAULT_COLOR_CYCLE,
    PlotStyle,
)


def _canvas_size(aspect_ratio: float) -> tuple[float, float]:
    return (CANVAS_HEIGHT_IN * aspect_ratio, CANVAS_HEIGHT_IN)


BUILTIN_PRESETS: dict[str, PlotStyle] = {
    "daily": PlotStyle(
        name="daily",
        label="日常分析",
        figure_size=_canvas_size(4.0 / 3.0),
        dpi=100,
        save_dpi=300,
        font_size=14.0,
        title_size=20.0,
        label_size=20.0,
        tick_size=14.0,
        legend_size=12.0,
        annotation_size=14.0,
        title_bold=True,
        label_bold=True,
        annotation_bold=True,
        line_width=2.0,
        axes_linewidth=1.0,
        tick_direction="in",
        tick_width=1.5,
        tick_length=6.0,
        grid=True,
        grid_color="#cccccc",
        grid_style="--",
        grid_width=0.8,
        grid_alpha=0.3,
        legend=True,
        legend_frame=True,
        legend_shadow=True,
        legend_columns=2,
        annotation=True,
        color_cycle=DEFAULT_COLOR_CYCLE,
    ),
    "ieee-single": PlotStyle(
        name="ieee-single",
        label="IEEE 单栏",
        figure_size=_canvas_size(1.25),
        dpi=100,
        save_dpi=600,
        font_family=("Arial", "DejaVu Sans"),
        math_fontset="dejavusans",
        font_size=8.0,
        title_size=8.0,
        label_size=8.0,
        tick_size=7.0,
        legend_size=7.0,
        annotation_size=7.0,
        title_bold=False,
        label_bold=False,
        annotation_bold=False,
        line_width=1.0,
        axes_linewidth=1.0,
        tick_direction="in",
        tick_width=0.8,
        tick_length=3.5,
        minor_ticks=True,
        spines_top=False,
        spines_right=False,
        grid=False,
        legend=True,
        legend_frame=False,
        legend_shadow=False,
        legend_columns=1,
        annotation=False,
        show_title=False,
        tight_layout=True,
        color_cycle=COLORBLIND_CYCLE,
        save_bbox_inches=False,
    ),
    "ieee-double": PlotStyle(
        name="ieee-double",
        label="IEEE 双栏",
        figure_size=_canvas_size(7.16 / 3.2),
        dpi=100,
        save_dpi=600,
        font_family=("Arial", "DejaVu Sans"),
        math_fontset="dejavusans",
        font_size=9.0,
        title_size=9.0,
        label_size=9.0,
        tick_size=8.0,
        legend_size=8.0,
        annotation_size=8.0,
        title_bold=False,
        label_bold=False,
        annotation_bold=False,
        line_width=1.2,
        axes_linewidth=1.0,
        tick_direction="in",
        tick_width=0.8,
        tick_length=4.0,
        minor_ticks=True,
        spines_top=False,
        spines_right=False,
        grid=False,
        legend=True,
        legend_frame=False,
        legend_shadow=False,
        legend_columns=2,
        annotation=False,
        show_title=False,
        tight_layout=True,
        color_cycle=COLORBLIND_CYCLE,
        save_bbox_inches=False,
    ),
    "presentation": PlotStyle(
        name="presentation",
        label="演示/组会",
        figure_size=_canvas_size(1.5),
        dpi=100,
        save_dpi=300,
        font_size=18.0,
        title_size=24.0,
        label_size=22.0,
        tick_size=18.0,
        legend_size=16.0,
        annotation_size=16.0,
        title_bold=True,
        label_bold=True,
        annotation_bold=True,
        line_width=3.0,
        axes_linewidth=1.5,
        tick_direction="out",
        tick_width=2.0,
        tick_length=7.0,
        grid=True,
        grid_alpha=0.25,
        legend=True,
        legend_frame=True,
        legend_shadow=False,
        legend_columns=1,
        annotation=True,
        color_cycle=DEFAULT_COLOR_CYCLE,
    ),
    "thesis": PlotStyle(
        name="thesis",
        label="论文/学位论文",
        figure_size=_canvas_size(4.0 / 3.0),
        dpi=100,
        save_dpi=400,
        font_family=("Arial", "DejaVu Sans"),
        math_fontset="dejavusans",
        font_size=12.0,
        title_size=14.0,
        label_size=14.0,
        tick_size=12.0,
        legend_size=11.0,
        annotation_size=11.0,
        title_bold=True,
        label_bold=False,
        annotation_bold=False,
        line_width=1.5,
        axes_linewidth=1.0,
        tick_direction="in",
        tick_width=1.0,
        tick_length=4.0,
        minor_ticks=True,
        grid=True,
        grid_color="#d9d9d9",
        grid_width=0.6,
        grid_alpha=0.35,
        legend=True,
        legend_frame=False,
        legend_shadow=False,
        legend_columns=1,
        annotation=True,
        color_cycle=COLORBLIND_CYCLE,
    ),
}

DEFAULT_PRESET_NAME = "daily"


def preset_names(user_presets: dict[str, dict] | None = None) -> list[str]:
    names = list(BUILTIN_PRESETS)
    if user_presets:
        names.extend(name for name in user_presets if name not in BUILTIN_PRESETS)
    return names


def preset_label(name: str, user_presets: dict[str, dict] | None = None) -> str:
    if user_presets and name in user_presets:
        return user_presets[name].get("label", name)
    if name in BUILTIN_PRESETS:
        return BUILTIN_PRESETS[name].label
    return name


def resolve_preset(
    name: str | None,
    user_presets: dict[str, dict] | None = None,
    *,
    fallback: str = DEFAULT_PRESET_NAME,
) -> PlotStyle:
    if name and user_presets and name in user_presets:
        return PlotStyle.from_dict(user_presets[name], name=name)
    if name and name in BUILTIN_PRESETS:
        return BUILTIN_PRESETS[name]
    return BUILTIN_PRESETS.get(fallback, BUILTIN_PRESETS[DEFAULT_PRESET_NAME])
