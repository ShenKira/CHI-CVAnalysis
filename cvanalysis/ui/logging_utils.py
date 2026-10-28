# -*- coding: utf-8 -*-
"""Logging handlers for the Qt UI and rotating file logs."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class QtLogEmitter(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, parent=None):
        super().__init__()
        self.emitter = QtLogEmitter(parent)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.emitter.message.emit(self.format(record))
        except Exception:
            pass


def configure_logging(log_path: Path) -> QtLogHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cvanalysis")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)
    qt_handler = QtLogHandler()
    logger.addHandler(qt_handler)
    return qt_handler
