# -*- coding: utf-8 -*-
"""Color-cycle resolution for CV plots."""

from __future__ import annotations

import matplotlib.colors as mcolors
from matplotlib.collections import Collection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.text import Text

from cvanalysis.plotting.style import DEFAULT_COLOR_CYCLE, PlotStyle

from cvanalysis.plotting.xkcd import generate_xkcd_color_sequence


def _repeat(colors: list[str], count: int) -> list[str]:
    if not colors:
        colors = list(DEFAULT_COLOR_CYCLE)
    repeats = (count + len(colors) - 1) // len(colors)
    return (colors * max(1, repeats))[:count]


def resolve_color_cycle(
    style: PlotStyle,
    count: int,
    color_config: dict | None = None,
) -> list[str]:
    config = color_config or {}
    mode = config.get("mode", "default")
    if mode == "custom":
        custom = [
            str(color)
            for color in config.get("custom_colors", [])
            if color and mcolors.is_color_like(str(color))
        ]
        if custom:
            return _repeat(custom, count)
    if mode == "xkcd" and config.get("enable_random", False) and generate_xkcd_color_sequence is not None:
        try:
            generated = generate_xkcd_color_sequence(
                config.get("random_seed", 42),
                float(config.get("delta_e_min", 20.0)),
                max(count, 1),
            )
            if generated:
                return _repeat([mcolors.to_hex(color) for color in generated], count)
        except Exception:
            pass
    return _repeat(list(style.color_cycle), count)


def _color_hex(value) -> str | None:
    try:
        rgba = mcolors.to_rgba(value)
    except (TypeError, ValueError):
        return None
    if rgba[3] <= 0:
        return None
    return mcolors.to_hex(rgba, keep_alpha=False)


def detect_figure_colors(figure: Figure) -> list[str]:
    """Return colors used by the current figure, with text colors last."""
    non_text: list[str] = []
    text_colors: list[str] = []
    seen_non: set[str] = set()
    seen_text: set[str] = set()
    backgrounds = {id(figure.patch), *(id(ax.patch) for ax in figure.axes)}

    def add(value, target: list[str], seen: set[str]) -> None:
        color = _color_hex(value)
        if color is not None and color not in seen:
            seen.add(color)
            target.append(color)

    for artist in figure.findobj():
        if isinstance(artist, Line2D):
            add(artist.get_color(), non_text, seen_non)
            add(artist.get_markerfacecolor(), non_text, seen_non)
            add(artist.get_markeredgecolor(), non_text, seen_non)
        elif isinstance(artist, Patch):
            if id(artist) in backgrounds:
                continue
            add(artist.get_facecolor(), non_text, seen_non)
            add(artist.get_edgecolor(), non_text, seen_non)
        elif isinstance(artist, Collection):
            for color in artist.get_facecolors():
                add(color, non_text, seen_non)
            for color in artist.get_edgecolors():
                add(color, non_text, seen_non)
        elif isinstance(artist, Text):
            if artist.get_text().strip():
                add(artist.get_color(), text_colors, seen_text)

    text_set = set(text_colors)
    return [color for color in non_text if color not in text_set] + text_colors


def apply_color_overrides(figure: Figure, overrides: dict | None) -> None:
    """Apply a current-plot color remapping to all matching figure artists."""
    mapping: dict[str, str] = {}
    for old, new in (overrides or {}).items():
        old_hex = _color_hex(old)
        new_hex = _color_hex(new)
        if old_hex is not None and new_hex is not None:
            mapping[old_hex] = new_hex
    if not mapping:
        return

    backgrounds = {id(figure.patch), *(id(ax.patch) for ax in figure.axes)}

    def replace(value):
        color = _color_hex(value)
        return mapping.get(color, value) if color is not None else value

    def replace_rgba(value):
        try:
            rgba = mcolors.to_rgba(value)
        except (TypeError, ValueError):
            return value
        color = mcolors.to_hex(rgba, keep_alpha=False)
        replacement = mapping.get(color)
        if replacement is None:
            return value
        new_rgba = mcolors.to_rgba(replacement)
        return (*new_rgba[:3], rgba[3])

    def apply_artist(artist) -> None:
        if isinstance(artist, Line2D):
            artist.set_color(replace(artist.get_color()))
            marker_face = artist.get_markerfacecolor()
            marker_edge = artist.get_markeredgecolor()
            new_face = replace_rgba(marker_face)
            new_edge = replace_rgba(marker_edge)
            if new_face is not marker_face:
                artist.set_markerfacecolor(new_face)
            if new_edge is not marker_edge:
                artist.set_markeredgecolor(new_edge)
        elif isinstance(artist, Patch):
            if id(artist) in backgrounds:
                return
            artist.set_facecolor(replace(artist.get_facecolor()))
            artist.set_edgecolor(replace(artist.get_edgecolor()))
        elif isinstance(artist, Collection):
            facecolors = artist.get_facecolors()
            if len(facecolors):
                artist.set_facecolor([replace_rgba(color) for color in facecolors])
            edgecolors = artist.get_edgecolors()
            if len(edgecolors):
                artist.set_edgecolor([replace_rgba(color) for color in edgecolors])
        elif isinstance(artist, Text):
            artist.set_color(replace(artist.get_color()))

    for artist in figure.findobj():
        apply_artist(artist)
    for legend in [*figure.legends, *(ax.get_legend() for ax in figure.axes)]:
        if legend is not None:
            for handle in getattr(legend, "legend_handles", []):
                apply_artist(handle)
