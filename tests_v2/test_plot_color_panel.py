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
from cvanalysis.plotting.colors import apply_color_overrides, detect_figure_color_groups, detect_figure_colors
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


def test_shared_graphic_and_text_color_can_be_changed_independently():
    figure = Figure()
    ax = figure.add_subplot(111)
    line, = ax.plot([0, 1], [0, 1], color="#000000")
    text = ax.text(0.5, 0.5, "label", color="#000000")
    groups = detect_figure_color_groups(figure)
    assert "#000000" in groups["graphics"] and "#000000" in groups["text"]
    apply_color_overrides(figure, {"#000000": "#008800"},
                          {"graphics": {"#008800": "#ff0000"}})
    assert mcolors.to_hex(line.get_color()) == "#ff0000"
    assert mcolors.to_hex(text.get_color()) == "#008800"


def test_role_color_replacement_preserves_graphics_opacity():
    figure = Figure()
    ax = figure.add_subplot(111)
    bar = ax.bar([0], [1], color=(0.1, 0.2, 0.3, 0.25))[0]
    source = mcolors.to_hex(bar.get_facecolor())
    apply_color_overrides(figure, None, {"graphics": {source: "#ff0000"}})
    assert mcolors.to_hex(bar.get_facecolor()) == "#ff0000"
    assert bar.get_facecolor()[3] == pytest.approx(0.25)


def test_new_role_color_maps_round_trip_without_losing_legacy(tmp_path, synthetic_cv_runs):
    from cvanalysis.services.project_service import load_project, save_project

    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    options = {"color_overrides": {"#000000": "#008800"},
               "color_overrides_by_role": {"graphics": {"#008800": "#ff0000"},
                                           "text": {"#008800": "#0000ff"}},
               "future_option": {"keep": True}}
    spec = PlotSpec("cv_overlay", [synthetic_cv_runs[0].run_id], analysis_options=options)
    path = tmp_path / "role-colors.cvproj"
    save_project(path, dataset, plots=[spec])
    loaded = load_project(path).plots[0]
    assert loaded.analysis_options == options


@pytest.mark.parametrize("placement", ["normal", "inside", "outside"])
def test_text_color_survives_legend_layout(placement, synthetic_cv_runs):
    from cvanalysis.plotting.export import render_to_new_figure

    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_cap_scan", [run.run_id for run in synthetic_cv_runs],
                    analysis_options={"color_overrides_by_role": {"text": {"#000000": "#ff00ff"}}})
    if placement != "normal":
        spec.paper_layout = {"enabled": True, "legend_placement": placement}
    figure = render_to_new_figure(dataset, spec, BUILTIN_PRESETS["daily"])
    figure.canvas.draw()
    legend = figure.axes[0].get_legend() or (figure.legends[0] if figure.legends else None)
    assert legend is not None and legend.get_texts()
    assert all(mcolors.to_hex(label.get_color()) == "#ff00ff" for label in legend.get_texts())


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
    role = next(role for role, colors in detect_figure_color_groups(tab.figure).items() if old_color in colors)
    panel._select_color(role, old_color)
    panel.palette.setCurrentColor(QColor("#ff0000"))
    panel._apply_selected_color()
    assert tab.spec.analysis_options["color_overrides_by_role"][role][old_color] == "#ff0000"
    assert other.spec.analysis_options.get("color_overrides") is None
    tab.deleteLater()
    other.deleteLater()
    panel.deleteLater()
    app.processEvents()


def test_inline_picker_repeated_edits_keep_text_and_legacy_separate():
    app = QApplication.instance() or QApplication([])

    class ExamplePlot:
        def __init__(self):
            self.spec = PlotSpec("cv_overlay", analysis_options={
                "color_overrides": {"#000000": "#008800"},
                "future_option": "keep",
            })
            self.figure = Figure()
            self.redraw()

        def redraw(self):
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            self.line, = ax.plot([0, 1], [0, 1], color="#000000")
            self.text = ax.text(0.5, 0.5, "label", color="#000000")
            apply_color_overrides(self.figure, self.spec.analysis_options.get("color_overrides"),
                                  self.spec.analysis_options.get("color_overrides_by_role"))

    tab = ExamplePlot()
    panel = PlotColorPanel()
    panel.bind(tab)
    assert ("graphics", "#008800") in panel._buttons
    assert ("text", "#008800") in panel._buttons
    panel._select_color("graphics", "#008800")
    panel.palette.setCurrentColor(QColor("#ff0000"))
    panel.apply_button.click()
    assert mcolors.to_hex(tab.line.get_color()) == "#ff0000"
    assert mcolors.to_hex(tab.text.get_color()) == "#008800"
    panel._select_color("graphics", "#ff0000")
    panel.palette.setCurrentColor(QColor("#0000ff"))
    panel.apply_button.click()
    tab.redraw()
    assert mcolors.to_hex(tab.line.get_color()) == "#0000ff"
    assert mcolors.to_hex(tab.text.get_color()) == "#008800"
    assert tab.spec.analysis_options["color_overrides"] == {"#000000": "#008800"}
    tab.spec.analysis_options["color_overrides_by_role"]["future_role"] = {"keep": "data"}
    panel._reset_colors()
    assert tab.spec.analysis_options == {
        "future_option": "keep", "color_overrides_by_role": {"future_role": {"keep": "data"}}
    }
    panel.bind(None)
    assert not panel.palette.isEnabled() and not panel.apply_button.isEnabled()
    panel.deleteLater()
    app.processEvents()


def test_inline_picker_accepts_exact_color_without_applying_until_requested():
    from cvanalysis.ui.widgets.inline_color_picker import InlineColorPicker

    app = QApplication.instance() or QApplication([])
    picker = InlineColorPicker()
    picker.show()
    app.processEvents()
    picker.hex_input.setText("#123abc")
    picker.hex_input.editingFinished.emit()
    assert picker.currentColor().name() == "#123abc"
    picker.hex_input.setText("not-a-color")
    picker.hex_input.editingFinished.emit()
    assert picker.hex_input.text() == "#123abc"
    picker.setCurrentColor(QColor("black"))
    QTest.mouseClick(picker.field, Qt.LeftButton, pos=picker.field.rect().center())
    assert picker.currentColor() != QColor("black")
    picker.close()
    picker.deleteLater()
    app.processEvents()


def test_inline_picker_fits_small_inspector(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    tab = PlotTab(PlotSpec("cv_overlay", [synthetic_cv_runs[0].run_id]), BUILTIN_PRESETS["daily"], dataset)
    dialog = PlotInspectorDialog(tab)
    dialog.resize(540, 500)
    dialog.show()
    app.processEvents()
    panel = dialog.color_panel
    for widget in (panel.palette.field, panel.palette.hex_input, panel.apply_button):
        assert widget.isVisible()
        top_left = widget.mapTo(dialog, QPoint())
        assert dialog.rect().contains(top_left)
        assert dialog.rect().contains(top_left + QPoint(widget.width() - 1, widget.height() - 1))
    dialog.close()
    dialog.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_inspector_bar_width_takes_effect(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_contribution_vs_rate", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    dialog = PlotInspectorDialog(tab)
    dialog.bar_width_spin.setValue(0.4)
    # The inspector intentionally debounces updates; allow a busy Qt event
    # loop to deliver the timer instead of assuming a fixed 150 ms deadline.
    for _ in range(100):
        if spec.analysis_options.get("bar_width") == 0.4:
            break
        QTest.qWait(20)
    assert spec.analysis_options["bar_width"] == 0.4
    capacitive, diffusive = tab.figure.axes[0].containers[:2]
    assert capacitive[0].get_x() == diffusive[0].get_x()
    assert diffusive[0].get_width() == pytest.approx(0.4)
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
    assert "分析 / 论文选项..." not in labels
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

    clipboard = QGuiApplication.clipboard()
    try:
        tab.copy_vector_plot()
        app.processEvents()
        mime = clipboard.mimeData()
        assert mime is not None
        assert mime.hasFormat("image/svg+xml")
        svg = bytes(mime.data("image/svg+xml"))
        assert b"<svg" in svg
        assert b"</svg>" in svg
    finally:
        # Qt's offscreen clipboard must release its owned QMimeData before
        # QApplication is torn down; otherwise Windows can crash at exit.
        clipboard.clear()

    tab.deleteLater()
    menu.deleteLater()
    app.processEvents()


def test_reset_style_clears_current_plot_overrides(synthetic_cv_runs):
    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec(
        "cv_contribution_vs_rate",
        [run.run_id for run in synthetic_cv_runs],
        analysis_options={"bar_width": 0.4, "color_overrides": {"#1f77b4": "#ff0000"},
                          "color_overrides_by_role": {"text": {"#000000": "#0000ff"}}},
        overrides={"line_width": 3.0},
    )
    tab = PlotTab(spec, BUILTIN_PRESETS["daily"], dataset)
    tab.reset_style()
    assert spec.overrides == {}
    assert "bar_width" not in spec.analysis_options
    assert "color_overrides" not in spec.analysis_options
    assert "color_overrides_by_role" not in spec.analysis_options
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
