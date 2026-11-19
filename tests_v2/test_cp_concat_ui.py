# -*- coding: utf-8 -*-
"""UI and project persistence for CP multi-file concatenation."""

from __future__ import annotations

import copy

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


def _second_run(run):
    second = copy.deepcopy(run)
    second.run_id = "cp_second"
    second.name = "cp_second"
    return second


def test_panel_exposes_concat_controls_and_persists_unified_reference(
    synthetic_cp_run,
):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    second_count = len(second.summary.cycles)
    assert second_count >= 2
    data = Dataset(cp_runs=[first, second])
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": True,
            "cp_concat_order": [second.run_id, first.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": 1},
                second.run_id: {"start": second_count, "end": second_count},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": second.run_id,
            "capacity_percent_reference_cycle": second_count,
        },
    )
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        assert panel.controls["cp_concat_enabled"].isChecked()
        mode = panel.controls["capacity_percent_mode"]
        assert mode.findData("unified") >= 0
        assert mode.currentData() == "unified"
        concat_mode = panel.controls["cp_concat_cycle_mode"]
        assert concat_mode.findData("sequential") >= 0
        assert concat_mode.findData("cumulative") >= 0
        assert concat_mode.currentData() == "sequential"
        assert "2 个 CP 文件" in panel.cp_concat_summary.text()
        assert "参与循环" in panel.cp_concat_summary.text()

        fired = []
        assert panel.cp_concat_button.property("secondary") is True
        panel.cp_concat_settings_requested.connect(lambda: fired.append(True))
        panel.cp_concat_button.click()
        assert fired

        assert not panel.controls["capacity_percent_reference"].isEnabled()
        assert not panel.controls[
            "capacity_percent_reference_exponent"
        ].isEnabled()
        assert not panel.controls["capacity_percent_cycle"].isEnabled()
        reference_run = panel.controls[
            "capacity_percent_reference_run_id"
        ]
        reference_cycle = panel.controls[
            "capacity_percent_reference_cycle"
        ]
        assert reference_run.isEnabled()
        assert reference_run.currentData() == second.run_id
        assert reference_cycle.isEnabled()
        assert [
            reference_cycle.itemData(index)
            for index in range(reference_cycle.count())
        ] == [second_count]
        assert f"Cycle {second_count}" in panel.cp_unified_preview.text()

        panel.apply()
        options = spec.analysis_options
        assert options["cp_concat_enabled"] is True
        assert options["cp_concat_order"] == [second.run_id, first.run_id]
        assert options["cp_concat_ranges"] == {
            second.run_id: {"start": second_count, "end": second_count},
            first.run_id: {"start": 1, "end": 1},
        }
        assert options["capacity_percent_mode"] == "unified"
        assert options["capacity_percent_reference_run_id"] == second.run_id
        assert options["capacity_percent_reference_cycle"] == second_count
        assert options["cp_concat_cycle_mode"] == "sequential"
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_panel_persists_normalized_concat_config_even_when_disabled(
    synthetic_cp_run,
):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    second_count = len(second.summary.cycles)
    data = Dataset(cp_runs=[first, second])
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": False,
            "cp_concat_order": ["removed-run", second.run_id],
            "cp_concat_ranges": {
                "removed-run": {"start": 1, "end": 2},
                second.run_id: {"start": 1, "end": 999},
            },
        },
    )
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        panel.apply()
        options = spec.analysis_options
        assert options["cp_concat_enabled"] is False
        assert not hasattr(spec, "cp_concat_enabled")
        assert options["cp_concat_order"] == [second.run_id, first.run_id]
        assert options["cp_concat_ranges"] == {
            second.run_id: {"start": 1, "end": second_count},
            first.run_id: {
                "start": 1,
                "end": len(first.summary.cycles),
            },
        }
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_apply_rejects_unified_reference_outside_displayed_range(
    synthetic_cp_run,
):
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    first_count = len(first.summary.cycles)
    assert first_count >= 2
    data = Dataset(cp_runs=[first, second])
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": first_count, "end": first_count},
                second.run_id: {"start": 1, "end": len(second.summary.cycles)},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": first.run_id,
            "capacity_percent_reference_cycle": first_count,
        },
    )
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    try:
        panel.bind(tab)
        cycle_combo = panel.controls["capacity_percent_reference_cycle"]
        cycle_combo.addItem("Cycle 1", 1)
        cycle_combo.setCurrentIndex(cycle_combo.count() - 1)
        panel.apply()
        assert "显示范围" in panel.error.text()
        assert (
            spec.analysis_options["capacity_percent_reference_cycle"]
            == first_count
        )
    finally:
        panel.deleteLater()
        tab.deleteLater()
        app.processEvents()


def test_cp_concat_dialog_normalizes_order_and_rejects_start_after_end(
    synthetic_cp_run,
):
    from cvanalysis.ui.dialogs.cp_concat_dialog import CPConcatDialog

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    second_count = len(second.summary.cycles)
    assert second_count >= 2
    dialog = CPConcatDialog(
        [first, second],
        order=[second.run_id],
        ranges={
            second.run_id: {"start": second_count, "end": second_count},
        },
    )
    try:
        assert dialog.order() == [second.run_id, first.run_id]
        assert dialog.ranges()[second.run_id] == {
            "start": second_count,
            "end": second_count,
        }
        row = dialog.order().index(first.run_id)
        start_spin = dialog._rows[row]["start_spin"]
        end_spin = dialog._rows[row]["end_spin"]
        start_spin.setValue(2)
        end_spin.setValue(1)
        dialog.accept()
        assert "起始循环不能大于结束循环" in dialog.error.text()
        assert not dialog.ok_button.isEnabled()
        assert dialog.result() != QDialog.Accepted

        start_spin.setValue(1)
        end_spin.setValue(len(first.summary.cycles))
        dialog.accept()
        assert dialog.result() == QDialog.Accepted
        assert dialog.order() == [second.run_id, first.run_id]
        assert dialog.ranges()[second.run_id] == {
            "start": second_count,
            "end": second_count,
        }
        assert dialog.ranges()[first.run_id] == {
            "start": 1,
            "end": len(first.summary.cycles),
        }
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_cp_concat_dialog_uses_design_button_roles(synthetic_cp_run):
    from cvanalysis.ui.dialogs.cp_concat_dialog import CPConcatDialog

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    dialog = CPConcatDialog([first, second])
    try:
        assert dialog.up_button.property("secondary") is True
        assert dialog.down_button.property("secondary") is True
        ok_button = dialog.findChild(QDialogButtonBox).button(
            QDialogButtonBox.Ok
        )
        assert ok_button.property("primary") is True
        assert ok_button.property("pill") is True
        assert ok_button.property("secondary") is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_cp_concat_dialog_accept_preserves_other_unapplied_inputs(
    synthetic_cp_run, tmp_path, monkeypatch
):
    from cvanalysis.ui import main_window as main_window_module
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": False,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": len(first.summary.cycles)},
                second.run_id: {"start": 1, "end": len(second.summary.cycles)},
            },
        },
    )

    class FakeDialog:
        def __init__(self, runs, order=None, ranges=None, parent=None):
            self._order = [run.run_id for run in runs]
            self._ranges = {
                run.run_id: {
                    "start": 1,
                    "end": 1 if run.run_id == second.run_id else len(run.summary.cycles),
                }
                for run in runs
            }

        def exec(self):
            return QDialog.Accepted

        def order(self):
            return list(self._order)

        def ranges(self):
            return {key: dict(value) for key, value in self._ranges.items()}

    monkeypatch.setattr(main_window_module, "CPConcatDialog", FakeDialog)
    window = MainWindow(settings_path=tmp_path / "pending_inputs.json")
    try:
        window.dataset = Dataset(cp_runs=[first, second])
        window._refresh_model_and_panel()
        tab = window._add_plot_tab(spec)
        window._show_analysis_options(tab)
        panel = window.options_panel
        panel.fraction.setText("0.42")
        window._edit_cp_concat(tab)
        assert panel.fraction.text() == "0.42"
        assert spec.analysis_options["cp_concat_enabled"] is False
        assert spec.analysis_options["cp_concat_ranges"][second.run_id] == {
            "start": 1,
            "end": 1,
        }
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()


def test_cp_concat_keeps_hidden_reference_until_run_is_deleted(
    synthetic_cp_run, tmp_path, monkeypatch
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    spec = PlotSpec(
        "cp_capacity",
        [first.run_id, second.run_id],
        analysis_options={
            "show_efficiency": False,
            "cp_concat_enabled": True,
            "cp_concat_order": [first.run_id, second.run_id],
            "cp_concat_ranges": {
                first.run_id: {"start": 1, "end": len(first.summary.cycles)},
                second.run_id: {"start": 1, "end": len(second.summary.cycles)},
            },
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": second.run_id,
            "capacity_percent_reference_cycle": 1,
        },
    )
    window = MainWindow(settings_path=tmp_path / "refresh_json.json")
    try:
        window.dataset = Dataset(cp_runs=[first, second])
        window._refresh_model_and_panel()
        tab = window._add_plot_tab(spec)
        window._show_analysis_options(tab)
        panel = window.options_panel
        model = window.dataset_model
        index = model.index_for_run(second.run_id)
        assert model.setData(index, Qt.Unchecked, Qt.CheckStateRole)
        combo = panel.controls["capacity_percent_reference_run_id"]
        assert combo.currentText().startswith("（未勾选）")
        panel.apply()
        assert spec.analysis_options["capacity_percent_reference_run_id"] == second.run_id
        assert second.run_id in spec.analysis_options["cp_concat_ranges"]
        assert model.setData(index, Qt.Checked, Qt.CheckStateRole)
        assert combo.currentData() == second.run_id
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
        window._remove_runs([second.run_id])
        assert [
            combo.itemData(index) for index in range(combo.count())
        ] == [first.run_id]
        assert spec.analysis_options["capacity_percent_reference_run_id"] == ""
        assert second.run_id not in spec.analysis_options["cp_concat_ranges"]
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()


def test_project_roundtrip_remaps_concat_and_unified_reference(
    synthetic_cp_run, tmp_path
):
    from cvanalysis.services.project_service import load_project, save_project

    run = synthetic_cp_run
    cycle_count = len(run.summary.cycles)
    spec = PlotSpec(
        "cp_capacity",
        [run.run_id],
        analysis_options={
            "cp_concat_enabled": True,
            "cp_concat_order": [run.run_id],
            "cp_concat_ranges": {
                run.run_id: {"start": 1, "end": cycle_count},
            },
            "cp_concat_cycle_mode": "cumulative",
            "capacity_percent_mode": "unified",
            "capacity_percent_reference_run_id": run.run_id,
            "capacity_percent_reference_cycle": 1,
            "future_unknown_field": {"keep": True},
        },
    )
    path = tmp_path / "concat.cvproj"
    save_project(path, Dataset(cp_runs=[run]), plots=[spec])
    restored = load_project(path).plots[0]
    new_run_id = restored.run_ids[0]
    assert new_run_id != run.run_id
    options = restored.analysis_options
    assert options["cp_concat_enabled"] is True
    assert options["cp_concat_order"] == [new_run_id]
    assert options["cp_concat_ranges"] == {
        new_run_id: {"start": 1, "end": cycle_count},
    }
    assert options["capacity_percent_reference_run_id"] == new_run_id
    assert options["capacity_percent_reference_cycle"] == 1
    assert options["cp_concat_cycle_mode"] == "cumulative"
    assert options["future_unknown_field"] == {"keep": True}


def test_concat_existing_cp_uses_workspace_without_file_dialog(
    synthetic_cp_run, tmp_path, monkeypatch
):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    first = synthetic_cp_run
    second = _second_run(first)
    window = MainWindow(settings_path=tmp_path / "settings.json")
    opened = []
    monkeypatch.setattr(
        window,
        "_edit_cp_concat",
        lambda tab=None: opened.append(tab),
    )

    def fail_file_dialog(*_args, **_kwargs):
        raise AssertionError("拼接已加载数据不应打开文件对话框")

    monkeypatch.setattr(
        "cvanalysis.ui.main_window.QFileDialog.getOpenFileNames",
        fail_file_dialog,
    )
    try:
        assert window.cp_concat_existing_action.text() == "拼接已加载 CP 容量-循环"
        assert not hasattr(window, "cp_concat_action")
        assert not hasattr(window.analysis_panel, "concat_cp_requested")
        window.dataset = Dataset(cp_runs=[first, second])
        window._refresh_model_and_panel()
        assert window.cp_concat_existing_action.isEnabled()
        window.concat_existing_cp()
        app.processEvents()
        tab = window._active_plot_tab()
        assert tab is not None and tab.spec.kind == "cp_capacity"
        assert set(tab.spec.run_ids) == {first.run_id, second.run_id}
        options = tab.spec.analysis_options
        assert options["cp_concat_enabled"] is True
        assert options["cp_concat_cycle_mode"] == "sequential"
        assert set(options["cp_concat_order"]) == {
            first.run_id,
            second.run_id,
        }
        assert opened and opened[0] is tab
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()


def test_concat_existing_cp_requires_at_least_two_workspace_runs(
    synthetic_cp_run, tmp_path
):
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    window = MainWindow(settings_path=tmp_path / "settings.json")
    try:
        window.dataset = Dataset(cp_runs=[run])
        window._refresh_model_and_panel()
        assert not window.cp_concat_existing_action.isEnabled()
        assert not window.analysis_panel.concat_existing_button.isEnabled()
        window.concat_existing_cp()
        app.processEvents()
        assert "至少需要 2 个" in window.statusBar().currentMessage()
        assert window.tabs.count() == 0
    finally:
        window._mark_clean()
        window.close()
        app.processEvents()
