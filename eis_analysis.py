# -*- coding: utf-8 -*-
"""v1-compatible EIS analysis module."""

from __future__ import annotations

from cvanalysis.compat.legacy_eis import EISAnalyzer, main

__all__ = ["EISAnalyzer", "main"]


if __name__ == "__main__":
    main()
