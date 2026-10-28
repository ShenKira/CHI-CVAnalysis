# -*- coding: utf-8 -*-
"""Core data model shared by parsers, analysis, plotting and the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import numpy as np


def abbreviate_name(name: str, max_chars: int = 32) -> str:
    """Shorten a long filename for tree/legend display without losing both ends."""
    name = str(name or "")
    if len(name) <= max_chars:
        return name
    if max_chars <= 3:
        return name[:max_chars]
    head = (max_chars - 1) // 2
    tail = max_chars - 1 - head
    return name[:head] + "…" + name[-tail:]


def new_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class ElectrodeParams:
    """Optional normalization parameters attached to a run."""

    area_cm2: float | None = None
    mass_mg: float | None = None

    def has_area(self) -> bool:
        return self.area_cm2 is not None and self.area_cm2 > 0

    def has_mass(self) -> bool:
        return self.mass_mg is not None and self.mass_mg > 0

    def copy(self) -> "ElectrodeParams":
        return ElectrodeParams(self.area_cm2, self.mass_mg)


@dataclass
class CVMetadata:
    technique: str = "Cyclic Voltammetry"
    init_e: float | None = None
    high_e: float | None = None
    low_e: float | None = None
    scan_rate: float | None = None
    segment: int | None = None
    sample_interval: float | None = None
    sensitivity: float | None = None
    quiet_time: float | None = None
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def voltage_window(self) -> float | None:
        if self.high_e is not None and self.low_e is not None:
            return abs(self.high_e - self.low_e)
        return None

    @property
    def expected_cycles(self) -> int | None:
        if self.segment is not None and self.segment >= 2:
            return self.segment // 2
        return None


@dataclass
class CPMetadata:
    """Metadata for a chronopotentiometry (constant-current) run."""

    technique: str = "Chronopotentiometry"
    init_pn: str | None = None
    high_e: float | None = None
    low_e: float | None = None
    high_hold_s: float | None = None
    low_hold_s: float | None = None
    cathodic_current_A: float | None = None
    anodic_current_A: float | None = None
    cathodic_time_s: float | None = None
    anodic_time_s: float | None = None
    switch_polarity: str | None = None
    segment: int | None = None
    sample_interval_s: float | None = None
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def voltage_window(self) -> float | None:
        if self.high_e is not None and self.low_e is not None:
            return abs(self.high_e - self.low_e)
        return None

    @property
    def hold_duration_s(self) -> float | None:
        values = [
            value
            for value in (self.high_hold_s, self.low_hold_s)
            if value is not None and value > 0
        ]
        return min(values) if values else None


@dataclass
class EISMetadata:
    technique: str = "A.C. Impedance"
    init_e: float | None = None
    high_freq: float | None = None
    low_freq: float | None = None
    amplitude: float | None = None
    quiet_time: float | None = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class CVCycle:
    """One complete CV cycle.

    ``potential``/``current`` keep the original acquisition order, while
    ``branch_up``/``branch_down`` are monotonic branches used for integration
    and for reading current at a selected potential.  Each branch has shape
    ``(N, 2)`` and is sorted by potential.
    """

    index: int
    potential: np.ndarray
    current: np.ndarray
    branch_up: np.ndarray
    branch_down: np.ndarray
    area_C: float = float("nan")
    capacitance_F: float = float("nan")
    is_outlier: bool = False
    outlier_reason: str | None = None
    warning: str | None = None
    integration_width_V: float = float("nan")
    is_partial: bool = False

    @property
    def integral_area_A_V(self) -> float:
        """CV loop integral in A·V; area_C remains a legacy API alias."""
        return self.area_C

    @property
    def valid(self) -> bool:
        return (
            not self.is_outlier
            and np.isfinite(self.capacitance_F)
            and self.capacitance_F > 0
        )

    def current_at(self, potential: float) -> tuple[float, float]:
        """Interpolate (forward, reverse) current at a potential.

        Returns ``(nan, nan)`` when the requested potential is outside the
        overlapping window of the two branches.
        """
        if self.branch_up.size < 2 or self.branch_down.size < 2:
            return float("nan"), float("nan")
        up_v = self.branch_up[:, 0]
        down_v = self.branch_down[:, 0]
        low = max(float(up_v[0]), float(down_v[0]))
        high = min(float(up_v[-1]), float(down_v[-1]))
        if not (low <= potential <= high):
            return float("nan"), float("nan")
        i_up = float(np.interp(potential, up_v, self.branch_up[:, 1]))
        i_down = float(np.interp(potential, down_v, self.branch_down[:, 1]))
        return i_up, i_down

    @property
    def voltage_window(self) -> float:
        if self.potential.size < 2:
            return float("nan")
        return max(0.0, float(np.nanmax(self.potential) - np.nanmin(self.potential)))


@dataclass
class CVRun:
    run_id: str
    name: str
    potential: np.ndarray
    current: np.ndarray
    metadata: CVMetadata
    source: Path | None = None
    run_index: int = 0
    params: ElectrodeParams = field(default_factory=ElectrodeParams)
    cycles: list[CVCycle] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    legend_template: str = ""
    parser_id: str = "chi_cv"
    parser_version: int = 1
    summary: Any = field(default=None, repr=False, compare=False)

    @property
    def scan_rate(self) -> float | None:
        return self.metadata.scan_rate

    @property
    def voltage_window(self) -> float | None:
        if self.metadata.voltage_window is not None:
            return self.metadata.voltage_window
        if self.potential.size:
            return float(np.nanmax(self.potential) - np.nanmin(self.potential))
        return None

    @property
    def display_name(self) -> str:
        return self.name or (self.source.stem if self.source else self.run_id)

    @property
    def display_short_name(self) -> str:
        return abbreviate_name(self.display_name, 34)

    @property
    def legend_name(self) -> str:
        return abbreviate_name(self.display_name, 26)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


@dataclass
class CPRun:
    """A chronopotentiometry run.

    ``time``/``potential`` are the acquisition-order active-current data.
    ``hold_time``/``hold_current`` keep the optional CHI block recorded during
    high/low potential holds.  Hold intervals are *not* part of ``time`` in
    the exported file; ``cvanalysis.analysis.cp`` can insert them for GCD
    display and analysis.
    """

    run_id: str
    name: str
    time: np.ndarray
    potential: np.ndarray
    metadata: CPMetadata
    hold_time: np.ndarray | None = None
    hold_current: np.ndarray | None = None
    source: Path | None = None
    run_index: int = 0
    params: ElectrodeParams = field(default_factory=ElectrodeParams)
    warnings: list[str] = field(default_factory=list)
    legend_template: str = ""
    parser_id: str = "chi_cp"
    parser_version: int = 1
    summary: Any = field(default=None, repr=False, compare=False)

    @property
    def display_name(self) -> str:
        return self.name or (self.source.stem if self.source else self.run_id)

    @property
    def display_short_name(self) -> str:
        return abbreviate_name(self.display_name, 34)

    @property
    def legend_name(self) -> str:
        return abbreviate_name(self.display_name, 26)

    @property
    def voltage_window(self) -> float | None:
        if self.metadata.voltage_window is not None:
            return self.metadata.voltage_window
        if self.potential.size:
            return float(np.nanmax(self.potential) - np.nanmin(self.potential))
        return None

    @property
    def has_hold_data(self) -> bool:
        return (
            self.hold_time is not None
            and self.hold_current is not None
            and len(self.hold_time) >= 2
            and len(self.hold_current) == len(self.hold_time)
        )

    @property
    def applied_current_A(self) -> float | None:
        for value in (self.metadata.anodic_current_A, self.metadata.cathodic_current_A):
            if value is not None and np.isfinite(value) and value != 0:
                return abs(float(value))
        return None

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


@dataclass
class EISRun:
    run_id: str
    name: str
    freq: np.ndarray
    z_real: np.ndarray
    z_imag: np.ndarray
    z_mag: np.ndarray
    phase: np.ndarray
    metadata: EISMetadata
    source: Path | None = None
    run_index: int = 0
    params: ElectrodeParams = field(default_factory=ElectrodeParams)
    warnings: list[str] = field(default_factory=list)
    legend_template: str = ""
    parser_id: str = "chi_eis"
    parser_version: int = 1
    summary: Any = field(default=None, repr=False, compare=False)

    @property
    def display_name(self) -> str:
        return self.name or (self.source.stem if self.source else self.run_id)

    @property
    def display_short_name(self) -> str:
        return abbreviate_name(self.display_name, 34)

    @property
    def legend_name(self) -> str:
        return abbreviate_name(self.display_name, 26)

    @property
    def z_complex(self) -> np.ndarray:
        return self.z_real + 1j * self.z_imag

    @property
    def sort_order(self) -> np.ndarray:
        """Indices sorted from high frequency to low frequency."""
        return np.argsort(-self.freq, kind="stable")

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


@dataclass
class Dataset:
    name: str = "未命名数据集"
    path: Path | None = None
    cv_runs: list[CVRun] = field(default_factory=list)
    eis_runs: list[EISRun] = field(default_factory=list)
    cp_runs: list[CPRun] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.cv_runs and not self.eis_runs and not self.cp_runs

    def all_runs(self) -> list[CVRun | EISRun | CPRun]:
        return [*self.cv_runs, *self.eis_runs, *self.cp_runs]

    def find_run(self, run_id: str) -> CVRun | EISRun | CPRun | None:
        for run in self.all_runs():
            if run.run_id == run_id:
                return run
        return None

    def find_cv(self, run_id: str) -> CVRun | None:
        return next((run for run in self.cv_runs if run.run_id == run_id), None)

    def find_eis(self, run_id: str) -> EISRun | None:
        return next((run for run in self.eis_runs if run.run_id == run_id), None)

    def find_cp(self, run_id: str) -> CPRun | None:
        return next((run for run in self.cp_runs if run.run_id == run_id), None)

    def add_runs(self, runs: Iterable[CVRun | EISRun | CPRun], *, replace: bool = False) -> None:
        if replace:
            self.cv_runs.clear()
            self.eis_runs.clear()
            self.cp_runs.clear()
        for run in runs:
            if isinstance(run, CVRun):
                self.cv_runs.append(run)
            elif isinstance(run, EISRun):
                self.eis_runs.append(run)
            elif isinstance(run, CPRun):
                self.cp_runs.append(run)

    def remove_run(self, run_id: str) -> None:
        self.cv_runs = [run for run in self.cv_runs if run.run_id != run_id]
        self.eis_runs = [run for run in self.eis_runs if run.run_id != run_id]
        self.cp_runs = [run for run in self.cp_runs if run.run_id != run_id]

    def merge(self, other: "Dataset") -> None:
        self.cv_runs.extend(other.cv_runs)
        self.eis_runs.extend(other.eis_runs)
        self.cp_runs.extend(other.cp_runs)
        self.warnings.extend(other.warnings)

    def clear(self) -> None:
        self.cv_runs.clear()
        self.eis_runs.clear()
        self.cp_runs.clear()
        self.warnings.clear()

    def apply_params(self, params: ElectrodeParams, *, run_ids: Iterable[str] | None = None) -> None:
        selected = set(run_ids) if run_ids is not None else None
        for run in self.all_runs():
            if selected is None or run.run_id in selected:
                run.params = params.copy()
