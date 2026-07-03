"""
EIS分析模块
解析CHI660E电化学工作站导出的A.C. Impedance (EIS)数据
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class EISAnalyzer:
    """分析CHI660E电化学工作站导出的EIS数据"""

    def __init__(self):
        self.file_path = None
        self.metadata = {}
        self.eis_data = []  # list of dicts: {freq, z_real, z_imag, z_mag, phase}

    def read_file(self, file_path: str) -> bool:
        """
        读入EIS数据文件

        Args:
            file_path: 文件路径

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"错误：无法读取文件 {file_path}")
            print(f"详情：{e}")
            return False

        self.file_path = file_path

        # 检查是否为EIS实验
        if "A.C. Impedance" not in content:
            print("错误：文件不包含'A.C. Impedance'字样，可能不是EIS实验数据")
            return False

        # 解析元数据
        self._parse_metadata(content)

        # 解析EIS数据
        self._parse_eis_data(content)

        if not self.eis_data:
            print("错误：未找到EIS数据")
            return False

        return True

    def _parse_metadata(self, content: str) -> None:
        """从文件内容中提取元数据"""
        lines = content.split('\n')

        for line in lines[:30]:  # 元数据通常在前30行
            # 初始电压
            if 'Init E (V)' in line:
                match = re.search(r'Init E \(V\)\s*=\s*([-\d.eE+]+)', line)
                if match:
                    self.metadata['init_e'] = float(match.group(1))

            # 高频
            if 'High Frequency (Hz)' in line:
                match = re.search(r'High Frequency \(Hz\)\s*=\s*([\d.eE+]+)', line)
                if match:
                    self.metadata['high_freq'] = float(match.group(1))

            # 低频
            if 'Low Frequency (Hz)' in line:
                match = re.search(r'Low Frequency \(Hz\)\s*=\s*([\d.eE+]+)', line)
                if match:
                    self.metadata['low_freq'] = float(match.group(1))

            # 振幅
            if 'Amplitude (V)' in line:
                match = re.search(r'Amplitude \(V\)\s*=\s*([\d.eE+]+)', line)
                if match:
                    self.metadata['amplitude'] = float(match.group(1))

            # 静置时间
            if 'Quiet Time (sec)' in line:
                match = re.search(r'Quiet Time \(sec\)\s*=\s*([\d.eE+]+)', line)
                if match:
                    self.metadata['quiet_time'] = float(match.group(1))

    def _parse_eis_data(self, content: str) -> None:
        """从文件内容中提取EIS数据"""
        lines = content.split('\n')
        data_start_idx = -1

        for i, line in enumerate(lines):
            if 'Freq/Hz' in line and 'Z\'' in line:
                data_start_idx = i + 1
                break

        if data_start_idx == -1:
            return

        for line in lines[data_start_idx:]:
            line = line.strip()
            if not line:
                continue

            try:
                parts = line.split(',')
                if len(parts) >= 5:
                    freq = float(parts[0].strip())
                    z_real = float(parts[1].strip())
                    z_imag = float(parts[2].strip())
                    z_mag = float(parts[3].strip())
                    phase = float(parts[4].strip())

                    self.eis_data.append({
                        'freq': freq,
                        'z_real': z_real,
                        'z_imag': z_imag,
                        'z_mag': z_mag,
                        'phase': phase,
                    })
            except ValueError:
                pass

    def get_data_count(self) -> int:
        """获取数据点数量"""
        return len(self.eis_data)

    def get_freq_range(self) -> Optional[tuple]:
        """获取频率范围 (low, high)"""
        if not self.eis_data:
            return None
        freqs = [d['freq'] for d in self.eis_data]
        return (min(freqs), max(freqs))


def main():
    """主函数 — CLI入口"""
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python eis_analysis.py <EIS数据文件路径>")
        sys.exit(1)

    file_path = sys.argv[1]
    analyzer = EISAnalyzer()

    if not analyzer.read_file(file_path):
        sys.exit(1)

    print("=" * 60)
    print("EIS数据分析结果")
    print("=" * 60)
    print()
    print("实验参数：")
    for key, val in analyzer.metadata.items():
        print(f"  {key}: {val}")
    print()
    print(f"数据点数: {analyzer.get_data_count()}")
    freq_range = analyzer.get_freq_range()
    if freq_range:
        print(f"频率范围: {freq_range[0]:.3e} ~ {freq_range[1]:.3e} Hz")
    print()
    print("前5个数据点:")
    for d in analyzer.eis_data[:5]:
        print(f"  f={d['freq']:.3e} Hz, Z'={d['z_real']:.3e} Ω, Z\"={d['z_imag']:.3e} Ω, Phase={d['phase']:.1f}°")


if __name__ == "__main__":
    main()
