# -*- coding: utf-8 -*-
"""Shared test fixtures and synthetic CHI data generators."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CVANALYSIS_DISABLE_SAVE_PROMPTS", "1")

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cvanalysis.domain.models import CVRun  # noqa: E402


def make_cv_text(
    *,
    scan_rate: float,
    capacitance: float = 1e-4,
    high: float = 1.0,
    low: float = 0.0,
    cycles: int = 2,
    points_per_segment: int = 101,
    offset_current: float = 0.0,
) -> str:
    potentials: list[float] = []
    currents: list[float] = []
    current_up = capacitance * scan_rate
    current_down = -capacitance * scan_rate
    for cycle in range(cycles):
        for index, potential in enumerate(np.linspace(low, high, points_per_segment)):
            if cycle == 0 and index == 0:
                continue
            potentials.append(float(potential))
            currents.append(current_up + offset_current)
        for potential in np.linspace(high, low, points_per_segment)[1:]:
            potentials.append(float(potential))
            currents.append(current_down + offset_current)
    lines = [
        "Synthetic CV",
        "Cyclic Voltammetry",
        "Instrument Model:  CHI660E",
        "",
        f"Init E (V) = {low}",
        f"High E (V) = {high}",
        f"Low E (V) = {low}",
        f"Scan Rate (V/s) = {scan_rate:g}",
        f"Segment = {cycles * 2}",
        "Sample Interval (V) = 0.01",
        "Quiet Time (sec) = 2",
        "Sensitivity (A/V) = 1e-3",
        "",
        "Potential/V, Current/A",
    ]
    lines.extend(f"{potential:.8g}, {current:.8e}" for potential, current in zip(potentials, currents))
    return "\n".join(lines) + "\n"


def make_cv_file(tmp_path: Path, name: str, **kwargs) -> Path:
    path = tmp_path / name
    path.write_text(make_cv_text(**kwargs), encoding="utf-8")
    return path


@pytest.fixture
def cv_text_factory():
    return make_cv_text


@pytest.fixture
def cv_file_factory(tmp_path):
    def factory(name: str, **kwargs):
        return make_cv_file(tmp_path, name, **kwargs)

    return factory


@pytest.fixture
def synthetic_cv_runs(cv_file_factory):
    from cvanalysis.io.registry import load_files
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis

    paths = [
        cv_file_factory("cv_010.txt", scan_rate=0.01, capacitance=1e-4),
        cv_file_factory("cv_020.txt", scan_rate=0.02, capacitance=1e-4),
        cv_file_factory("cv_050.txt", scan_rate=0.05, capacitance=1e-4),
    ]
    dataset, issues = load_files(paths)
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    return dataset.cv_runs


def make_cp_text(
    *,
    current_a: float = 1e-6,
    high: float = 2.0,
    low: float = 0.0,
    segment_duration: float = 2.0,
    hold_duration: float = 10.0,
) -> str:
    segments = [
        (0.3, low, 0.5),
        (low, high, segment_duration),
        (high, low, segment_duration),
        (low, high, segment_duration),
        (high, low, segment_duration),
    ]
    rows: list[str] = []
    t_end = 0.0
    for start, end, duration in segments:
        count = max(5, int(round(duration / 0.01)) + 1)
        for index, (time_s, potential) in enumerate(
            zip(
                np.linspace(t_end, t_end + duration, count),
                np.linspace(start, end, count),
            )
        ):
            if rows and index == 0:
                continue
            rows.append(f"{time_s:.6g}, {potential:.8g}")
        t_end += duration
    hold_rows: list[str] = []
    hold_time = 0.0
    for polarity in (-1, 1, -1, 1, -1):
        count = max(5, int(round(hold_duration / 0.01)) + 1)
        for index, relative in enumerate(np.linspace(0.0, hold_duration, count)):
            hold_rows.append(f"{hold_time + relative:.6g}, {polarity * current_a:.8e}, ")
        hold_time += hold_duration + 0.02
    lines = [
        "Synthetic Chronopotentiometry",
        "Chronopotentiometry",
        "Instrument Model:  CHI660E",
        "",
        f"Cathodic Current (A) = {current_a:g}",
        f"Anodic Current (A) = {current_a:g}",
        "Init P/N = N",
        "Data Storage Interval (s) = 0.01",
        f"High E Limit (V) = {high:g}",
        f"High E Hold Time (s) = {hold_duration:g}",
        f"Low E Limit (V) = {low:g}",
        f"Low E Hold Time (s) = {hold_duration:g}",
        "Cathodic Time (s) = 10",
        "Anodic Time (s) = 10",
        "Current Switching Polarity = Potential",
        "Segment = 5",
        "",
        "Time/sec, Potential/V",
        *rows,
        "",
        "Hold Time/sec, Current/A",
        *hold_rows,
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def synthetic_cp_run(tmp_path):
    from cvanalysis.io.registry import load_files
    from cvanalysis.services.dataset_service import AnalysisSettings, refresh_analysis

    path = tmp_path / "cp_synthetic.txt"
    path.write_text(make_cp_text(), encoding="utf-8")
    dataset, issues = load_files([path])
    assert not issues
    refresh_analysis(dataset, AnalysisSettings())
    return dataset.cp_runs[0]


@pytest.fixture
def synthetic_eis_run():
    from cvanalysis.domain.models import EISMetadata, EISRun

    frequency = np.logspace(5, -2, 80)
    omega = 2 * np.pi * frequency
    rs, rct, capacitance = 10.0, 100.0, 1e-5
    impedance = rs + rct / (1 + 1j * omega * rct * capacitance)
    return EISRun(
        run_id="eis_synthetic",
        name="synthetic_rc",
        freq=frequency,
        z_real=impedance.real,
        z_imag=impedance.imag,
        z_mag=np.abs(impedance),
        phase=np.degrees(np.angle(impedance)),
        metadata=EISMetadata(high_freq=float(frequency.max()), low_freq=float(frequency.min())),
    )
