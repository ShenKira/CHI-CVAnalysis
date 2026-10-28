# -*- coding: utf-8 -*-
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from cvanalysis.io.registry import load_files
from cvanalysis.ui.main_window import MainWindow


def test_workspace_import_and_plot_smoke(tmp_path, synthetic_cv_runs, synthetic_eis_run):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window.settings_service.settings["analysis"]["area_cm2"] = 2.0
    dataset = type("D", (), {})()
    # Use a real Dataset through the public workflow.
    from cvanalysis.domain.models import Dataset

    dataset = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run])
    window._on_import_complete(dataset, [])
    app.processEvents()
    assert window.tabs.count() >= 1
    assert window.results_panel.cv_model.rowCount() == 3
    assert window.results_panel.eis_model.rowCount() == 1
    assert synthetic_cv_runs[0].summary.mean_cap_per_area == synthetic_cv_runs[0].summary.mean_capacitance_F / 2.0

    for kind in (
        "cv_cap_scan",
        "cv_current_scan",
        "cv_bvalue",
        "cv_contribution",
        "cv_contribution_vs_rate",
        "cv_trasatti",
        "eis_nyquist",
        "eis_bode",
    ):
        window._request_plot(kind)
        app.processEvents()
    assert window.tabs.count() >= 7

    window._select_run_ids([synthetic_eis_run.run_id])
    window.fit_selected_eis()
    from PySide6.QtTest import QTest
    for _ in range(500):
        app.processEvents()
        if not window._tasks:
            break
        QTest.qWait(10)
    assert synthetic_eis_run.run_id in window.fits
    assert any(window.tabs.widget(i).spec.kind == "eis_fit" for i in range(window.tabs.count()))
    window.close()


def test_dataset_tree_model_parent_and_row_identity(tmp_path, synthetic_cv_runs):
    from cvanalysis.ui.models.dataset_model import DatasetTreeModel
    from cvanalysis.domain.models import Dataset

    app = QApplication.instance() or QApplication([])
    model = DatasetTreeModel()
    model.set_dataset(Dataset(cv_runs=list(synthetic_cv_runs)))
    group = model.index(0, 0)
    run = model.index(0, 0, group)
    cycle = model.index(0, 0, run)
    assert group.isValid() and run.isValid() and cycle.isValid()
    assert not model.parent(group).isValid()
    assert model.parent(run) == group
    assert model.parent(cycle) == run
    assert model.rowCount(run) >= 1
    assert model.data(cycle).startswith("Cycle")
    app.processEvents()


def test_quick_style_dialog_and_plot_tab_overrides(tmp_path, synthetic_cv_runs):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.presets import BUILTIN_PRESETS
    from cvanalysis.plotting.spec import PlotSpec
    from cvanalysis.ui.dialogs.quick_style_dialog import QuickStyleDialog
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    dialog = QuickStyleDialog(BUILTIN_PRESETS["ieee-single"], "IEEE")
    dialog.line_width_spin.setValue(2.5)
    dialog.xlabel_size_spin.setValue(11.0)
    dialog.font_family_edit.setText("Arial, DejaVu Sans")
    dialog.aspect_combo.setCurrentIndex(dialog.aspect_combo.findData("4:3"))
    dialog.sync_export_cb.setChecked(True)
    dialog.set_plot_flags(False, False)
    overrides = dialog.overrides()
    assert overrides["line_width"] == 2.5
    assert overrides["xlabel_size"] == 11.0
    assert overrides["font_family"] == ("Arial", "DejaVu Sans")
    assert overrides["axes_aspect"] == "4:3"
    assert overrides["figure_size"] == pytest.approx((3.2 * 4.0 / 3.0, 3.2))
    assert overrides["legend"] is False
    assert overrides["annotation"] is False
    dialog.close()

    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    spec = PlotSpec("cv_overlay", [run.run_id for run in synthetic_cv_runs])
    tab = PlotTab(spec, BUILTIN_PRESETS["ieee-single"], dataset)
    tab.apply_overrides({"line_width": 3.25, "legend": False, "annotation": False})
    assert spec.overrides["line_width"] == 3.25
    assert tab.style.line_width == 3.25
    assert tab.spec.show_legend is False
    assert tab.spec.annotations is False
    tab.deleteLater()
    app.processEvents()


def test_non_default_preset_opens_quick_style_dialog(tmp_path, synthetic_cv_runs):
    from unittest.mock import patch
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QDialog
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    class FakeDialog(QObject):
        apply_requested = Signal(dict)
        save_requested = Signal(dict)

        def __init__(self, style, preset_name, parent=None):
            super().__init__(parent)
            self.style = style
            self.preset_name = preset_name

        def exec(self):
            self.apply_requested.emit({"line_width": 4.0, "xlabel_size": 12.0})
            return QDialog.Rejected

    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    with patch("cvanalysis.ui.main_window.QuickStyleDialog", FakeDialog):
        index = window.preset_combo.findData("ieee-single")
        window.preset_combo.setCurrentIndex(index)
        app.processEvents()
    tab = window.tabs.currentWidget()
    assert tab.spec.preset == "ieee-single"
    assert tab.spec.overrides["line_width"] == 4.0
    assert tab.style.line_width == 4.0
    window.close()


def test_dataset_multi_select_delete_and_clear(tmp_path, synthetic_cv_runs):
    from unittest.mock import patch
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow
    from PySide6.QtWidgets import QMessageBox

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    window._select_all_runs()
    assert len(window._selected_run_ids()) == len(synthetic_cv_runs)
    window._clear_tree_selection()
    assert window._selected_run_ids() == []
    window._select_all_runs()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        window._delete_selected_runs()
    app.processEvents()
    assert window.dataset.is_empty
    assert window.tabs.count() == 0
    window.close()


def test_long_filename_is_shortened_in_tree_and_detail_label(tmp_path, synthetic_cv_runs):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    run = synthetic_cv_runs[0]
    run.name = "Sample-ABCDE-12345_CV_1dot5V_0dot01Vps_really_long_filename_for_test"
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    index = window.dataset_model.index_for_run(run.run_id)
    short_label = window.dataset_model.data(index)
    assert len(short_label) <= 34
    assert "…" in short_label
    window._select_run_ids([run.run_id])
    app.processEvents()
    assert run.display_name in window.file_detail_label.text()
    window.close()


def test_plot_selection_is_per_tab_and_defaults_follow_checked_runs(tmp_path, synthetic_cv_runs):
    from PySide6.QtCore import Qt
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    overlay = next(
        window.tabs.widget(i)
        for i in range(window.tabs.count())
        if window.tabs.widget(i).spec.kind == "cv_overlay"
    )
    assert len(overlay.spec.run_ids) == len(synthetic_cv_runs)
    assert overlay.spec.follow_dataset is True

    first = synthetic_cv_runs[0]
    index = window.dataset_model.index_for_run(first.run_id)
    window.dataset_model.setData(index, Qt.Unchecked, Qt.CheckStateRole)
    app.processEvents()
    assert set(overlay.spec.run_ids) == {run.run_id for run in synthetic_cv_runs[1:]}

    overlay.follow_cb.setChecked(False)
    app.processEvents()
    assert overlay.spec.follow_dataset is False
    second = synthetic_cv_runs[1]
    second_index = window.dataset_model.index_for_run(second.run_id)
    window.dataset_model.setData(second_index, Qt.Unchecked, Qt.CheckStateRole)
    app.processEvents()
    assert set(overlay.spec.run_ids) == {run.run_id for run in synthetic_cv_runs[1:]}

    overlay.follow_cb.setChecked(True)
    app.processEvents()
    assert overlay.spec.run_ids == [synthetic_cv_runs[2].run_id]

    window._request_plot("cv_cap_scan")
    app.processEvents()
    created = [
        window.tabs.widget(i)
        for i in range(window.tabs.count())
        if window.tabs.widget(i).spec.kind == "cv_cap_scan"
    ][-1]
    assert created.spec.run_ids == [synthetic_cv_runs[2].run_id]

    window._request_plot("cv_overlay", run_ids=[first.run_id])
    explicit = [
        window.tabs.widget(i)
        for i in range(window.tabs.count())
        if window.tabs.widget(i).spec.kind == "cv_overlay"
    ][-1]
    assert explicit.spec.run_ids == [first.run_id]
    assert explicit.spec.follow_dataset is False
    window.close()


def test_plot_data_dialog_collects_runs_cycles_and_templates(tmp_path, synthetic_cv_runs):
    from PySide6.QtCore import Qt
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.spec import PlotSpec
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog

    app = QApplication.instance() or QApplication([])
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    run = synthetic_cv_runs[0]
    spec = PlotSpec("cv_overlay", [run.run_id])
    dialog = PlotDataDialog(dataset, spec, spec.kind)
    dialog._set_all_checked(False)
    item = dialog._run_items[run.run_id]
    item.setCheckState(0, Qt.Checked)
    dialog._template_edits[run.run_id].setText("{CV_Voltage}-{Cycle_Number}")
    assert dialog.selected_run_ids() == [run.run_id]
    assert dialog.legend_templates() == {run.run_id: "{CV_Voltage}-{Cycle_Number}"}
    assert dialog.cycle_selection() == {}

    item.child(0).setCheckState(0, Qt.Unchecked)
    assert dialog.cycle_selection() == {run.run_id: [run.cycles[1].index]}
    dialog.close()
    app.processEvents()


def test_legend_template_dialog_constructs_with_parent(tmp_path, synthetic_cv_runs):
    from unittest.mock import patch
    from PySide6.QtWidgets import QDialog
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.dialogs.legend_dialog import LegendTemplateDialog
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    run = synthetic_cv_runs[0]
    window._select_run_ids([run.run_id])
    with patch.object(LegendTemplateDialog, "exec", return_value=QDialog.Rejected):
        window._edit_legend_template_for_selection()
    window.close()


def test_main_window_applies_legend_template_and_plot_data_dialog(tmp_path, synthetic_cv_runs):
    from unittest.mock import patch
    from PySide6.QtWidgets import QDialog
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    run = synthetic_cv_runs[0]
    overlay = next(
        window.tabs.widget(i)
        for i in range(window.tabs.count())
        if window.tabs.widget(i).spec.kind == "cv_overlay"
    )

    class FakeLegendDialog:
        def __init__(self, runs, parent=None, *, file_numbers=None):
            self.runs = runs

        def exec(self):
            return QDialog.Accepted

        def template(self):
            return "{CV_Voltage}-{Cycle_Number}"

    window._select_run_ids([run.run_id])
    with patch("cvanalysis.ui.main_window.LegendTemplateDialog", FakeLegendDialog):
        window._edit_legend_template_for_selection()
    assert run.legend_template == "{CV_Voltage}-{Cycle_Number}"

    class FakeDataDialog:
        def __init__(self, dataset, spec, kind, parent=None):
            self.spec = spec

        def exec(self):
            return QDialog.Accepted

        def selected_run_ids(self):
            return [run.run_id]

        def cycle_selection(self):
            return {run.run_id: [1]}

        def legend_templates(self):
            return {run.run_id: "{Scan_Rate}"}

    with patch("cvanalysis.ui.main_window.PlotDataDialog", FakeDataDialog):
        window._edit_plot_data(overlay)
    assert overlay.spec.run_ids == [run.run_id]
    assert overlay.spec.cycle_selection == {run.run_id: [1]}
    assert overlay.spec.legend_templates == {run.run_id: "{Scan_Rate}"}
    assert overlay.spec.follow_dataset is False
    window.close()


def test_results_panel_table_resize_modes(tmp_path):
    from PySide6.QtWidgets import QHeaderView
    from cvanalysis.ui.widgets.results_panel import ResultsPanel

    app = QApplication.instance() or QApplication([])
    panel = ResultsPanel()
    header = panel.cv_table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Interactive
    assert header.sectionResizeMode(1) == QHeaderView.Interactive
    assert not header.stretchLastSection()
    panel.deleteLater()
    app.processEvents()


def test_column_drag_survives_refresh_restart_and_reset(tmp_path, synthetic_cv_runs):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from cvanalysis.domain.models import Dataset

    app = QApplication.instance() or QApplication([])
    path = tmp_path / "columns.json"
    window = MainWindow(settings_path=path)
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    window.show()
    app.processEvents()
    header = window.results_panel.cv_table.horizontalHeader()
    start_width = header.sectionSize(1)
    boundary = header.sectionViewportPosition(1) + start_width
    start = QPoint(boundary - 1, header.height() // 2)
    QTest.mousePress(header.viewport(), Qt.LeftButton, pos=start)
    QTest.mouseMove(header.viewport(), start + QPoint(35, 0))
    QTest.mouseRelease(header.viewport(), Qt.LeftButton, pos=start + QPoint(35, 0))
    assert header.sectionSize(1) > start_width
    dragged_width = header.sectionSize(1)
    window.tree.header().resizeSection(7, 240)
    window.results_panel.eis_table.horizontalHeader().resizeSection(7, 250)
    window._refresh_model_and_panel()
    app.processEvents()
    assert header.sectionSize(1) == dragged_width
    window.close()

    reopened = MainWindow(settings_path=path)
    app.processEvents()
    assert reopened.results_panel.cv_table.columnWidth(1) == dragged_width
    assert reopened.tree.columnWidth(7) == 240
    assert reopened.results_panel.eis_table.columnWidth(7) == 250
    reopened.reset_layout()
    app.processEvents()
    assert reopened.tree.columnWidth(7) != 240
    assert reopened.results_panel.eis_table.columnWidth(7) != 250
    reopened.close()


def test_plot_dialog_columns_are_resizable_and_content_fit_is_bounded(tmp_path, synthetic_cv_runs):
    from PySide6.QtWidgets import QHeaderView
    from cvanalysis.domain.models import Dataset
    from cvanalysis.plotting.spec import PlotSpec
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog

    app = QApplication.instance() or QApplication([])
    run = synthetic_cv_runs[0]
    run.name = "very_long_name_" * 100
    dialog = PlotDataDialog(Dataset(cv_runs=[run]), PlotSpec("cv_overlay", [run.run_id]), "cv_overlay")
    dialog.show()
    app.processEvents()
    for column in range(3):
        assert dialog.tree.header().sectionResizeMode(column) == QHeaderView.Interactive
        assert dialog.tree.columnWidth(column) <= 360
    assert run.display_name in dialog.tree.topLevelItem(0).toolTip(0)
    dialog.tree.header().resizeSection(2, 420)
    dialog._refresh_previews()
    app.processEvents()
    assert dialog.tree.columnWidth(2) == 420
    dialog.close()


def test_column_restore_ignores_invalid_settings_and_initial_fit_keeps_units(tmp_path):
    from cvanalysis.ui.widgets.results_panel import ResultsPanel

    app = QApplication.instance() or QApplication([])
    panel = ResultsPanel()
    columns = panel.cv_columns
    columns.restore({"文件": "bad", "扫速": -1, "循环": True, "有效": 100000})
    columns.restore(None)
    panel.cv_model.set_data(panel.cv_model.headers, [["sample", "0.01", 2, 2, "100 μF", "", "", "", "", ""]])
    app.processEvents()
    assert panel.cv_table.columnWidth(4) >= panel.cv_table.sizeHintForColumn(4)
    columns.fit_all()
    panel.cv_table.horizontalHeader().resizeSection(9, 500)
    assert panel.cv_table.columnWidth(9) == 500
    columns.fit_column(9)
    assert panel.cv_table.columnWidth(9) <= 320
    panel.deleteLater()
    app.processEvents()


def test_analysis_tabs_follow_data_type_without_resetting_display_preferences(synthetic_cv_runs, synthetic_eis_run):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.widgets.analysis_panel import AnalysisPanel
    from cvanalysis.ui.widgets.results_panel import ResultsPanel

    app = QApplication.instance() or QApplication([])
    panel = AnalysisPanel()
    dataset = Dataset(cv_runs=list(synthetic_cv_runs), eis_runs=[synthetic_eis_run])
    results = ResultsPanel()
    panel.update_dataset(dataset, selected_run_ids=[synthetic_eis_run.run_id])
    results.update_dataset(dataset, selected_run_ids=[synthetic_eis_run.run_id])
    assert panel.analysis_tabs.currentIndex() == 1
    assert results.results_tabs.currentIndex() == 1
    panel.analysis_tabs.setCurrentIndex(2)
    panel.update_dataset(dataset, selected_run_ids=[synthetic_eis_run.run_id])
    assert panel.analysis_tabs.currentIndex() == 2
    panel.update_dataset(dataset, selected_run_ids=[synthetic_cv_runs[0].run_id])
    results.update_dataset(dataset, selected_run_ids=[synthetic_cv_runs[0].run_id])
    assert panel.analysis_tabs.currentIndex() == 0
    assert results.results_tabs.currentIndex() == 0
    results.deleteLater()
    panel.deleteLater()
    app.processEvents()


def test_analysis_refresh_preserves_scan_rate_and_clears_unfiltered_tab_bounds(synthetic_cv_runs):
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.widgets.analysis_panel import AnalysisPanel

    app = QApplication.instance() or QApplication([])
    panel = AnalysisPanel()
    dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    panel.update_dataset(dataset)
    panel.scan_rate_spin.setValue(0.01)
    panel.update_dataset(dataset)
    assert panel.scan_rate_spin.value() == 0.01
    panel.set_options({"frequency_low": 1, "frequency_high": 100})
    assert panel.options()["frequency_low"] == 1
    panel.set_options({"frequency_low": None, "frequency_high": None})
    assert panel.freq_low_edit.text() == ""
    assert panel.freq_high_edit.text() == ""
    panel.set_options({"frequency_low": 10})
    panel.set_options({"show_legend": False})
    assert panel.options()["frequency_low"] == 10
    panel.deleteLater()
    app.processEvents()


def test_quick_style_save_overwrites_builtin_as_user_override(tmp_path, synthetic_cv_runs):
    from unittest.mock import patch
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    app.processEvents()
    tab = window.tabs.currentWidget()
    tab.set_style(window.settings_service.resolve_style("ieee-single"), clear_overrides=True)

    class FakeBox:
        class ButtonRole:
            AcceptRole = 1
            ActionRole = 2

        class StandardButton:
            Cancel = 0
            Yes = 1

        def __init__(self, *args, **kwargs):
            self.overwrite = None
            self.save_as = None
            self._clicked = None

        def setWindowTitle(self, *args):
            pass

        def setText(self, *args):
            pass

        def addButton(self, text, role=None):
            button = object()
            if isinstance(text, str) and self.overwrite is None:
                self.overwrite = button
            elif isinstance(text, str):
                self.save_as = button
            return button

        def exec(self):
            self._clicked = self.overwrite

        def clickedButton(self):
            return self._clicked

        @staticmethod
        def question(*args, **kwargs):
            return FakeBox.StandardButton.Yes

        @staticmethod
        def warning(*args, **kwargs):
            pass

    class FakeDialog:
        def __init__(self):
            self.accepted = False

        def accept(self):
            self.accepted = True

    dialog = FakeDialog()
    with patch("cvanalysis.ui.main_window.QMessageBox", FakeBox):
        window._save_quick_overrides(tab, {"line_width": 3.7, "xlabel_size": 13.0}, dialog)
    assert dialog.accepted
    assert "ieee-single" in window.settings_service.user_presets
    assert window.settings_service.resolve_style("ieee-single").line_width == 3.7
    assert tab.spec.preset == "ieee-single"
    assert tab.spec.overrides == {}
    window.close()
