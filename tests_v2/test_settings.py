# -*- coding: utf-8 -*-
import json

from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.services.settings_service import SettingsService


def test_fresh_settings(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    assert service.active_preset == "daily"
    assert service.resolve_style().label == BUILTIN_PRESETS["daily"].label
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    # v1 mirror is present so the frozen v1 GUI can still read this file.
    for key in ("plot", "colors", "eis_plot", "axis", "grid", "tick"):
        assert key in data
    assert data["schema_version"] == 2


def test_v1_migration_preserves_unknown_keys_and_values(tmp_path):
    v1 = {
        "plot": {
            "title": {"fontsize": 18, "bold": True},
            "xlabel": {"fontsize": 16, "bold": False},
            "ylabel": {"fontsize": 16, "bold": False},
            "xtick": {"fontsize": 12, "bold": False},
            "ytick": {"fontsize": 12, "bold": False},
            "legend": {"fontsize": 10, "bold": False},
            "text": {"fontsize": 11, "bold": False},
            "line_width": 1.7,
        },
        "colors": {
            "mode": "custom",
            "custom_colors": ["#111111", "#222222"],
            "random_seed": 7,
            "delta_e_min": 30,
            "enable_random": False,
        },
        "axis": {"linewidth": 1.2},
        "grid": {"color": "#aaaaaa", "linewidth": 0.5},
        "tick": {"direction": "out", "width": 1.1, "length": 5},
        "unknown_section": {"keep": True},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(v1), encoding="utf-8")
    service = SettingsService(path)
    assert service.migrated_from_v1
    assert service.active_preset == "custom-legacy"
    style = service.resolve_style()
    assert style.label_size == 16
    assert style.label_bold is False
    assert style.tick_direction == "out"
    assert service.settings["unknown_section"] == {"keep": True}
    assert (tmp_path / "config.json.v1.bak").exists()
    # Legacy mirror is updated for the old GUI.
    assert service.settings["plot"]["xlabel"]["fontsize"] == 16


def test_presets_round_trip(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    style = service.resolve_style("ieee-single")
    service.save_preset("my-ieee", style, "我的 IEEE")
    assert "my-ieee" in service.user_presets
    assert service.active_preset == "my-ieee"
    exported = tmp_path / "preset.json"
    service.export_preset("my-ieee", exported)
    service.delete_preset("my-ieee")
    name = service.import_preset(exported)
    assert name == "my-ieee"
    assert service.resolve_style(name).label == "我的 IEEE"


def test_v2_adopts_legacy_mirror_edits(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    service.set_active_preset("ieee-single")
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    raw["plot"]["xlabel"] = {"fontsize": 15, "bold": True}
    raw["plot"]["line_width"] = 2.5
    (tmp_path / "config.json").write_text(json.dumps(raw), encoding="utf-8")
    reloaded = SettingsService(tmp_path / "config.json")
    assert reloaded.active_preset == "custom-legacy"
    assert reloaded.resolve_style().label_size == 15
    assert reloaded.resolve_style().line_width == 2.5


def test_builtin_preset_user_override_can_be_removed(tmp_path):
    from cvanalysis.plotting.presets import BUILTIN_PRESETS, preset_label

    service = SettingsService(tmp_path / "config.json")
    original = BUILTIN_PRESETS["ieee-single"]
    custom = original.with_overrides({"line_width": 2.8, "xlabel_size": 10.0})
    service.save_preset("ieee-single", custom, "IEEE ????????")
    assert service.resolve_style("ieee-single").line_width == 2.8
    assert preset_label("ieee-single", service.user_presets) == "IEEE ????????"
    assert "ieee-single" in service.user_presets
    service.delete_preset("ieee-single")
    assert service.resolve_style("ieee-single").line_width == 1.0


def test_ui_stylesheet_scale():
    from cvanalysis.ui.theme import application_stylesheet

    base = application_stylesheet()
    scaled = application_stylesheet(1.2)
    assert "font-size: 11.0pt" in base
    assert "font-size: 13.2pt" in scaled
    assert scaled != base


def test_malformed_v2_config_is_sanitized_instead_of_crashing(tmp_path):
    import json

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "not-a-number",
                "presets": "oops",
                "analysis": "oops",
                "eis": None,
                "ui": {"scale": "not-a-number", "bottom_layout_version": "2"},
                "colors": {"custom_colors": "red"},
            }
        ),
        encoding="utf-8",
    )
    service = SettingsService(path)
    assert service.active_preset == "daily"
    assert service.analysis["outlier_count"] == 1
    assert service.analysis["outlier_method"] == "trim"
    assert service.analysis["outlier_z"] == 3.0
    assert service.eis["fit_model"] == "auto"
    assert service.ui_state["scale"] == 1.0
    assert service.ui_state["bottom_layout_version"] is None
    assert service.load_warnings
    assert (tmp_path / "config.json").exists()


def test_invalid_user_preset_values_are_coerced_or_ignored(tmp_path):
    import json

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "presets": {
                    "active": "broken",
                    "user": {
                        "broken": {
                            "title_size": "huge",
                            "figure_size": ["x", 6],
                            "color_cycle": ["#zzzzzz", "#ffffff"],
                            "legend_columns": 0,
                        },
                        "not-a-style": "oops",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    service = SettingsService(path)
    assert "not-a-style" not in service.user_presets
    style = service.resolve_style("broken")
    assert style.title_size == 20.0
    assert style.figure_size == (3.2 * 4.0 / 3.0, 3.2)
    assert style.legend_columns == 2
    assert "#ffffff" in style.color_cycle


def test_main_window_starts_with_malformed_config(tmp_path):
    import json

    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "bad",
                "presets": [],
                "analysis": {"outlier_count": "many", "sensitivity_factor": None},
                "ui": {"scale": "huge"},
            }
        ),
        encoding="utf-8",
    )
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=path)
    assert window._ui_scale == 1.0
    assert window.active_analysis["outlier_count"] == 1
    window.close()
    app.processEvents()
