"""Regression checks for I-T templates, CP references and detachable options."""
import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.cp_renderer import draw_cp_capacity
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.legend import legend_tokens, preview_label, render_legend_template
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.main_window import MainWindow


def test_it_tokens_and_blank_template():
    run = SweepRun("it1", "sample", "it", np.array([0., 1.]), np.array([1e-6, 2e-6]),
                   SweepMetadata("Amperometric i-t Curve", {"Init E (V)": "1.5", "Run Time (sec)": "120", "Sample Interval (s)": "0.1"}))
    assert {"IT_Potential", "IT_Run_Time", "IT_Sample_Interval", "Points"} <= {t.token for t in legend_tokens("it")}
    assert render_legend_template("{IT_Potential}-{IT_Run_Time}", run) == ("1.5V-120s", [])
    assert render_legend_template("{ }", run) == ("", [])
    assert preview_label(run, "{ }", fallback="default") == ("", [])
    spec = PlotSpec("it_curve", [run.run_id], legend_templates={run.run_id: "{IT_Potential}"})
    fig = Figure()
    render_plot(fig, Dataset(it_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert fig.axes[0].get_legend().get_texts()[0].get_text() == "1.5V"
    spec.legend_templates[run.run_id] = "{ }"
    render_plot(fig, Dataset(it_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert fig.axes[0].get_legend() is None


def test_blank_template_is_clear_in_both_editor_previews():
    from cvanalysis.ui.dialogs.legend_dialog import LegendTemplateDialog
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog

    app = QApplication.instance() or QApplication([])
    run = SweepRun("it1", "sample", "it", np.array([0., 1.]), np.array([1e-6, 2e-6]),
                   SweepMetadata("Amperometric i-t Curve", {"Init E (V)": "1.5"}))
    data = Dataset(it_runs=[run])
    spec = PlotSpec("it_curve", [run.run_id])
    dialog = LegendTemplateDialog([run])
    assert dialog.token_combo.findData("IT_Potential") >= 0
    dialog.template_edit.setText("{ }")
    assert "不显示图例" in dialog.preview.toPlainText()
    assert not dialog.warning.text()
    dialog.close()
    dialog.deleteLater()
    picker = PlotDataDialog(data, spec, "it_curve")
    assert picker.token_combo.findData("IT_Run_Time") >= 0
    picker._template_edits[run.run_id].setText("{ }")
    assert "不显示图例" in picker._run_items[run.run_id].text(2)
    assert picker.legend_templates()[run.run_id] == "{ }"
    picker.close()
    picker.deleteLater()
    app.processEvents()


def test_it_blank_template_survives_project_roundtrip(tmp_path):
    from cvanalysis.services.project_service import load_project, save_project

    run = SweepRun("it1", "sample", "it", np.array([0., 1.]), np.array([1e-6, 2e-6]),
                   SweepMetadata("Amperometric i-t Curve", {"Init E (V)": "1.5"}))
    spec = PlotSpec("it_curve", [run.run_id], legend_templates={run.run_id: "{ }"})
    path = tmp_path / "it-blank.cvproj"
    save_project(path, Dataset(it_runs=[run]), plots=[spec])
    state = load_project(path)
    restored = state.plots[0]
    assert restored.legend_templates[restored.run_ids[0]] == "{ }"
    figure = Figure()
    render_plot(figure, state.dataset, restored, BUILTIN_PRESETS["daily"])
    assert figure.axes[0].get_legend() is None


@pytest.mark.parametrize("quantity", ["capacity", "capacitance"])
def test_cp_cycle_reference_is_separate_per_direction(synthetic_cp_run, quantity):
    run = synthetic_cp_run
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"cp_quantity": quantity,
        "capacity_series": "both", "show_efficiency": False,
        "capacity_percent_mode": "cycle", "capacity_percent_cycle": 1})
    fig = Figure()
    warnings = draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert warnings and all("IR 降留空" in warning for warning in warnings)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)
    assert fig.axes[0].lines[1].get_ydata()[0] == pytest.approx(100)
    spec.analysis_options["capacity_series"] = "mean"
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)


def test_cp_manual_reference_exponent(synthetic_cp_run):
    run = synthetic_cp_run
    reference = run.summary.cycles[0].discharge_capacity_C / 3.6
    exponent = -7
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"capacity_series": "discharge", "show_efficiency": False,
        "capacity_percent_mode": "manual", "capacity_percent_reference": reference / 10 ** exponent,
        "capacity_percent_reference_exponent": exponent})
    fig = Figure()
    draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(100)
    spec.analysis_options.update(capacity_percent_reference=1.65, capacity_percent_reference_exponent=0)
    warnings = draw_cp_capacity(fig, Dataset(cp_runs=[run]), spec, BUILTIN_PRESETS["daily"])
    fig.canvas.draw()
    assert any("数量级" in warning for warning in warnings)
    assert not fig.axes[0].yaxis.get_offset_text().get_text()
    assert any("e-" in label.get_text() for label in fig.axes[0].get_yticklabels())


def test_options_detach_restore_and_unsaved_input(tmp_path, synthetic_cv_runs):
    from shiboken6 import isValid
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window.show()
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    QTest.qWait(80)
    panel = window.options_panel
    panel.pages.setCurrentIndex(2)
    panel.fraction.setText("0.731")
    before = window.bottom_splitter.sizes()
    QTest.mouseDClick(panel.context, Qt.LeftButton, pos=panel.context.rect().center())
    app.processEvents()
    assert window._options_dialog is not None and window._options_dialog.isVisible()
    assert window.bottom_splitter.indexOf(panel) == -1 and panel.fraction.text() == "0.731"
    window.settings_service.ui_state["material"] = "solid"
    window._refresh_glass_settings()
    window.settings_service.ui_state["material"] = "liquid_glass"
    window._refresh_glass_settings()
    assert panel.fraction.text() == "0.731"
    window._options_dialog.close()
    QTest.qWait(60)
    assert window._options_dialog is None and window.bottom_splitter.indexOf(panel) == 2
    assert panel.fraction.text() == "0.731" and panel.pages.currentIndex() == 2
    assert all(abs(a-b) <= 2 for a, b in zip(before, window.bottom_splitter.sizes()))
    bar = panel.pages.tabBar()
    QTest.mouseDClick(bar, Qt.LeftButton, pos=bar.tabRect(2).center())
    app.processEvents()
    assert window._options_dialog is not None, (bar in panel._detach_surfaces, bar.isVisible(), bar.tabRect(2), bar.geometry())
    window._options_dialog.close()
    app.processEvents()
    for _ in range(3):
        window._detach_options_panel()
        app.processEvents()
        assert window._options_dialog is not None
        window._options_dialog.close()
        app.processEvents()
        assert window.bottom_splitter.indexOf(panel) == 2 and panel.fraction.text() == "0.731"
        assert isValid(panel.pages.tabBar()) and isValid(window.liquid_tab_bars[2])
        assert window.liquid_tab_bars[2].bar is panel.pages.tabBar()
    assert window.analysis_panel.analysis_tabs.tabText(window.analysis_panel.analysis_tabs.count() - 1) == "显示"
    window._mark_clean()
    window.close()
    app.processEvents()


def test_closing_main_window_with_detached_panel_is_safe(tmp_path, synthetic_cv_runs):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window.show()
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    QTest.qWait(40)
    window._detach_options_panel()
    assert window._options_dialog is not None
    window._mark_clean()
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    assert not isValid(window)
