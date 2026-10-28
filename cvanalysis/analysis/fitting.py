# -*- coding: utf-8 -*-
"""Equivalent-circuit fitting for EIS data.

Only a small, well-behaved set of models is shipped by default.  The model
registry is deliberately simple so additional circuits can be added without
touching the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from cvanalysis.domain.errors import FitError

try:
    from scipy.optimize import least_squares
except Exception:  # pragma: no cover
    least_squares = None


METHOD_VERSION = 2


@dataclass
class EISFitResult:
    model: str
    model_label: str
    parameters: dict[str, float]
    stderr: dict[str, float]
    rmse_ohm: float
    r2: float
    frequencies: np.ndarray
    z_fit: np.ndarray
    residual_real: np.ndarray
    residual_imag: np.ndarray
    success: bool
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    method_version: int = METHOD_VERSION

    @property
    def c_eff_F(self) -> float | None:
        value = self.parameters.get("C_eff_F")
        return value if value is not None and np.isfinite(value) else None


def _z_rct_cpe(parameters: np.ndarray, omega: np.ndarray) -> np.ndarray:
    rs, rct, q, n = parameters
    return rs + 1.0 / (1.0 / rct + q * (1j * omega) ** n)


def _z_rct_c(parameters: np.ndarray, omega: np.ndarray) -> np.ndarray:
    rs, rct, capacitance = parameters
    return rs + rct / (1.0 + 1j * omega * rct * capacitance)


def _z_rs_cpe(parameters: np.ndarray, omega: np.ndarray) -> np.ndarray:
    rs, q, n = parameters
    return rs + 1.0 / (q * (1j * omega) ** n)


def _z_rs_c(parameters: np.ndarray, omega: np.ndarray) -> np.ndarray:
    rs, capacitance = parameters
    return rs + 1.0 / (1j * omega * capacitance)


MODEL_SPECS: dict[str, dict] = {
    "rct_cpe": {
        "label": "Rs-(Rct||CPE)",
        "function": _z_rct_cpe,
        "names": ("Rs_ohm", "Rct_ohm", "Q_S_s_n", "n"),
        "kind": "semicircle_cpe",
    },
    "rct_c": {
        "label": "Rs-(Rct||C)",
        "function": _z_rct_c,
        "names": ("Rs_ohm", "Rct_ohm", "C_F"),
        "kind": "semicircle_c",
    },
    "rs_cpe": {
        "label": "Rs-CPE (blocking)",
        "function": _z_rs_cpe,
        "names": ("Rs_ohm", "Q_S_s_n", "n"),
        "kind": "series_cpe",
    },
    "rs_c": {
        "label": "Rs-C (ideal)",
        "function": _z_rs_c,
        "names": ("Rs_ohm", "C_F"),
        "kind": "series_c",
    },
}


def available_models() -> dict[str, str]:
    return {key: spec["label"] for key, spec in MODEL_SPECS.items()}


def _initial_guess(
    model: str,
    freq: np.ndarray,
    z_real: np.ndarray,
    z_imag: np.ndarray,
) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    z_real = np.asarray(z_real, dtype=float)
    z_imag = np.asarray(z_imag, dtype=float)
    freq = np.asarray(freq, dtype=float)
    finite = np.isfinite(z_real) & np.isfinite(z_imag) & np.isfinite(freq) & (freq > 0)
    if finite.sum() < 4:
        raise FitError("有效 EIS 数据点不足，无法拟合")
    z_real = z_real[finite]
    z_imag = z_imag[finite]
    freq = freq[finite]
    scale = max(float(np.nanmax(np.abs(z_real))), float(np.nanmax(np.abs(z_imag))), 1e-12)
    rs0 = max(float(np.nanmin(z_real)), 1e-12)
    # The high-frequency intercept is a physical lower bound: Rs cannot be
    # orders of magnitude above the smallest measured real impedance.
    rs_upper = max(rs0 * 10.0, 1e-9)
    neg_imag = -z_imag
    peak = int(np.argmax(neg_imag))
    if 0 < peak < len(freq) - 1 and neg_imag[peak] > 0:
        rct0 = max(2.0 * float(neg_imag[peak]), rs0 * 0.1)
        f0 = float(freq[peak])
    else:
        rct0 = max(float(np.nanmax(z_real) - np.nanmin(z_real)) * 2.0, rs0 * 10.0, 1e-6)
        f0 = float(np.sqrt(np.nanmin(freq) * np.nanmax(freq)))
    f0 = max(f0, 1e-9)
    upper_scale = max(float(np.nanmax(np.abs(z_real))), rct0, scale) * 100.0
    kind = MODEL_SPECS[model]["kind"]

    if kind == "semicircle_cpe":
        n0 = 0.8
        q0 = 1.0 / max(rct0 * (2.0 * np.pi * f0) ** n0, 1e-30)
        x0 = np.array([rs0, rct0, q0, n0], dtype=float)
        lower = np.array([0.0, 1e-12, 1e-15, 0.2], dtype=float)
        upper = np.array([rs_upper, upper_scale, 1e3, 1.0], dtype=float)
    elif kind == "semicircle_c":
        c0 = 1.0 / max(rct0 * 2.0 * np.pi * f0, 1e-30)
        x0 = np.array([rs0, rct0, c0], dtype=float)
        lower = np.array([0.0, 1e-12, 1e-15], dtype=float)
        upper = np.array([rs_upper, upper_scale, 1e3], dtype=float)
    else:
        # Series CPE / C: estimate the reactive impedance near a central
        # frequency, where both ends of a blocking-electrode spectrum matter.
        z_mag = np.hypot(z_real, z_imag)
        reference = float(np.exp(np.mean(np.log([np.nanmin(freq), np.nanmax(freq)]))))
        ref_index = int(np.argmin(np.abs(np.log(freq) - np.log(reference))))
        reactive = max(float(z_mag[ref_index] - rs0), scale * 1e-6)
        n0 = 0.9
        q0 = 1.0 / max(reactive * (2.0 * np.pi * reference) ** n0, 1e-30)
        if kind == "series_cpe":
            x0 = np.array([rs0, q0, n0], dtype=float)
            lower = np.array([0.0, 1e-15, 0.2], dtype=float)
            upper = np.array([rs_upper, 1e3, 1.0], dtype=float)
        else:
            c0 = 1.0 / max(reactive * 2.0 * np.pi * reference, 1e-30)
            x0 = np.array([rs0, c0], dtype=float)
            lower = np.array([0.0, 1e-15], dtype=float)
            upper = np.array([rs_upper, 1e3], dtype=float)
    return x0, (lower, upper)


def fit_eis_model(
    freq: np.ndarray,
    z_real: np.ndarray,
    z_imag: np.ndarray,
    model: str = "rct_cpe",
) -> EISFitResult:
    if least_squares is None:
        raise FitError("当前环境缺少 scipy，无法执行等效电路拟合")
    if model not in MODEL_SPECS:
        raise FitError(f"未知的 EIS 拟合模型: {model}")

    freq = np.asarray(freq, dtype=float)
    z_real = np.asarray(z_real, dtype=float)
    z_imag = np.asarray(z_imag, dtype=float)
    finite = np.isfinite(freq) & np.isfinite(z_real) & np.isfinite(z_imag) & (freq > 0)
    if finite.sum() < 4:
        raise FitError("有效 EIS 数据点不足，无法拟合")
    freq = freq[finite]
    z_real = z_real[finite]
    z_imag = z_imag[finite]
    order = np.argsort(-freq)
    freq = freq[order]
    z_real = z_real[order]
    z_imag = z_imag[order]
    omega = 2.0 * np.pi * freq
    z_observed = z_real + 1j * z_imag

    spec = MODEL_SPECS[model]
    model_function: Callable[[np.ndarray, np.ndarray], np.ndarray] = spec["function"]
    x0, (lower, upper) = _initial_guess(model, freq, z_real, z_imag)
    x0 = np.clip(x0, lower + 1e-15, upper - 1e-15)
    scale = max(float(np.nanmax(np.abs(z_observed))), 1e-12)

    weights = np.maximum(np.abs(z_observed), scale * 1e-6)

    def residual(parameters: np.ndarray) -> np.ndarray:
        prediction = model_function(parameters, omega)
        # Relative weighting prevents the large low-frequency impedance from
        # completely hiding the high-frequency intercept (Rs).
        residual_complex = (prediction - z_observed) / weights
        return np.concatenate([residual_complex.real, residual_complex.imag])

    try:
        result = least_squares(
            residual,
            x0,
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=0.1,
            x_scale="jac",
            max_nfev=20000,
        )
    except Exception as exc:  # noqa: BLE001
        raise FitError(f"EIS 拟合失败: {exc}") from exc
    if not result.success:
        raise FitError(f"EIS 拟合未收敛: {result.message}")

    parameters = np.asarray(result.x, dtype=float)
    z_fit = model_function(parameters, omega)
    residual_complex = z_fit - z_observed
    rmse = float(np.sqrt(np.mean(np.abs(residual_complex) ** 2)))
    ss_res = float(np.sum(np.abs(residual_complex) ** 2))
    ss_tot = float(np.sum(np.abs(z_observed - np.mean(z_observed)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    names = spec["names"]
    parameter_dict = {name: float(value) for name, value in zip(names, parameters)}
    stderr_dict: dict[str, float] = {}
    try:
        jacobian = np.asarray(result.jac, dtype=float)
        dof = max(1, 2 * len(freq) - len(parameters))
        covariance = np.linalg.pinv(jacobian.T @ jacobian) * (2.0 * float(result.cost) / dof)
        errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        stderr_dict = {name: float(value) for name, value in zip(names, errors)}
    except Exception:
        stderr_dict = {name: float("nan") for name in names}

    warnings: list[str] = []
    kind = spec["kind"]
    if kind == "semicircle_cpe":
        n_value = parameter_dict["n"]
        rct = parameter_dict["Rct_ohm"]
        q_value = parameter_dict["Q_S_s_n"]
        if n_value < 0.4:
            warnings.append("CPE 指数 n 较低，电极界面可能明显非理想")
        try:
            c_eff = q_value ** (1.0 / n_value) * rct ** ((1.0 - n_value) / n_value)
            tau = (rct * q_value) ** (1.0 / n_value)
            parameter_dict["C_eff_F"] = float(c_eff)
            parameter_dict["tau_s"] = float(tau)
            parameter_dict["f0_Hz"] = float(1.0 / (2.0 * np.pi * tau)) if tau > 0 else float("nan")
        except Exception:
            warnings.append("无法由 CPE 参数换算有效电容")
    elif kind == "semicircle_c":
        capacitance = parameter_dict["C_F"]
        rct = parameter_dict["Rct_ohm"]
        tau = rct * capacitance
        parameter_dict["C_eff_F"] = float(capacitance)
        parameter_dict["tau_s"] = float(tau)
        parameter_dict["f0_Hz"] = float(1.0 / (2.0 * np.pi * tau)) if tau > 0 else float("nan")
    elif kind == "series_cpe":
        n_value = parameter_dict["n"]
        q_value = parameter_dict["Q_S_s_n"]
        if n_value < 0.5:
            warnings.append("CPE 指数 n 较低，低频行为更接近扩散而非电容")
        # Effective capacitance at 1 Hz: Z_CPE = 1/(jωC_eff) with
        # C_eff = Q (2πf)^(n-1).
        parameter_dict["C_eff_F"] = float(q_value * (2.0 * np.pi) ** (n_value - 1.0))
        parameter_dict["f0_Hz"] = 1.0
    else:
        capacitance = parameter_dict["C_F"]
        parameter_dict["C_eff_F"] = float(capacitance)
        parameter_dict["f0_Hz"] = float(1.0 / (2.0 * np.pi * max(parameter_dict["Rs_ohm"] * capacitance, 1e-30)))

    if r2 < 0.95:
        warnings.append("拟合 R² 较低，模型可能不适合该数据")
    if rmse / max(float(np.nanmedian(np.abs(z_observed))), 1e-12) > 0.2:
        warnings.append("拟合残差较大，请检查频率范围或模型")

    return EISFitResult(
        model=model,
        model_label=spec["label"],
        parameters=parameter_dict,
        stderr=stderr_dict,
        rmse_ohm=rmse,
        r2=float(r2),
        frequencies=freq,
        z_fit=z_fit,
        residual_real=residual_complex.real,
        residual_imag=residual_complex.imag,
        success=True,
        message=str(result.message),
        warnings=warnings,
    )
