#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CVAnalysis v2 entry point."""

from __future__ import annotations

import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _startup_log_path() -> Path:
    """Return a writable diagnostic log path, even in windowed builds."""
    candidates: list[Path] = []
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        candidates.append(Path(base) / "CVAnalysis" / "logs")
    candidates.append(Path(tempfile.gettempdir()))
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".cvanalysis_startup_probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return directory / "startup_error.log"
        except Exception:
            continue
    return Path(tempfile.gettempdir()) / "cvanalysis_startup_error.log"


_STARTUP_LOG = _startup_log_path()
try:
    _CRASH_STREAM = _STARTUP_LOG.open("a", encoding="utf-8")
    faulthandler.enable(_CRASH_STREAM)
except Exception:
    _CRASH_STREAM = None


def _append_startup_log(details: str) -> None:
    try:
        with _STARTUP_LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n")
            stream.write(details)
            stream.write("\n")
    except Exception:
        pass


def _native_message(title: str, text: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:
        pass


def _report_startup_failure(details: str) -> None:
    _append_startup_log(details)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "CVAnalysis 启动失败",
            f"{details}\n\n日志: {_STARTUP_LOG}",
        )
        return
    except Exception:
        pass
    _native_message(
        "CVAnalysis 启动失败",
        f"{details}\n\n日志: {_STARTUP_LOG}",
    )
    if sys.stderr is not None:
        try:
            sys.stderr.write(details + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def main() -> None:
    try:
        from cvanalysis.ui.app import run

        raise SystemExit(run())
    except SystemExit:
        raise
    except Exception:
        _report_startup_failure(traceback.format_exc())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
