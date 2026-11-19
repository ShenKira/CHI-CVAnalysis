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


def test_eis_rejects_depressed_and_truncated_arcs_for_geometric_rct(synthetic_eis_run):
    from dataclasses import replace

    f = np.logspace(5, -5, 201)
    omega = 2 * np.pi * f
    q = 1 / (100 * (2 * np.pi * 100)**.6)
    z = 10 + 1 / (.01 + q * (1j * omega)**.6)
    run = replace(synthetic_eis_run, freq=f, z_real=z.real, z_imag=z.imag,
                  z_mag=abs(z), phase=np.angle(z, deg=True))
    quick = analyze_eis(run)
    assert quick.rct_ohm is None and quick.cdl_F is None
    assert quick.f_peak_hz == pytest.approx(100.)
    fit = fit_eis_model(f, z.real, z.imag, "rct_cpe")
    model_metrics = metrics_from_fit(run, fit, quick)
    assert model_metrics.rct_ohm == pytest.approx(100., rel=1e-5)
    assert model_metrics.fit_frequency_range_hz == pytest.approx((1e-5, 1e5))
    truncated = analyze_eis(filter_eis_run(run, 80., 250.))
    assert truncated.rct_ohm is None and truncated.recommended_model is None
    run.z_real[-2] = .3
    assert analyze_eis(run).rs_ohm > 9
