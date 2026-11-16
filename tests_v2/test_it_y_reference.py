"""I-T manual horizontal reference line and label."""
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.export import render_plot, render_svg_bytes
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec


def sample():
    runs = [SweepRun(f'it-{i}', f'sample {i}', 'it', np.array([0., 1., 2.]),
                     np.array([1e-6, 2e-6, 3e-6]) * (i + 1), SweepMetadata('test', {}))
            for i in range(2)]
    return Dataset(it_runs=runs)


def draw(data, options, *, normalization='none'):
    fig = Figure(figsize=(7, 5))
    FigureCanvasAgg(fig)
    spec = PlotSpec('it_curve', [run.run_id for run in data.it_runs], normalization=normalization,
                    analysis_options=options)
    warnings = render_plot(fig, data, spec, BUILTIN_PRESETS['daily'])
    fig.canvas.draw()
    return fig, spec, warnings


def line_and_label(fig):
    ax = fig.axes[0]
    lines = [line for line in ax.lines if line.get_gid() == 'it_manual_y_reference']
    labels = [text for text in ax.texts if text.get_gid() == 'it_manual_y_reference_label']
    return lines, labels


def test_manual_reference_drawn_once_with_custom_label_and_export():
    data = sample()
    options = {'it_y_reference_value': 1.25,
               'it_y_reference_unit': {'label': 'µA', 'factor': 1e6, 'dimension': 'current'},
               'it_y_reference_label': 'Threshold {value:.2f} {unit}',
               'unit_overrides': {'current': 'µA'}, 'it_reference_time': 1.}
    fig, spec, warnings = draw(data, options)
    assert not warnings
    lines, labels = line_and_label(fig)
    assert len(lines) == len(labels) == 1
    assert list(lines[0].get_ydata()) == pytest.approx([1.25, 1.25])
    assert labels[0].get_text() == 'Threshold 1.25 µA'
    assert 'Threshold 1.25 µA' not in [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    box = labels[0].get_window_extent(fig.canvas.get_renderer())
    bounds = fig.axes[0].get_window_extent(fig.canvas.get_renderer())
    assert bounds.contains(box.x0, box.y0) and bounds.contains(box.x1, box.y1)
    fig.axes[0].set_xlim(1.7, 2.1)
    fig.canvas.draw()
    assert labels[0]._check_xy(fig.canvas.get_renderer())
    box = labels[0].get_window_extent(fig.canvas.get_renderer())
    assert bounds.contains(box.x0, box.y0) and bounds.contains(box.x1, box.y1)
    assert b'<svg' in render_svg_bytes(data, spec, BUILTIN_PRESETS['daily'])


def test_reference_unit_conversion_and_incompatible_dimension():
    data = sample()
    options = {'it_y_reference_value': 1.5,
               'it_y_reference_unit': {'label': 'µA', 'factor': 1e6, 'dimension': 'current'},
               'unit_overrides': {'current': 'nA'}}
    fig, _, warnings = draw(data, options)
    assert not warnings
    lines, labels = line_and_label(fig)
    assert lines[0].get_ydata()[0] == pytest.approx(1500.)
    assert 'nA' in labels[0].get_text()
    options['it_current_display'] = 'reference_area'
    options['it_reference_area_cm2'] = 2.
    fig, _, warnings = draw(data, options)
    assert not line_and_label(fig)[0]
    assert any('参考线' in warning and '不兼容' in warning for warning in warnings)


def test_reference_capacitance_denominator_conversion():
    data = sample()
    options = {'it_y_reference_value': 2.,
               'it_y_reference_unit': {'label': 'nA/µF', 'factor': 1e3,
                                       'dimension': 'current_per_capacitance'},
               'it_current_display': 'reference_capacitance',
               'it_reference_capacitance_f': 1e-6,
               'it_reference_capacitance_unit': 'mF',
               'unit_overrides': {'current': 'nA/mF'}}
    fig, _, warnings = draw(data, options)
    assert not warnings
    lines, labels = line_and_label(fig)
    assert lines[0].get_ydata()[0] == pytest.approx(2000.)
    assert 'nA/mF' in labels[0].get_text()


def test_reference_editor_project_roundtrip_and_invalid_input(tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.plotting.it_references import store_references
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    from PySide6.QtWidgets import QDialog
    app = QApplication.instance() or QApplication([])
    data = sample()
    unit = {'label': 'µA', 'factor': 1e6, 'dimension': 'current'}
    editor = ItReferenceSettingsDialog(unit)
    try:
        editor.value_edit.setText('nan')
        editor.accept()
        assert editor.result() != QDialog.Accepted
        assert editor.error.text()
        editor.value_edit.setText('1.25')
        editor.label_edit.setText('Y={value:.2f} {unit}')
        editor.accept()
        assert editor.result() == QDialog.Accepted
        assert editor.record['legend_mode'] == 'hidden'
        spec = PlotSpec('it_curve', [r.run_id for r in data.it_runs],
                        analysis_options={'unit_overrides': {'current': 'µA'}})
        store_references(spec.analysis_options, [editor.record])
        path = tmp_path / 'reference.cvproj'
        save_project(path, data, plots=[spec])
        state = load_project(path)
        assert state.plots[0].analysis_options['it_y_references'][0]['unit'] == unit
        fig = Figure()
        FigureCanvasAgg(fig)
        assert not render_plot(fig, state.dataset, state.plots[0], BUILTIN_PRESETS['daily'])
        fig.canvas.draw()
        assert line_and_label(fig)[0][0].get_ydata()[0] == pytest.approx(1.25)
        assert 'Y=1.25 µA' not in [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    finally:
        editor.deleteLater()
        app.processEvents()


def test_editor_requires_new_value_when_switching_dimension():
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    old = {'label': 'µA', 'factor': 1e6, 'dimension': 'current'}
    new = {'label': 'µA/cm²', 'factor': 1e6, 'dimension': 'current_area'}
    editor = ItReferenceSettingsDialog(new, {'value': 2., 'unit': old})
    try:
        editor._use_current_unit()
        assert editor.value_edit.text() == ''
        editor.value_edit.setText('3')
        editor.accept()
        assert editor.record['unit'] == new
    finally:
        editor.deleteLater()
        app.processEvents()


def test_editor_converts_same_dimension_units():
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    old = {'label': 'µA', 'factor': 1e6, 'dimension': 'current'}
    new = {'label': 'nA', 'factor': 1e9, 'dimension': 'current'}
    editor = ItReferenceSettingsDialog(new, {'value': 2., 'unit': old})
    try:
        editor._use_current_unit()
        assert float(editor.value_edit.text()) == pytest.approx(2000.)
        editor.accept()
        assert editor.record['unit'] == new
    finally:
        editor.deleteLater()
        app.processEvents()


def test_reference_editor_renders_math_preview_and_rejects_invalid_math():
    from PySide6.QtWidgets import QDialog
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    unit = {'label': 'A', 'factor': 1., 'dimension': 'current'}
    editor = ItReferenceSettingsDialog(unit)
    try:
        editor.value_edit.setText('2')
        editor.label_edit.setText(r'$I_{value:.2f}$')
        assert editor.preview.pixmap() is not None
        editor.label_edit.setText(r'$\notacommand{x}$')
        editor.accept()
        assert editor.result() != QDialog.Accepted
        assert editor.error.text()
    finally:
        editor.deleteLater()
        app.processEvents()


def test_editor_handles_invalid_saved_unit_without_reinterpreting():
    from PySide6.QtWidgets import QDialog
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    current = {'label': 'A', 'factor': 1., 'dimension': 'current'}
    editor = ItReferenceSettingsDialog(current, {'value': 10., 'unit': 'bad unit'})
    try:
        editor.accept()
        assert editor.result() != QDialog.Accepted
        editor._use_current_unit()
        assert editor.value_edit.text() == ''
    finally:
        editor.deleteLater()
        app.processEvents()


def test_multiple_lines_have_independent_colors_and_legend_modes(tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    data = sample()
    unit = {'label': 'µA', 'factor': 1e6, 'dimension': 'current'}
    records = [
        {'id': 'one', 'value': 1.2, 'unit': unit, 'label': 'first {value:.1f}',
         'color': '#ff0000', 'legend_mode': 'hidden'},
        {'id': 'two', 'value': 2.5, 'unit': unit, 'label': 'second',
         'color': '#0044ff', 'legend_mode': 'label'},
        {'id': 'three', 'value': 3., 'unit': unit, 'label': 'third',
         'color': '#009900', 'legend_mode': 'custom', 'legend_label': 'limit {value:.2f} {unit}'},
    ]
    fig, spec, warnings = draw(data, {'it_y_references': records, 'unit_overrides': {'current': 'µA'}})
    assert not warnings
    lines, labels = line_and_label(fig)
    assert [line.get_ydata()[0] for line in lines] == pytest.approx([1.2, 2.5, 3.])
    assert [line.get_color() for line in lines] == ['#ff0000', '#0044ff', '#009900']
    assert len(labels) == 3
    legend = [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    assert 'first 1.2' not in legend
    assert 'second' in legend
    assert 'limit 3.00 µA' in legend
    assert b'<svg' in render_svg_bytes(data, spec, BUILTIN_PRESETS['daily'])
    path = tmp_path / 'references.cvproj'
    save_project(path, data, plots=[spec])
    restored = load_project(path)
    assert restored.plots[0].analysis_options['it_y_references'] == records
    fig = Figure()
    FigureCanvasAgg(fig)
    assert not render_plot(fig, restored.dataset, restored.plots[0], BUILTIN_PRESETS['daily'])
    assert len(line_and_label(fig)[0]) == 3


def test_math_and_newline_render_in_reference_label_and_legend():
    from io import BytesIO
    reference = {'id': 'math', 'value': 2., 'label': r'$I_{ref}={value:.2f}$\nsecond',
                 'legend_mode': 'custom', 'legend_label': r'$\frac{1}{2}$\nlimit'}
    fig, spec, warnings = draw(sample(), {'it_y_references': [reference]})
    assert not warnings
    assert line_and_label(fig)[1][0].get_text() == '$I_{ref}={2.00}$\nsecond'
    assert '$\\frac{1}{2}$\nlimit' in [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    assert b'<svg' in render_svg_bytes(sample(), spec, BUILTIN_PRESETS['daily'])
    for extension in ('png', 'pdf', 'tiff'):
        output = BytesIO()
        fig.savefig(output, format=extension)
        assert len(output.getvalue()) > 100


def test_invalid_imported_math_does_not_break_entire_plot():
    reference = {'id': 'bad-math', 'value': 2., 'label': r'$\badcommand{x}$', 'legend_mode': 'label'}
    fig, _, warnings = draw(sample(), {'it_y_references': [reference]})
    assert any('公式无效' in message for message in warnings)
    assert len(line_and_label(fig)[0]) == 1
    assert line_and_label(fig)[1][0].get_text().startswith(r'\$')


def test_manual_plot_title_supports_math_and_newline():
    data = sample()
    spec = PlotSpec('it_curve', [run.run_id for run in data.it_runs],
                    title=r'$I_{ref}$\nsecond')
    fig = Figure()
    FigureCanvasAgg(fig)
    assert not render_plot(fig, data, spec, BUILTIN_PRESETS['daily'].with_overrides({'show_title': True}))
    fig.canvas.draw()
    assert fig.axes[0].get_title() == '$I_{ref}$\nsecond'


def test_manual_and_hidden_labels_are_independent_of_legend(tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    data = sample()
    records = [
        {'id': 'manual', 'value': 1.5e-6, 'label': 'manual', 'color': '#ff0000',
         'legend_mode': 'hidden', 'label_visible': True, 'label_position_mode': 'manual',
         'label_position': [22., 73.]},
        {'id': 'hidden', 'value': 2.5e-6, 'label': 'legend only', 'color': '#0044ff',
         'legend_mode': 'label', 'label_visible': False},
    ]
    fig, spec, warnings = draw(data, {'it_y_references': records})
    assert not warnings
    lines, labels = line_and_label(fig)
    assert len(lines) == 2 and len(labels) == 1
    assert labels[0].get_position() == pytest.approx((.22, .73))
    assert labels[0].get_text() == 'manual'
    assert 'legend only' in [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    fig.set_size_inches(9, 4)
    fig.canvas.draw()
    assert labels[0].get_position() == pytest.approx((.22, .73))
    path = tmp_path / 'position.cvproj'
    save_project(path, data, plots=[spec])
    loaded = load_project(path)
    assert loaded.plots[0].analysis_options['it_y_references'] == records
    restored = Figure()
    FigureCanvasAgg(restored)
    assert not render_plot(restored, loaded.dataset, loaded.plots[0], BUILTIN_PRESETS['daily'])
    restored.canvas.draw()
    assert line_and_label(restored)[1][0].get_position() == pytest.approx((.22, .73))
    assert b'<svg' in render_svg_bytes(loaded.dataset, loaded.plots[0], BUILTIN_PRESETS['daily'])


def test_reference_label_controls_preserve_position_when_hidden():
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    unit = {'label': 'A', 'factor': 1., 'dimension': 'current'}
    editor = ItReferenceSettingsDialog(unit)
    try:
        editor.value_edit.setText('2')
        editor.label_position_mode.setCurrentIndex(editor.label_position_mode.findData('manual'))
        editor.label_x.setValue(23.5)
        editor.label_y.setValue(72.)
        editor.label_visible.setChecked(False)
        assert not editor.label_x.isEnabled()
        editor.legend_mode.setCurrentIndex(editor.legend_mode.findData('label'))
        editor.label_edit.setText('legend only')
        editor.accept()
        assert editor.record['label_visible'] is False
        assert editor.record['label_position_mode'] == 'manual'
        assert editor.record['label_position'] == [23.5, 72.]
        assert editor.record['legend_mode'] == 'label'
        restored = ItReferenceSettingsDialog(unit, editor.record)
        try:
            assert not restored.label_visible.isChecked()
            restored.label_visible.setChecked(True)
            assert restored.label_x.isEnabled()
            assert restored.label_x.value() == pytest.approx(23.5)
        finally:
            restored.deleteLater()
    finally:
        editor.deleteLater()
        app.processEvents()


def test_invalid_manual_label_position_falls_back_to_auto():
    reference = {'id': 'bad', 'value': 2e-6, 'label': 'threshold',
                 'label_position_mode': 'manual', 'label_position': [float('nan'), 50]}
    fig, _, warnings = draw(sample(), {'it_y_references': [reference]})
    assert len(line_and_label(fig)[1]) == 1
    assert any('标签坐标无效' in warning for warning in warnings)


def test_reference_legend_survives_hidden_dataset_legends():
    data = sample()
    for run in data.it_runs:
        run.legend_template = '{ }'
    record = {'id': 'one', 'value': 2., 'label': 'line', 'legend_mode': 'label', 'color': '#444444'}
    fig, _, _ = draw(data, {'it_y_references': [record]})
    assert [text.get_text() for text in fig.axes[0].get_legend().get_texts()] == ['line']


def test_custom_legend_can_start_with_underscore():
    data = sample()
    for run in data.it_runs:
        run.legend_template = '{ }'
    record = {'id': 'one', 'value': 2., 'label': 'line', 'legend_mode': 'custom',
              'legend_label': '_limit', 'color': '#444444'}
    fig, _, _ = draw(data, {'it_y_references': [record]})
    assert [text.get_text() for text in fig.axes[0].get_legend().get_texts()] == ['_limit']


def test_manager_cancel_isolated_and_delete():
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceManagerDialog
    app = QApplication.instance() or QApplication([])
    records = [{'id': 'one', 'value': 1., 'unit': {'label': 'A', 'factor': 1., 'dimension': 'current'},
                'label': 'first', 'color': '#ff0000', 'legend_mode': 'hidden'}]
    dialog = ItReferenceManagerDialog(records, records[0]['unit'], 'one')
    try:
        assert dialog.table.currentRow() == 0
        dialog.delete_selected()
        assert not dialog.records
        dialog.reject()
        assert len(records) == 1
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_manager_double_click_edits_value_color_and_legend(monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QDialog
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceManagerDialog, ItReferenceSettingsDialog
    app = QApplication.instance() or QApplication([])
    unit = {'label': 'A', 'factor': 1., 'dimension': 'current'}
    records = [{'id': 'one', 'value': 1., 'unit': unit, 'label': 'first',
                'color': '#ff0000', 'legend_mode': 'hidden'}]
    dialog = ItReferenceManagerDialog(records, unit, 'one')
    try:
        def fake_exec(editor):
            editor.value_edit.setText('2')
            editor.color_picker.setCurrentColor(QColor('#0088ff'))
            editor.legend_mode.setCurrentIndex(editor.legend_mode.findData('custom'))
            editor.legend_edit.setText('limit {value:.2f}')
            editor.accept()
            return QDialog.Accepted
        monkeypatch.setattr(ItReferenceSettingsDialog, 'exec', fake_exec)
        dialog.table.cellDoubleClicked.emit(0, 0)
        updated = dialog.records[0]
        assert updated['value'] == 2.
        assert updated['color'] == '#0088ff'
        assert updated['legend_mode'] == 'custom'
        assert updated['legend_label'] == 'limit {value:.2f}'
        assert records[0]['value'] == 1.
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_panel_table_updates_without_resetting_unapplied_input(monkeypatch):
    from PySide6.QtWidgets import QDialog
    from cvanalysis.ui.dialogs.it_reference_dialog import ItReferenceSettingsDialog
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    data = sample()
    tab = PlotTab(PlotSpec('it_curve', [r.run_id for r in data.it_runs]), BUILTIN_PRESETS['daily'], data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    try:
        menu = tab._build_settings_menu()
        assert '参考线与图例...' in [action.text() for action in menu.actions()]
        pending = panel.controls['it_reference_time']
        pending.setText('1.234')
        def fake_exec(dialog):
            dialog.value_edit.setText('1.5')
            dialog.accept()
            return QDialog.Accepted
        monkeypatch.setattr(ItReferenceSettingsDialog, 'exec', fake_exec)
        tab.open_it_reference_manager(add=True)
        assert panel._it_reference_table.rowCount() == 1
        assert pending.text() == '1.234'
        assert tab.spec.analysis_options['it_y_references'][0]['legend_mode'] == 'hidden'
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('position_mode', ['auto', 'manual', 'hidden'])
def test_double_click_on_line_and_label_opens_selected_manager(monkeypatch, position_mode):
    from matplotlib.backend_bases import MouseEvent
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    data = sample()
    reference = {'id': 'chosen', 'value': 2e-6, 'label': 'threshold',
                 'color': '#666666', 'legend_mode': 'hidden',
                 'label_position_mode': position_mode, 'label_position': [30, 70],
                 'label_visible': position_mode != 'hidden'}
    tab = PlotTab(PlotSpec('it_curve', [r.run_id for r in data.it_runs],
                           analysis_options={'it_y_references': [reference]}),
                  BUILTIN_PRESETS['daily'], data)
    calls = []
    monkeypatch.setattr(tab, 'open_it_reference_manager', lambda **kw: calls.append(kw))
    try:
        tab.canvas.draw()
        ax = tab.figure.axes[0]
        x, y = ax.transData.transform((.2, 2e-6))
        event = MouseEvent('button_press_event', tab.canvas, x, y, button=1, dblclick=True)
        tab._reference_double_click(event)
        assert calls == [{'selected_id': 'chosen'}]
        calls.clear()
        if position_mode == 'hidden':
            assert not line_and_label(tab.figure)[1]
            return
        label = line_and_label(tab.figure)[1][0]
        box = label.get_window_extent(tab.canvas.get_renderer())
        event = MouseEvent('button_press_event', tab.canvas, (box.x0 + box.x1) / 2,
                           (box.y0 + box.y1) / 2, button=1, dblclick=True)
        tab._reference_double_click(event)
        assert calls == [{'selected_id': 'chosen'}]
    finally:
        tab.deleteLater()
        app.processEvents()
