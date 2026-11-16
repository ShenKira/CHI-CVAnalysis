"""Hold-stage notices, independent CP series legends and LSV display clipping."""
from pathlib import Path

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cvanalysis.analysis.cp import analyze_cp_run
from cvanalysis.domain.models import Dataset, SweepMetadata, SweepRun
from cvanalysis.plotting.export import render_plot, render_svg_bytes
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec

STYLE = BUILTIN_PRESETS["daily"]


def legend_texts(figure):
    legends = list(figure.legends) + [ax.get_legend() for ax in figure.axes if ax.get_legend()]
    return [text.get_text() for legend in legends for text in legend.get_texts()]


def test_cp_existing_project_restores_capacity_legend_and_gcd_blank():
    from cvanalysis.services.project_service import load_project
    from cvanalysis.plotting.export import render_to_new_figure
    path = Path(__file__).resolve().parents[1] / "CP.cvproj"
    if not path.exists():
        pytest.skip("optional user project not present")
    state = load_project(path)
    run = state.dataset.cp_runs[0]
    assert run.legend_template == "{ }"
    capacity = next(spec for spec in state.plots if spec.kind == "cp_capacity")
    style = STYLE.with_overrides(capacity.overrides)
    fig = render_to_new_figure(state.dataset, capacity, style)
    FigureCanvasAgg(fig)
    fig.canvas.draw()
    texts = legend_texts(fig)
    assert any("Capacity" in text for text in texts)
    assert "CE" in texts
    renderer = fig.canvas.get_renderer()
    legend = fig.legends[0] if fig.legends else fig.axes[0].get_legend()
    box = legend.get_window_extent(renderer).transformed(fig.transFigure.inverted())
    assert box.x0 >= -.01 and box.x1 <= 1.01 and box.y0 >= -.01 and box.y1 <= 1.01
    visible_ticks = [(x, tick) for x, tick in zip(fig.axes[0].get_xticks(), fig.axes[0].get_xticklabels())
                     if fig.axes[0].get_xlim()[0] <= x <= fig.axes[0].get_xlim()[1] and tick.get_text()]
    boxes = [tick.get_window_extent(renderer) for _, tick in visible_ticks]
    assert all(left.x1 <= right.x0 for left, right in zip(boxes, boxes[1:]))
    assert run.legend_template == "{ }"
    gcd = next(spec for spec in state.plots if spec.kind == "cp_gcd")
    render_plot(fig, state.dataset, gcd, STYLE)
    assert not legend_texts(fig)
    capacity.show_legend = False
    render_plot(fig, state.dataset, capacity, style)
    assert not legend_texts(fig)


@pytest.mark.parametrize("paper", [False, True])
def test_cp_custom_legends_and_hidden_role(synthetic_cp_run, paper):
    run = synthetic_cp_run
    run.legend_template = "{ }"
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"capacity_series": "both",
        "show_efficiency": True, "cp_legend_charge": "{name} charge [{unit}]",
        "cp_legend_discharge": "{ }", "cp_legend_efficiency": "CE ({unit})"},
        paper_layout={"enabled": paper, "fraction": .33, "text_width_mm": 160., "body_pt": 10.})
    fig = Figure()
    FigureCanvasAgg(fig)
    # The plot's show-legend switch remains authoritative for this plot type.
    style = STYLE.with_overrides({"legend": False})
    render_plot(fig, Dataset(cp_runs=[run]), spec, style)
    texts = legend_texts(fig)
    assert len(texts) == 2
    assert any(run.display_name in text and "charge [mAh]" in text for text in texts)
    assert "CE (%)" in texts
    assert len(fig.axes[0].lines) == 2 and len(fig.axes[1].lines) == 1
    spec.show_legend = False
    render_plot(fig, Dataset(cp_runs=[run]), spec, style)
    assert not legend_texts(fig)


def test_cp_legend_controls_and_project_roundtrip(synthetic_cp_run, tmp_path):
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    run.legend_template = "{ }"
    data = Dataset(cp_runs=[run])
    spec = PlotSpec("cp_capacity", [run.run_id], analysis_options={"capacity_series": "mean"})
    tab = PlotTab(spec, STYLE, data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    panel.controls["cp_legend_mean"].setText("{quantity} [{unit}]")
    panel.controls["cp_legend_efficiency"].setText("Coulombic efficiency")
    panel.apply()
    assert legend_texts(tab.figure) == ["Capacity [mAh]", "Coulombic efficiency"]
    panel.controls["show_legend"].setChecked(False)
    panel.apply()
    assert not legend_texts(tab.figure)
    assert spec.analysis_options["cp_legend_mean"] == "{quantity} [{unit}]"
    panel.controls["show_legend"].setChecked(True)
    panel.apply()
    path = tmp_path / "cp-legend.cvproj"
    save_project(path, data, plots=[spec])
    restored = load_project(path)
    fig = Figure()
    render_plot(fig, restored.dataset, restored.plots[0], STYLE)
    assert legend_texts(fig) == ["Capacity [mAh]", "Coulombic efficiency"]
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_hold_absence_is_not_a_warning(synthetic_cp_run):
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog
    run = synthetic_cp_run
    run.hold_time = run.hold_current = None
    run.metadata.high_hold_s = run.metadata.low_hold_s = 0
    summary = analyze_cp_run(run, force=True)
    assert not run.hold_description()
    assert "保持段" not in PlotDataDialog._run_tooltip(run)
    assert all("未记录保持段电流" not in warning for warning in summary.warnings)
    for kind in ("cp_gcd", "cp_capacity"):
        fig = Figure()
        warnings = render_plot(fig, Dataset(cp_runs=[run]), PlotSpec(kind, [run.run_id]), STYLE)
        assert all("未记录保持段电流" not in warning for warning in warnings)


def test_configured_hold_without_current_is_informational(synthetic_cp_run):
    from cvanalysis.ui.dialogs.plot_data_dialog import PlotDataDialog
    run = synthetic_cp_run
    run.hold_time = run.hold_current = None
    summary = analyze_cp_run(run, force=True)
    assert "保持段参数配置" in run.hold_description()
    assert "高电位保持" in run.hold_description()
    assert "保持段参数配置" in PlotDataDialog._run_tooltip(run)
    assert all("未记录保持段电流" not in warning for warning in summary.warnings)


def test_hold_info_is_reported_on_import_and_in_remarks(synthetic_cp_run, tmp_path):
    from cvanalysis.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    run = synthetic_cp_run
    assert run.has_hold_data
    window = MainWindow(settings_path=tmp_path / "settings.json")
    window._on_import_complete(Dataset(cp_runs=[run]), [])
    app.processEvents()
    assert "保持段信息" in window.statusBar().currentMessage()
    model = window.results_panel.cp_model
    remark = model.data(model.index(0, 7), Qt.DisplayRole)
    assert "包含保持段电流" in remark
    assert "高电位保持" in remark and "低电位保持" in remark
    assert "保持段" in window.dataset_model.data(window.dataset_model.index_for_run(run.run_id), Qt.ToolTipRole)
    window._mark_clean()
    window.close()
    app.processEvents()


@pytest.mark.parametrize("normalization,area,unit,scale", [
    ("none", None, "µA", 1e6), ("area", 2., "µA/cm²", .5e6)])
def test_lsv_clip_is_optional_scaled_and_never_mutates_raw(normalization, area, unit, scale):
    run = SweepRun("lsv", "sample", "lsv", np.array([0., .5, 1., 1.5]),
                   np.array([-3e-6, -1e-6, 0., 2e-6]), SweepMetadata("test", {}))
    run.params.area_cm2 = area
    original = run.current.copy()
    spec = PlotSpec("lsv_curve", [run.run_id], normalization=normalization,
                    analysis_options={"unit_overrides": {"current": unit}, "lsv_clip_negative": True})
    fig = Figure()
    data = Dataset(lsv_runs=[run])
    render_plot(fig, data, spec, STYLE)
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(), np.maximum(original, 0) * scale)
    assert unit in fig.axes[0].get_ylabel()
    np.testing.assert_array_equal(run.current, original)
    assert b"<svg" in render_svg_bytes(data, spec, STYLE)
    spec.analysis_options["lsv_clip_negative"] = False
    render_plot(fig, data, spec, STYLE)
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(), original * scale)
    np.testing.assert_array_equal(run.current, original)


def test_lsv_clip_control_roundtrips_and_it_is_unaffected(tmp_path):
    import csv
    from cvanalysis.services.export_service import export_analysis_csv
    from cvanalysis.services.project_service import load_project, save_project
    from cvanalysis.ui.widgets.analysis_options_panel import AnalysisOptionsPanel
    from cvanalysis.ui.widgets.plot_tab import PlotTab
    app = QApplication.instance() or QApplication([])
    lsv = SweepRun("lsv", "sample", "lsv", np.array([0., 1.]), np.array([-1e-6, 2e-6]), SweepMetadata("test", {}))
    it = SweepRun("it", "sample", "it", np.array([0., 1.]), np.array([-1e-6, 2e-6]), SweepMetadata("test", {}))
    data = Dataset(lsv_runs=[lsv], it_runs=[it])
    tab = PlotTab(PlotSpec("lsv_curve", [lsv.run_id]), STYLE, data)
    panel = AnalysisOptionsPanel()
    panel.bind(tab)
    panel.controls["lsv_clip_negative"].setChecked(True)
    panel.apply()
    path = tmp_path / "lsv-clip.cvproj"
    save_project(path, data, plots=[tab.spec])
    restored = load_project(path)
    fig = Figure()
    render_plot(fig, restored.dataset, restored.plots[0], STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == 0
    assert restored.dataset.lsv_runs[0].current[0] == pytest.approx(-1e-6)
    export_analysis_csv(restored.dataset, tmp_path / "csv")
    with (tmp_path / "csv" / "lsv_points.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert float(next(csv.DictReader(handle))["current_A"]) == pytest.approx(-1e-6)
    render_plot(fig, data, PlotSpec("it_curve", [it.run_id], analysis_options={"lsv_clip_negative": True}), STYLE)
    assert fig.axes[0].lines[0].get_ydata()[0] == pytest.approx(-1e-6)
    panel.deleteLater()
    tab.deleteLater()
    app.processEvents()


def test_lsv_automatic_unit_uses_clipped_data():
    run = SweepRun("lsv", "sample", "lsv", np.array([0., 1.]), np.array([-1., 2e-6]), SweepMetadata("test", {}))
    spec = PlotSpec("lsv_curve", [run.run_id], analysis_options={"lsv_clip_negative": True,
                    "unit_overrides": {"current": "auto"}})
    fig = Figure()
    render_plot(fig, Dataset(lsv_runs=[run]), spec, STYLE)
    assert "µA" in fig.axes[0].get_ylabel()
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(), [0, 2])
