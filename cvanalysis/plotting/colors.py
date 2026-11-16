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


def _normalized_color_mapping(raw):
    result = {}
    for old, new in raw.items() if isinstance(raw, dict) else ():
        old_hex, new_hex = _color_hex(old), _color_hex(new)
        if old_hex is not None and new_hex is not None:
            result[old_hex] = new_hex
    return result


def detect_figure_color_groups(figure: Figure) -> dict[str, list[str]]:
    """Return separate graphics and text colors, even when their RGBs match."""
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

    return {"graphics": non_text, "text": text_colors}


def detect_figure_colors(figure: Figure) -> list[str]:
    """Compatibility list of unique colors, with text colors last."""
    groups = detect_figure_color_groups(figure)
    text_colors = groups["text"]
    text_set = set(text_colors)
    return [color for color in groups["graphics"] if color not in text_set] + text_colors


def apply_color_overrides(figure: Figure, overrides: dict | None, by_role: dict | None = None) -> None:
    """Apply legacy global remaps, followed by independent graphics/text remaps."""
    mapping = _normalized_color_mapping(overrides)
    by_role = by_role if isinstance(by_role, dict) else {}
    roles = {role: _normalized_color_mapping(by_role.get(role)) for role in ("graphics", "text")}
    if not mapping and not any(roles.values()):
        return

    backgrounds = {id(figure.patch), *(id(ax.patch) for ax in figure.axes)}

    def mapped(color, role):
        return roles[role].get(mapping.get(color, color), mapping.get(color, color))

    def replace(value, role):
        color = _color_hex(value)
        if color is None:
            return value
        if color in mapping:
            value = mapping[color]
            color = mapping[color]
        replacement = roles[role].get(color)
        if replacement is None or replacement == color:
            return value
        rgba = mcolors.to_rgba(value)
        return (*mcolors.to_rgba(replacement)[:3], rgba[3])

    def replace_rgba(value, role):
        try:
            rgba = mcolors.to_rgba(value)
        except (TypeError, ValueError):
            return value
        color = mcolors.to_hex(rgba, keep_alpha=False)
        replacement = mapped(color, role)
        if replacement == color:
            return value
        new_rgba = mcolors.to_rgba(replacement)
        return (*new_rgba[:3], rgba[3])

    def apply_artist(artist) -> None:
        if isinstance(artist, Line2D):
            artist.set_color(replace(artist.get_color(), "graphics"))
            marker_face = artist.get_markerfacecolor()
            marker_edge = artist.get_markeredgecolor()
            new_face = replace_rgba(marker_face, "graphics")
            new_edge = replace_rgba(marker_edge, "graphics")
            if new_face is not marker_face:
                artist.set_markerfacecolor(new_face)
            if new_edge is not marker_edge:
                artist.set_markeredgecolor(new_edge)
        elif isinstance(artist, Patch):
            if id(artist) in backgrounds:
                return
            artist.set_facecolor(replace(artist.get_facecolor(), "graphics"))
            artist.set_edgecolor(replace(artist.get_edgecolor(), "graphics"))
        elif isinstance(artist, Collection):
            facecolors = artist.get_facecolors()
            if len(facecolors):
                artist.set_facecolor([replace_rgba(color, "graphics") for color in facecolors])
            edgecolors = artist.get_edgecolors()
            if len(edgecolors):
                artist.set_edgecolor([replace_rgba(color, "graphics") for color in edgecolors])
        elif isinstance(artist, Text):
            artist.set_color(replace(artist.get_color(), "text"))

    for artist in figure.findobj():
        apply_artist(artist)
    for legend in [*figure.legends, *(ax.get_legend() for ax in figure.axes)]:
        if legend is not None:
            for handle in getattr(legend, "legend_handles", []):
                apply_artist(handle)


def apply_rebuilt_legend_text_overrides(figure: Figure, overrides, by_role):
    """Recolor legend labels recreated by final layout after the main pass."""
    role = _normalized_color_mapping(by_role.get("text")) if isinstance(by_role, dict) else {}
    if not role:
        return
    legacy = _normalized_color_mapping(overrides)
    for legend in [*figure.legends, *(ax.get_legend() for ax in figure.axes)]:
        if legend is None:
            continue
        for text in [*legend.get_texts(), legend.get_title()]:
            original = _color_hex(text.get_color())
            if original is None:
                continue
            # A rebuilt legend may expose either its original color or a
            # legacy-mapped one. Match the visible color first.
            new = role.get(original, role.get(legacy.get(original, original)))
            if new is not None:
                alpha = mcolors.to_rgba(text.get_color())[3]
                text.set_color((*mcolors.to_rgba(new)[:3], alpha))
