# -*- coding: utf-8 -*-
"""Theme catalog loaded from JSON instead of hard-coded UI colors."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_THEME_ID = "default"
THEME_FILE_NAME = "themes.json"
THEME_TEMPLATE_NAME = "default_themes.json"
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")


@dataclass(frozen=True)
class ThemeDefinition:
    id: str
    label: str
    description: str
    colors: dict[str, str]
    swatches: tuple[str, ...] = ()

    def color(self, role: str, fallback: str = "") -> str:
        return self.colors.get(role, fallback)


def template_path() -> Path:
    return Path(__file__).resolve().with_name(THEME_TEMPLATE_NAME)


def theme_path_for_config(config_path: str | Path) -> Path:
    return Path(config_path).resolve().with_name(THEME_FILE_NAME)


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("主题文件顶层必须是对象")
    return data


def _theme_from_payload(payload: dict) -> ThemeDefinition | None:
    if not isinstance(payload, dict):
        return None
    theme_id = str(payload.get("id", "")).strip()
    if not theme_id:
        return None
    label = str(payload.get("label", theme_id)).strip() or theme_id
    description = str(payload.get("description", "")).strip()
    raw_colors = payload.get("colors")
    if not isinstance(raw_colors, dict):
        return None
    colors: dict[str, str] = {}
    for key, value in raw_colors.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        value = value.strip()
        if _HEX_COLOR.match(value):
            colors[key] = value
    if not colors:
        return None
    raw_swatches = payload.get("swatches")
    swatches = tuple(
        str(value).strip()
        for value in (raw_swatches if isinstance(raw_swatches, list) else [])
        if isinstance(value, str) and _HEX_COLOR.match(value.strip())
    )
    return ThemeDefinition(theme_id, label, description, colors, swatches)


def _parse_themes(data: dict) -> list[ThemeDefinition]:
    raw_themes = data.get("themes")
    if not isinstance(raw_themes, list):
        return []
    themes: list[ThemeDefinition] = []
    seen: set[str] = set()
    for payload in raw_themes:
        theme = _theme_from_payload(payload)
        if theme is None or theme.id in seen:
            continue
        seen.add(theme.id)
        themes.append(theme)
    return themes


def load_themes(path: str | Path | None = None) -> list[ThemeDefinition]:
    """Load a theme catalog, falling back to the packaged template.

    A missing catalog is created from ``default_themes.json``.  If a user
    catalog is malformed, the packaged defaults are used for this session; the
    user's file is not overwritten so it can be repaired manually.
    """
    target = Path(path) if path is not None else template_path()
    if path is not None:
        try:
            ensure_theme_file(target)
        except OSError:
            pass
    try:
        themes = _parse_themes(_read_json(target))
    except (OSError, ValueError, json.JSONDecodeError):
        themes = []
    try:
        fallback = _parse_themes(_read_json(template_path()))
    except (OSError, ValueError, json.JSONDecodeError):
        fallback = []
    fallback_default = next(
        (item for item in fallback if item.id == DEFAULT_THEME_ID),
        fallback[0] if fallback else None,
    )
    if themes:
        if fallback_default is not None:
            merged: list[ThemeDefinition] = []
            for theme in themes:
                colors = {**fallback_default.colors, **theme.colors}
                merged.append(
                    ThemeDefinition(
                        theme.id,
                        theme.label,
                        theme.description,
                        colors,
                        theme.swatches or fallback_default.swatches,
                    )
                )
            return merged
        return themes
    if fallback:
        return fallback
    return [ThemeDefinition(DEFAULT_THEME_ID, "默认（蓝色）", "", {}, ())]


def ensure_theme_file(path: str | Path) -> bool:
    """Create the per-user theme catalog from the packaged template if absent."""
    target = Path(path)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    template = template_path()
    content = template.read_text(encoding="utf-8")
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, target)
    return True


def normalize_theme(value: object, theme_ids: Iterable[str]) -> str:
    ids = list(theme_ids)
    fallback = DEFAULT_THEME_ID if DEFAULT_THEME_ID in ids else (ids[0] if ids else DEFAULT_THEME_ID)
    text = str(value or "").strip().lower()
    aliases = {
        "k-on": "kon",
        "k-on!": "kon",
        "k_on": "kon",
        "keion": "kon",
    }
    text = aliases.get(text, text)
    if text in {item.lower() for item in ids}:
        for item in ids:
            if item.lower() == text:
                return item
    return fallback


def get_theme(theme_id: str | None, themes: Iterable[ThemeDefinition]) -> ThemeDefinition:
    items = list(themes)
    normalized = normalize_theme(theme_id, [item.id for item in items])
    for item in items:
        if item.id == normalized:
            return item
    return items[0]


def theme_labels(themes: Iterable[ThemeDefinition]) -> list[tuple[str, str]]:
    return [(item.id, item.label) for item in themes]
