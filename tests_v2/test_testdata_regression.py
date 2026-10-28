# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from matplotlib.figure import Figure

from cvanalysis.io.registry import load_files
from cvanalysis.plotting.export import render_plot
from cvanalysis.plotting.presets import BUILTIN_PRESETS
from cvanalysis.plotting.spec import PlotSpec
from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis


TESTDATA = Path(__file__).resolve().parents[1] / "testdata"


@pytest.mark.skipif(not TESTDATA.exists(), reason="testdata directory is not present")
def test_multi_cv_testdata_overlay_geometry():
    paths = sorted(str(path) for path in TESTDATA.glob("*_CV_*.txt"))[:9]
    if len(paths) < 2:
        pytest.skip("not enough CV testdata files")
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    assert len(dataset.cv_runs) == len(paths)
    style = BUILTIN_PRESETS["daily"]
    spec = PlotSpec("cv_overlay", [run.run_id for run in dataset.cv_runs])
    figure = Figure(figsize=style.figure_size, dpi=100)
    render_plot(figure, dataset, spec, style)
    ax = figure.axes[0]
    legend = ax.get_legend()
    assert legend is not None
    assert len(legend.get_texts()) == len(dataset.cv_runs)
    # A duplicated per-cycle legend used to squeeze this below 0.5.
    assert ax.get_position().width > 0.6
