"""End-to-end LSV and i-t loading, plotting, and project persistence."""
from pathlib import Path
import json

import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QPushButton

from cvanalysis.io.registry import load_files
from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.export import render_plot, render_svg_bytes
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.export_service import export_analysis_csv
from cvanalysis.services.project_service import load_project, save_project
from cvanalysis.ui.main_window import MainWindow
from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog


def _input_files(tmp_path):
    lsv = tmp_path / "lsv.txt"
    lsv.write_text("Linear Sweep Voltammetry\nInit E (V) = 0\nFinal E (V) = 2\nPotential/V, Current/A\n0, 1e-6\n1, 2e-6\n2, 3e-6\n", encoding="utf-8")
    it = tmp_path / "it.txt"
    it.write_text("Amperometric i-t Curve\nInit E (V) = 1.5\nTime/sec, Current/A\n0, 1e-6\n1, 2e-6\n2, 3e-6\n", encoding="utf-8")
    return lsv, it


def test_sweep_import_plot_project_and_csv(tmp_path):
    lsv, it = _input_files(tmp_path)
    dataset, issues = load_files([lsv, it])
    assert not issues and len(dataset.lsv_runs) == len(dataset.it_runs) == 1
    ls, ir = dataset.lsv_runs[0], dataset.it_runs[0]
    a = PlotSpec("lsv_curve", [ls.run_id], analysis_options={"lsv_window_low": .5, "lsv_window_high": 1.5})
    b = PlotSpec("it_curve", [ir.run_id], analysis_options={"it_reference_time": 1.1})
    for spec in (a, b):
        figure = Figure()
        assert not render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
        assert len(figure.axes[0].lines) == 3
        assert b"<svg" in render_svg_bytes(dataset, spec, BUILTIN_PRESETS["daily"])
    fig = Figure()
    render_plot(fig, dataset, b, BUILTIN_PRESETS["daily"])
    assert fig.axes[0].lines[1].get_ydata()[0] == 2e-6
    path = tmp_path / "mixed.cvproj"
    save_project(path, dataset, plots=[a, b])
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 3
    # Embedded arrays must remain usable when original instrument files move.
    lsv.rename(tmp_path / "moved-lsv.txt")
    it.rename(tmp_path / "moved-it.txt")
    restored = load_project(path)
    assert not restored.warnings
    np.testing.assert_array_equal(restored.dataset.lsv_runs[0].x, ls.x)
    np.testing.assert_array_equal(restored.dataset.it_runs[0].current, ir.current)
    assert [p.kind for p in restored.plots] == ["lsv_curve", "it_curve"]
    assert restored.plots[0].analysis_options == a.analysis_options
    assert restored.plots[1].analysis_options == b.analysis_options
    written = export_analysis_csv(restored.dataset, tmp_path / "csv")
    assert {"lsv_points.csv", "it_points.csv"} <= {p.name for p in written}


def test_project_unknown_run_kind_is_rejected_without_reinterpretation(tmp_path):
    dataset, _ = load_files(_input_files(tmp_path))
    path = tmp_path / "unknown.cvproj"
    save_project(path, dataset)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runs"][0]["kind"] = "future_technique"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="future_technique"):
        load_project(path)


def test_new_plot_kind_without_runs_still_uses_v3(tmp_path):
    path = tmp_path / "empty-sweep.cvproj"
    save_project(path, Dataset(), plots=[PlotSpec("lsv_curve")])
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 3
    state = load_project(path)
    save_project(path, state.dataset)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 3


def test_out_of_range_it_reference_is_reported_without_fabricating_point(tmp_path):
    dataset, issues = load_files(_input_files(tmp_path))
    assert not issues
    spec = PlotSpec("it_curve", [dataset.it_runs[0].run_id], analysis_options={"it_reference_time": 9})
    figure = Figure()
    warnings = render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert warnings and "参考时间" in warnings[0]
    assert len(figure.axes[0].lines) == 1


def test_sweep_reference_respects_area_normalization(tmp_path):
    dataset, issues = load_files(_input_files(tmp_path))
    assert not issues
    run = dataset.it_runs[0]
    run.params.area_cm2 = 2
    spec = PlotSpec("it_curve", [run.run_id], normalization="area", analysis_options={"it_reference_time": 1})
    figure = Figure()
    assert not render_plot(figure, dataset, spec, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].lines[1].get_ydata()[0] == 1e-6
    assert "A/cm²" in figure.axes[0].get_ylabel()


def test_sweep_gui_selection_options_and_project(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset, issues = load_files(_input_files(tmp_path))
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window.show()
    window._on_import_complete(dataset, issues)
    app.processEvents()
    assert window.dataset_model.index_for_run(dataset.lsv_runs[0].run_id).isValid()
    assert window.dataset_model.index_for_run(dataset.it_runs[0].run_id).isValid()
    for run in (dataset.lsv_runs[0], dataset.it_runs[0]):
        window._select_run_ids([run.run_id])
        app.processEvents()
        assert run.display_name in window.file_detail_label.text()
    window.tree.selectionModel().clearSelection()
    for kind, keys in (("lsv_curve", ("lsv_window_low", "lsv_window_high")),
                       ("it_curve", ("it_reference_time",))):
        page_index = 3 if kind == "lsv_curve" else 4
        window.analysis_panel.analysis_tabs.setCurrentIndex(page_index)
        button = window.analysis_panel.analysis_tabs.widget(page_index).findChild(QPushButton)
        assert button is not None
        assert button.property("pill") is True and button in window.pointer_lights.overlays
        button.click()
        tab = window._active_plot_tab()
        assert tab.spec.kind == kind
        assert window.analysis_panel.analysis_tabs.currentIndex() == (3 if kind == "lsv_curve" else 4)
        for key in keys:
            assert key in window.options_panel.controls
        if kind == "lsv_curve":
            window.options_panel.controls["lsv_window_low"].setText("0.5")
            window.options_panel.apply()
            assert "lsv_window_low" not in tab.spec.analysis_options
            window.options_panel.controls["lsv_window_low"].setText("0.5")
            window.options_panel.controls["lsv_window_high"].setText("1.5")
        else:
            window.options_panel.controls["it_reference_time"].setText("1.1")
        window.options_panel.apply()
        assert len(tab.figure.axes[0].lines) == 3
        assert all(tab.spec.analysis_options.get(key) is not None for key in keys)
        dialog = PlotDataDialog(window.dataset, tab.spec, kind, parent=window)
        assert len(dialog._run_items) == 1
        dialog.close()
        dialog.deleteLater()
    window._mark_clean()
    window.close()
    app.processEvents()
