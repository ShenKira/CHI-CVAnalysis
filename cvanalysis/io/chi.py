# -*- coding: utf-8 -*-
"""CHI660E text format parsers.

The parser is intentionally forgiving: CHI can export comma, tab, space or
quoted-comma separated files, and real-world files occasionally contain a
stray non-numeric line.  Invalid data lines are skipped with a warning instead
of aborting the whole file.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from cvanalysis.domain.errors import ParseError
from cvanalysis.domain.models import (
    CPMetadata,
    CPRun,
    CVMetadata,
    CVRun,
    EISMetadata,
    EISRun,
    new_id,
)
from cvanalysis.io.base import (
    ParseResult,
    float_or_none,
    int_or_none,
    split_fields,
)

_CV_HEADER_RE = re.compile(
    r"Potential\s*/\s*V\s*,\s*Current\s*/\s*A", re.IGNORECASE
)
_EIS_HEADER_RE = re.compile(
    r"Freq\s*/\s*Hz.*Z\s*['\"]", re.IGNORECASE
)
_CP_HEADER_RE = re.compile(
    r"Time\s*/\s*s(?:ec)?\s*,\s*Potential\s*/\s*V", re.IGNORECASE
)
_HOLD_HEADER_RE = re.compile(
    r"Hold\s*Time\s*/\s*s(?:ec)?\s*,\s*Current\s*/\s*A", re.IGNORECASE
)
_METADATA_RE = re.compile(r"^\s*([^=]+?)\s*=\s*(.+?)\s*$")


def _parse_raw_metadata(lines: list[str], stop: int) -> dict[str, str]:
    raw: dict[str, str] = {}
    for line in lines[:stop]:
        match = _METADATA_RE.match(line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            if key and value:
                raw[key] = value
    return raw


def _raw_value(raw: dict[str, str], *keys: str) -> str | None:
    normalized = {key.lower().replace(" ", ""): value for key, value in raw.items()}
    for key in keys:
        needle = key.lower().replace(" ", "")
        for existing, value in normalized.items():
            if existing.startswith(needle):
                return value
    return None


def _raw_float(raw: dict[str, str], *keys: str) -> float | None:
    value = _raw_value(raw, *keys)
    return float_or_none(value) if value is not None else None


def _raw_int(raw: dict[str, str], *keys: str) -> int | None:
    value = _raw_value(raw, *keys)
    return int_or_none(value) if value is not None else None



class ChiCVParser:
    parser_id = "chi_cv"
    parser_version = 1

    def detect(self, text: str) -> bool:
        return "Cyclic Voltammetry" in text

    def parse(self, text: str, path: Path) -> ParseResult:
        lines = text.splitlines()
        header_index = -1
        for index, line in enumerate(lines):
            if _CV_HEADER_RE.search(line):
                header_index = index
                break
        if header_index < 0:
            raise ParseError(f"未找到 Potential/V, Current/A 数据表头: {path.name}")

        raw = _parse_raw_metadata(lines, header_index)
        metadata = CVMetadata(
            init_e=_raw_float(raw, "Init E (V)"),
            high_e=_raw_float(raw, "High E (V)"),
            low_e=_raw_float(raw, "Low E (V)"),
            scan_rate=_raw_float(raw, "Scan Rate (V/s)"),
            segment=_raw_int(raw, "Segment"),
            sample_interval=_raw_float(raw, "Sample Interval (V)"),
            sensitivity=_raw_float(raw, "Sensitivity (A/V)"),
            quiet_time=_raw_float(raw, "Quiet Time (sec)"),
            raw=raw,
        )

        potentials: list[float] = []
        currents: list[float] = []
        skipped = 0
        stopped_at_section = False
        for line in lines[header_index + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            probe = stripped.lstrip("\"'")
            if potentials and (
                probe.startswith(("Results", "Segment", "Channel"))
                or (
                    probe[:1].isalpha()
                    and ("/" in probe or "=" in probe)
                )
            ):
                # CHI files can contain a second block after the CV data
                # (time/current, another technique, metadata, ...).  Only the
                # leading Potential/Current block belongs to this run.
                stopped_at_section = True
                break
            if stripped.startswith("Potential") or "=" in stripped:
                continue
            fields = split_fields(stripped)
            if len(fields) < 2:
                skipped += 1
                continue
            potential = float_or_none(fields[0])
            current = float_or_none(fields[1])
            if potential is None or current is None:
                # Stray non-numeric lines inside the main block are skipped.
                skipped += 1
                continue
            potentials.append(potential)
            currents.append(current)

        if len(potentials) < 2:
            raise ParseError(f"CV 数据点不足: {path.name}")

        potential_array = np.asarray(potentials, dtype=float)
        current_array = np.asarray(currents, dtype=float)
        if not np.isfinite(potential_array).all() or not np.isfinite(current_array).all():
            raise ParseError(f"CV 数据包含无效数值: {path.name}")
        if float(np.nanmax(potential_array) - np.nanmin(potential_array)) <= 0:
            raise ParseError(f"CV 电位范围为零: {path.name}")

        warnings: list[str] = []
        if stopped_at_section:
            warnings.append("检测到 CV 数据后的附加区块，已忽略其内容")
        if skipped:
            warnings.append(f"跳过 {skipped} 行无法解析的数据")
        if metadata.scan_rate is None or metadata.scan_rate <= 0:
            warnings.append("缺少有效扫速，无法计算循环电容")
        if metadata.sensitivity is None:
            warnings.append("缺少灵敏度信息，电流溢出检查已跳过")
        if len(potential_array) < 20:
            warnings.append("数据点很少，循环分割和积分结果可能不可靠")

        run = CVRun(
            run_id=new_id("cv"),
            name=path.stem,
            source=path,
            potential=potential_array,
            current=current_array,
            metadata=metadata,
            warnings=warnings,
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )
        return ParseResult(runs=[run], warnings=warnings, parser_id=self.parser_id, parser_version=self.parser_version)


class ChiCPParser:
    """Parse CHI Chronopotentiometry exports.

    The main numeric block is ``Time/sec, Potential/V``.  CHI may append an
    optional ``Hold Time/sec, Current/A`` block containing the current recorded
    while the potential is held at the high/low limit.  That block is kept
    separately so the UI can choose whether to insert the hold plateaus into
    the potential-time curve.
    """

    parser_id = "chi_cp"
    parser_version = 1

    def detect(self, text: str) -> bool:
        return "Chronopotentiometry" in text or bool(_CP_HEADER_RE.search(text))

    def parse(self, text: str, path: Path) -> ParseResult:
        lines = text.splitlines()
        header_index = -1
        for index, line in enumerate(lines):
            if _CP_HEADER_RE.search(line):
                header_index = index
                break
        if header_index < 0:
            raise ParseError(f"未找到 Time/sec, Potential/V 数据表头: {path.name}")

        raw = _parse_raw_metadata(lines, header_index)
        metadata = CPMetadata(
            init_pn=_raw_value(raw, "Init P/N"),
            high_e=_raw_float(raw, "High E Limit (V)"),
            low_e=_raw_float(raw, "Low E Limit (V)"),
            high_hold_s=_raw_float(raw, "High E Hold Time (s)"),
            low_hold_s=_raw_float(raw, "Low E Hold Time (s)"),
            cathodic_current_A=_raw_float(raw, "Cathodic Current (A)"),
            anodic_current_A=_raw_float(raw, "Anodic Current (A)"),
            cathodic_time_s=_raw_float(raw, "Cathodic Time (s)"),
            anodic_time_s=_raw_float(raw, "Anodic Time (s)"),
            switch_polarity=_raw_value(raw, "Current Switching Polarity"),
            segment=_raw_int(raw, "Segment"),
            sample_interval_s=_raw_float(raw, "Data Storage Interval (s)"),
            raw=raw,
        )
        if metadata.init_pn:
            metadata.init_pn = metadata.init_pn.strip()

        times: list[float] = []
        potentials: list[float] = []
        hold_times: list[float] = []
        hold_currents: list[float] = []
        skipped = 0
        mode = "main"

        for line in lines[header_index + 1 :]:
            stripped = line.strip()
            if not stripped or "=" in stripped:
                continue
            if _HOLD_HEADER_RE.search(stripped):
                mode = "hold"
                continue
            if _CP_HEADER_RE.search(stripped):
                mode = "main"
                continue
            fields = split_fields(stripped)
            if len(fields) < 2:
                skipped += 1
                continue
            first = float_or_none(fields[0])
            second = float_or_none(fields[1])
            if first is None or second is None:
                # A non-numeric line is a new section header; ignore until a
                # recognized header appears so later blocks are not mixed in.
                if not stripped[0].lstrip("-+").isdigit():
                    mode = "other"
                skipped += 1
                continue
            if mode == "hold":
                hold_times.append(first)
                hold_currents.append(second)
            elif mode == "main":
                times.append(first)
                potentials.append(second)
            else:
                skipped += 1

        if len(times) < 3:
            raise ParseError(f"CP 数据点不足: {path.name}")
        time_array = np.asarray(times, dtype=float)
        potential_array = np.asarray(potentials, dtype=float)
        if not np.isfinite(time_array).all() or not np.isfinite(potential_array).all():
            raise ParseError(f"CP 数据包含无效数值: {path.name}")
        if float(np.nanmax(potential_array) - np.nanmin(potential_array)) <= 0:
            raise ParseError(f"CP 电位范围为 0: {path.name}")

        warnings: list[str] = []
        if np.any(np.diff(time_array) < 0):
            order = np.argsort(time_array, kind="stable")
            time_array = time_array[order]
            potential_array = potential_array[order]
            warnings.append("时间列不是单调递增，已按时间重新排序")
        if skipped:
            warnings.append(f"跳过 {skipped} 行无法解析的数据")
        if metadata.cathodic_current_A is None and metadata.anodic_current_A is None:
            warnings.append("缺少施加电流信息，GCD 容量分析可能不可用")
        if len(time_array) < 20:
            warnings.append("数据点较少，充放电分段和容量结果可能不可靠")

        hold_time_array = np.asarray(hold_times, dtype=float) if hold_times else None
        hold_current_array = np.asarray(hold_currents, dtype=float) if hold_currents else None
        if hold_time_array is not None and hold_current_array is not None:
            if hold_time_array.size != hold_current_array.size:
                warnings.append("保持段电流数据不完整，已忽略该块")
                hold_time_array = None
                hold_current_array = None
            elif not np.isfinite(hold_time_array).all() or not np.isfinite(hold_current_array).all():
                warnings.append("保持段电流包含无效数值，已忽略该块")
                hold_time_array = None
                hold_current_array = None
            elif hold_time_array.size < 2:
                hold_time_array = None
                hold_current_array = None

        run = CPRun(
            run_id=new_id("cp"),
            name=path.stem,
            source=path,
            time=time_array,
            potential=potential_array,
            hold_time=hold_time_array,
            hold_current=hold_current_array,
            metadata=metadata,
            warnings=warnings,
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )
        return ParseResult(runs=[run], warnings=warnings, parser_id=self.parser_id, parser_version=self.parser_version)


class ChiEISParser:
    parser_id = "chi_eis"
    parser_version = 1

    def detect(self, text: str) -> bool:
        return "A.C. Impedance" in text

    def parse(self, text: str, path: Path) -> ParseResult:
        lines = text.splitlines()
        header_index = -1
        for index, line in enumerate(lines):
            if _EIS_HEADER_RE.search(line):
                header_index = index
                break
        if header_index < 0:
            raise ParseError(f"未找到 EIS 数据表头: {path.name}")

        raw = _parse_raw_metadata(lines, header_index)
        metadata = EISMetadata(
            init_e=_raw_float(raw, "Init E (V)"),
            high_freq=_raw_float(raw, "High Frequency (Hz)"),
            low_freq=_raw_float(raw, "Low Frequency (Hz)"),
            amplitude=_raw_float(raw, "Amplitude (V)"),
            quiet_time=_raw_float(raw, "Quiet Time (sec)"),
            raw=raw,
        )

        freq: list[float] = []
        z_real: list[float] = []
        z_imag: list[float] = []
        z_mag: list[float] = []
        phase: list[float] = []
        skipped = 0

        for line in lines[header_index + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Freq") or "=" in stripped:
                continue
            fields = split_fields(stripped)
            if len(fields) < 3:
                skipped += 1
                continue
            f = float_or_none(fields[0])
            real = float_or_none(fields[1])
            imag = float_or_none(fields[2])
            if f is None or real is None or imag is None or f <= 0:
                skipped += 1
                continue
            magnitude = float_or_none(fields[3]) if len(fields) >= 4 else None
            phase_value = float_or_none(fields[4]) if len(fields) >= 5 else None
            if magnitude is None or magnitude <= 0:
                magnitude = float(np.hypot(real, imag))
            if phase_value is None:
                phase_value = float(np.degrees(np.arctan2(imag, real)))
            freq.append(f)
            z_real.append(real)
            z_imag.append(imag)
            z_mag.append(magnitude)
            phase.append(phase_value)

        if len(freq) < 3:
            raise ParseError(f"EIS 数据点不足: {path.name}")

        warnings: list[str] = []
        if skipped:
            warnings.append(f"跳过 {skipped} 行无法解析的数据")
        if metadata.high_freq is None:
            metadata.high_freq = float(max(freq))
        if metadata.low_freq is None:
            metadata.low_freq = float(min(freq))

        run = EISRun(
            run_id=new_id("eis"),
            name=path.stem,
            source=path,
            freq=np.asarray(freq, dtype=float),
            z_real=np.asarray(z_real, dtype=float),
            z_imag=np.asarray(z_imag, dtype=float),
            z_mag=np.asarray(z_mag, dtype=float),
            phase=np.asarray(phase, dtype=float),
            metadata=metadata,
            warnings=warnings,
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )
        return ParseResult(runs=[run], warnings=warnings, parser_id=self.parser_id, parser_version=self.parser_version)


