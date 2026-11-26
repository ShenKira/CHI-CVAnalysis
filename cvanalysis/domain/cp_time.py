"""Validate and reuse the active-current sampling grid of CHI CP files."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import numpy as np

from cvanalysis.domain.models import CPRun


def _text_quantum(token: str) -> float:
    try:
        exponent = Decimal(token).as_tuple().exponent
        return 10.0 ** exponent if isinstance(exponent, int) else 0.0
    except (InvalidOperation, OverflowError):
        return 0.0


def _grid_status(
    time: np.ndarray, step: float | None, tokens: list[str] | None,
) -> str:
    time = np.asarray(time, dtype=float)
    if (step is None or not np.isfinite(step) or step <= 0 or time.size < 8
            or time.ndim != 1 or not np.isfinite(time).all() or time[0] < 0 or np.any(np.diff(time) < 0)):
        return "unverified"
    grid = time[0] + np.arange(time.size, dtype=float) * step
    if not np.isfinite(grid).all():
        return "unverified"
    epsilon = np.maximum(step * 1e-9, grid * (8 * np.finfo(float).eps))
    error = np.abs(time - grid)
    if np.all(error <= epsilon):
        return "as_recorded"
    if tokens is not None:
        quantum = np.fromiter(map(_text_quantum, tokens), dtype=float, count=time.size)
        status = "verified_text"
    else:
        # Embedded older projects retained numbers, but not their printed digits.
        quantum = np.zeros_like(time)
        positive = time > 0
        quantum[positive] = 10.0 ** (np.floor(np.log10(time[positive])) - 3)
        status = "verified_legacy"
    if time[0] == 0:
        quantum[0] = 0
    if np.any(quantum[:8] > step * .1) or np.any(error > quantum / 2 + epsilon):
        return "unverified"
    return status


def prepare_cp_time(
    run: CPRun, *, tokens: list[str] | None = None, damaged: bool = False,
) -> None:
    """Record the source of the time axis without altering the raw samples."""
    if run.parser_id != "chi_cp":
        run.time_grid_status = "as_recorded"
        return
    if tokens is None:
        damaged |= any("行无法解析的数据" in item or "已按时间重新排序" in item for item in run.warnings)
    run.time_grid_status = (
        "unverified" if damaged else _grid_status(run.time, run.metadata.sample_interval_s, tokens)
    )


def cp_analysis_time(run: CPRun) -> np.ndarray:
    if not run.time_grid_status:
        prepare_cp_time(run)
    time = np.asarray(run.time, dtype=float)
    step = run.metadata.sample_interval_s
    if (run.time_grid_status in {"verified_text", "verified_legacy"} and time.size
            and step is not None and np.isfinite(step) and step > 0):
        return time[0] + np.arange(time.size, dtype=float) * step
    return time


def cp_time_warning(run: CPRun) -> str:
    if run.time_grid_status in {"verified_text", "verified_legacy"}:
        step = run.metadata.sample_interval_s
        if step is not None and np.isfinite(step) and step > 0:
            return f"CHI 导出时间戳发生舍入，已用逐行校验通过的 {step:g} s 采样网格计算"
    if np.any(np.diff(run.time) == 0):
        return "存在重复时间戳，无法验证固定采样网格。已按原时间列计算，容量与 IR 降可能受影响"
    if (run.time_grid_status == "unverified" and run.metadata.sample_interval_s is not None
            and np.size(run.time) >= 8):
        return "时间列无法验证为设定采样网格。容量、CE 和 IR 降按原时间戳计算"
    return ""
