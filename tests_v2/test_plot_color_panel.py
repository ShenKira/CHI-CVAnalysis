# -*- coding: utf-8 -*-
from unittest.mock import patch

import matplotlib.colors as mcolors
import pytest
from matplotlib.figure import Figure
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.colors import apply_color_overrides, detect_figure_colors
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.dialogs.plot_inspector_dialog import PlotInspectorDialog
from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.widgets.plot_color_panel import PlotColorPanel
from cvanalysis.ui.widgets.plot_tab import PlotTab
from cvanalysis.ui.widgets.wheel_guard import WheelGuard


def test_detected_colors_put_text_colors_last():
    figure = Figure(figsize=(8, 6))
    ax = figure.add_subplot(111)
    ax.plot([0, 1], [0, 1], color="#1f77b4")
    ax.text(0.5, 0.5, "annotation", color="#000000")
    colors = detect_figure_colors(figure)
    assert "#1f77b4" in colors
    assert colors[-1] == "#000000"


def test_color_overrides_remap_lines_patches_and_text():
    figure = Figure(figsize=(8, 6))
    ax = figure.add_subplot(111)
    line, = ax.plot([0, 1], [0, 1], color="#1f77b4")
    bar = ax.bar([0], [1], color="#ff7f0e")[0]
    text = ax.text(0.5, 0.5, "label", color="#000000")

    apply_color_overrides(
        figure,
        {
            "#1f77b4": "#ff0000",
            "#ff7f0e": "#00ff00",
            "#000000": "#0000ff",
        },
    )
    assert mcolors.to_hex(line.get_color()) == "#ff0000"
    assert mcolors.to_hex(bar.get_facecolor()) == "#00ff00"
    assert mcolors.to_hex(text.get_color()) == "#0000ff"


def test_detected_colors_include_line_marker_fill_and_edge():
    figure = Figure(figsize=(8, 6))
    ax = figure.add_subplot(111)
    line, = ax.plot([0, 1], [0, 1], color="#1f77b4", marker="o")
    line.set_markerfacecolor("#ff7f0e")
    line.set_markeredgecolor("#2ca02c")
    colors = detect_figure_colors(figure)
    assert "#1f77b4" in colors
    assert "#ff7f0e" in colors
    assert "#2ca02c" in colors


def test_color_overrides_remap_line_marker_fill_and_edge():
    figure = Figure(figsize=(8, 6))
    ax = figure.add_subplot(111)
    line, = ax.plot([0, 1], [0, 1], color="#1f77b4", marker="o")
    line.set_markerfacecolor("#1f77b4")
    line.set_markeredgecolor("#1f77b4")

    apply_color_overrides(figure, {"#1f77b4": "#ff0000"})
    assert mcolors.to_hex(line.get_color()) == "#ff0000"
    assert mcolors.to_hex(line.get_markerfacecolor()) == "#ff0000"
    assert mcolors.to_hex(line.get_markeredgecolor()) == "#ff0000"


def test_plot_color_panel_changes_current_plot_only():
    app = QApplication.instance() or QApplication([])
    dataset = Dataset()
    figure_spec = PlotSpec("cv_overlay")
    tab = PlotTab(figure_spec, BUILTIN_PRESETS["daily"], dataset)
    other = PlotTab(PlotSpec("cv_overlay"), BUILTIN_PRESETS["daily"], dataset)
    panel = PlotColorPanel()
    panel.bind(tab)
    colors = detect_figure_colors(tab.figure)
    # The synthetic plot has text; fall back to a real figure color when empty.
    old_color = colors[0] if colors else "#1f77b4"
    with patch(
        "cvanalysis.ui.widgets.plot_color_panel.QColorDialog.getColor",
        return_value=QColor("#ff0000"),
    ):
        panel._choose_color(old_color)
    assert tab.spec.analysis_options["color_overrides"][old_color] == "#ff0000"
    assert other.spec.analysis_options.get("color_overrides") is None
    tab.deleteLater()
    other.deleteLater()
    panel.deleteLater()
    app.processEvents()


def test_inspector_bar_width_takes_effect(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_contribution_vs_rate", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    dialog = PlotInspectorDialog(tab)
    dialog.bar_width_spin.setValue(0.4)
    QTest.qWait(150)
    assert spec.analysis_options["bar_width"] == 0.4
    assert tab.figure.axes[0].patches[0].get_width() == 0.4
    dialog.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_plot_context_menu_ratio_and_fit_to_tab(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    menu = tab._build_context_menu()
    labels = [action.text() for action in menu.actions() if action.text()]
    assert "当前图设置..." in labels
    assert "图片比例" in labels
    assert "按比例适应标签页" in labels
    ratio_menu = next(action.menu() for action in menu.actions() if action.text() == "图片比例")
    assert [action.text() for action in ratio_menu.actions()] == ["保持预设", "1:1", "5:4", "4:3", "16:9"]

    tab.resize(640, 520)
    tab.show()
    app.processEvents()
    host_size = tab.canvas_host.size()

    tab._set_canvas_ratio(16.0 / 9.0)
    app.processEvents()
    assert spec.overrides["axes_aspect"] == "auto"
    width, height = tab.style.figure_size
    assert width / height == pytest.approx(16.0 / 9.0, rel=1e-6)
    canvas_size = tab.canvas.size()
    assert canvas_size.width() <= tab.canvas_host.width()
    assert canvas_size.height() <= tab.canvas_host.height()
    assert canvas_size.width() / canvas_size.height() == pytest.approx(16.0 / 9.0, rel=0.02)
    assert tab.figure.get_size_inches()[0] / tab.figure.get_size_inches()[1] == pytest.approx(16.0 / 9.0, rel=0.02)

    for _ in range(20):
        app.processEvents()
    assert tab.canvas_host.size() == host_size
    tab.set_fit_to_view(False)
    app.processEvents()
    assert tab.canvas_host.size() == host_size
    tab.set_fit_to_view(True)
    app.processEvents()
    assert tab.canvas_host.size() == host_size
    tab.deleteLater()
    menu.deleteLater()
    app.processEvents()


def test_context_menu_copies_current_vector_plot(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    menu = tab._build_context_menu()
    labels = [action.text() for action in menu.actions() if action.text()]
    assert "复制当前矢量图" in labels

    with patch.object(tab, "copy_vector_plot") as copy_mock:
        action = next(action for action in menu.actions() if action.text() == "复制当前矢量图")
        action.trigger()
        copy_mock.assert_called_once()

    tab.copy_vector_plot()
    app.processEvents()
    mime = QGuiApplication.clipboard().mimeData()
    assert mime is not None
    assert mime.hasFormat("image/svg+xml")
    svg = bytes(mime.data("image/svg+xml"))
    assert b"<svg" in svg
    assert b"</svg>" in svg

    tab.deleteLater()
    menu.deleteLater()
    app.processEvents()


def test_reset_style_clears_current_plot_overrides(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec(
        "cv_contribution_vs_rate",
        [run.run_id for run in synthetic_cv_runs],
        analysis_options={"bar_width": 0.4, "color_overrides": {"#1f77b4": "#ff0000"}},
        overrides={"line_width": 3.0},
    )
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    tab.reset_style()
    assert spec.overrides == {}
    assert "bar_width" not in spec.analysis_options
    assert "color_overrides" not in spec.analysis_options
    tab.deleteLater()
    app.processEvents()


def test_main_window_has_results_log_and_options_columns(tmp_path, synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    window.show()
    app.processEvents()
    assert window.log_title.text() == "日志"
    assert window.log_dock.titleBarWidget() is not None
    assert window.bottom_splitter.count() == 3
    assert window.bottom_splitter.widget(0) is window.results_panel
    assert window.bottom_splitter.widget(1).isAncestorOf(window.log_title)
    assert window.bottom_splitter.widget(2) is window.options_panel
    assert window.results_panel.cv_model.rowCount() == len(synthetic_cv_runs)
    window.close()
    app.processEvents()


def test_wheel_guard_requires_click_focus_and_hover():
    app = QApplication.instance() or QApplication([])
    spin = QDoubleSpinBox()
    spin.show()
    spin.setFocus()
    app.processEvents()
    guard = WheelGuard()
    app.installEventFilter(guard)
    center = spin.mapToGlobal(spin.rect().center())
    with patch("cvanalysis.ui.widgets.wheel_guard.QCursor.pos", return_value=center):
        assert not guard._wheel_allowed(spin)

    QTest.mouseClick(spin, Qt.LeftButton, pos=spin.rect().center())
    app.processEvents()
    assert guard._armed_widget is spin
    with patch("cvanalysis.ui.widgets.wheel_guard.QCursor.pos", return_value=center):
        assert guard._wheel_allowed(spin)
    with patch("cvanalysis.ui.widgets.wheel_guard.QCursor.pos", return_value=QPoint(0, 0)):
        assert not guard._wheel_allowed(spin)
    spin.clearFocus()
    app.processEvents()
    with patch("cvanalysis.ui.widgets.wheel_guard.QCursor.pos", return_value=center):
        assert not guard._wheel_allowed(spin)
    app.removeEventFilter(guard)
    spin.deleteLater()
    guard.deleteLater()
    app.processEvents()
