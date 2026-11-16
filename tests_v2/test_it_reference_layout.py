"""I-T reference labels: formatting, positioning, redraw and persistence."""
import copy

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.export import render_plot, render_svg_bytes
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


@pytest.fixture
def it_data():
    first = SweepRun("it-first", "sample A", "it", np.array([0., 1., 2.]),
                     np.array([1e-6, 2e-6, 3e-6]), SweepMetadata("test", {}))
    second = copy.deepcopy(first)
    second.run_id = "it-second"
    second.name = "sample B"
    return Dataset(it_runs=[first, second])


def render(data, options, run_ids=None):
    fig = Figure(figsize=(7, 5))
    FigureCanvasAgg(fig)
    spec = PlotSpec("it_curve", run_ids or [data.it_runs[0].run_id], analysis_options=options)
    warnings = render_plot(fig, data, spec, BUILTIN_PRESETS["daily"])
    fig.canvas.draw()
    return fig, spec, warnings


@pytest.mark.parametrize("number_format,digits,unit,expected", [
    ("auto", 4, "original", "t=1 s, I=2e-06 A"),
    ("fixed", 2, "µA", "t=1.00 s, I=2.00 µA"),
    ("scientific", 2, "µA", "t=1.00e+00 s, I=2.00e+00 µA"),
    ("significant", 3, "nA", "t=1.00 s, I=2.00e+03 nA"),
    ("auto", 4, "auto", "t=1 s, I=2 µA"),
])
def test_reference_number_format_and_units(it_data, number_format, digits, unit, expected):
    fig, _, warnings = render(it_data, {"it_reference_time": 1, "it_reference_number_format": number_format,
                                       "it_reference_digits": digits, "it_reference_current_unit": unit})
    assert not warnings
    assert fig.axes[0].texts[0].get_text() == expected
    assert fig.axes[0].lines[0].get_ydata()[1] == pytest.approx(2e-6)


@pytest.mark.parametrize("normalization,params,expected", [
    ("area", {"area_cm2": 2}, "1 µA/cm²"),
    ("mass", {"mass_mg": 2}, "1 mA/g"),
])
def test_reference_auto_unit_uses_normalized_current(it_data, normalization, params, expected):
    run = it_data.it_runs[0]
    for key, value in params.items():
        setattr(run.params, key, value)
    fig = Figure()
    spec = PlotSpec("it_curve", [run.run_id], normalization=normalization,
                    analysis_options={"it_reference_time": 1, "it_reference_label_mode": "current",
                                      "it_reference_current_unit": "auto"})
    render_plot(fig, it_data, spec, BUILTIN_PRESETS["daily"])
    assert expected in fig.axes[0].texts[0].get_text()
    spec.analysis_options["it_reference_current_unit"] = "pA"
    render_plot(fig, it_data, spec, BUILTIN_PRESETS["daily"])
    assert ("pA/cm²" if normalization == "area" else "pA/g") in fig.axes[0].texts[0].get_text()


def test_custom_template_and_literal_text(it_data):
    options = {"it_reference_time": 1.1, "it_reference_label_mode": "custom",
               "it_reference_label_text": "{name}: {time} s / {current} {unit} / {unknown}",
               "it_reference_current_unit": "µA"}
    fig, _, _ = render(it_data, options)
    assert fig.axes[0].texts[0].get_text() == "sample A: 1 s / 2 µA / {unknown}"
    options["it_reference_label_text"] = "Existing literal label { }"
    fig, _, _ = render(it_data, options)
    assert fig.axes[0].texts[0].get_text() == "Existing literal label { }"


def test_custom_numeric_format_keeps_zeros_on_canvas_and_svg(it_data):
    options = {"it_reference_time": 1, "it_reference_label_mode": "custom",
               "it_reference_label_text": "I={current:.3f} {unit}",
               "it_reference_current_unit": "µA"}
    fig, spec, _ = render(it_data, options)
    assert fig.axes[0].texts[0].get_text() == "I=2.000 µA"
    assert b"<svg" in render_svg_bytes(it_data, spec, BUILTIN_PRESETS["daily"])


def test_custom_template_panel_previews_and_rejects_invalid_expression(it_data):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = it_data.it_runs[0]
    tab = PlotTab(PlotSpec("it_curve", [run.run_id]), BUILTIN_PRESETS["daily"], it_data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    try:
        mode = panel.controls["it_reference_label_mode"]
        mode.setCurrentIndex(mode.findData("custom"))
        edit = panel.controls["it_reference_label_text"]
        edit.setText("I={current:.2f} {unit}")
        panel.apply()
        assert tab.spec.analysis_options["it_reference_label_text"] == edit.text()
        edit.setText("{current.__class__}")
        panel.apply()
        assert tab.spec.analysis_options["it_reference_label_text"] == "I={current:.2f} {unit}"
        assert panel.error.text()
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_auto_positions_reflow_and_avoid_each_other(it_data):
    runs = it_data.it_runs
    fig, spec, _ = render(it_data, {"it_reference_time": 2}, [run.run_id for run in runs])
    ax = fig.axes[0]
    assert len(ax.texts) == 2
    def check():
        renderer = fig.canvas.get_renderer()
        bounds = ax.get_window_extent(renderer)
        boxes = [text.get_window_extent(renderer) for text in ax.texts]
        for box in boxes:
            assert box.x0 >= bounds.x0 - 1 and box.x1 <= bounds.x1 + 1
            assert box.y0 >= bounds.y0 - 1 and box.y1 <= bounds.y1 + 1
            legend = ax.get_legend()
            if legend is not None:
                intersection = Bbox.intersection(box, legend.get_window_extent(renderer))
                assert intersection is None or intersection.width * intersection.height < 1
        intersection = Bbox.intersection(*boxes)
        assert intersection is None or intersection.width * intersection.height < 1
    check()
    fig.set_size_inches(9, 4)
    ax.set_xlim(-1, 2.1)
    fig.canvas.draw()
    check()
    assert b"<svg" in render_svg_bytes(it_data, spec, BUILTIN_PRESETS["daily"])


def test_auto_position_avoids_nearby_reference_line(it_data):
    from matplotlib.path import Path
    fig, _, _ = render(it_data, {"it_reference_time": 1, "it_reference_label_mode": "current"})
    ax = fig.axes[0]
    nearby = ax.axhline(2.12e-6, color="red")
    fig.canvas.draw()
    box = ax.texts[0].get_window_extent(fig.canvas.get_renderer())
    path = Path(nearby.get_transform().transform(nearby.get_xydata()))
    assert not path.intersects_bbox(box, filled=False)
    # A later data change must trigger a new placement even on a cached redraw.
    center_y = (box.y0 + box.y1) / 2
    data_y = ax.transData.inverted().transform((box.x0, center_y))[1]
    nearby.set_ydata([data_y, data_y])
    fig.canvas.draw()
    box = ax.texts[0].get_window_extent(fig.canvas.get_renderer())
    path = Path(nearby.get_transform().transform(nearby.get_xydata()))
    assert not path.intersects_bbox(box, filled=False)


def test_reference_time_label_visibility_keeps_lines_points_and_manual_y_label(it_data):
    runs = it_data.it_runs
    options = {"it_reference_time": 1, "it_reference_show_labels": False,
               "it_y_references": [{"id": "user-line", "value": 2.5e-6,
                                    "label": "manual Y", "legend_mode": "hidden"}]}
    fig, spec, warnings = render(it_data, options, [run.run_id for run in runs])
    assert not warnings
    ax = fig.axes[0]
    assert [text.get_text() for text in ax.texts] == ['manual Y']
    assert len([line for line in ax.lines if line.get_linestyle() == '--']) == 3
    assert len([line for line in ax.lines if line.get_marker() == 'o']) == 2
    assert b'<svg' in render_svg_bytes(it_data, spec, BUILTIN_PRESETS['daily'])
    options['it_reference_show_labels'] = True
    options['it_reference_label_visibility'] = {runs[0].run_id: False}
    fig, _, _ = render(it_data, options, [run.run_id for run in runs])
    assert len(fig.axes[0].texts) == 2  # one time-point label and one manual Y label


def test_reference_time_label_controls_and_project_remap(it_data, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    runs = it_data.it_runs
    tab = PlotTab(PlotSpec('it_curve', [run.run_id for run in runs]), BUILTIN_PRESETS['daily'], it_data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    try:
        panel.controls['it_reference_time'].setText('1')
        assert panel.controls['it_reference_show_labels'].isChecked()
        panel._it_label_visibility_items[runs[0].run_id].setCheckState(Qt.Unchecked)
        mode = panel.controls['it_reference_position']
        mode.setCurrentIndex(mode.findData('manual'))
        for spin, value in zip(panel._it_position_controls[runs[0].run_id], (20., 30.)):
            spin.setValue(value)
        panel.controls['it_reference_show_labels'].setChecked(False)
        panel.apply()
        assert tab.spec.analysis_options['it_reference_show_labels'] is False
        assert len(tab.figure.axes[0].texts) == 0
        assert len([line for line in tab.figure.axes[0].lines if line.get_linestyle() == '--']) == 2
        path = tmp_path / 'time-labels.cvproj'
        save_project(path, it_data, plots=[tab.spec])
        state = load_project(path)
        restored = state.plots[0]
        restored_runs = state.dataset.it_runs
        assert restored.analysis_options['it_reference_show_labels'] is False
        assert restored.analysis_options['it_reference_label_visibility'][restored_runs[0].run_id] is False
        assert restored.analysis_options['it_reference_positions'][restored_runs[0].run_id] == [20., 30.]
        restored_tab = PlotTab(restored, BUILTIN_PRESETS['daily'], state.dataset)
        try:
            panel.bind(restored_tab)
            assert not panel.controls['it_reference_show_labels'].isChecked()
            panel.controls['it_reference_show_labels'].setChecked(True)
            panel.apply()
            assert len(restored_tab.figure.axes[0].texts) == 1
            assert panel._it_label_visibility_items[restored_runs[0].run_id].checkState() == Qt.Unchecked
        finally:
            restored_tab.deleteLater()
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()
@pytest.mark.parametrize("inverted", [False, True])
def test_auto_labels_align_and_follow_numeric_order_after_reflow(inverted):
    values = [1.2e-6, -4e-6, 8e-6, 0.0]
    runs = [SweepRun(f"it-{i}", "sample " + "x" * i, "it",
                     np.array([0., 1., 2.]), np.array([value, value, value]),
                     SweepMetadata("test", {}))
            for i, value in enumerate(values)]
    data = Dataset(it_runs=runs)
    fig, spec, _ = render(data, {"it_reference_time": 1,
                                 "it_reference_label_mode": "custom",
                                 "it_reference_label_text": "{name}: {current} {unit}"},
                          [run.run_id for run in runs])
    ax = fig.axes[0]
    if inverted:
        ax.invert_yaxis()
    for width, height in ((7, 5), (5, 3)):
        fig.set_size_inches(width, height)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bounds = ax.get_window_extent(renderer)
        ordered = sorted(ax.texts, key=lambda text: text.xy[1])
        boxes = [text.get_window_extent(renderer) for text in ordered]
        assert all(text.get_ha() == "left" for text in ordered)
        assert max(box.x0 for box in boxes) - min(box.x0 for box in boxes) < 0.1
        for box in boxes:
            assert bounds.x0 <= box.x0 and box.x1 <= bounds.x1
            assert bounds.y0 <= box.y0 and box.y1 <= bounds.y1
        assert all(lower.y1 <= upper.y0 for lower, upper in zip(boxes, boxes[1:]))
    assert b"<svg" in render_svg_bytes(data, spec, BUILTIN_PRESETS["daily"])


def test_manual_positions_and_settings_survive_project_reload(it_data, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    runs = it_data.it_runs
    tab = PlotTab(PlotSpec("it_curve", [run.run_id for run in runs]), BUILTIN_PRESETS["daily"], it_data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    panel.controls["it_reference_time"].setText("1")
    position = panel.controls["it_reference_position"]
    position.setCurrentIndex(position.findData("manual"))
    for run, coords in zip(runs, ((20., 30.), (70., 80.))):
        for widget, value in zip(panel._it_position_controls[run.run_id], coords):
            widget.setValue(value)
    panel.controls["it_reference_leader"].setChecked(True)
    current_unit = panel.controls["it_reference_current_unit"]
    current_unit.setCurrentIndex(current_unit.findData("µA"))
    number_format = panel.controls["it_reference_number_format"]
    number_format.setCurrentIndex(number_format.findData("fixed"))
    panel.controls["it_reference_digits"].setValue(2)
    panel.apply()
    path = tmp_path / "reference.cvproj"
    save_project(path, it_data, plots=[tab.spec])
    state = load_project(path)
    spec = state.plots[0]
    positions = spec.analysis_options["it_reference_positions"]
    assert [positions[run_id] for run_id in spec.run_ids] == [[20., 30.], [70., 80.]]
    fig = Figure()
    FigureCanvasAgg(fig)
    render_plot(fig, state.dataset, spec, BUILTIN_PRESETS["daily"])
    fig.canvas.draw()
    labels = fig.axes[0].texts
    assert [text.get_position() for text in labels] == [(0.2, 0.3), (0.7, 0.8)]
    assert all(text.arrow_patch is not None for text in labels)
    assert all(text.get_text() == "t=1.00 s, I=2.00 µA" for text in labels)
    restored_tab = PlotTab(spec, BUILTIN_PRESETS["daily"], state.dataset)
    panel.bind(restored_tab)
    assert [tuple(widget.value() for widget in panel._it_position_controls[run_id])
            for run_id in spec.run_ids] == [(20., 30.), (70., 80.)]
    panel.deleteLater()
    tab.deleteLater()
    restored_tab.deleteLater()
    app.processEvents()
