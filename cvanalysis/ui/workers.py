# -*- coding: utf-8 -*-
"""Background workers for file import."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from cvanalysis.io.registry import load_files
from cvanalysis.services.dataset_service import refresh_analysis, AnalysisSettings


class ImportThread(QThread):
    completed = Signal(object, object)  # Dataset, list[ParseIssue]
    failed = Signal(str)

    def __init__(self, paths: list[str | Path], parent=None, settings=None):
        super().__init__(parent)
        self.paths = [Path(path) for path in paths]
        self.settings = settings or AnalysisSettings()

    def run(self) -> None:
        try:
            dataset, issues = load_files(self.paths, cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                dataset.warnings.extend(refresh_analysis(dataset, self.settings))
            if not self.isInterruptionRequested():
                self.completed.emit(dataset, issues)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TaskThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        try:
            result = self.task()
            if not self.isInterruptionRequested():
                self.completed.emit(result)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
