# -*- coding: utf-8 -*-
"""v1-compatible CV analysis module.

The implementation now lives in :mod:`cvanalysis.compat.legacy_cv`.  Keep this
module so existing scripts and the v1 GUI continue to work unchanged.
"""

from __future__ import annotations

from cvanalysis.compat.legacy_cv import CVAnalyzer, main

__all__ = ["CVAnalyzer", "main"]


if __name__ == "__main__":
    main()
