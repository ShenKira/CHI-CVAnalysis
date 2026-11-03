# -*- coding: utf-8 -*-
import json
import warnings

import pytest
from matplotlib.figure import Figure

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.texts import (
    DEFAULT_TEXTS,
    DEFAULT_TEXT_PRESET_NAME,
    axis_text,
    plot_text,
    plot_text_context,
    resolve_text_values,
    safe_format,
    validate_text_template,
)
from cvanalysis.services.settings_service import SettingsService


def test_text_catalog_defaults_are_valid_and_keep_special_notation():
    assert len(DEFAULT_TEXTS) >= 100
    assert DEFAULT_TEXTS["axis.cv_trasatti.x"] == "$v^{-1/2}$ (V/s)$^{-1/2}$"
    assert DEFAULT_TEXTS["annotation.cv_trasatti.r2"].startswith("R² =")
    assert DEFAULT_TEXTS["legend.cp_discharge"] == "{label} Discharge"
    assert DEFAULT_TEXTS["legend.cp_charge"] == "{label} Charge"
    assert not any(
        "\u4e00" <= char <= "\u9fff"
        for template in DEFAULT_TEXTS.values()
        for char in template
    )
    for key, template in DEFAULT_TEXTS.items():
        valid, message = validate_text_template(key, template)
        assert valid, (key, message)
    assert safe_format(DEFAULT_TEXTS["axis.cv_trasatti.x"], {"unit": "u"}) == DEFAULT_TEXTS["axis.cv_trasatti.x"]
    assert safe_format(DEFAULT_TEXTS["axis.cv_overlay.y_area"], {"unit": "µA/cm²"}) == "Current density (µA/cm²)"


def test_text_font_family_has_symbol_and_cjk_fallbacks():
    families = BUILTIN_PRESETS["ieee-single"].text_font_family()
    assert families[0] == "Arial"
    assert "DejaVu Sans" in families


def test_axis_text_precedence_and_blank_semantics():
    spec = PlotSpec("cv_overlay", analysis_options={"axis_labels": {"main": {"y": " "}}})
    values = resolve_text_values({"axis.cv_overlay.x": "E (V)"})
    with plot_text_context(spec, values):
        assert axis_text(spec, "main", "x") == "E (V)"
        assert axis_text(spec, "main", "y") == ""
        assert axis_text(spec, "main", "y", unit="mA") == ""
        assert plot_text(spec, "title.cv_overlay") == ""
        assert plot_text(spec, "legend.cp_discharge", label="A") == "A Discharge"
    spec.analysis_options["axis_labels"] = {}
    with plot_text_context(spec, values):
        assert axis_text(spec, "main", "x") == "E (V)"
    spec.analysis_options["axis_labels"] = {"main": {"x": "Literal X"}}
    with plot_text_context(spec, values):
        assert axis_text(spec, "main", "x") == "Literal X"


def test_compact_axis_keys_are_used_for_paper_mode():
    spec = PlotSpec("cv_cap_scan", paper_layout={"enabled": True, "fraction": .25, "text_width_mm": 160})
    with plot_text_context(spec, None):
        assert axis_text(spec, "main", "x") == "v (V/s)"
        assert axis_text(spec, "main", "y", unit="mF") == "C (mF)"
    spec = PlotSpec("eis_bode", paper_layout={"enabled": True})
    with plot_text_context(spec, None):
        assert axis_text(spec, "phase", "y") == "Phase (°)"
        assert axis_text(spec, "magnitude", "x") == "Frequency (Hz)"


def test_custom_text_values_render_axes_titles_and_legends(synthetic_cv_runs):
    run = synthetic_cv_runs[0]
    dataset = Dataset(cv_runs=[run])
    spec = PlotSpec("cv_overlay", [run.run_id])
    style = BUILTIN_PRESETS["daily"].with_overrides({"show_title": True})
    values = {
        "axis.cv_overlay.x": "E (V)",
        "axis.cv_overlay.y_none": "J ({unit})",
        "title.cv_overlay": "Custom CV title",
        "legend.cv_cycle": "Scan {cycle}",
    }
    figure = Figure(figsize=style.figure_size, dpi=100)
    render_plot(figure, dataset, spec, style, text_values=values)
    ax = figure.axes[0]
    assert ax.get_xlabel() == "E (V)"
    assert ax.get_ylabel().startswith("J (")
    assert ax.get_title() == "Custom CV title"
    labels = [text.get_text() for text in ax.get_legend().get_texts()]
    assert labels and all(label.startswith("Scan ") for label in labels)


def test_axis_label_override_wins_and_whitespace_is_blank(synthetic_cv_runs):
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id for run in synthetic_cv_runs],
        analysis_options={"axis_labels": {"main": {"x": "My X", "y": " "}}},
    )
    figure = Figure(figsize=(5, 4), dpi=100)
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"], text_values={"axis.cv_overlay.x": "Preset X"})
    ax = figure.axes[0]
    assert ax.get_xlabel() == "My X"
    assert ax.get_ylabel() == ""


def test_special_glyphs_and_mathtext_render_without_missing_glyphs(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec("eis_nyquist", [synthetic_eis_run.run_id], annotations=True)
    style = BUILTIN_PRESETS["daily"].with_overrides({"show_title": True})
    values = {
        "axis.eis_nyquist.x": "$Z'$ (kΩ)",
        "axis.eis_nyquist.y": "-Z'' (kΩ)",
        "title.eis_nyquist": "R² ≈ 0.99",
        "annotation.eis.rs": "Rs ≈ {value}",
        "annotation.eis.r2": "R² = {value:.4f}",
    }
    figure = Figure(figsize=style.figure_size, dpi=100)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_plot(figure, dataset, spec, style, text_values=values)
        figure.canvas.draw()
    missing = [
        str(item.message)
        for item in caught
        if "Glyph" in str(item.message) or "missing" in str(item.message).lower()
    ]
    assert not missing
    assert figure.axes[0].get_xlabel() == "$Z'$ (kΩ)"
    assert figure.axes[0].get_ylabel() == "-Z'' (kΩ)"
    assert figure.axes[0].get_title() == "R² ≈ 0.99"


def test_cp_legend_defaults_are_english(synthetic_cp_run):
    dataset = Dataset(cp_runs=[synthetic_cp_run])
    spec = PlotSpec(
        "cp_capacity",
        [synthetic_cp_run.run_id],
        analysis_options={"show_charge": True, "show_efficiency": True},
    )
    figure = Figure(figsize=(5, 4), dpi=100)
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert any(label.endswith(" Discharge") for label in labels)
    assert any(label.endswith(" Charge") for label in labels)
    assert not any("放电" in label or "充电" in label for label in labels)


def test_fresh_config_materializes_text_presets(tmp_path):
    path = tmp_path / "config.json"
    service = SettingsService(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["text_presets"]["active"] == DEFAULT_TEXT_PRESET_NAME
    values = data["text_presets"]["presets"]["default"]["values"]
    assert values["axis.cv_overlay.x"] == "Potential (V)"
    assert service.resolve_text_preset()["legend.cp_charge"] == "{label} Charge"


def test_text_preset_crud_and_config_direct_edit(tmp_path):
    path = tmp_path / "config.json"
    service = SettingsService(path)
    values = service.resolve_text_preset()
    values["axis.cv_overlay.x"] = "Direct X"
    values["future.text.key"] = "keep"
    service.save_text_preset("custom", values, "Custom text")
    service.set_active_text_preset("custom")
    assert service.active_text_preset == "custom"
    assert service.resolve_text_preset()["axis.cv_overlay.x"] == "Direct X"
    assert service.text_presets["custom"]["values"]["future.text.key"] == "keep"

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["text_presets"]["presets"]["custom"]["values"]["axis.cv_overlay.x"] = "Edited in JSON"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    reloaded = SettingsService(path)
    assert reloaded.active_text_preset == "custom"
    assert reloaded.resolve_text_preset()["axis.cv_overlay.x"] == "Edited in JSON"

    assert reloaded.delete_text_preset(DEFAULT_TEXT_PRESET_NAME) is False
    assert reloaded.reset_text_preset(DEFAULT_TEXT_PRESET_NAME) is True
    assert reloaded.delete_text_preset("custom") is True
    assert reloaded.active_text_preset == DEFAULT_TEXT_PRESET_NAME


def test_text_preset_import_export_round_trip(tmp_path):
    service = SettingsService(tmp_path / "config.json")
    values = service.resolve_text_preset()
    values["axis.eis_nyquist.x"] = "Zreal (Ω)"
    service.save_text_preset("my-text", values, "My text")
    exported = tmp_path / "my-text.json"
    service.export_text_preset("my-text", exported)
    service.delete_text_preset("my-text")
    name = service.import_text_preset(exported)
    assert name == "my-text"
    assert service.resolve_text_preset(name)["axis.eis_nyquist.x"] == "Zreal (Ω)"


def test_malformed_text_preset_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "text_presets": {
                    "active": "custom",
                    "presets": {
                        "custom": {
                            "values": {
                                "axis.cv_overlay.x": 42,
                                "annotation.cv_bvalue.b": "b = {b:bad}",
                            }
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    service = SettingsService(path)
    assert service.active_text_preset == "custom"
    resolved = service.resolve_text_preset()
    assert resolved["axis.cv_overlay.x"] == "Potential (V)"
    assert resolved["annotation.cv_bvalue.b"] == "b = {b:.3f}"
    assert any("文本预设" in warning for warning in service.load_warnings)


def test_old_v2_config_without_text_presets_is_upgraded_in_place(tmp_path):
    path = tmp_path / "config.json"
    legacy = {
        "schema_version": 2,
        "presets": {"active": "daily", "user": {}},
        "analysis": {"area_cm2": 1.5},
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    service = SettingsService(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["analysis"]["area_cm2"] == 1.5
    assert "text_presets" in saved
    assert service.resolve_text_preset()["axis.cv_overlay.x"] == "Potential (V)"


def test_axis_labels_round_trip_in_project(tmp_path, synthetic_cv_runs):
    from cvanalysis.services.project_service import load_project, save_project

    path = tmp_path / "labels.cvproj"
    spec = PlotSpec(
        "cv_overlay",
        [synthetic_cv_runs[0].run_id],
        analysis_options={"axis_labels": {"main": {"x": "E (V)", "y": " "}}},
    )
    save_project(path, Dataset(cv_runs=list(synthetic_cv_runs)), plots=[spec])
    state = load_project(path)
    labels = state.plots[0].analysis_options["axis_labels"]["main"]
    assert labels == {"x": "E (V)", "y": " "}


def test_inspector_axis_label_edits_apply_and_clear(synthetic_cv_runs):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    dialog = PlotInspectorDialog(tab)
    edits = dialog.axis_label_edits["main"]
    edits["x"].setText("E vs Ag/AgCl (V)")
    QTest.qWait(180)
    assert spec.analysis_options["axis_labels"]["main"]["x"] == "E vs Ag/AgCl (V)"
    assert tab.figure.axes[0].get_xlabel() == "E vs Ag/AgCl (V)"
    edits["y"].setText("   ")
    QTest.qWait(180)
    assert spec.analysis_options["axis_labels"]["main"]["y"] == " "
    assert tab.figure.axes[0].get_ylabel() == ""
    edits["x"].clear()
    QTest.qWait(180)
    assert "x" not in spec.analysis_options["axis_labels"]["main"]
    assert tab.figure.axes[0].get_xlabel() == "Potential (V)"
    dialog.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_inspector_multi_axis_label_fields(synthetic_eis_run):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec("eis_bode", [synthetic_eis_run.run_id])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    dialog = PlotInspectorDialog(tab)
    assert set(dialog.axis_label_edits) == {"phase", "magnitude"}
    assert set(dialog.axis_label_edits["phase"]) == {"x", "y"}
    assert set(dialog.axis_label_edits["magnitude"]) == {"x", "y"}
    dialog.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_text_preset_manager_has_text_section_and_editor(tmp_path):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.dialogs.preset_manager_dialog import PresetManagerDialog
    from cvanalysis.ui.dialogs.text_preset_dialog import TextPresetEditorDialog

    app = QApplication.instance() or QApplication([])
    service = SettingsService(tmp_path / "config.json")
    dialog = PresetManagerDialog(service)
    assert dialog.tabs.count() == 2
    assert dialog.text_list.count() == 1
    values = service.resolve_text_preset()
    service.save_text_preset("custom", values, "Custom")
    dialog._refresh_text_list()
    assert dialog.text_list.count() == 2

    editor = TextPresetEditorDialog(service, "custom")
    editor.edits["axis.cv_overlay.x"].setText("E (V)")
    editor.activate_cb.setChecked(True)
    editor._accept()
    assert service.active_text_preset == "custom"
    assert service.resolve_text_preset("custom")["axis.cv_overlay.x"] == "E (V)"
    dialog.deleteLater()
    editor.deleteLater()
    app.processEvents()


def test_active_text_preset_applies_to_open_tabs(tmp_path, synthetic_cv_runs):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    tab = window.tabs.currentWidget()
    values = window.settings_service.resolve_text_preset()
    values["axis.cv_overlay.x"] = "Preset applied X"
    window.settings_service.save_text_preset("custom", values, "Custom")
    window.settings_service.set_active_text_preset("custom")
    window._apply_text_preset_to_all()
    assert tab.text_values["axis.cv_overlay.x"] == "Preset applied X"
    assert tab.figure.axes[0].get_xlabel() == "Preset applied X"
    window.close()
    app.processEvents()
