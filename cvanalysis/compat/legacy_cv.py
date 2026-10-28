# -*- coding: utf-8 -*-
"""v1 ``CVAnalyzer`` compatibility adapter."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from cvanalysis.analysis.cv import analyze_cv_run

try:
    _trapz = np.trapezoid
except AttributeError:
    _trapz = np.trapz
from cvanalysis.domain.models import CVMetadata, CVRun
from cvanalysis.io.registry import parse_file


class CVAnalyzer:
    """Compatibility facade around the v2 CV parser and analysis engine."""

    def __init__(self, sensitivity_threshold_factor: int = 10, outlier_count: int = 1):
        self.sensitivity_threshold_factor = sensitivity_threshold_factor
        self.outlier_count = outlier_count
        self.file_path: str | None = None
        self.metadata: Dict[str, object] = {}
        self.voltage_current_data: List[Tuple[float, float]] = []
        self.is_cv = False
        self._run: CVRun | None = None
        self._calc_cursor = 0

    def read_file(self, file_path: str) -> bool:
        try:
            result = parse_file(Path(file_path))
        except Exception as exc:
            print(f"错误：无法读取文件 {file_path}")
            print(f"详情：{exc}")
            return False
        run = next((item for item in result.runs if isinstance(item, CVRun)), None)
        if run is None:
            print("错误：文件不包含可用的 CV 数据")
            return False
        self._run = run
        self.file_path = file_path
        self.is_cv = True
        metadata = run.metadata
        self.metadata = {
            key: value
            for key, value in {
                "init_e": metadata.init_e,
                "high_e": metadata.high_e,
                "low_e": metadata.low_e,
                "scan_rate": metadata.scan_rate,
                "segment": metadata.segment,
                "sample_interval": metadata.sample_interval,
                "sensitivity": metadata.sensitivity,
                "quiet_time": metadata.quiet_time,
            }.items()
            if value is not None
        }
        self.voltage_current_data = list(zip(run.potential.tolist(), run.current.tolist()))
        return True

    def analyze(self) -> bool:
        if self._run is None:
            print("错误：没有可用的数据")
            return False
        summary = analyze_cv_run(
            self._run,
            sensitivity_factor=self.sensitivity_threshold_factor,
            outlier_count=self.outlier_count,
            segmentation="legacy",
        )
        print("=" * 70)
        print("CV数据分析结果")
        print("=" * 70)
        if summary.total_cycles == 0:
            print("错误：无法分割循环数据")
            return False
        print(f"识别到 {summary.total_cycles} 轮循环")
        print(f"有效循环数: {summary.valid_cycles}")
        if summary.mean_capacitance_F:
            print(
                f"平均电容值: {summary.mean_capacitance_F:.6e} F = "
                f"{summary.mean_capacitance_F * 1000:.6f} mF"
            )
        if summary.sd_capacitance_F:
            print(
                f"标准偏差: {summary.sd_capacitance_F:.6e} F = "
                f"{summary.sd_capacitance_F * 1000:.6f} mF"
            )
        if summary.cv_percent is not None:
            print(f"变异系数: {summary.cv_percent:.2f}%")
        print("=" * 70)
        return True

    def _split_into_cycles(self) -> List[List[Tuple[float, float]]]:
        if self._run is None:
            return []
        if not self._run.cycles:
            analyze_cv_run(
                self._run,
                sensitivity_factor=self.sensitivity_threshold_factor,
                outlier_count=self.outlier_count,
                segmentation="legacy",
            )
        self._calc_cursor = 0
        return [
            list(zip(cycle.potential.tolist(), cycle.current.tolist()))
            for cycle in self._run.cycles
        ]

    def _calculate_cycle_capacitance(self, cycle_num: int, cycle_data) -> Optional[Dict]:
        if self._run is None:
            return None
        if not self._run.cycles:
            analyze_cv_run(
                self._run,
                sensitivity_factor=self.sensitivity_threshold_factor,
                outlier_count=self.outlier_count,
                segmentation="legacy",
            )
        cycle = next((item for item in self._run.cycles if item.index == cycle_num), None)
        if cycle is not None:
            self._calc_cursor = max(self._calc_cursor, cycle.index)
        elif self._calc_cursor < len(self._run.cycles):
            cycle = self._run.cycles[self._calc_cursor]
            self._calc_cursor += 1
        if cycle is None:
            return None
        return {
            "cycle_num": cycle_num,
            "area": cycle.area_C,
            "capacitance": cycle.capacitance_F,
            "is_outlier": cycle.is_outlier,
            "outlier_reason": cycle.outlier_reason,
            "warning": cycle.warning,
        }

    def _get_valid_capacitances(self, cycle_results: List[Dict] | None = None) -> List[float]:
        if cycle_results:
            return [
                float(result["capacitance"])
                for result in cycle_results
                if not result.get("is_outlier", False)
                and result.get("capacitance") is not None
                and np.isfinite(result["capacitance"])
                and result["capacitance"] > 0
            ]
        if self._run is None:
            return []
        return [cycle.capacitance_F for cycle in self._run.cycles if cycle.valid]

    def _calculate_robust_average(self, values: List[float]) -> float:
        clean = [value for value in values if value is not None and np.isfinite(value)]
        if not clean:
            return float("nan")
        if len(clean) <= self.outlier_count:
            return float(statistics.mean(clean))
        mean = statistics.mean(clean)
        stdev = statistics.stdev(clean) if len(clean) > 1 else 0
        if stdev == 0:
            return mean
        z_scores = sorted(((abs(value - mean) / stdev, value) for value in clean), reverse=True)
        remaining = [value for _, value in z_scores[self.outlier_count :]]
        return float(statistics.mean(remaining)) if remaining else mean

    def _get_outlier_cycles(self, cycle_results: List[Dict] | None = None) -> List[int]:
        if cycle_results:
            valid = [
                result
                for result in cycle_results
                if not result.get("is_outlier", False)
                and result.get("capacitance") is not None
                and np.isfinite(result["capacitance"])
                and result["capacitance"] > 0
            ]
            if len(valid) <= self.outlier_count:
                return []
            values = [float(result["capacitance"]) for result in valid]
            mean = float(np.mean(values))
            sd = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
            if sd == 0:
                return []
            scored = sorted(
                ((abs(value - mean) / sd, result["cycle_num"]) for value, result in zip(values, valid)),
                reverse=True,
            )
            return sorted(int(cycle_num) for _, cycle_num in scored[: self.outlier_count])
        if self._run is not None and self._run.summary is not None:
            return list(self._run.summary.outlier_cycles)
        return []

    def _split_forward_reverse(self, cycle_data):
        data = np.asarray(cycle_data, dtype=float)
        if data.ndim != 2 or len(data) < 2:
            return [], []
        max_index = int(np.argmax(data[:, 0]))
        return data[: max_index + 1].tolist(), data[max_index:].tolist()

    def _calculate_area(self, forward_scan, reverse_scan) -> float:
        forward = np.asarray(forward_scan, dtype=float)
        reverse = np.asarray(reverse_scan, dtype=float)
        if len(forward) < 2 or len(reverse) < 2:
            return 0.0
        low = max(forward[:, 0].min(), reverse[:, 0].min())
        high = min(forward[:, 0].max(), reverse[:, 0].max())
        if high <= low:
            return 0.0
        grid = np.linspace(low, high, max(60, len(forward)))
        i_forward = np.interp(grid, forward[:, 0], forward[:, 1])
        i_reverse = np.interp(grid, reverse[:, 0], reverse[:, 1])
        return float(abs(_trapz(i_forward - i_reverse, grid)))


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python cv_analysis.py <数据文件路径>")
        sys.exit(1)
    analyzer = CVAnalyzer()
    if not analyzer.read_file(sys.argv[1]):
        sys.exit(1)
    if not analyzer.analyze():
        sys.exit(1)


if __name__ == "__main__":
    main()
