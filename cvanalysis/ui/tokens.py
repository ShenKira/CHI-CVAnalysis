# -*- coding: utf-8 -*-
"""Shared UI metrics and typography for the desktop workspace.

The design system deliberately keeps colour in ``default_themes.json`` and
layout/shape tokens here.  User themes can therefore change palette without
being able to break spacing, focus rings or control geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_FONT_SIZE = 11.0
MIN_FONT_SIZE = 9.0
MAX_FONT_SIZE = 14.0

FONT_FAMILIES = (
    "Microsoft YaHei UI",
    "Segoe UI Variable Text",
    "Segoe UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Arial",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class UiTokens:
    """Geometry and type values derived from the user's UI scale."""

    scale: float
    font_size_pt: float
    small_font_pt: float
    title_font_pt: float
    control_height: int
    row_height: int
    button_padding_y: int
    button_padding_x: int
    tab_padding_y: int
    radius_sm: int = 4
    radius_md: int = 6
    radius_lg: int = 8
    radius_pill: int = 999
    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 12
    space_lg: int = 16
    # Plot context menu material: geometry is in logical pixels.
    glass_radius: int = 12
    glass_margin: int = 6
    glass_padding: int = 12
    glass_blur: float = 3.5
    glass_tint: float = 0.30
    glass_min_channel: int = 166

    @classmethod
    def from_scale(cls, scale: float | None) -> "UiTokens":
        try:
            value = float(scale)
        except (TypeError, ValueError):
            value = 1.0
        value = _clamp(value, 0.8, 1.6)
        font = _clamp(BASE_FONT_SIZE * value, MIN_FONT_SIZE, MAX_FONT_SIZE)
        return cls(
            scale=value,
            font_size_pt=round(font, 1),
            small_font_pt=round(max(8.5, font - 1.0), 1),
            title_font_pt=round(min(16.0, font + 1.5), 1),
            control_height=max(22, min(40, round(24 * value))),
            row_height=max(20, min(36, round(22 * value))),
            button_padding_y=max(4, round(6 * value)),
            button_padding_x=max(10, round(14 * value)),
            tab_padding_y=max(5, round(7 * value)),
        )

    def scaled(self, value: int | float, *, minimum: int = 1) -> int:
        return max(minimum, int(round(float(value) * self.scale)))
