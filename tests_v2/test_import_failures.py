# -*- coding: utf-8 -*-
import copy
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox

from cvanalysis.analysis.eis import analyze_eis, filter_eis_run
from cvanalysis.domain.models import Dataset, EISMetadata, EISRun
from cvanalysis.io.registry import load_files
from cvanalysis.services.dataset_service import refresh_analysis
from cvanalysis.ui.main_window import MainWindow


def _empty_eis_run() -> EISRun:
    return EISRun(
        run_id="eis_empty",
        name="empty",
        freq=np.asarray([], dtype=float),
        z_real=np.asarray([], dtype=float),
        z_imag=np.asarray([], dtype=float),
        z_mag=np.asarray([], dtype=float),
        phase=np.asarray([], dtype=float),
        metadata=EISMetadata(),
    )


def test_empty_eis_data_is_reported_without_crashing():
    run = _empty_eis_run()
    metrics = analyze_eis(run)
    assert metrics.points == 0
    assert metrics.rs_ohm is None
    assert metrics.warnings
    filtered = filter_eis_run(run, 1.0, 1000.0)
    assert filtered.freq.size == 0


def test_refresh_analysis_continues_after_one_eis_failure(monkeypatch, synthetic_eis_run):
    bad = copy.deepcopy(synthetic_eis_run)
    bad.run_id = "eis_bad"
    bad.name = "bad-eis"
    good = copy.deepcopy(synthetic_eis_run)
    good.run_id = "eis_good"
    good.name = "good-eis"
    dataset = Dataset(eis_runs=[bad, good])

    import cvanalysis.services.dataset_service as dataset_service

    original = dataset_service.analyze_eis

    def fake_analyze(run):
        if run.run_id == bad.run_id:
            raise ValueError("bad impedance data")
        return original(run)

    monkeypatch.setattr(dataset_service, "analyze_eis", fake_analyze)
    warnings = refresh_analysis(dataset)
    assert any("bad-eis" in message and "EIS 分析失败" in message for message in warnings)
    assert bad.summary is None
    assert good.summary is not None


def test_partial_import_reports_failed_file_and_keeps_others(tmp_path):
    bad = tmp_path / "broken-eis.txt"
    bad.write_text("this is not an EIS file", encoding="utf-8")
    good = Path(__file__).parent / "fixtures" / "test_EIS.txt"
    dataset, issues = load_files([bad, good])
    assert len(issues) == 1
    assert issues[0].path == bad
    assert len(dataset.eis_runs) == 1

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "config.json")
    with patch.object(QMessageBox, "warning") as warning:
        window._on_import_complete(dataset, issues)
        app.processEvents()
    assert warning.called
    message = warning.call_args.args[2]
    assert "broken-eis.txt" in message
    assert len(window.dataset.eis_runs) == 1
    window.close()
    app.processEvents()
