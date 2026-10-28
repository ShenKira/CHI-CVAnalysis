import json
import threading
import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from cvanalysis.domain.models import Dataset
from cvanalysis.analysis.cv import summarize_run, analyze_cv_run
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.export import render_to_new_figure
from cvanalysis.plotting.paper import paper_overrides


def test_trimmed_statistics_share_sample_and_recompute_clears_flags(synthetic_cv_runs):
    run = synthetic_cv_runs[0]
    analyze_cv_run(run, sensitivity_factor=1e-12)
    assert all(c.is_outlier for c in run.cycles)
    analyze_cv_run(run, sensitivity_factor=1e12)
    assert not any(c.is_outlier for c in run.cycles)
    import copy
    run.cycles.append(copy.deepcopy(run.cycles[0]))
    for index, (cycle, value) in enumerate(zip(run.cycles, [1, 1.1, 10]), 1):
        cycle.index = index
        cycle.capacitance_F = value
    summary = summarize_run(run, outlier_count=1)
    assert summary.mean_capacitance_F == pytest.approx(1.05)
    assert summary.sd_capacitance_F == pytest.approx(np.std([1, 1.1], ddof=1))
    assert summary.valid_cycles == 2 and summary.excluded_cycles == 1
    assert summary.outlier_cycles == [3]


@pytest.mark.parametrize("fraction", [.5, .33, .25])
def test_paper_export_dimensions_and_final_fonts(fraction, synthetic_cv_runs, tmp_path):
    style = BUILTIN_PRESETS["daily"]
    layout = dict(enabled=True, fraction=fraction, text_width_mm=160, body_pt=10)
    overrides = paper_overrides(layout, style)
    scale = 160 * fraction / (style.figure_size[0] * 25.4)
    small_figure_scale = .8 if fraction < .33 else 1.0
    assert overrides["annotation_size"] * scale == pytest.approx(7.5 * small_figure_scale)
    assert overrides["tick_size"] * scale == pytest.approx(8 * small_figure_scale)
    spec = PlotSpec("cv_cap_scan", [r.run_id for r in synthetic_cv_runs], paper_layout=layout)
    figure = render_to_new_figure(Dataset(cv_runs=synthetic_cv_runs), spec, style)
    assert tuple(figure.get_size_inches()) == pytest.approx(style.figure_size)
    assert figure.axes[0].xaxis.label.get_fontsize() * scale == pytest.approx(9 * small_figure_scale)
    assert paper_overrides(layout, style.with_overrides(overrides)) == overrides
    assert not overrides["save_bbox_inches"]
    from io import BytesIO
    from PIL import Image
    output = BytesIO()
    figure.savefig(output, format="png", dpi=300)
    output.seek(0)
    with Image.open(output) as exported:
        assert exported.size == (round(style.figure_size[0] * 300), round(style.figure_size[1] * 300))
    from cvanalysis.plotting.export import export_figure
    path = tmp_path / "paper.png"
    export_figure(figure, path, style)
    with Image.open(path) as exported:
        assert exported.size == (round(style.figure_size[0] * style.save_dpi), round(style.figure_size[1] * style.save_dpi))
    with pytest.raises(ValueError):
        paper_overrides({**layout, "fraction": 0}, style)


def test_cap_scan_linear_fit_and_independent_switches(synthetic_cv_runs):
    from cvanalysis.plotting.cv_renderer import draw_cap_scan
    runs = synthetic_cv_runs
    for run in runs:
        run.summary.mean_capacitance_F = 2 * run.scan_rate + .5
    spec = PlotSpec("cv_cap_scan", [r.run_id for r in runs], x_log=True,
                    analysis_options={"fit_method": "linear", "error_bars": False})
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    fit = next(line for line in ax.lines if line.get_label() == "Fitted Curve")
    assert ax.get_xscale() == "log"
    assert "mF" in ax.get_ylabel()
    assert np.polyfit(fit.get_xdata(), fit.get_ydata(), 1)[0] == pytest.approx(2000)
    np.testing.assert_allclose(fit.get_ydata(), 2000 * fit.get_xdata() + 500)
    assert not ax.containers[0].has_yerr
    spec.analysis_options["fit_line"] = False
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert not any(line.get_label() in {"Fitted Curve", "Fitted Line"} for line in figure.axes[0].lines)
    spec.analysis_options["fit_method"] = "none"
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert not any("R²" in t.get_text() for t in figure.axes[0].texts)


def test_cap_scan_power_fit_keeps_automatic_log_x_for_wide_rate_span(synthetic_cv_runs):
    from cvanalysis.plotting.cv_renderer import draw_cap_scan

    runs = synthetic_cv_runs
    for run, rate in zip(runs, (.01, .2, .5)):
        run.metadata.scan_rate = rate
        run.summary = None
    spec = PlotSpec("cv_cap_scan", [run.run_id for run in runs], analysis_options={"fit_method": "power"})
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_xscale() == "log"


@pytest.mark.parametrize(
    ("x_scale", "y_scale"),
    [("linear", "linear"), ("log", "linear"), ("linear", "log"), ("log", "log")],
)
def test_coordinate_straight_fit_is_linear_in_selected_axes(synthetic_cv_runs, x_scale, y_scale):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from cvanalysis.plotting.cv_renderer import draw_cap_scan

    runs = synthetic_cv_runs
    rates = (.01, .05, .5)
    values = (.001, .1, 1.0)
    for run, rate, value in zip(runs, rates, values):
        run.summary.scan_rate = rate
        run.summary.mean_capacitance_F = value
    spec = PlotSpec(
        "cv_cap_scan",
        [run.run_id for run in runs],
        analysis_options={
            "fit_method": "coordinate_line",
            "x_axis_scale": x_scale,
            "y_axis_scale": y_scale,
            "error_bars": False,
        },
    )
    figure = Figure()
    FigureCanvasAgg(figure)
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["daily"])
    ax = figure.axes[0]
    figure.canvas.draw()
    fit = next(line for line in ax.lines if line.get_label() == "Fitted Line")
    rendered = ax.transData.transform(np.column_stack((fit.get_xdata(), fit.get_ydata())))
    r2_screen = np.corrcoef(rendered[:, 0], rendered[:, 1])[0, 1] ** 2
    assert ax.get_xscale() == x_scale
    assert ax.get_yscale() == y_scale
    assert r2_screen == pytest.approx(1.0, abs=1e-10)


def test_cap_scan_auto_scales_update_in_options_panel(tmp_path, synthetic_cv_runs):
    from PySide6.QtWidgets import QApplication
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    runs = list(synthetic_cv_runs)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cv_runs=runs), [])
    window._request_plot("cv_cap_scan")
    panel = window.options_panel
    tab = window.tabs.currentWidget()
    auto_label = lambda control: control.itemText(control.findData("auto"))
    assert auto_label(panel.controls["x_axis_scale"]) == "自动（线性）"
    assert auto_label(panel.controls["y_axis_scale"]) == "自动（线性）"

    for run, rate, value in zip(runs, (.01, .5, 1.0), (.001, .1, 1.0)):
        run.summary.scan_rate = rate
        run.summary.mean_capacitance_F = value
    tab.redraw()
    assert auto_label(panel.controls["x_axis_scale"]) == "自动（对数）"
    assert auto_label(panel.controls["y_axis_scale"]) == "自动（对数）"
    window.close()
    app.processEvents()


def test_paper_cap_scan_keeps_standardized_fit_legend_label(synthetic_cv_runs):
    from cvanalysis.plotting.cv_renderer import draw_cap_scan

    runs = synthetic_cv_runs
    spec = PlotSpec(
        "cv_cap_scan",
        [run.run_id for run in runs],
        paper_layout={"enabled": True, "fraction": .25, "text_width_mm": 160, "body_pt": 10},
        analysis_options={"fit_method": "coordinate_line", "x_axis_scale": "linear", "y_axis_scale": "linear"},
    )
    figure = Figure()
    draw_cap_scan(figure, Dataset(cv_runs=runs), spec, BUILTIN_PRESETS["ieee-single"])
    labels = [text.get_text() for text in figure.legends[0].get_texts()]
    assert "Fitted Line" in labels


def test_portable_project_fits_settings_and_unknown_fields(tmp_path, synthetic_cv_runs, synthetic_eis_run):
    from cvanalysis.services.project_service import save_project, load_project
    from cvanalysis.services.dataset_service import fit_eis_runs
    dataset = Dataset(cv_runs=synthetic_cv_runs, eis_runs=[synthetic_eis_run])
    fits = fit_eis_runs(dataset, [synthetic_eis_run.run_id], model="rct_c")
    spec = PlotSpec.from_dict({"kind": "cv_cap_scan", "run_ids": [synthetic_cv_runs[0].run_id], "future": {"x": 1}, "analysis_options": {"fit_method": "linear"}, "paper_layout": {"enabled": True, "fraction": .25}})
    path = tmp_path / "portable.cvproj"
    save_project(path, dataset, plots=[spec], fits=fits, analysis_settings={"outlier_count": 0})
    for run in synthetic_cv_runs:
        run.source.unlink()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["future_project"] = 123
    path.write_text(json.dumps(payload), encoding="utf-8")
    state = load_project(path)
    assert not state.warnings
    assert len(state.dataset.cv_runs) == 3
    assert state.analysis_settings["outlier_count"] == 0
    np.testing.assert_allclose(next(iter(state.fits.values())).z_fit, fits[synthetic_eis_run.run_id].z_fit)
    assert state.plots[0].to_dict()["future"] == {"x": 1}
    assert state.plots[0].analysis_options["fit_method"] == "linear"
    save_project(path, state.dataset, plots=state.plots)
    assert json.loads(path.read_text(encoding="utf-8"))["future_project"] == 123


def test_reusable_dialog_applies_to_current_plot_and_validates(tmp_path, synthetic_cv_runs):
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=synthetic_cv_runs), [])
    window._request_plot("cv_cap_scan")
    dialog = window.options_panel
    tab = window.tabs.currentWidget()
    dialog.controls["fit_method"].setCurrentIndex(dialog.controls["fit_method"].findData("linear"))
    dialog.controls["error_bars"].setChecked(False)
    dialog.paper_enabled.setChecked(True)
    dialog.fraction.setText("0/25")
    dialog.legend_placement.setCurrentIndex(dialog.legend_placement.findData("outside"))
    dialog.legend_outside_threshold.setValue(.4)
    dialog.legend_columns.setCurrentIndex(dialog.legend_columns.findData(2))
    dialog.apply()
    assert tab.spec.analysis_options == {
        "fit_method": "linear", "x_axis_scale": "auto", "y_axis_scale": "auto",
        "error_bars": False, "fit_line": True,
    }
    assert tab.spec.paper_layout["legend_placement"] == "outside"
    assert tab.spec.paper_layout["legend_outside_threshold"] == .4
    assert tab.spec.paper_layout["legend_columns"] == 2
    assert tab.style.figure_size == tab.base_style.figure_size
    assert not dialog.isWindow()
    dialog.fraction.setText("0")
    dialog.apply()
    assert tab.spec.paper_layout["fraction"] == .25
    window._request_plot("cv_bvalue")
    assert window.options_panel is dialog
    assert dialog.tab is window.tabs.currentWidget()
    assert "fit_method" not in dialog.controls
    window.close()
    app.processEvents()


def test_background_task_keeps_ui_alive_and_close_waits(tmp_path):
    from cvanalysis.ui.main_window import MainWindow
    from PySide6.QtCore import QTimer
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window.show()
    gate = threading.Event()
    applied = []
    window._run_task(lambda: gate.wait(3), applied.append)
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    app.processEvents()
    assert ticks
    window.close()
    assert window.isVisible()
    gate.set()
    for _ in range(200):
        QTest.qWait(10)
        app.processEvents()
        if not window._tasks:
            break
    assert not window._tasks
    assert not window.isVisible()
    assert not applied


def test_frequency_errors_are_visible_and_not_unrestricted():
    from cvanalysis.ui.widgets.analysis_panel import AnalysisPanel
    app = QApplication.instance() or QApplication([])
    panel = AnalysisPanel()
    for text in ("abc", "nan", "inf", "0", "-1"):
        panel.freq_low_edit.setText(text)
        assert not panel.validate_frequency()
        assert panel.frequency_error.text()
    panel.freq_low_edit.setText("10")
    panel.freq_high_edit.setText("1")
    assert not panel.validate_frequency()
    panel.freq_high_edit.setText("1e6")
    assert panel.validate_frequency()
    panel.deleteLater()
    app.processEvents()


def test_export_integral_units_and_parser_messages(synthetic_cv_runs):
    from cvanalysis.services.export_service import cv_cycles_frame
    from cvanalysis.io.chi import ChiCVParser
    from pathlib import Path
    frame = cv_cycles_frame(Dataset(cv_runs=synthetic_cv_runs))
    assert "area_C" not in frame.columns
    row = frame.iloc[0]
    assert row["loop_charge_C"] == pytest.approx(row["integral_area_A_V"] / synthetic_cv_runs[0].scan_rate)
    assert "included_in_statistics" in frame.columns
    with pytest.raises(Exception, match="未找到"):
        ChiCVParser().parse("Cyclic Voltammetry\ninvalid", Path("bad.txt"))


def test_half_width_doubles_source_fonts_and_custom_body_sets_floor():
    style = BUILTIN_PRESETS["daily"].with_overrides({"figure_size": (160 / 25.4, 3.2)})
    full = dict(enabled=True, text_width_mm=160, fraction=1, body_pt=10)
    baseline = paper_overrides(full, style)
    half = paper_overrides({**full, "fraction": .5}, style)
    quarter = paper_overrides({**full, "fraction": .25}, style)
    assert baseline["title_size"] == pytest.approx(10)
    assert half["title_size"] == pytest.approx(20)
    assert quarter["title_size"] == pytest.approx(32)
    assert half["annotation_size"] * .5 == pytest.approx(7.5)
    assert quarter["annotation_size"] * .25 == pytest.approx(6.0)
    custom = paper_overrides({**full, "fraction": .5, "body_pt": 12}, style)
    assert custom["annotation_size"] * .5 == pytest.approx(9)
    assert custom["xlabel_size"] * .5 == pytest.approx(10.8)


def test_paper_font_shrink_applies_only_below_one_third():
    style = BUILTIN_PRESETS["daily"]
    base_layout = dict(enabled=True, text_width_mm=160, body_pt=10)
    below = paper_overrides({**base_layout, "fraction": .329}, style)
    at_boundary = paper_overrides({**base_layout, "fraction": .33}, style)
    below_scale = 160 * .329 / (style.figure_size[0] * 25.4)
    boundary_scale = 160 * .33 / (style.figure_size[0] * 25.4)
    assert below["title_size"] * below_scale == pytest.approx(8.0)
    assert below["xlabel_size"] * below_scale == pytest.approx(7.2)
    assert at_boundary["title_size"] * boundary_scale == pytest.approx(10.0)
    assert at_boundary["xlabel_size"] * boundary_scale == pytest.approx(9.0)


def test_fixed_bottom_panel_clear_and_layout_restore(tmp_path, synthetic_cv_runs):
    from cvanalysis.ui.main_window import MainWindow
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "layout.json"
    window = MainWindow(settings_path=path)
    window.show()
    app.processEvents()
    window._on_import_complete(Dataset(cv_runs=synthetic_cv_runs), [])
    window._request_plot("cv_cap_scan")
    app.processEvents()
    panel = window.options_panel
    assert not panel.isWindow()
    assert window.dockWidgetArea(window.log_dock) == Qt.BottomDockWidgetArea
    assert window.log_dock.features() == QDockWidget.NoDockWidgetFeatures
    assert window.log_dock.height() >= 300
    assert window.bottom_splitter.widget(2) is panel
    window.bottom_splitter.setSizes([430, 700, 580])
    app.processEvents()
    widths = window.bottom_splitter.sizes()
    window.close_all_plots()
    assert panel.tab is None and not panel.apply_button.isEnabled()
    assert panel.isVisible()
    window.close()
    restored = MainWindow(settings_path=path)
    restored.show()
    app.processEvents()
    # Offscreen restoreGeometry clamps the window to its virtual screen, so the
    # exact widths cannot all fit; the fixed settings panel keeps its minimum.
    assert restored.bottom_splitter.sizes()[2] >= restored.options_panel.minimumWidth()
    assert restored.bottom_splitter.sizes()[0] > 0
    assert restored.bottom_splitter.sizes()[1] > 0
    restored.close()


def test_legacy_dock_state_is_skipped_when_migrating_bottom_panel(tmp_path):
    import json
    from pathlib import Path
    from PySide6.QtCore import QTimer, Qt
    from cvanalysis.ui.app import create_application
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or create_application([])
    legacy = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    legacy.setdefault("ui", {})["bottom_layout_version"] = 1
    path = tmp_path / "legacy-layout.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    window = MainWindow(settings_path=path)
    window.show()
    QTimer.singleShot(50, app.quit)
    assert app.exec() == 0
    assert window.dockWidgetArea(window.log_dock) == Qt.BottomDockWidgetArea
    window.close()
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["ui"]["bottom_layout_version"] == 4


def test_old_v2_dock_state_is_ignored_without_losing_plot_config(tmp_path):
    import json
    from pathlib import Path
    from PySide6.QtCore import QTimer
    from cvanalysis.ui.app import create_application
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or create_application([])
    legacy = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
    legacy["ui"]["bottom_layout_version"] = 2
    legacy["presets"]["active"] = "ieee-single"
    for key in ("plot", "axis", "grid", "tick"):
        legacy.pop(key, None)
    legacy["ui"].setdefault("column_widths", {}).setdefault("dataset", {})["名称"] = 222
    preset_names = set(legacy.get("presets", {}).get("user", {}))
    path = tmp_path / "old-v2-layout.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    window = MainWindow(settings_path=path)
    window.show()
    QTimer.singleShot(50, app.quit)
    assert app.exec() == 0
    window.close()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["ui"]["bottom_layout_version"] == 4
    assert saved["ui"]["window_state"] is None
    assert saved["ui"]["column_widths"]["dataset"]["名称"] == 222
    assert saved["presets"]["active"] == "ieee-single"
    assert preset_names.issubset(set(saved["presets"]["user"]))
