# -*- coding: utf-8 -*-
from pathlib import Path

import numpy as np

from cvanalysis.io.registry import load_files, parse_file


def test_cv_parser_and_metadata(cv_file_factory):
    path = cv_file_factory("cv.txt", scan_rate=0.1, capacitance=1e-4)
    result = parse_file(path)
    run = result.runs[0]
    assert run.metadata.scan_rate == 0.1
    assert run.metadata.segment == 4
    assert len(run.potential) > 100
    assert np.isclose(float(np.max(run.potential)), 1.0)


def test_tab_and_space_delimited_cv(tmp_path, cv_text_factory):
    text = cv_text_factory(scan_rate=0.1)
    comma_lines = text.splitlines()
    header_index = next(i for i, line in enumerate(comma_lines) if line.startswith("Potential"))
    prefix = comma_lines[: header_index + 1]
    data = [line.split(",") for line in comma_lines[header_index + 1 :]]
    tab_path = tmp_path / "tab.txt"
    tab_path.write_text("\n".join(prefix + ["\t".join(part) for part in data]) + "\n", encoding="utf-8")
    space_path = tmp_path / "space.txt"
    space_path.write_text("\n".join(prefix + [" ".join(part) for part in data]) + "\n", encoding="utf-8")

    for path in (tab_path, space_path):
        result = parse_file(path)
        run = result.runs[0]
        assert len(run.potential) > 100
        assert np.isclose(float(np.max(run.potential)), 1.0)


def test_cv_parser_ignores_following_numeric_block(tmp_path, cv_text_factory):
    text = cv_text_factory(scan_rate=0.1)
    lines = text.splitlines()
    header = next(index for index, line in enumerate(lines) if line.startswith("Potential"))
    data_lines = [line for line in lines[header + 1 :] if line.strip()]
    path = tmp_path / "trailing_block.txt"
    path.write_text(
        text
        + "\nTime/sec, Current/A\n"
        + "0.000, 1.000e-3\n"
        + "1.000, 2.000e-3\n",
        encoding="utf-8",
    )
    run = parse_file(path).runs[0]
    assert len(run.potential) == len(data_lines)
    assert any("附加区块" in warning for warning in run.warnings)


def test_cv_parser_skips_stray_line_inside_main_block(tmp_path, cv_text_factory):
    text = cv_text_factory(scan_rate=0.1)
    lines = text.splitlines()
    header = next(index for index, line in enumerate(lines) if line.startswith("Potential"))
    data_lines = [line for line in lines[header + 1 :] if line.strip()]
    inserted = [*lines[: header + 1], *data_lines[:10], "not a data row", *data_lines[10:]]
    path = tmp_path / "stray_line.txt"
    path.write_text("\n".join(inserted) + "\n", encoding="utf-8")
    run = parse_file(path).runs[0]
    assert len(run.potential) == len(data_lines)
    assert any("跳过 1 行" in warning for warning in run.warnings)


def test_quoted_comma_cv(tmp_path, cv_text_factory):
    text = cv_text_factory(scan_rate=0.1)
    lines = text.splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("Potential"))
    prefix = lines[: header_index + 1]
    data = [f'"{line}"' for line in lines[header_index + 1 :]]
    path = tmp_path / "quoted.txt"
    path.write_text("\n".join(prefix + data) + "\n", encoding="utf-8")
    run = parse_file(path).runs[0]
    assert len(run.potential) > 100


def test_eis_parser_sample():
    path = Path(__file__).parent / "fixtures" / "test_EIS.txt"
    result = parse_file(path)
    run = result.runs[0]
    assert len(run.freq) == 97
    assert run.metadata.high_freq == 1_000_000.0
    assert run.metadata.low_freq == 0.01
    assert np.all(run.freq > 0)


def test_batch_load_keeps_going_after_bad_file(tmp_path, cv_file_factory):
    good = cv_file_factory("good.txt", scan_rate=0.1)
    bad = tmp_path / "bad.txt"
    bad.write_text("not a data file", encoding="utf-8")
    dataset, issues = load_files([good, bad])
    assert len(dataset.cv_runs) == 1
    assert len(issues) == 1
    assert issues[0].path == bad


def test_legacy_cv_analyzer_adapter(cv_file_factory):
    from cv_analysis import CVAnalyzer

    path = cv_file_factory("legacy.txt", scan_rate=0.1)
    analyzer = CVAnalyzer()
    assert analyzer.read_file(str(path))
    assert "scan_rate" in analyzer.metadata
    assert len(analyzer.voltage_current_data) > 100
    cycles = analyzer._split_into_cycles()
    assert len(cycles) == 2
    result = analyzer._calculate_cycle_capacitance(1, cycles[0])
    assert result["cycle_num"] == 1
    assert result["capacitance"] > 0
    assert analyzer._get_valid_capacitances()


def test_legacy_eis_analyzer_adapter():
    from eis_analysis import EISAnalyzer

    path = Path(__file__).parent / "fixtures" / "test_EIS.txt"
    analyzer = EISAnalyzer()
    assert analyzer.read_file(str(path))
    assert analyzer.get_data_count() == 97
    low, high = analyzer.get_freq_range()
    assert low == 0.01 and high == 999000.0
