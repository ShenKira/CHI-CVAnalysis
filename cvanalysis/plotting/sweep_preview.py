"""Standalone LSV and i-t plotting primitives awaiting GUI/project integration."""
from __future__ import annotations

import math

import numpy as np
from matplotlib.figure import Figure

from cvanalysis.io.chi_sweep import CHISweepData


def draw_lsv_preview(figure: Figure, run: CHISweepData, *, voltage_window=None):
    if run.x_unit != "V":
        raise ValueError("LSV requires potential/current data")
    figure.clear()
    ax = figure.add_subplot(111)
    ax.plot(run.x, run.current, label=run.source.stem)
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (A)")
    if voltage_window is not None:
        low, high = sorted(float(value) for value in voltage_window)
        if not math.isfinite(low) or not math.isfinite(high) or low == high:
            raise ValueError("voltage window must have two distinct finite endpoints")
        ax.axvspan(low, high, alpha=.12, color="tab:blue")
        ax.axvline(low, linestyle="--", color="tab:blue")
        ax.axvline(high, linestyle="--", color="tab:blue")
        ax.text(.5, .97, f"ΔV = {high-low:.4g} V", transform=ax.transAxes,
                ha="center", va="top")
    return ax


def draw_it_preview(figure: Figure, run: CHISweepData, *, reference_time=None):
    if run.x_unit != "s":
        raise ValueError("i-t requires time/current data")
    figure.clear()
    ax = figure.add_subplot(111)
    ax.plot(run.x, run.current, label=run.source.stem)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Current (A)")
    if reference_time is not None:
        time = float(reference_time)
        if not math.isfinite(time) or time < np.min(run.x) or time > np.max(run.x):
            raise ValueError("reference time is outside the measured data")
        index = int(np.argmin(np.abs(run.x - time)))
        actual_time, current = float(run.x[index]), float(run.current[index])
        ax.axhline(current, linestyle="--", color="tab:red")
        ax.plot([actual_time], [current], "o", color="tab:red")
        ax.annotate(f"t={actual_time:.4g} s, I={current:.4g} A", (actual_time, current),
                    xytext=(5, 8), textcoords="offset points")
    return ax
