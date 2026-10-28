# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from matplotlib.figure import Figure

from cvanalysis.analysis.fitting import fit_eis_model
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.style import PlotStyle
from cvanalysis.plotting.ticks import apply_log_tick_formats, apply_unified_ticks


def test_log_tick_formats_apply_independently_and_leave_linear_axes_alone():
    figure = Figure()
    first = figure.add_subplot(211)
    second = figure.add_subplot(212)
    first.set_xscale("log")
    first.set_yscale("log")
    second.set_xscale("log")
    for ax in (first, second):
        ax.set_xlim(0.001, 100)
    first.set_ylim(0.01, 100)
    linear_formatter = second.yaxis.get_major_formatter()
    apply_log_tick_formats(figure, {"log_tick_formats": {"x": "decimal", "y": "scientific"}})
    figure.canvas.draw()
    for ax in (first, second):
        labels = [label.get_text() for label in ax.get_xticklabels()]
        assert "0.001" in labels and "100" in labels
        assert all("e" not in label.lower() for label in labels)
    assert "10^" in first.yaxis.get_major_formatter()(0.01)
    assert second.yaxis.get_major_formatter() is linear_formatter


def test_log_format_render_and_export(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec("eis_bode", [synthetic_eis_run.run_id],
                    analysis_options={"log_tick_formats": {"x": "decimal", "y": "scientific"}})
    from cvanalysis.plotting.export import render_to_new_figure, render_svg_bytes
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    figure.canvas.draw()
    for ax in figure.axes:
        assert ax.xaxis.get_major_formatter()(0.001) == "0.001"
    assert "10^" in figure.axes[1].yaxis.get_major_formatter()(100)
    assert b"<svg" in render_svg_bytes(dataset, spec, BUILTIN_PRESETS["daily"])


def test_top_right_ticks_can_be_disabled_independently():
    figure = Figure(figsize=(3.2, 3.2))
    ax = figure.add_subplot(111)
    PlotStyle(ticks_top=False, ticks_right=True).apply_axes(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    figure.canvas.draw()
    assert ax.spines["top"].get_visible()
    assert ax.spines["right"].get_visible()
    assert not ax.xaxis.majorTicks[0].tick2line.get_visible()
    assert ax.yaxis.majorTicks[0].tick2line.get_visible()


def test_ticks_require_visible_spines():
    figure = Figure(figsize=(3.2, 3.2))
    ax = figure.add_subplot(111)
    PlotStyle(spines_top=False, spines_right=False, ticks_top=True, ticks_right=True).apply_axes(ax)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    figure.canvas.draw()
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    assert not ax.xaxis.majorTicks[0].tick2line.get_visible()
    assert not ax.yaxis.majorTicks[0].tick2line.get_visible()


def test_style_roundtrip_preserves_tick_switches():
    style = PlotStyle.from_dict(
        {"ticks_top": False, "ticks_right": False, "spines_top": True, "spines_right": True}
    )
    assert style.spines_top and style.spines_right
    assert not style.ticks_top and not style.ticks_right
    restored = PlotStyle.from_dict(style.to_dict())
    assert not restored.ticks_top and not restored.ticks_right


def test_unified_ticks_use_the_same_interval():
    figure = Figure(figsize=(4.0, 3.2), dpi=100)
    ax = figure.add_axes([0.2, 0.2, 0.45, 0.75])
    ax.set_xlim(0, 0.5)
    ax.set_ylim(0, 0.5)
    figure.canvas.draw()
    before_x = np.diff(ax.get_xticks())
    before_y = np.diff(ax.get_yticks())
    assert before_x.size and before_y.size
    assert not np.allclose(np.median(before_x), np.median(before_y))

    warnings = apply_unified_ticks(figure, "eis_nyquist", {"unified_xy_ticks": True})
    assert not warnings
    x_ticks = np.asarray([value for value in ax.get_xticks() if 0 <= value <= 0.5])
    y_ticks = np.asarray([value for value in ax.get_yticks() if 0 <= value <= 0.5])
    assert x_ticks.size >= 3 and y_ticks.size >= 3
    assert np.allclose(np.diff(x_ticks), 0.1)
    assert np.allclose(np.diff(y_ticks), 0.1)


def test_unified_ticks_accept_manual_interval():
    figure = Figure(figsize=(4.0, 3.2), dpi=100)
    ax = figure.add_axes([0.2, 0.2, 0.45, 0.75])
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 400)
    figure.canvas.draw()
    warnings = apply_unified_ticks(
        figure,
        "eis_nyquist",
        {"unified_xy_ticks": True, "unified_tick_interval": 100.0},
    )
    assert not warnings
    for ticks in (ax.get_xticks(), ax.get_yticks()):
        inside = np.asarray([value for value in ticks if 0 <= value <= 400])
        assert np.allclose(np.diff(inside), 100.0)
        assert list(inside) == [0.0, 100.0, 200.0, 300.0, 400.0]


def test_manual_tick_interval_is_converted_with_units(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        analysis_options={
            "unit_overrides": {"impedance": "Ω"},
            "axis_limits": {
                "main": {"x_min": -0.01, "x_max": 0.4, "y_min": 0.0, "y_max": 0.4}
            },
            "axis_limit_units": {
                "main": {
                    "x": {"label": "kΩ", "factor": 1e-3},
                    "y": {"label": "kΩ", "factor": 1e-3},
                }
            },
            "unified_xy_ticks": True,
            "unified_tick_interval": 0.1,
            "unified_tick_interval_unit": {"label": "kΩ", "factor": 1e-3},
        },
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert not warnings
    ax = figure.axes[0]
    assert ax.get_xlim() == pytest.approx((-10.0, 400.0))
    for ticks in (ax.get_xticks(), ax.get_yticks()):
        inside = np.asarray([value for value in ticks if 0 <= value <= 400])
        assert np.allclose(np.diff(inside), 100.0)


def test_unified_ticks_skip_log_axes():
    figure = Figure(figsize=(4.0, 3.2))
    ax = figure.add_subplot(111)
    ax.set_xscale("log")
    ax.set_xlim(1, 100)
    ax.set_ylim(0, 1)
    warnings = apply_unified_ticks(figure, "cv_bvalue", {"unified_xy_ticks": True})
    assert any("线性" in warning for warning in warnings)


def test_eis_unit_override_and_manual_limit_conversion(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        analysis_options={
            "unit_overrides": {"impedance": "kΩ"},
            "axis_limits": {
                "main": {"x_min": 0.0, "x_max": 100.0, "y_min": 0.0, "y_max": 100.0}
            },
            "axis_limit_units": {
                "main": {
                    "x": {"label": "Ω", "factor": 1.0},
                    "y": {"label": "Ω", "factor": 1.0},
                }
            },
        },
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert not [warning for warning in warnings if "单位" in warning]
    ax = figure.axes[0]
    assert "kΩ" in ax.get_xlabel()
    assert "kΩ" in ax.get_ylabel()
    assert ax.get_xlim() == pytest.approx((0.0, 0.1))
    assert ax.get_ylim() == pytest.approx((0.0, 0.1))


def test_eis_bode_and_fit_use_selected_impedance_unit(synthetic_eis_run):
    dataset = Dataset(eis_runs=[synthetic_eis_run])
    fit = fit_eis_model(
        synthetic_eis_run.freq,
        synthetic_eis_run.z_real,
        synthetic_eis_run.z_imag,
        model="rct_c",
    )
    for kind in ("eis_bode", "eis_fit"):
        spec = PlotSpec(
            kind,
            [synthetic_eis_run.run_id],
            fit_enabled=True,
            analysis_options={"unit_overrides": {"impedance": "kΩ"}},
        )
        figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
        render_plot(
            figure,
            dataset,
            spec,
            BUILTIN_PRESETS["daily"],
            fits={synthetic_eis_run.run_id: fit},
        )
        if kind == "eis_bode":
            assert "kΩ" in figure.axes[1].get_ylabel()
        else:
            assert "kΩ" in figure.axes[0].get_ylabel()
            assert "kΩ" in figure.axes[1].get_ylabel()


def test_cv_current_unit_override_and_invalid_fallback(synthetic_cv_runs):
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    ids = [run.run_id for run in synthetic_cv_runs]
    spec = PlotSpec(
        "cv_overlay",
        ids,
        analysis_options={"unit_overrides": {"current": "mA"}},
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert not warnings
    assert "Current (mA)" in figure.axes[0].get_ylabel()

    invalid = PlotSpec(
        "cv_bvalue",
        ids,
        target_voltage=0.5,
        analysis_options={"unit_overrides": {"current": "kΩ"}},
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    warnings = render_plot(figure, dataset, invalid, BUILTIN_PRESETS["daily"])
    assert any("电流单位" in warning for warning in warnings)
    assert "µA" in figure.axes[0].get_ylabel()


def test_cp_current_unit_override_affects_annotation(synthetic_cp_run):
    dataset = Dataset(cp_runs=[synthetic_cp_run])
    spec = PlotSpec(
        "cp_gcd",
        [synthetic_cp_run.run_id],
        analysis_options={"unit_overrides": {"current": "mA"}},
    )
    figure = Figure(figsize=BUILTIN_PRESETS["daily"].figure_size)
    render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    texts = " ".join(text.get_text() for text in figure.axes[0].texts)
    assert "mA" in texts


def test_b_value_current_mode_ui_persists(tmp_path, synthetic_cv_runs):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=synthetic_cv_runs), [])
    app.processEvents()
    window._request_plot("cv_bvalue")
    app.processEvents()
    panel = window.options_panel
    assert "b_current_mode" in panel.controls
    combo = panel.controls["b_current_mode"]
    combo.setCurrentIndex(combo.findData("up"))
    panel.apply()
    tab = window.tabs.currentWidget()
    assert tab.spec.analysis_options["b_current_mode"] == "up"
    assert tab.spec.analysis_options.get("b_current_mode") != "absolute"
    window.close()
    app.processEvents()


def test_unit_selector_converts_manual_limits(tmp_path, synthetic_eis_run):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(eis_runs=[synthetic_eis_run]), [])
    app.processEvents()
    window._request_plot("eis_nyquist")
    app.processEvents()

    panel = window.options_panel
    assert set(panel.unit_controls) == {"impedance"}
    main = panel.axis_controls["main"]
    main["y_min"].setText("0")
    main["y_max"].setText("100")
    combo = panel.unit_controls["impedance"]
    combo.setCurrentIndex(combo.findData("kΩ"))
    panel.apply()

    tab = window.tabs.currentWidget()
    assert panel.error.text() == "已应用"
    assert tab.spec.analysis_options["unit_overrides"]["impedance"] == "kΩ"
    assert tab.spec.analysis_options["axis_limits"]["main"]["y_max"] == pytest.approx(0.1)
    assert tab.spec.analysis_options["axis_limit_units"]["main"]["y"]["label"] == "kΩ"
    assert tab.figure.axes[0].get_ylim() == pytest.approx((0.0, 0.1))
    assert "kΩ" in tab.figure.axes[0].get_ylabel()
    assert panel.axis_controls["main"]["y_max"].text() == "0.1"

    combo = panel.unit_controls["impedance"]
    combo.setCurrentIndex(combo.findData("auto"))
    panel.apply()
    tab = window.tabs.currentWidget()
    assert "unit_overrides" not in tab.spec.analysis_options
    assert tab.spec.analysis_options["axis_limits"]["main"]["y_max"] == pytest.approx(100.0)
    assert tab.spec.analysis_options["axis_limit_units"]["main"]["y"]["label"] == "Ω"
    assert tab.figure.axes[0].get_ylim() == pytest.approx((0.0, 100.0))
    assert panel.axis_controls["main"]["y_max"].text() == "100"

    panel.unified_ticks_cb.setChecked(True)
    for side, value in (("x", "decimal"), ("y", "scientific")):
        combo = panel.log_tick_controls[side]
        combo.setCurrentIndex(combo.findData(value))
    panel.apply()
    assert tab.spec.analysis_options["unified_xy_ticks"] is True
    assert tab.spec.analysis_options["log_tick_formats"] == {"x": "decimal", "y": "scientific"}
    panel.bind(tab)
    assert panel.log_tick_controls["x"].currentData() == "decimal"
    window.close()


def test_manual_tick_interval_ui_and_unit_conversion(tmp_path, synthetic_eis_run):
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(eis_runs=[synthetic_eis_run]), [])
    app.processEvents()
    window._request_plot("eis_nyquist")
    app.processEvents()

    panel = window.options_panel
    main = panel.axis_controls["main"]
    main["x_min"].setText("-10")
    main["x_max"].setText("400")
    main["y_min"].setText("0")
    main["y_max"].setText("400")
    panel.unified_ticks_cb.setChecked(True)
    panel.unified_interval_edit.setText("100")
    panel.apply()

    tab = window.tabs.currentWidget()
    assert panel.error.text() == "已应用"
    assert tab.spec.analysis_options["unified_tick_interval"] == pytest.approx(100.0)
    assert tab.spec.analysis_options["unified_tick_interval_unit"]["label"] == "Ω"
    assert panel.unified_interval_edit.text() == "100"
    inside = np.asarray([value for value in tab.figure.axes[0].get_xticks() if 0 <= value <= 400])
    assert np.allclose(np.diff(inside), 100.0)

    combo = panel.unit_controls["impedance"]
    combo.setCurrentIndex(combo.findData("kΩ"))
    panel.apply()
    tab = window.tabs.currentWidget()
    assert tab.spec.analysis_options["unified_tick_interval"] == pytest.approx(0.1)
    assert (
        tab.spec.analysis_options["unified_tick_interval_unit"]["label"] == "kΩ"
    )
    assert panel.unified_interval_edit.text() == "0.1"
    inside = np.asarray([value for value in tab.figure.axes[0].get_xticks() if 0 <= value <= 0.4])
    assert np.allclose(np.diff(inside), 0.1)
    window.close()


def test_style_dialogs_expose_independent_tick_switches():
    from PySide6.QtWidgets import QApplication

    from cvanalysis.ui.dialogs.quick_style_dialog import QuickStyleDialog
    from cvanalysis.ui.dialogs.style_dialog import StyleEditorDialog

    app = QApplication.instance() or QApplication([])
    style = PlotStyle(ticks_top=False, ticks_right=True)
    quick = QuickStyleDialog(style, "test")
    assert not quick.ticks_top_cb.isChecked()
    assert quick.ticks_right_cb.isChecked()
    quick.ticks_top_cb.setChecked(True)
    quick.ticks_right_cb.setChecked(False)
    overrides = quick.overrides()
    assert overrides["ticks_top"] is True
    assert overrides["ticks_right"] is False
    quick.deleteLater()

    editor = StyleEditorDialog(style)
    assert not editor.ticks_top_cb.isChecked()
    assert editor.ticks_right_cb.isChecked()
    editor.ticks_top_cb.setChecked(True)
    edited = editor.edited_style()
    assert edited.ticks_top is True
    assert edited.ticks_right is True
    editor.deleteLater()


def test_unit_and_tick_options_project_round_trip(tmp_path, synthetic_eis_run):
    from cvanalysis.services.project_service import load_project, save_project

    dataset = Dataset(eis_runs=[synthetic_eis_run])
    spec = PlotSpec(
        "eis_nyquist",
        [synthetic_eis_run.run_id],
        analysis_options={
            "unit_overrides": {"impedance": "kΩ"},
            "axis_limits": {"main": {"y_min": 0.0, "y_max": 0.1}},
            "axis_limit_units": {
                "main": {"y": {"label": "kΩ", "factor": 1e-3}}
            },
            "unified_xy_ticks": True,
            "unified_tick_interval": 0.1,
            "unified_tick_interval_unit": {"label": "kΩ", "factor": 1e-3},
            "log_tick_formats": {"x": "decimal", "y": "scientific"},
        },
    )
    path = tmp_path / "unit-ticks.cvproj"
    save_project(path, dataset, plots=[spec])
    state = load_project(path)
    options = state.plots[0].analysis_options
    assert options["unit_overrides"]["impedance"] == "kΩ"
    assert options["axis_limit_units"]["main"]["y"]["factor"] == pytest.approx(1e-3)
    assert options["unified_xy_ticks"] is True
    assert options["unified_tick_interval"] == pytest.approx(0.1)
    assert options["unified_tick_interval_unit"]["factor"] == pytest.approx(1e-3)
    assert options["log_tick_formats"] == {"x": "decimal", "y": "scientific"}
