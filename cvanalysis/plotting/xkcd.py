# -*- coding: utf-8 -*-
"""Deterministic xkcd color selection for multi-curve plots."""

from __future__ import annotations

import random

import matplotlib.colors as mcolors
import numpy as np


def _rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) * 100 / 95.047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) * 100 / 100.0
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) * 100 / 108.883
    x = x ** (1 / 3) if x > 0.008856 else 7.787 * x + 16 / 116
    y = y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116
    z = z ** (1 / 3) if z > 0.008856 else 7.787 * z + 16 / 116
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def _delta_e(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return float(np.sqrt(sum((a - b) ** 2 for a, b in zip(first, second))))


def _hex_to_lab(hex_color: str) -> tuple[float, float, float]:
    return _rgb_to_lab(mcolors.hex2color(hex_color))


def generate_xkcd_color_sequence(
    random_seed: int | None = None,
    delta_e_min: float = 20.0,
    num_colors: int = 50,
) -> list[str]:
    """Return xkcd colors with bounded lightness and pairwise separation.

    The selection is deterministic for a given seed and falls back to the
    default color cycle if too few candidates satisfy the constraints.
    """
    count = max(1, int(num_colors))
    rng = random.Random(random_seed)
    candidates = list(dict.fromkeys(mcolors.XKCD_COLORS.values()))
    rng.shuffle(candidates)
    white_lab = _rgb_to_lab((1.0, 1.0, 1.0))
    selected: list[tuple[str, tuple[float, float, float]]] = []

    def try_add(hex_color: str, check_pairwise: bool) -> None:
        try:
            lab = _hex_to_lab(hex_color)
        except Exception:
            return
        if lab[0] >= 80:
            return
        if _delta_e(lab, white_lab) < delta_e_min:
            return
        if check_pairwise and any(_delta_e(lab, other) < delta_e_min for _, other in selected):
            return
        if hex_color not in {color for color, _ in selected}:
            selected.append((hex_color, lab))

    for color in candidates:
        if len(selected) >= count:
            break
        try_add(color, check_pairwise=True)

    if len(selected) < count:
        for color in candidates:
            if len(selected) >= count:
                break
            try_add(color, check_pairwise=False)

    fallback = list(mcolors.TABLEAU_COLORS.values())
    result = [color for color, _ in selected[:count]]
    index = 0
    while len(result) < count:
        result.append(fallback[index % len(fallback)])
        index += 1
    return result
