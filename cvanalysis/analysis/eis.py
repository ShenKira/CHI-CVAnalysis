# -*- coding: utf-8 -*-
"""Rapid EIS metrics and frequency filtering."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cvanalysis.analysis.fitting import EISFitResult
from cvanalysis.domain.models import EISRun


METHOD_VERSION = 2


@dataclass
class EISMetrics:
    run_id: str
    rs_ohm: float | None
    rct_ohm: float | None
    f_peak_hz: float | None
    cdl_F: float | None
    tau_s: float | None
    phase_at_1hz_deg: float | None
    mag_at_1hz_ohm: float | None
    low_freq_mag_ohm: float | None
    low_freq_phase_deg: float | None
    high_freq_hz: float | None
    low_freq_hz: float | None
    points: int
    semicircle_detected: bool
    recommended_model: str | None = None
    warnings: list[str] = field(default_factory=list)
    method: str = "geometric"
    method_version: int = METHOD_VERSION
    fit_model: str | None = None
    fit_frequency_range_hz: tuple[float, float] | None = None
    effective_capacitance_F: float | None = None


def _interp_log_frequency(freq: np.ndarray, values: np.ndarray, target: float) -> float | None:
    if target <= 0 or freq.size < 2:
        return None
    order = np.argsort(freq)
    f_sorted = freq[order]
    v_sorted = values[order]
    if target < f_sorted[0] or target > f_sorted[-1]:
        return None
    return float(np.interp(np.log10(target), np.log10(f_sorted), v_sorted))


def analyze_eis(run: EISRun, *, phase_frequencies: tuple[float, ...] = (1.0, 0.1)) -> EISMetrics:
    freq = np.asarray(run.freq, dtype=float)
    z_real = np.asarray(run.z_real, dtype=float)
    z_imag = np.asarray(run.z_imag, dtype=float)
    phase = np.asarray(run.phase, dtype=float)
    z_mag = np.asarray(run.z_mag, dtype=float)
    finite = np.isfinite(freq) & np.isfinite(z_real) & np.isfinite(z_imag) & (freq > 0)
    freq = freq[finite]
    z_real = z_real[finite]
    z_imag = z_imag[finite]
    phase = phase[finite]
    z_mag = z_mag[finite]
    warnings: list[str] = []
    if freq.size < 3:
        warnings.append("EIS 数据点不足")
    order = np.argsort(-freq)
    freq = freq[order]
    z_real = z_real[order]
    z_imag = z_imag[order]
    phase = phase[order]
    z_mag = z_mag[order]

    if freq.size == 0:
        return EISMetrics(
            run_id=run.run_id,
            rs_ohm=None,
            rct_ohm=None,
            f_peak_hz=None,
            cdl_F=None,
            tau_s=None,
            phase_at_1hz_deg=None,
            mag_at_1hz_ohm=None,
            low_freq_mag_ohm=None,
            low_freq_phase_deg=None,
            high_freq_hz=None,
            low_freq_hz=None,
            points=0,
            semicircle_detected=False,
            warnings=warnings,
        )

    high = (freq >= freq[0] / 2) & (z_real >= 0)
    rs = float(np.median(z_real[high][:5])) if high.any() else None
    if rs is None:
        warnings.append("高频端没有有效的非负阻抗实部，无法估算 Rs")
    neg_imag = -z_imag
    peak_index = int(np.argmax(neg_imag))
    peak = float(neg_imag[peak_index])
    interior_peak = 0 < peak_index < len(freq) - 1 and peak > 0
    f_peak = float(freq[peak_index]) if interior_peak else None
    span = float(z_real[-1] - z_real[0])
    arc_candidate = (
        freq.size >= 7 and 2 <= peak_index <= len(freq) - 3 and peak > 0 and span > 0
        and abs(neg_imag[0]) <= .2 * peak and abs(neg_imag[-1]) <= .2 * peak
        and np.all(np.diff(z_real) >= -.02 * span)
        and np.all(np.diff(neg_imag[:peak_index + 1]) >= -.03 * peak)
        and np.all(np.diff(neg_imag[peak_index:]) <= .03 * peak)
        and np.all(neg_imag >= -.03 * peak)
    )
    semicircle = False
    if arc_candidate:
        distances = np.hypot(z_real - (z_real[0] + span / 2), neg_imag) / (span / 2)
        semicircle = abs(2 * peak / span - 1) <= .10 and np.max(np.abs(distances - 1)) <= .10
    if semicircle:
        rct = 2.0 * peak
        cdl = 1.0 / (2.0 * np.pi * f_peak * rct) if rct > 0 and f_peak > 0 else None
        tau = 1.0 / (2.0 * np.pi * f_peak) if f_peak > 0 else None
    else:
        rct = None
        cdl = None
        tau = None
        warnings.append("未检测到覆盖两侧且近似理想的单弧，几何 Rct/Cdl 留空")

    phase_1hz = _interp_log_frequency(freq, phase, 1.0)
    mag_1hz = _interp_log_frequency(freq, z_mag, 1.0)
    low_index = int(np.argmin(freq))
    low_mag = float(z_mag[low_index]) if z_mag.size else None
    low_phase = float(phase[low_index]) if phase.size else None
    if np.median(z_imag) > 0:
        warnings.append("Z'' 为正值，文件可能使用了相反的虚部符号约定")

    return EISMetrics(
        run_id=run.run_id,
        rs_ohm=rs,
        rct_ohm=rct,
        f_peak_hz=f_peak,
        cdl_F=cdl,
        tau_s=tau,
        phase_at_1hz_deg=phase_1hz,
        mag_at_1hz_ohm=mag_1hz,
        low_freq_mag_ohm=low_mag,
        low_freq_phase_deg=low_phase,
        high_freq_hz=float(np.max(freq)) if freq.size else None,
        low_freq_hz=float(np.min(freq)) if freq.size else None,
        points=int(freq.size),
        semicircle_detected=semicircle,
        recommended_model="rct_cpe" if arc_candidate else None,
        warnings=warnings,
    )


def metrics_from_fit(run: EISRun, fit: EISFitResult, base: EISMetrics | None = None) -> EISMetrics:
    """Combine geometric metrics with fitted Rs/Rct/Cdl."""
    base = base or analyze_eis(run)
    parameters = fit.parameters
    rs = parameters.get("Rs_ohm")
    rct = parameters.get("Rct_ohm")
    cdl = parameters.get("C_eff_F") if rct is not None else None
    warnings = list(base.warnings)
    warnings.extend(fit.warnings)
    if rs is not None and base.rs_ohm is not None and rs < max(1e-9, 1e-4 * base.rs_ohm):
        warnings.append("拟合 Rs 接近 0，且明显低于高频估计，请核对电路和频段")
    return EISMetrics(
        run_id=base.run_id,
        rs_ohm=rs,
        rct_ohm=rct,
        f_peak_hz=base.f_peak_hz,
        cdl_F=cdl,
        tau_s=parameters.get("tau_s"),
        phase_at_1hz_deg=base.phase_at_1hz_deg,
        mag_at_1hz_ohm=base.mag_at_1hz_ohm,
        low_freq_mag_ohm=base.low_freq_mag_ohm,
        low_freq_phase_deg=base.low_freq_phase_deg,
        high_freq_hz=base.high_freq_hz,
        low_freq_hz=base.low_freq_hz,
        points=base.points,
        semicircle_detected=base.semicircle_detected,
        recommended_model=base.recommended_model,
        warnings=warnings,
        method="equivalent-circuit-fit",
        fit_model=fit.model_label,
        fit_frequency_range_hz=(float(np.min(fit.frequencies)), float(np.max(fit.frequencies))) if fit.frequencies.size else None,
        effective_capacitance_F=fit.c_eff_F,
    )


def filter_eis_run(
    run: EISRun,
    low_freq: float | None = None,
    high_freq: float | None = None,
) -> EISRun:
    """Return a shallow copy of a run restricted to a frequency range."""
    if run.freq.size == 0:
        low = high = 0.0
    else:
        low = low_freq if low_freq is not None else float(np.nanmin(run.freq))
        high = high_freq if high_freq is not None else float(np.nanmax(run.freq))
    if low > high:
        low, high = high, low
    mask = (run.freq >= low) & (run.freq <= high)
    return EISRun(
        run_id=run.run_id,
        name=run.name,
        source=run.source,
        run_index=run.run_index,
        freq=run.freq[mask],
        z_real=run.z_real[mask],
        z_imag=run.z_imag[mask],
        z_mag=run.z_mag[mask],
        phase=run.phase[mask],
        metadata=run.metadata,
        params=run.params.copy(),
        warnings=list(run.warnings),
        parser_id=run.parser_id,
        parser_version=run.parser_version,
        summary=run.summary,
    )
