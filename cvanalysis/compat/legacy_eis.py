# -*- coding: utf-8 -*-
"""v1 ``EISAnalyzer`` compatibility adapter."""

from __future__ import annotations

from pathlib import Path

from cvanalysis.domain.models import EISRun
from cvanalysis.io.registry import parse_file


class EISAnalyzer:
    def __init__(self):
        self.file_path: str | None = None
        self.metadata: dict = {}
        self.eis_data: list[dict] = []
        self._run: EISRun | None = None

    def read_file(self, file_path: str) -> bool:
        try:
            result = parse_file(Path(file_path))
        except Exception as exc:
            print(f"错误：无法读取文件 {file_path}")
            print(f"详情：{exc}")
            return False
        run = next((item for item in result.runs if isinstance(item, EISRun)), None)
        if run is None:
            print("错误：文件不包含可用的 EIS 数据")
            return False
        self._run = run
        self.file_path = file_path
        metadata = run.metadata
        self.metadata = {
            key: value
            for key, value in {
                "init_e": metadata.init_e,
                "high_freq": metadata.high_freq,
                "low_freq": metadata.low_freq,
                "amplitude": metadata.amplitude,
                "quiet_time": metadata.quiet_time,
            }.items()
            if value is not None
        }
        self.eis_data = [
            {
                "freq": float(freq),
                "z_real": float(z_real),
                "z_imag": float(z_imag),
                "z_mag": float(z_mag),
                "phase": float(phase),
            }
            for freq, z_real, z_imag, z_mag, phase in zip(
                run.freq, run.z_real, run.z_imag, run.z_mag, run.phase
            )
        ]
        return True

    def get_data_count(self) -> int:
        return len(self.eis_data)

    def get_freq_range(self) -> tuple[float, float] | None:
        if not self.eis_data:
            return None
        frequencies = [item["freq"] for item in self.eis_data]
        return (min(frequencies), max(frequencies))


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python eis_analysis.py <EIS数据文件路径>")
        sys.exit(1)
    analyzer = EISAnalyzer()
    if not analyzer.read_file(sys.argv[1]):
        sys.exit(1)
    print(f"数据点数: {analyzer.get_data_count()}")
    frequency_range = analyzer.get_freq_range()
    if frequency_range:
        print(f"频率范围: {frequency_range[0]:.3e} ~ {frequency_range[1]:.3e} Hz")


if __name__ == "__main__":
    main()
