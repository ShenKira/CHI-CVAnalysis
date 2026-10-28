# -*- coding: utf-8 -*-
"""Parser registry and batch file loading."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from cvanalysis.domain.models import Dataset
from cvanalysis.io.base import DataParser, ParseIssue, ParseResult, read_text_file
from cvanalysis.io.chi import ChiCPParser, ChiCVParser, ChiEISParser


DEFAULT_PARSERS: tuple[DataParser, ...] = (ChiCVParser(), ChiEISParser(), ChiCPParser())


def available_parsers() -> list[DataParser]:
    return list(DEFAULT_PARSERS)


def detect_parser(text: str, parsers: Iterable[DataParser] | None = None) -> DataParser | None:
    for parser in parsers or DEFAULT_PARSERS:
        if parser.detect(text):
            return parser
    return None


def parse_file(path: str | Path, parsers: Iterable[DataParser] | None = None) -> ParseResult:
    file_path = Path(path)
    text = read_text_file(file_path)
    parser = detect_parser(text, parsers)
    if parser is None:
        raise ValueError(
            "无法识别文件类型，文件需包含 'Cyclic Voltammetry'、'A.C. Impedance' "
            "或 'Chronopotentiometry' 标记"
        )
    result = parser.parse(text, file_path)
    for run in result.runs:
        run.name = run.name or file_path.stem
    return result


def load_files(paths: Iterable[str | Path], parsers: Iterable[DataParser] | None = None, *, cancelled=None) -> tuple[Dataset, list[ParseIssue]]:
    """Load a batch of files and return a dataset plus per-file issues.

    A bad file never aborts the batch.  Multiple runs in one file are kept and
    numbered so that the UI can present them individually.
    """
    dataset = Dataset()
    issues: list[ParseIssue] = []
    for raw_path in paths:
        if cancelled and cancelled():
            break
        path = Path(raw_path)
        try:
            result = parse_file(path, parsers)
            if not result.runs:
                issues.append(ParseIssue(path, "文件中没有可用的数据"))
                continue
            for index, run in enumerate(result.runs):
                run.run_index = index
                if len(result.runs) > 1:
                    run.name = f"{path.stem} #{index + 1}"
            dataset.add_runs(result.runs)
            dataset.warnings.extend(result.warnings)
        except Exception as exc:  # noqa: BLE001 - report per-file failures to the UI
            issues.append(ParseIssue(path, str(exc)))
    return dataset, issues
