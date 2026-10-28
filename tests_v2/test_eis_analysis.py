# -*- coding: utf-8 -*-
import numpy as np
import pytest

from cvanalysis.analysis.eis import analyze_eis, filter_eis_run, metrics_from_fit
from cvanalysis.analysis.fitting import fit_eis_model


def test_geometric_eis_metrics(synthetic_eis_run):
    metrics = analyze_eis(synthetic_eis_run)
    assert metrics.semicircle_detected
    assert metrics.rs_ohm == pytest.approx(10.0, rel=0.15)
    assert metrics.rct_ohm == pytest.approx(100.0, rel=0.15)
    assert metrics.cdl_F == pytest.approx(1e-5, rel=0.25)
    assert metrics.recommended_model == "rct_cpe"
    assert metrics.points == len(synthetic_eis_run.freq)


def test_fit_ideal_rc(synthetic_eis_run):
    fit = fit_eis_model(
        synthetic_eis_run.freq,
        synthetic_eis_run.z_real,
        synthetic_eis_run.z_imag,
        model="rct_c",
    )
    assert fit.parameters["Rs_ohm"] == pytest.approx(10.0, rel=1e-3)
    assert fit.parameters["Rct_ohm"] == pytest.approx(100.0, rel=1e-3)
    assert fit.parameters["C_F"] == pytest.approx(1e-5, rel=1e-3)
    assert fit.r2 > 0.9999


def test_fit_auto_recommendation_and_metrics(synthetic_eis_run):
    fit = fit_eis_model(
        synthetic_eis_run.freq,
        synthetic_eis_run.z_real,
        synthetic_eis_run.z_imag,
        model="rct_cpe",
    )
    assert fit.parameters["n"] == pytest.approx(1.0, abs=0.02)
    metrics = metrics_from_fit(synthetic_eis_run, fit)
    assert metrics.rs_ohm == pytest.approx(10.0, rel=0.02)
    assert metrics.rct_ohm == pytest.approx(100.0, rel=0.02)
    assert metrics.cdl_F == pytest.approx(1e-5, rel=0.05)


def test_frequency_filter(synthetic_eis_run):
    filtered = filter_eis_run(synthetic_eis_run, 1e-1, 1e3)
    assert np.all(filtered.freq >= 0.1)
    assert np.all(filtered.freq <= 1000)
    assert len(filtered.freq) < len(synthetic_eis_run.freq)
