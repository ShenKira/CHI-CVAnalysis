# -*- coding: utf-8 -*-
"""Parser interfaces and shared text-reading utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from cvanalysis.domain.errors import ParseError
from cvanalysis.domain.models import CVRun, EISRun


@dataclass
class ParseIssue:
    path: Path
    message: str


@dataclass
class ParseResult:
    runs: list[CVRun | EISRun] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parser_id: str = ""
    parser_version: int = 1


class DataParser(Protocol):
    parser_id: str
    parser_version: int

    def detect(self, text: str) -> bool: ...

    def parse(self, text: str, path: Path) -> ParseResult: ...


_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp1252", "latin-1")


def read_text_file(path: Path) -> str:
    """Read a CHI text export, trying common encodings.

    CHI files are usually ASCII/UTF-8, but exports edited on Chinese Windows
    can be GBK-encoded.  We deliberately avoid a hard dependency on chardet.
    """
    raw = path.read_bytes()
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError(f"无法识别文件编码: {path}")


def split_fields(line: str) -> list[str]:
    """Split a data line by comma, tab or whitespace (in that order)."""
    text = line.strip().strip('"').strip("'").strip()
    if not text:
        return []
    if "," in text:
        return [part.strip().strip('"').strip("'") for part in text.split(",")]
    if "\t" in text:
        return [part.strip() for part in text.split("\t")]
    return text.split()


def float_or_none(text: str) -> float | None:
    try:
        return float(text.strip())
    except (TypeError, ValueError):
        return None


def int_or_none(text: str) -> int | None:
    try:
        return int(float(text.strip()))
    except (TypeError, ValueError):
        return None
