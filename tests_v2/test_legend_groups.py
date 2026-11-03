# -*- coding: utf-8 -*-
"""Regression tests for CV cycle legend grouping."""

from __future__ import annotations

from matplotlib.figure import Figure

from cvanalysis.io.registry import load_files
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.legend import cycle_legend_groups, cycle_legend_limit
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis


def _load_run(cv_file_factory, cycles: int):
    path = cv_file_factory(
        f"cv_{cycles}_cycles.txt",
        scan_rate=0.1,
        cycles=cycles,
        points_per_segment=11,
    )
    dataset, issues = load_files([path])
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    return dataset.cv_runs[0]


def test_cycle_legend_groups_are_balanced_and_labeled():
    class Cycle:
        def __init__(self, index):
            self.index = index

    groups = cycle_legend_groups([Cycle(index) for index in range(1, 501)], 10)
    assert groups is not None
    assert len(groups) == 10
    assert (groups[0].start, groups[0].end) == (1, 50)
    assert (groups[-1].start, groups[-1].end) == (451, 500)
    assert [len(group.cycles) for group in groups] == [50] * 10

    renumbered = cycle_legend_groups(
        [Cycle(index) for index in range(5, 17)], 10, renumber=True
    )
    assert renumbered is not None
    assert [(group.start, group.end) for group in renumbered[:3]] == [
        (1, 2),
        (3, 4),
        (5, 5),
    ]
    assert cycle_legend_groups([Cycle(1), Cycle(2)], 10) is None


def test_cycle_legend_limit_defaults_and_accepts_override():
    spec = PlotSpec("cv_overlay", ["run"])
    assert cycle_legend_limit(spec) == 10

    spec.analysis_options["legend_cycle_limit"] = 25
    assert cycle_legend_limit(spec) == 25

    spec.analysis_options["legend_cycle_limit"] = 0
    assert cycle_legend_limit(spec) == 0

    spec.analysis_options["legend_cycle_limit"] = "invalid"
    assert cycle_legend_limit(spec) == 10


def test_500_cycle_overlay_merges_into_ten_legend_entries(cv_file_factory):
    run = _load_run(cv_file_factory, 500)
    assert len(run.cycles) == 500

    spec = PlotSpec("cv_overlay", [run.run_id])
    figure = Figure(figsize=(8, 6))
    render_plot(
        figure,
        type("D", (), {"cv_runs": [run], "eis_runs": []})(),
        spec,
        BUILTIN_PRESETS["daily"],
    )

    ax = figure.axes[0]
    assert len(ax.lines) == 500
    legend = ax.get_legend()
    assert legend is not None
    labels = [text.get_text() for text in legend.get_texts()]
    assert labels == [f"Cycle {start}-{end}" for start, end in (
        (1, 50), (51, 100), (101, 150), (151, 200), (201, 250),
        (251, 300), (301, 350), (351, 400), (401, 450), (451, 500),
    )]
    assert ax.lines[0].get_color() == ax.lines[49].get_color()
    assert ax.lines[0].get_color() != ax.lines[50].get_color()


def test_cycle_legend_limit_zero_keeps_every_cycle(cv_file_factory):
    run = _load_run(cv_file_factory, 12)
    spec = PlotSpec(
        "cv_overlay",
        [run.run_id],
        analysis_options={"legend_cycle_limit": 0},
    )
    figure = Figure(figsize=(8, 6))
    render_plot(
        figure,
        type("D", (), {"cv_runs": [run], "eis_runs": []})(),
        spec,
        BUILTIN_PRESETS["daily"],
    )
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels == [f"Cycle {cycle.index}" for cycle in run.cycles]


def test_grouped_template_uses_range_as_cycle_number(cv_file_factory):
    run = _load_run(cv_file_factory, 12)
    run.legend_template = "{Cycle_Number}"
    spec = PlotSpec("cv_overlay", [run.run_id])
    figure = Figure(figsize=(8, 6))
    render_plot(
        figure,
        type("D", (), {"cv_runs": [run], "eis_runs": []})(),
        spec,
        BUILTIN_PRESETS["daily"],
    )
    labels = [text.get_text() for text in figure.axes[0].get_legend().get_texts()]
    assert labels == ["1-2", "3-4", "5", "6", "7", "8", "9", "10", "11", "12"]


def test_legend_limit_control_writes_analysis_option(tmp_path, synthetic_cv_runs):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from cvanalysis.domain.models import Dataset
    from cvanalysis.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    window._on_import_complete(Dataset(cv_runs=list(synthetic_cv_runs)), [])
    tab = window.tabs.currentWidget()
    window.options_panel.bind(tab)
    control = window.options_panel.controls["legend_cycle_limit"]
    control.setValue(0)
    window.options_panel.apply()
    assert tab.spec.analysis_options["legend_cycle_limit"] == 0
    window.close()
    app.processEvents()


def test_legend_limit_round_trips_in_plot_spec():
    spec = PlotSpec(
        "cv_overlay",
        ["run"],
        analysis_options={"legend_cycle_limit": 0, "axis_limits": {"main": {"y_min": 0}}},
    )
    restored = PlotSpec.from_dict(spec.to_dict())
    assert restored.analysis_options["legend_cycle_limit"] == 0
    assert restored.analysis_options["axis_limits"]["main"]["y_min"] == 0
