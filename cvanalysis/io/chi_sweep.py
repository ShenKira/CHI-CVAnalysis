"""CHI LSV and amperometric i-t data readers and parser adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from cvanalysis.domain.errors import ParseError
from cvanalysis.io.base import float_or_none, split_fields
from cvanalysis.io.chi import _parse_raw_metadata
from cvanalysis.io.base import ParseResult
from cvanalysis.domain.models import SweepMetadata, SweepRun, new_id


@dataclass
class CHISweepData:
    technique: str
    source: Path
    x: np.ndarray
    current: np.ndarray
    metadata: dict[str, str]
    x_unit: str
    warnings: list[str]


class _ChiSweepReader:
    technique = ""
    header = None
    x_unit = ""

    def detect(self, text: str) -> bool:
        return self.technique.casefold() in text.casefold()

    def parse(self, text: str, path: Path) -> CHISweepData:
        if not self.detect(text):
            raise ParseError(f"文件类型不是 {self.technique}: {path.name}")
        lines = text.splitlines()
        index = next((i for i, line in enumerate(lines) if self.header.search(line)), None)
        if index is None:
            raise ParseError(f"未找到 {self.technique} 数据表头: {path.name}")
        xs, currents = [], []
        skipped = 0
        for line in lines[index + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            fields = split_fields(stripped)
            x = float_or_none(fields[0]) if fields else None
            current = float_or_none(fields[1]) if len(fields) > 1 else None
            if x is None or current is None:
                if xs and ("/" in stripped or "=" in stripped):
                    break
                skipped += 1
                continue
            xs.append(x)
            currents.append(current)
        if len(xs) < 2:
            raise ParseError(f"{self.technique} 数据点不足: {path.name}")
        x = np.asarray(xs, dtype=float)
        current = np.asarray(currents, dtype=float)
        if not np.isfinite(x).all() or not np.isfinite(current).all():
            raise ParseError(f"{self.technique} 数据包含无效数值: {path.name}")
        warnings = [f"跳过 {skipped} 行无法解析的数据"] if skipped else []
        return CHISweepData(self.technique, Path(path), x, current,
                            _parse_raw_metadata(lines, index), self.x_unit, warnings)


class ChiLSVReader(_ChiSweepReader):
    technique = "Linear Sweep Voltammetry"
    header = re.compile(r"Potential\s*/\s*V\s*,\s*Current\s*/\s*A", re.IGNORECASE)
    x_unit = "V"


class ChiITReader(_ChiSweepReader):
    technique = "Amperometric i-t Curve"
    header = re.compile(r"Time\s*/\s*s(?:ec)?\s*,\s*Current\s*/\s*A", re.IGNORECASE)
    x_unit = "s"


class _ChiSweepParser:
    parser_version = 1
    reader_class = None
    kind = ""

    @property
    def parser_id(self):
        return "chi_" + self.kind

    def detect(self, text):
        return self.reader_class().detect(text)

    def parse(self, text, path):
        data = self.reader_class().parse(text, path)
        run = SweepRun(new_id(self.kind), path.stem, self.kind, data.x, data.current,
                       SweepMetadata(data.technique, data.metadata), source=path,
                       warnings=list(data.warnings), parser_id=self.parser_id)
        return ParseResult(runs=[run], warnings=data.warnings, parser_id=self.parser_id)


class ChiLSVParser(_ChiSweepParser):
    reader_class = ChiLSVReader
    kind = "lsv"


class ChiITParser(_ChiSweepParser):
    reader_class = ChiITReader
    kind = "it"
