from copy import deepcopy

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from cvanalysis.domain.models import Dataset
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.ui.dialogs.dunn_window_dialog import DunnWindowDialog
from cvanalysis.ui.main_window import MainWindow


def test_dunn_window_editor_stages_roi_and_keeps_exact_measured_rate(
    tmp_path, test_application, synthetic_cv_runs,
):
    window = MainWindow(settings_path=tmp_path / "settings.json")
    synthetic_cv_runs[0].metadata.scan_rate = .0123456789012345
    window.dataset = Dataset(cv_runs=list(synthetic_cv_runs))
    ids = [run.run_id for run in synthetic_cv_runs]
    first = window._add_plot_tab(PlotSpec("cv_contribution", ids))
    second = window._add_plot_tab(PlotSpec("cv_contribution_vs_rate", ids))
    window.tabs.setCurrentWidget(first)
    panel = window.options_panel
    panel.fraction.setText(".47")

    panel._open_dunn_window()
    test_application.processEvents()
    editor = first.findChild(DunnWindowDialog)
    editor.low_edit.setText(".2")
    editor.high_edit.setText(".8")
    editor.reject()
    test_application.processEvents()
    assert first not in panel._dunn_drafts

    panel._open_dunn_window()
    test_application.processEvents()
    editor = next(item for item in first.findChildren(DunnWindowDialog) if item.isVisible())
    canvas = editor._raw_canvas
    canvas.draw()

    def canvas_point(voltage):
        y = sum(editor._raw_ax.get_ylim()) / 2
        x_px, y_px = editor._raw_ax.transData.transform((voltage, y))
        scale = canvas.devicePixelRatioF()
        return QPoint(round(x_px / scale), round(canvas.height() - y_px / scale))

    QTest.mousePress(canvas, Qt.LeftButton, pos=canvas_point(.25))
    QTest.mouseMove(canvas, pos=canvas_point(.75))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=canvas_point(.75))
    assert float(editor.low_edit.text()) == pytest.approx(.25, abs=.01)
    assert float(editor.high_edit.text()) == pytest.approx(.75, abs=.01)
    editor.low_edit.setText(".2")
    editor.high_edit.setText(".8")
    editor.pages.setCurrentIndex(2)
    editor._render_result()
    assert editor._diagnostics_table.rowCount() == len(ids)
    assert editor._result.potential_window == (.2, .8)
    editor.accept()
    assert "dunn_roi_by_branch" not in first.spec.analysis_options
    assert panel.fraction.text() == ".47"

    window.tabs.setCurrentWidget(second)
    assert second not in panel._dunn_drafts
    window.tabs.setCurrentWidget(first)
    assert panel._dunn_drafts[first][0] == {"up": [.2, .8]}
    rate = synthetic_cv_runs[0].metadata.scan_rate
    panel._dunn_rate_combo.setCurrentIndex(panel._dunn_rate_combo.findData(rate))
    panel.apply()
    assert first.spec.selected_scan_rate == rate
    assert first.spec.analysis_options["dunn_roi_by_branch"] == {"up": [.2, .8]}
    assert "dunn_roi_by_branch" not in second.spec.analysis_options

    narrow = deepcopy(synthetic_cv_runs[0])
    narrow.run_id = "narrow-cv"
    for cycle in narrow.cycles:
        cycle.branch_up = cycle.branch_up[cycle.branch_up[:, 0] >= .5]
    first.dataset.cv_runs.append(narrow)
    first.spec.run_ids = [*first.spec.run_ids, narrow.run_id]
    first.redraw()
    assert "超出共同实测范围" in panel._dunn_summary.text()
    assert first.spec.analysis_options["dunn_roi_by_branch"] == {"up": [.2, .8]}
    window.close()
