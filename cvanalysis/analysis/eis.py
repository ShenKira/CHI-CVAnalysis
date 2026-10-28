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
    recommended_model: str = "rct_cpe"
    warnings: list[str] = field(default_factory=list)
    method: str = "geometric"
    method_version: int = METHOD_VERSION


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
            recommended_model="rs_cpe",
            warnings=warnings,
        )

    rs = float(np.nanmin(z_real)) if z_real.size else None
    neg_imag = -z_imag
    peak_index = int(np.argmax(neg_imag)) if neg_imag.size else -1
    semicircle = 0 < peak_index < len(freq) - 1 and neg_imag[peak_index] > 0
    if semicircle:
        rct = 2.0 * float(neg_imag[peak_index])
        f_peak = float(freq[peak_index])
        cdl = 1.0 / (2.0 * np.pi * f_peak * rct) if rct > 0 and f_peak > 0 else None
        tau = 1.0 / (2.0 * np.pi * f_peak) if f_peak > 0 else None
    else:
        rct = None
        f_peak = None
        cdl = None
        tau = None
        warnings.append("未检测到完整半圆，Rct/Cdl 仅能通过拟合获得")

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
        recommended_model="rct_cpe" if semicircle else "rs_cpe",
        warnings=warnings,
    )


def metrics_from_fit(run: EISRun, fit: EISFitResult, base: EISMetrics | None = None) -> EISMetrics:
    """Combine geometric metrics with fitted Rs/Rct/Cdl."""
    base = base or analyze_eis(run)
    parameters = fit.parameters
    rs = parameters.get("Rs_ohm", base.rs_ohm)
    rct = parameters.get("Rct_ohm", base.rct_ohm)
    cdl = parameters.get("C_eff_F", base.cdl_F)
    tau = parameters.get("tau_s", base.tau_s)
    f_peak = parameters.get("f0_Hz", base.f_peak_hz) if base.semicircle_detected else base.f_peak_hz
    warnings = list(base.warnings)
    warnings.extend(fit.warnings)
    if rs is not None and base.rs_ohm is not None and rs < max(1e-9, 1e-4 * base.rs_ohm):
        warnings.append("拟合 Rs 接近 0，已使用高频最小实部作为 Rs 估计")
        rs = base.rs_ohm
    return EISMetrics(
        run_id=base.run_id,
        rs_ohm=rs,
        rct_ohm=rct,
        f_peak_hz=f_peak,
        cdl_F=cdl,
        tau_s=tau,
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
