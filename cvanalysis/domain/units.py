# -*- coding: utf-8 -*-
"""Unit scaling and normalization helpers.

All physical values are stored in SI units inside the application.  These
helpers only deal with presentation.  Keeping this logic in one place avoids
the historical problem where table and plot code produced different units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class UnitFamily:
    """A family of SI-prefixed units."""

    name: str
    units: tuple[tuple[str, float], ...]

    def choose(self, value: float | None) -> tuple[str, float]:
        """Return ``(unit_label, multiplier)`` for a value in base units."""
        if value is None or not np.isfinite(value):
            return self.units[0]
        magnitude = abs(float(value))
        if magnitude == 0:
            return self.units[0]
        for label, factor in self.units:
            if magnitude * factor >= 1.0:
                return label, factor
        return self.units[-1]


CAPACITANCE = UnitFamily(
    "capacitance",
    (("F", 1.0), ("mF", 1e3), ("µF", 1e6), ("nF", 1e9), ("pF", 1e12)),
)
CURRENT = UnitFamily(
    "current",
    (("A", 1.0), ("mA", 1e3), ("µA", 1e6), ("nA", 1e9), ("pA", 1e12)),
)
CURRENT_DENSITY = UnitFamily(
    "current_density",
    (("A/cm²", 1.0), ("mA/cm²", 1e3), ("µA/cm²", 1e6), ("nA/cm²", 1e9)),
)
SPECIFIC_CURRENT = UnitFamily(
    "specific_current",
    (("A/g", 1.0), ("mA/g", 1e3), ("µA/g", 1e6), ("nA/g", 1e9)),
)
CHARGE = UnitFamily(
    "charge",
    (("C", 1.0), ("mC", 1e3), ("µC", 1e6), ("nC", 1e9)),
)
CHARGE_DENSITY = UnitFamily(
    "charge_density",
    (("C/cm²", 1.0), ("mC/cm²", 1e3), ("µC/cm²", 1e6), ("nC/cm²", 1e9)),
)
SPECIFIC_CHARGE = UnitFamily(
    "specific_charge",
    (("C/g", 1.0), ("mC/g", 1e3), ("µC/g", 1e6), ("nC/g", 1e9)),
)
IMPEDANCE = UnitFamily(
    "impedance",
    (("MΩ", 1e-6), ("kΩ", 1e-3), ("Ω", 1.0), ("mΩ", 1e3)),
)
IMPEDANCE_AREA = UnitFamily(
    "impedance_area",
    (("MΩ·cm²", 1e-6), ("kΩ·cm²", 1e-3), ("Ω·cm²", 1.0), ("mΩ·cm²", 1e3)),
)
SPECIFIC_CAPACITANCE = UnitFamily(
    "specific_capacitance",
    (("F/g", 1.0), ("mF/g", 1e3), ("µF/g", 1e6), ("nF/g", 1e9)),
)
AREAL_CAPACITANCE = UnitFamily(
    "areal_capacitance",
    (("F/cm²", 1.0), ("mF/cm²", 1e3), ("µF/cm²", 1e6), ("nF/cm²", 1e9)),
)


def choose_unit(family: UnitFamily, value: float | None) -> tuple[str, float]:
    """Public wrapper for unit selection."""
    return family.choose(value)


def unit_labels(family: UnitFamily) -> list[str]:
    """Return the selectable labels for a unit family, largest first."""
    return [label for label, _ in family.units]


def unit_factor(family: UnitFamily, label: str | None) -> float | None:
    """Return the display multiplier for ``label``, or ``None`` if unknown."""
    if not label or label == "auto":
        return None
    for candidate, factor in family.units:
        if candidate == label:
            return factor
    return None


def resolve_unit(
    family: UnitFamily,
    values: Iterable[float] | None = None,
    override: str | None = None,
    *,
    use_max: bool = True,
) -> tuple[str, float]:
    """Resolve an automatic or user-selected display unit.

    Invalid or incompatible overrides deliberately fall back to the automatic
    choice so imported projects never break when normalization changes.
    """
    factor = unit_factor(family, override)
    if factor is not None and override is not None:
        return override, factor
    return choose_unit_for_values(family, values, use_max=use_max)


def choose_unit_for_values(
    family: UnitFamily,
    values: Iterable[float] | None,
    *,
    use_max: bool = True,
) -> tuple[str, float]:
    """Choose a unit from a collection of values.

    ``use_max`` is normally the right choice for axes.  For capacitance a
    representative (median) value can be nicer when a single cycle is much
    larger than the rest.
    """
    if values is None:
        return family.units[0]
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return family.units[0]
    representative = float(np.nanmax(np.abs(array)) if use_max else np.nanmedian(np.abs(array)))
    return family.choose(representative)


def scaled(value: float | None, family: UnitFamily) -> tuple[float | None, str, float]:
    """Scale one value and return ``(display_value, unit, multiplier)``."""
    unit, factor = family.choose(value)
    if value is None or not np.isfinite(value):
        return None, unit, factor
    return float(value) * factor, unit, factor


def current_family(normalization: str = "none") -> UnitFamily:
    if normalization == "area":
        return CURRENT_DENSITY
    if normalization == "mass":
        return SPECIFIC_CURRENT
    return CURRENT


def capacitance_family(normalization: str = "none") -> UnitFamily:
    if normalization == "area":
        return AREAL_CAPACITANCE
    if normalization == "mass":
        return SPECIFIC_CAPACITANCE
    return CAPACITANCE


def charge_family(normalization: str = "none") -> UnitFamily:
    if normalization == "area":
        return CHARGE_DENSITY
    if normalization == "mass":
        return SPECIFIC_CHARGE
    return CHARGE


def impedance_family(normalization: str = "none") -> UnitFamily:
    return IMPEDANCE_AREA if normalization == "area" else IMPEDANCE


def normalize_current(current: np.ndarray | float, normalization: str, *, area_cm2: float | None, mass_mg: float | None):
    """Return current normalized to area or mass when requested.

    Missing electrode parameters are treated as ``1.0`` so plots remain usable;
    callers should surface a warning in that case.
    """
    values = np.asarray(current, dtype=float)
    if normalization == "area" and area_cm2 and area_cm2 > 0:
        return values / float(area_cm2)
    if normalization == "mass" and mass_mg and mass_mg > 0:
        return values / (float(mass_mg) * 1e-3)
    return values


def normalize_capacitance(capacitance: float | None, normalization: str, *, area_cm2: float | None, mass_mg: float | None):
    if capacitance is None or not np.isfinite(capacitance):
        return None
    if normalization == "area" and area_cm2 and area_cm2 > 0:
        return capacitance / float(area_cm2)
    if normalization == "mass" and mass_mg and mass_mg > 0:
        return capacitance / (float(mass_mg) * 1e-3)
    return capacitance


def normalize_charge(charge: float | None, normalization: str, *, area_cm2: float | None, mass_mg: float | None):
    if charge is None or not np.isfinite(charge):
        return None
    if normalization == "area" and area_cm2 and area_cm2 > 0:
        return charge / float(area_cm2)
    if normalization == "mass" and mass_mg and mass_mg > 0:
        return charge / (float(mass_mg) * 1e-3)
    return charge


def normalize_impedance(value, normalization: str, *, area_cm2: float | None):
    if normalization == "area" and area_cm2 and area_cm2 > 0:
        return np.asarray(value, dtype=float) * float(area_cm2)
    return np.asarray(value, dtype=float)


def format_number(value: float | None, *, digits: int = 6, scientific: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    if scientific:
        return f"{value:.{digits}e}"
    return f"{value:.{digits}g}"


def format_with_unit(value: float | None, family: UnitFamily, *, digits: int = 4) -> str:
    display, unit, _ = scaled(value, family)
    if display is None:
        return "—"
    return f"{display:.{digits}g} {unit}"


def current_label(normalization: str = "none", family: UnitFamily | None = None) -> str:
    fam = family or current_family(normalization)
    if normalization == "area":
        return f"Current density ({fam.units[0][0]})"
    if normalization == "mass":
        return f"Specific current ({fam.units[0][0]})"
    return "Current (A)"


def capacitance_label(normalization: str = "none") -> str:
    if normalization == "area":
        return "Areal capacitance (F/cm²)"
    if normalization == "mass":
        return "Specific capacitance (F/g)"
    return "Capacitance (F)"
