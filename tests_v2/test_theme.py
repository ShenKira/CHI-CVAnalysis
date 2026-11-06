# -*- coding: utf-8 -*-
import json

from PySide6.QtWidgets import QApplication

from cvanalysis.appearance import load_themes, normalize_theme
from cvanalysis.services.settings_service import SettingsService
from cvanalysis.ui.dialogs.settings_dialog import SettingsDialog
from cvanalysis.ui.theme import application_stylesheet


def test_default_and_kon_stylesheets_come_from_json():
    default = application_stylesheet(1.0, "default")
    kon = application_stylesheet(1.0, "kon")
    assert "__" not in default
    assert "__" not in kon
    assert "#1976d2" in default
    assert "#c92f3a" in kon
    assert "#24262f" in kon
    assert "#d8b79e" in kon
    assert "#4fb8a1" in kon
    assert "#1976d2" not in kon


def test_invalid_theme_falls_back_to_default():
    default = application_stylesheet(1.0, "default")
    assert application_stylesheet(1.0, "not-a-theme") == default
    assert normalize_theme("K-ON", ["default", "kon"]) == "kon"
    assert normalize_theme("unknown", ["default", "kon"]) == "default"


def test_settings_creates_theme_json_with_two_palettes(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    theme_path = tmp_path / "themes.json"
    assert theme_path.exists()
    payload = json.loads(theme_path.read_text(encoding="utf-8"))
    themes = [item["id"] for item in payload["themes"]]
    assert themes == ["default", "kon"]
    assert service.ui_state["theme"] == "default"
    assert {theme.id for theme in load_themes(theme_path)} == {"default", "kon"}


def test_theme_setting_round_trips_and_invalid_value_falls_back(tmp_path):
    path = tmp_path / "config.json"
    service = SettingsService(path)
    service.settings["ui"]["theme"] = "kon"
    service.save()
    assert SettingsService(path).ui_state["theme"] == "kon"

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["ui"]["theme"] = "not-a-theme"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert SettingsService(path).ui_state["theme"] == "default"


def test_main_window_applies_saved_theme(tmp_path):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    path = tmp_path / "config.json"
    service = SettingsService(path)
    service.settings["ui"]["theme"] = "kon"
    service.save()
    window = MainWindow(settings_path=path)
    assert "#c92f3a" in app.styleSheet()
    assert "#c92f3a" in window.styleSheet()
    window.close()
    app.setStyleSheet(application_stylesheet(1.0, "default"))
    app.processEvents()


def test_settings_dialog_gui_group_contains_theme_and_scale(tmp_path):
    app = QApplication.instance() or QApplication([])
    service = SettingsService(tmp_path / "config.json")
    dialog = SettingsDialog(
        service.settings,
        themes=service.available_themes(),
    )
    assert [dialog.theme_combo.itemData(i) for i in range(dialog.theme_combo.count())] == [
        "default",
        "kon",
    ]
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("kon"))
    values = dialog.values()
    assert values["ui"]["theme"] == "kon"
    assert values["ui"]["scale"] == service.ui_state["scale"]
    assert dialog.theme_preview is not None
    dialog.deleteLater()
    app.processEvents()
