# -*- coding: utf-8 -*-
"""Versioned application settings with v1 config migration.

The on-disk ``config.json`` intentionally keeps the top-level v1 fields
(``plot``, ``colors``, ``eis_plot``, ``axis``, ``grid``, ``tick``) in sync with
the active v2 preset.  This lets an older v1 build continue to read the file
after a v2 session, while v2 stores its richer state under new keys.
"""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from cvanalysis.appearance import (
    DEFAULT_THEME_ID,
    ensure_theme_file,
    load_themes,
    normalize_theme,
    theme_path_for_config,
)
from cvanalysis.plotting.presets import DEFAULT_PRESET_NAME, BUILTIN_PRESETS, preset_names, resolve_preset
from cvanalysis.plotting.style import DEFAULT_COLOR_CYCLE, PlotStyle
from cvanalysis.plotting.texts import (
    DEFAULT_TEXTS,
    DEFAULT_TEXT_PRESET_LABEL,
    DEFAULT_TEXT_PRESET_NAME,
    TEXT_FIELD_MAP,
    invalid_text_values,
    resolve_text_values,
)


SCHEMA_VERSION = 2
# Bump this whenever the bottom dock graph or fixed panels change.  Saved
# QMainWindow dock graphs are not restored anymore; the version still lets old
# configs reset only their layout while keeping presets, columns and analysis
# settings intact.
BOTTOM_LAYOUT_VERSION = 4
_KNOWN_KEYS = {
    "schema_version", "app", "analysis", "eis", "presets", "text_presets",
    "plotting", "ui", "plot", "colors", "eis_plot", "axis", "grid", "tick",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "app": {
        "language": "zh_CN",
        "recent_projects": [],
        "last_directory": "",
    },
    "analysis": {
        "area_cm2": None,
        "mass_mg": None,
        "outlier_count": 1,
        "outlier_method": "trim",
        "outlier_z": 3.0,
        "sensitivity_factor": 10.0,
        "segmentation": "robust",
        "default_normalization": "none",
        "target_voltage": None,
        "phase_frequency_hz": 1.0,
    },
    "eis": {
        "fit_model": "auto",
        "fit_enabled": False,
        "phase_frequency_hz": 1.0,
    },
    "presets": {
        "active": DEFAULT_PRESET_NAME,
        "user": {},
    },
    "text_presets": {
        "active": DEFAULT_TEXT_PRESET_NAME,
        "presets": {
            DEFAULT_TEXT_PRESET_NAME: {
                "name": DEFAULT_TEXT_PRESET_NAME,
                "label": DEFAULT_TEXT_PRESET_LABEL,
                "values": dict(DEFAULT_TEXTS),
            }
        },
    },
    "plotting": {
        "default_normalization": "none",
    },
    "ui": {
        "geometry": None,
        "window_state": None,
        "last_plot_preset": DEFAULT_PRESET_NAME,
        "scale": 1.0,
        "theme": DEFAULT_THEME_ID,
        "dataset_splitter": None,
        "analysis_splitter": None,
        "column_widths": {},
        "bottom_splitter": None,
        "bottom_layout_version": None,
    },
    "colors": {
        "mode": "default",
        "random_seed": 42,
        "delta_e_min": 40.0,
        "enable_random": False,
        "custom_colors": list(DEFAULT_COLOR_CYCLE),
    },
}

DEFAULT_LEGACY_PLOT = {
    "title": {"fontsize": 20, "bold": True},
    "xlabel": {"fontsize": 20, "bold": True},
    "ylabel": {"fontsize": 20, "bold": True},
    "xtick": {"fontsize": 14, "bold": False},
    "ytick": {"fontsize": 14, "bold": False},
    "legend": {"fontsize": 12, "bold": False},
    "text": {"fontsize": 14, "bold": True},
    "line_width": 2.0,
}

_NORMALIZATIONS = {"none", "area", "mass"}
_SEGMENTATIONS = {"robust", "legacy"}
_OUTLIER_METHODS = {"trim", "zscore"}
_COLOR_MODES = {"default", "custom", "xkcd"}
_FIT_MODELS = {"auto", "rct_cpe", "rct_c", "rs_cpe", "rs_c"}


def _as_float(value: Any, default: float | None = None, *, minimum: float | None = None, maximum: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    if minimum is not None and number < minimum:
        return default
    if maximum is not None and number > maximum:
        return default
    return number


def _as_int(value: Any, default: int | None = None, *, minimum: int | None = None) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if minimum is not None and number < minimum:
        return default
    return number


def _as_bool(value: Any, default: bool = False) -> bool:
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


def _as_choice(value: Any, choices: set[str], default: str) -> str:
    text = str(value) if isinstance(value, str) else ""
    return text if text in choices else default


def _as_path_text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "CVAnalysis"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "CVAnalysis"


def default_config_path() -> Path:
    env_dir = os.environ.get("CVANALYSIS_CONFIG_DIR")
    if env_dir:
        return Path(env_dir) / "config.json"
    frozen = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals() or hasattr(sys, "nuitka")
    candidate = Path(sys.executable).resolve().parent if frozen else _project_root()
    try:
        probe = candidate / ".cvanalysis_write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return candidate / "config.json"
    except Exception:
        return app_data_dir() / "config.json"


def _deep_merge(default: dict, loaded: dict) -> dict:
    result = copy.deepcopy(default)
    for key, value in (loaded or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def legacy_style_from_config(config: dict) -> PlotStyle:
    """Build a PlotStyle from a v1-style config document."""
    config = config if isinstance(config, dict) else {}
    plot = config.get("plot") if isinstance(config.get("plot"), dict) else {}
    axis = config.get("axis") if isinstance(config.get("axis"), dict) else {}
    grid = config.get("grid") if isinstance(config.get("grid"), dict) else {}
    tick = config.get("tick") if isinstance(config.get("tick"), dict) else {}
    colors = config.get("colors") if isinstance(config.get("colors"), dict) else {}
    title = plot.get("title") if isinstance(plot.get("title"), dict) else {}
    xlabel = plot.get("xlabel") if isinstance(plot.get("xlabel"), dict) else {}
    xtick = plot.get("xtick") if isinstance(plot.get("xtick"), dict) else {}
    legend = plot.get("legend") if isinstance(plot.get("legend"), dict) else {}
    text = plot.get("text") if isinstance(plot.get("text"), dict) else {}
    base = BUILTIN_PRESETS[DEFAULT_PRESET_NAME]
    custom_colors = colors.get("custom_colors")
    if not isinstance(custom_colors, (list, tuple)) or not custom_colors:
        custom_colors = base.color_cycle
    custom_colors = tuple(str(color) for color in custom_colors if isinstance(color, str))
    overrides = {
        "name": "custom-legacy",
        "label": "旧版自定义（已迁移）",
        "title_size": _as_float(title.get("fontsize"), base.title_size, minimum=0.1),
        "label_size": _as_float(xlabel.get("fontsize"), base.label_size, minimum=0.1),
        "tick_size": _as_float(xtick.get("fontsize"), base.tick_size, minimum=0.1),
        "legend_size": _as_float(legend.get("fontsize"), base.legend_size, minimum=0.1),
        "annotation_size": _as_float(text.get("fontsize"), base.annotation_size, minimum=0.1),
        "title_bold": _as_bool(title.get("bold"), base.title_bold),
        "label_bold": _as_bool(xlabel.get("bold"), base.label_bold),
        "annotation_bold": _as_bool(text.get("bold"), base.annotation_bold),
        "line_width": _as_float(plot.get("line_width"), base.line_width, minimum=0.01),
        "axes_linewidth": _as_float(axis.get("linewidth"), base.axes_linewidth, minimum=0.01),
        "grid": True,
        "grid_color": _as_path_text(grid.get("color"), base.grid_color),
        "grid_width": _as_float(grid.get("linewidth"), base.grid_width, minimum=0.01),
        "tick_direction": _as_choice(tick.get("direction"), {"in", "out"}, base.tick_direction),
        "tick_width": _as_float(tick.get("width"), base.tick_width, minimum=0.01),
        "tick_length": _as_float(tick.get("length"), base.tick_length, minimum=0.0),
        "color_cycle": custom_colors,
        "font_family": base.font_family,
        "figure_size": base.figure_size,
        "show_title": False,
        "annotation": True,
    }
    return base.with_overrides(overrides)


def legacy_mirror(style: PlotStyle, color_config: dict | None = None) -> dict[str, Any]:
    """Create the v1-style top-level sections from a v2 PlotStyle."""
    return {
        "plot": {
            "title": {"fontsize": round(style.title_size), "bold": style.title_bold},
            "xlabel": {"fontsize": round(style.label_size), "bold": style.label_bold},
            "ylabel": {"fontsize": round(style.label_size), "bold": style.label_bold},
            "xtick": {"fontsize": round(style.tick_size), "bold": False},
            "ytick": {"fontsize": round(style.tick_size), "bold": False},
            "legend": {"fontsize": round(style.legend_size), "bold": False},
            "text": {"fontsize": round(style.annotation_size), "bold": style.annotation_bold},
            "line_width": style.line_width,
        },
        "axis": {"linewidth": style.axes_linewidth},
        "grid": {"color": style.grid_color, "linewidth": style.grid_width},
        "tick": {
            "direction": style.tick_direction,
            "width": style.tick_width,
            "length": style.tick_length,
        },
        "colors": copy.deepcopy(color_config or DEFAULT_SETTINGS["colors"]),
        "eis_plot": {
            "nyquist": {
                "color": style.color_cycle[0] if style.color_cycle else "#1f77b4",
                "marker": "o",
                "marker_size": max(2, round(style.marker_size)),
                "line_style": "-",
                "line_width": style.line_width,
            },
            "bode": {
                "color": style.color_cycle[1] if len(style.color_cycle) > 1 else "#ff7f0e",
                "marker": "s",
                "marker_size": max(2, round(style.marker_size)),
                "line_style": "-",
                "line_width": style.line_width,
                "z_color": style.color_cycle[2] if len(style.color_cycle) > 2 else "#2ca02c",
                "char_freq_line_color": "#d62728",
                "char_freq_line_width": max(0.5, style.line_width),
            },
        },
    }


class SettingsService:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_config_path()
        self.theme_path = theme_path_for_config(self.path)
        self.theme_created = False
        self.raw: dict[str, Any] = {}
        self.settings: dict[str, Any] = {}
        self.migrated_from_v1 = False
        self.load_warnings: list[str] = []
        try:
            self.theme_created = ensure_theme_file(self.theme_path)
        except OSError as exc:
            self.load_warnings.append(f"无法创建主题配置文件，将使用内置默认主题: {exc}")
        self.load()

    def available_themes(self):
        return load_themes(self.theme_path)

    def theme_ids(self) -> list[str]:
        return [theme.id for theme in self.available_themes()]

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        self.load_warnings = []
        if not self.path.exists():
            self.raw = {}
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            self._sanitize_settings()
            self._sync_legacy_with_style(self.resolve_style())
            self._save_quietly()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raw = {}
            self.load_warnings.append(f"配置文件无法解析，已使用默认设置: {exc}")
        if not isinstance(raw, dict):
            raw = {}
            self.load_warnings.append("配置文件顶层不是对象，已使用默认设置")
        self.raw = raw

        if not self.raw:
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            self._sanitize_settings()
            self._sync_legacy_with_style(self.resolve_style())
            self._save_quietly()
            return

        raw_version = self.raw.get("schema_version", 1)
        try:
            version = int(raw_version)
        except (TypeError, ValueError, OverflowError):
            version = SCHEMA_VERSION
            self.load_warnings.append(f"配置版本号无效（{raw_version!r}），按当前版本读取")

        if version < SCHEMA_VERSION:
            try:
                self._migrate_from_v1()
            except Exception as exc:  # noqa: BLE001 - never block startup on a bad config
                self.load_warnings.append(f"旧版配置迁移失败，已使用默认设置: {exc}")
                self.settings = copy.deepcopy(DEFAULT_SETTINGS)
                self._sanitize_settings()
                self._sync_legacy_with_style(self.resolve_style())
                self._save_quietly()
        else:
            self.settings = _deep_merge(DEFAULT_SETTINGS, self.raw)
            self.settings["schema_version"] = SCHEMA_VERSION
            # Preserve unknown top-level keys on save.
            for key, value in self.raw.items():
                if key not in self.settings:
                    self.settings[key] = copy.deepcopy(value)
            self._sanitize_settings()
            try:
                self._adopt_legacy_drift()
            except Exception as exc:  # noqa: BLE001
                self.load_warnings.append(f"旧版样式镜像读取失败，已忽略: {exc}")
        self._sanitize_settings()
        if self.active_preset not in preset_names(self.user_presets):
            self.active_preset = DEFAULT_PRESET_NAME
        self._sync_legacy_with_style(self.resolve_style())
        if "text_presets" not in self.raw:
            self._save_quietly()

    def _save_quietly(self) -> None:
        try:
            self.save()
        except Exception as exc:  # noqa: BLE001 - read-only config must not block startup
            self.load_warnings.append(f"配置无法写入磁盘: {exc}")

    def _sanitize_settings(self) -> None:
        """Coerce persisted values into shapes the UI can safely consume."""
        settings = self.settings
        if not isinstance(settings, dict):
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            settings = self.settings
            self.load_warnings.append("配置内容不是对象，已恢复默认值")

        for key in (
            "app", "analysis", "eis", "presets", "text_presets", "plotting",
            "ui", "colors",
        ):
            if not isinstance(settings.get(key), dict):
                if key in settings:
                    self.load_warnings.append(f"配置项 {key} 类型无效，已恢复默认值")
                settings[key] = copy.deepcopy(DEFAULT_SETTINGS[key])

        app = settings["app"]
        recent = app.get("recent_projects")
        app["recent_projects"] = [
            value for value in recent if isinstance(value, str)
        ] if isinstance(recent, list) else []
        app["last_directory"] = _as_path_text(app.get("last_directory"), "")

        analysis = settings["analysis"]
        area = analysis.get("area_cm2")
        analysis["area_cm2"] = None if area is None else _as_float(area, None, minimum=0.0)
        mass = analysis.get("mass_mg")
        analysis["mass_mg"] = None if mass is None else _as_float(mass, None, minimum=0.0)
        target = analysis.get("target_voltage")
        analysis["target_voltage"] = None if target is None else _as_float(target, None)
        analysis["outlier_count"] = _as_int(analysis.get("outlier_count"), 1, minimum=0)
        analysis["outlier_method"] = _as_choice(
            analysis.get("outlier_method"), _OUTLIER_METHODS, "trim"
        )
        analysis["outlier_z"] = _as_float(
            analysis.get("outlier_z"), 3.0, minimum=0.1
        )
        analysis["sensitivity_factor"] = _as_float(
            analysis.get("sensitivity_factor"), 10.0, minimum=0.000001
        )
        analysis["segmentation"] = _as_choice(
            analysis.get("segmentation"), _SEGMENTATIONS, "robust"
        )
        analysis["default_normalization"] = _as_choice(
            analysis.get("default_normalization"), _NORMALIZATIONS, "none"
        )
        analysis["phase_frequency_hz"] = _as_float(
            analysis.get("phase_frequency_hz"), 1.0, minimum=0.000001
        )

        eis = settings["eis"]
        eis["fit_model"] = _as_choice(eis.get("fit_model"), _FIT_MODELS, "auto")
        eis["fit_enabled"] = _as_bool(eis.get("fit_enabled"), False)
        eis["phase_frequency_hz"] = _as_float(
            eis.get("phase_frequency_hz"), 1.0, minimum=0.000001
        )

        plotting = settings["plotting"]
        plotting["default_normalization"] = _as_choice(
            plotting.get("default_normalization"), _NORMALIZATIONS, "none"
        )

        color_config = settings["colors"]
        color_config["mode"] = _as_choice(color_config.get("mode"), _COLOR_MODES, "default")
        color_config["random_seed"] = _as_int(color_config.get("random_seed"), 42)
        color_config["delta_e_min"] = _as_float(
            color_config.get("delta_e_min"), 40.0, minimum=0.0
        )
        color_config["enable_random"] = _as_bool(
            color_config.get("enable_random"), False
        )
        custom_colors = color_config.get("custom_colors")
        color_config["custom_colors"] = [
            str(color) for color in custom_colors if isinstance(color, str)
        ] if isinstance(custom_colors, (list, tuple)) else list(DEFAULT_COLOR_CYCLE)

        ui = settings["ui"]
        ui["scale"] = _as_float(ui.get("scale"), 1.0, minimum=0.8, maximum=1.6)
        ui["theme"] = normalize_theme(ui.get("theme"), self.theme_ids())
        for key in ("geometry", "window_state"):
            if ui.get(key) is not None and not isinstance(ui.get(key), str):
                ui[key] = None
        for key in ("dataset_splitter", "analysis_splitter", "bottom_splitter"):
            value = ui.get(key)
            valid = isinstance(value, list) and all(
                isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in value
            )
            ui[key] = value if valid else None
        ui["column_widths"] = (
            ui.get("column_widths") if isinstance(ui.get("column_widths"), dict) else {}
        )
        version = _as_int(ui.get("bottom_layout_version"), None)
        ui["bottom_layout_version"] = (
            version if version == BOTTOM_LAYOUT_VERSION else None
        )
        ui["last_plot_preset"] = (
            ui.get("last_plot_preset")
            if isinstance(ui.get("last_plot_preset"), str)
            else DEFAULT_PRESET_NAME
        )

        presets = settings["presets"]
        user = presets.get("user")
        if not isinstance(user, dict):
            user = {}
            self.load_warnings.append("用户预设结构无效，已忽略")
        valid_user: dict[str, dict] = {}
        for name, data in user.items():
            if not isinstance(name, str) or not isinstance(data, dict):
                self.load_warnings.append(f"忽略无效用户预设: {name!r}")
                continue
            try:
                style = PlotStyle.from_dict(data, name=name)
                legacy_mirror(style, color_config)
            except Exception as exc:  # noqa: BLE001
                self.load_warnings.append(f"忽略无效用户预设 {name}: {exc}")
                continue
            valid_user[name] = data
        presets["user"] = valid_user
        active = presets.get("active")
        presets["active"] = (
            active
            if isinstance(active, str) and active in preset_names(valid_user)
            else DEFAULT_PRESET_NAME
        )

        text_presets = settings["text_presets"]
        preset_items = text_presets.get("presets")
        if not isinstance(preset_items, dict):
            preset_items = {}
            self.load_warnings.append("文本预设结构无效，已恢复默认文字")
        valid_text: dict[str, dict] = {}
        for name, data in preset_items.items():
            if not isinstance(name, str) or not name or not isinstance(data, dict):
                self.load_warnings.append(f"忽略无效文本预设: {name!r}")
                continue
            values = data.get("values")
            if not isinstance(values, dict):
                values = {}
                self.load_warnings.append(f"文本预设 {name} 的 values 结构无效，已使用默认文字")
            messages = invalid_text_values(values)
            clean_values = {
                str(key): value
                for key, value in values.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            if name == DEFAULT_TEXT_PRESET_NAME:
                merged_defaults = dict(DEFAULT_TEXTS)
                merged_defaults.update(clean_values)
                clean_values = merged_defaults
            for message in messages:
                if message not in self.load_warnings:
                    self.load_warnings.append(message)
            label = data.get("label")
            if not isinstance(label, str) or not label.strip():
                label = (
                    DEFAULT_TEXT_PRESET_LABEL
                    if name == DEFAULT_TEXT_PRESET_NAME
                    else name
                )
            entry = dict(data)
            entry["name"] = name
            entry["label"] = label
            entry["values"] = clean_values
            valid_text[name] = entry
        if DEFAULT_TEXT_PRESET_NAME not in valid_text:
            valid_text[DEFAULT_TEXT_PRESET_NAME] = {
                "name": DEFAULT_TEXT_PRESET_NAME,
                "label": DEFAULT_TEXT_PRESET_LABEL,
                "values": dict(DEFAULT_TEXTS),
            }
        text_presets["presets"] = valid_text
        text_active = text_presets.get("active")
        text_presets["active"] = (
            text_active
            if isinstance(text_active, str) and text_active in valid_text
            else DEFAULT_TEXT_PRESET_NAME
        )
        settings["schema_version"] = SCHEMA_VERSION

    def _adopt_legacy_drift(self) -> None:
        """Adopt edits made by the frozen v1 GUI to the legacy mirror.

        The v1 GUI writes only the top-level legacy sections.  If those no
        longer match the active v2 preset, preserve the change as a user preset
        instead of silently discarding it on the next v2 save.
        """
        if not isinstance(self.raw.get("plot"), dict):
            return
        mirror = legacy_mirror(self.resolve_style(), self.settings.get("colors"))
        legacy_keys = ("plot", "axis", "grid", "tick")
        if all(self.raw.get(key) == mirror.get(key) for key in legacy_keys):
            return
        legacy_style = legacy_style_from_config(self.raw)
        self.settings.setdefault("presets", {}).setdefault("user", {})["custom-legacy"] = {
            **legacy_style.to_dict(),
            "label": legacy_style.label,
        }
        self.active_preset = "custom-legacy"

    def _migrate_from_v1(self) -> None:
        self.migrated_from_v1 = True
        legacy_style = legacy_style_from_config(self.raw)
        raw_colors = self.raw.get("colors") if isinstance(self.raw.get("colors"), dict) else {}
        color_config = _deep_merge(DEFAULT_SETTINGS["colors"], raw_colors)
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.settings["colors"] = color_config
        raw_analysis = self.raw.get("analysis") if isinstance(self.raw.get("analysis"), dict) else {}
        self.settings["analysis"] = _deep_merge(
            DEFAULT_SETTINGS["analysis"],
            raw_analysis,
        )
        raw_presets = self.raw.get("presets")
        user_presets = raw_presets.get("user") if isinstance(raw_presets, dict) else {}
        if not isinstance(user_presets, dict):
            user_presets = {}
        self.settings["presets"] = {
            "active": "custom-legacy",
            "user": {
                "custom-legacy": {
                    **legacy_style.to_dict(),
                    "label": "旧版自定义（已迁移）",
                }
            },
        }
        if user_presets:
            self.settings["presets"]["user"].update(user_presets)
        # Preserve v1 specifics that are not represented by PlotStyle.
        for key in ("app", "eis", "plotting", "ui"):
            raw_section = self.raw.get(key)
            if isinstance(raw_section, dict):
                self.settings[key] = _deep_merge(self.settings.get(key, {}), raw_section)
        raw_text_presets = self.raw.get("text_presets")
        if isinstance(raw_text_presets, dict):
            self.settings["text_presets"] = _deep_merge(
                self.settings["text_presets"],
                raw_text_presets,
            )
        for key, value in self.raw.items():
            if key not in _KNOWN_KEYS:
                self.settings[key] = copy.deepcopy(value)
        self._backup_v1()
        self._sanitize_settings()
        self._sync_legacy_with_style(legacy_style, color_config)
        self._save_quietly()

    def _backup_v1(self) -> None:
        try:
            backup = self.path.with_name(self.path.name + ".v1.bak")
            if not backup.exists():
                shutil.copy2(self.path, backup)
        except Exception:
            pass

    def save(self) -> None:
        self._sanitize_settings()
        self.settings["schema_version"] = SCHEMA_VERSION
        self.settings["presets"]["active"] = self.active_preset
        self.settings["text_presets"]["active"] = self.active_text_preset
        self._sync_legacy_with_style(self.resolve_style(), self.color_config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, self.path)
        self.raw = copy.deepcopy(self.settings)

    # -- views -----------------------------------------------------------
    @property
    def active_preset(self) -> str:
        presets = self.settings.get("presets")
        if not isinstance(presets, dict):
            return DEFAULT_PRESET_NAME
        name = presets.get("active", DEFAULT_PRESET_NAME)
        return name if isinstance(name, str) and name else DEFAULT_PRESET_NAME

    @active_preset.setter
    def active_preset(self, name: str) -> None:
        presets = self.settings.setdefault("presets", {})
        if not isinstance(presets, dict):
            presets = {}
            self.settings["presets"] = presets
        presets["active"] = name

    @property
    def user_presets(self) -> dict[str, dict]:
        presets = self.settings.get("presets")
        if not isinstance(presets, dict):
            return {}
        user = presets.get("user")
        return user if isinstance(user, dict) else {}

    @property
    def active_text_preset(self) -> str:
        section = self.settings.get("text_presets")
        if not isinstance(section, dict):
            return DEFAULT_TEXT_PRESET_NAME
        name = section.get("active", DEFAULT_TEXT_PRESET_NAME)
        presets = section.get("presets")
        available = presets if isinstance(presets, dict) else {}
        if isinstance(name, str) and name in available:
            return name
        return DEFAULT_TEXT_PRESET_NAME

    @active_text_preset.setter
    def active_text_preset(self, name: str) -> None:
        section = self.settings.setdefault("text_presets", {})
        if not isinstance(section, dict):
            section = {}
            self.settings["text_presets"] = section
        section["active"] = name

    @property
    def text_presets(self) -> dict[str, dict]:
        section = self.settings.get("text_presets")
        if not isinstance(section, dict):
            return {}
        presets = section.get("presets")
        return presets if isinstance(presets, dict) else {}

    def resolve_text_preset(self, name: str | None = None) -> dict[str, str]:
        presets = self.text_presets
        selected = name or self.active_text_preset
        entry = presets.get(selected)
        if not isinstance(entry, dict):
            entry = presets.get(DEFAULT_TEXT_PRESET_NAME)
        values = entry.get("values") if isinstance(entry, dict) else None
        return resolve_text_values(values if isinstance(values, dict) else None)

    def set_active_text_preset(self, name: str) -> None:
        if name not in self.text_presets:
            name = DEFAULT_TEXT_PRESET_NAME
        self.active_text_preset = name
        self.save()

    def save_text_preset(
        self,
        name: str,
        values: dict | None,
        label: str | None = None,
    ) -> None:
        name = str(name).strip()
        if not name:
            raise ValueError("文本预设名称不能为空")
        clean_values = {
            str(key): value
            for key, value in (values or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if name == DEFAULT_TEXT_PRESET_NAME:
            merged = dict(DEFAULT_TEXTS)
            merged.update(clean_values)
            clean_values = merged
        entry = {
            "name": name,
            "label": str(label).strip() if isinstance(label, str) and label.strip() else name,
            "values": clean_values,
        }
        section = self.settings.setdefault("text_presets", {})
        if not isinstance(section, dict):
            section = {}
            self.settings["text_presets"] = section
        presets = section.setdefault("presets", {})
        if not isinstance(presets, dict):
            presets = {}
            section["presets"] = presets
        presets[name] = entry
        self.save()

    def delete_text_preset(self, name: str) -> bool:
        if name == DEFAULT_TEXT_PRESET_NAME:
            return False
        presets = self.text_presets
        if name not in presets:
            return False
        del presets[name]
        if self.active_text_preset == name:
            self.active_text_preset = DEFAULT_TEXT_PRESET_NAME
        self.save()
        return True

    def reset_text_preset(self, name: str) -> bool:
        if name != DEFAULT_TEXT_PRESET_NAME:
            return False
        presets = self.text_presets
        entry = presets.setdefault(
            DEFAULT_TEXT_PRESET_NAME,
            {"name": DEFAULT_TEXT_PRESET_NAME},
        )
        entry["name"] = DEFAULT_TEXT_PRESET_NAME
        entry["label"] = DEFAULT_TEXT_PRESET_LABEL
        entry["values"] = dict(DEFAULT_TEXTS)
        self.save()
        return True

    def export_text_preset(self, name: str, path: str | Path) -> None:
        presets = self.text_presets
        entry = presets.get(name)
        if not isinstance(entry, dict):
            raise ValueError(f"文本预设不存在: {name}")
        payload = {
            "format": "cvanalysis-text-preset",
            "version": 1,
            "name": name,
            "label": entry.get("label", name),
            "values": resolve_text_values(entry.get("values")),
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def import_text_preset(self, path: str | Path) -> str:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = data.get("preset", data) if isinstance(data, dict) else {}
        if not isinstance(payload, dict):
            raise ValueError("文本预设文件格式无效")
        values = payload.get("values", payload.get("text", {}))
        if not isinstance(values, dict):
            raise ValueError("文本预设 values 结构无效")
        name = str(payload.get("name") or Path(path).stem).strip()
        if not name:
            name = Path(path).stem
        if name == DEFAULT_TEXT_PRESET_NAME:
            name = f"{DEFAULT_TEXT_PRESET_NAME}-custom"
        label = payload.get("label") if isinstance(payload.get("label"), str) else name
        self.save_text_preset(name, values, label)
        return name

    @property
    def color_config(self) -> dict:
        value = self.settings.get("colors")
        return value if isinstance(value, dict) else DEFAULT_SETTINGS["colors"]

    @property
    def analysis(self) -> dict:
        value = self.settings.get("analysis")
        return value if isinstance(value, dict) else DEFAULT_SETTINGS["analysis"]

    @property
    def eis(self) -> dict:
        value = self.settings.get("eis")
        return value if isinstance(value, dict) else DEFAULT_SETTINGS["eis"]

    @property
    def ui_state(self) -> dict:
        value = self.settings.get("ui")
        return value if isinstance(value, dict) else DEFAULT_SETTINGS["ui"]

    def resolve_style(self, name: str | None = None) -> PlotStyle:
        return resolve_preset(name or self.active_preset, self.user_presets)

    def set_active_preset(self, name: str) -> None:
        self.active_preset = name
        style = self.resolve_style(name)
        self._sync_legacy_with_style(style, self.color_config)
        self.save()

    def save_preset(self, name: str, style: PlotStyle, label: str | None = None) -> None:
        data = style.to_dict()
        data["label"] = label or name
        data["name"] = name
        self.settings.setdefault("presets", {}).setdefault("user", {})[name] = data
        self.active_preset = name
        self.save()

    def delete_preset(self, name: str) -> bool:
        user = self.settings.setdefault("presets", {}).setdefault("user", {})
        if name not in user:
            return False
        del user[name]
        if self.active_preset == name and name not in BUILTIN_PRESETS:
            self.active_preset = DEFAULT_PRESET_NAME
        self.save()
        return True

    def export_preset(self, name: str, path: str | Path) -> None:
        style = self.resolve_style(name)
        Path(path).write_text(
            json.dumps({"format": "cvanalysis-preset", "version": 1, "style": style.to_dict()}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def import_preset(self, path: str | Path) -> str:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = data.get("style", data)
        style = PlotStyle.from_dict(payload)
        name = str(payload.get("name") or Path(path).stem)
        if name in BUILTIN_PRESETS:
            name = f"{name}-custom"
        style.name = name
        self.save_preset(name, style, style.label)
        return name

    def _sync_legacy_with_style(self, style: PlotStyle, color_config: dict | None = None) -> None:
        legacy = legacy_mirror(style, color_config or self.color_config)
        for key, value in legacy.items():
            self.settings[key] = copy.deepcopy(value)
        self.settings["plotting"] = {
            **self.settings.get("plotting", {}),
            "default_normalization": self.settings.get("plotting", {}).get(
                "default_normalization", self.analysis.get("default_normalization", "none")
            ),
        }

    def legacy_config(self) -> dict[str, Any]:
        """Return a v1-compatible view of the active settings."""
        return {
            "plot": copy.deepcopy(self.settings.get("plot", DEFAULT_LEGACY_PLOT)),
            "colors": copy.deepcopy(self.settings.get("colors", DEFAULT_SETTINGS["colors"])),
            "eis_plot": copy.deepcopy(self.settings.get("eis_plot", {})),
            "axis": copy.deepcopy(self.settings.get("axis", {})),
            "grid": copy.deepcopy(self.settings.get("grid", {})),
            "tick": copy.deepcopy(self.settings.get("tick", {})),
        }
