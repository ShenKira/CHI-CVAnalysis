# -*- coding: utf-8 -*-
"""Application-specific exception types."""

from __future__ import annotations


class CVAnalysisError(Exception):
    """Base class for expected application errors."""


class ParseError(CVAnalysisError):
    """Raised when a data file cannot be parsed."""


class AnalysisError(CVAnalysisError):
    """Raised when an analysis cannot be completed."""


class FitError(CVAnalysisError):
    """Raised when a numerical fit fails."""
