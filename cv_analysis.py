import re
import statistics
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class CVAnalyzer:
    """分析CHI660E电化学工作站导出的循环伏安数据"""
    
    def __init__(self, sensitivity_threshold_factor: int = 10, outlier_count: int = 1):
        """
        初始化分析器
        
        Args:
            sensitivity_threshold_factor: 电流超出多少倍灵敏度时发出警告（默认10倍）
            outlier_count: 排除最离群值时的个数（默认1个）
        """
        self.sensitivity_threshold_factor = sensitivity_threshold_factor
        self.outlier_count = outlier_count
        self.file_path = None
        self.metadata = {}
        self.voltage_current_data = []
        self.is_cv = False
        
    def read_file(self, file_path: str) -> bool:
        """
        读入数据文件
        
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
        
        # 检查是否为CV实验
        if "Cyclic Voltammetry" not in content:
            print("错误：文件不包含'Cyclic Voltammetry'字样，可能不是CV实验数据")
            return False
        
        self.is_cv = True
        
        # 解析元数据
        self._parse_metadata(content)
        
        # 解析电压-电流数据
        self._parse_voltage_current_data(content)
        
        if not self.voltage_current_data:
            print("错误：未找到电压-电流数据")
            return False
        
        return True
    
    def _parse_metadata(self, content: str) -> None:
        """从文件内容中提取元数据"""
        lines = content.split('\n')
        
        for line in lines[:50]:  # 元数据通常在前50行
            # 解析初始电压
            if 'Init E (V)' in line:
                match = re.search(r'Init E \(V\)\s*=\s*([-\d.]+)', line)
                if match:
                    self.metadata['init_e'] = float(match.group(1))
            
            # 解析最高电压
            if 'High E (V)' in line:
                match = re.search(r'High E \(V\)\s*=\s*([-\d.]+)', line)
                if match:
                    self.metadata['high_e'] = float(match.group(1))
            
            # 解析最低电压
            if 'Low E (V)' in line:
                match = re.search(r'Low E \(V\)\s*=\s*([-\d.]+)', line)
                if match:
                    self.metadata['low_e'] = float(match.group(1))
            
            # 解析扫速
            if 'Scan Rate (V/s)' in line:
                match = re.search(r'Scan Rate \(V/s\)\s*=\s*([\d.e-]+)', line)
                if match:
                    self.metadata['scan_rate'] = float(match.group(1))
            
            # 解析段数
            if 'Segment' in line and '=' in line:
                match = re.search(r'Segment\s*=\s*(\d+)', line)
                if match:
                    self.metadata['segment'] = int(match.group(1))
            
            # 解析采样间隔
            if 'Sample Interval (V)' in line:
                match = re.search(r'Sample Interval \(V\)\s*=\s*([\d.e-]+)', line)
                if match:
                    self.metadata['sample_interval'] = float(match.group(1))
            
            # 解析灵敏度
            if 'Sensitivity (A/V)' in line:
                match = re.search(r'Sensitivity \(A/V\)\s*=\s*([\d.e-]+)', line)
                if match:
                    self.metadata['sensitivity'] = float(match.group(1))
    
    def _parse_voltage_current_data(self, content: str) -> None:
        """从文件内容中提取电压-电流数据"""
        # 找到数据开始行 "Potential/V, Current/A"
        lines = content.split('\n')
        data_start_idx = -1
        
        for i, line in enumerate(lines):
            if 'Potential/V, Current/A' in line:
                data_start_idx = i + 1
                break
        
        if data_start_idx == -1:
            return
        
        # 提取数据行
        for line in lines[data_start_idx:]:
            line = line.strip()
            if not line:
                continue
            
            # 尝试解析电压-电流对
            try:
                parts = line.split(',')
                if len(parts) == 2:
                    voltage = float(parts[0].strip())
                    current = float(parts[1].strip())
                    self.voltage_current_data.append((voltage, current))
            except ValueError:
                # 跳过无法解析的行
                pass
    
    def analyze(self) -> bool:
        """执行分析"""
        if not self.is_cv:
            print("错误：未识别为CV实验")
            return False
        
        if not self.voltage_current_data:
            print("错误：没有可用的数据")
            return False
        
        print("="*70)
        print("CV数据分析结果")
        print("="*70)
        print()
        
        # 打印元数据
        self._print_metadata()
        print()
        
        # 分割数据为多个循环
        cycles = self._split_into_cycles()
        
        if not cycles:
            print("错误：无法分割循环数据")
            return False
        
        print(f"识别到 {len(cycles)} 轮循环")
        print()
        
        # 计算每个循环的电容
        capacitances = []
        cycle_results = []
        
        for cycle_num, cycle_data in enumerate(cycles, 1):
            result = self._calculate_cycle_capacitance(cycle_num, cycle_data)
            if result is not None:
                capacitances.append(result['capacitance'])
                cycle_results.append(result)
        
        # 打印每个循环的结果
        print("各循环的计算结果：")
        print("-"*70)
        for result in cycle_results:
            print(f"循环 {result['cycle_num']}:")
            print(f"  面积 (Area): {result['area']:.6e} C")
            print(f"  电容 (Capacitance): {result['capacitance']:.6e} F = {result['capacitance']*1000:.6f} mF")
            if result['warning']:
                print(f"  警告: {result['warning']}")
            print()
        
        if not capacitances:
            print("错误：所有循环都因超出灵敏度范围被忽略")
            return False
        
        # 计算平均值（排除最离群值）
        avg_capacitance = self._calculate_robust_average(capacitances)
        
        print("="*70)
        print("最终结果：")
        print("-"*70)
        print(f"有效循环数: {len(capacitances)}")
        print(f"被排除的离群值个数: {self.outlier_count}")
        if len(capacitances) > 1:
            print(f"平均电容值: {avg_capacitance:.6e} F = {avg_capacitance*1000:.6f} mF")
            print(f"最小值: {min(capacitances):.6e} F = {min(capacitances)*1000:.6f} mF")
            print(f"最大值: {max(capacitances):.6e} F = {max(capacitances)*1000:.6f} mF")
            std_dev = statistics.stdev(capacitances) if len(capacitances) > 1 else 0
            print(f"标准偏差: {std_dev:.6e} F = {std_dev*1000:.6f} mF")
            print(f"变异系数: {(std_dev/avg_capacitance)*100:.2f}%")
        else:
            print(f"电容值: {capacitances[0]:.6e} F = {capacitances[0]*1000:.6f} mF")
        print("="*70)
        
        return True
    
    def _print_metadata(self) -> None:
        """打印元数据"""
        print("实验参数：")
        if 'init_e' in self.metadata:
            print(f"  初始电压 (Init E): {self.metadata['init_e']} V")
        if 'high_e' in self.metadata:
            print(f"  最高电压 (High E): {self.metadata['high_e']} V")
        if 'low_e' in self.metadata:
            print(f"  最低电压 (Low E): {self.metadata['low_e']} V")
        if 'scan_rate' in self.metadata:
            print(f"  扫描速率 (Scan Rate): {self.metadata['scan_rate']} V/s")
        if 'segment' in self.metadata:
            print(f"  段数 (Segment): {self.metadata['segment']} (循环数: {self.metadata['segment']//2})")
        if 'sample_interval' in self.metadata:
            print(f"  采样间隔 (Sample Interval): {self.metadata['sample_interval']} V")
        if 'sensitivity' in self.metadata:
            print(f"  灵敏度 (Sensitivity): {self.metadata['sensitivity']:.0e} A/V")
    
    def _split_into_cycles(self) -> List[List[Tuple[float, float]]]:
        """
        将数据分割为多个循环
        基于电压方向的变化来识别循环边界
        
        Returns:
            每个循环的[(voltage, current)]列表
        """
        if len(self.voltage_current_data) < 2:
            return []
        
        cycles = []
        current_cycle = []
        
        # 根据Segment数计算预期循环数
        segment = self.metadata.get('segment', 10)
        expected_cycles = segment // 2
        
        # 识别电压方向的变化
        # 通过检查相邻数据点之间的电压趋势
        direction_changes = [0]  # 第一个点的方向为正（向上）
        
        for i in range(1, len(self.voltage_current_data)):
            curr_v = self.voltage_current_data[i][0]
            prev_v = self.voltage_current_data[i-1][0]
            
            if curr_v > prev_v:
                direction_changes.append(1)  # 向上
            elif curr_v < prev_v:
                direction_changes.append(-1)  # 向下
            else:
                direction_changes.append(direction_changes[-1])  # 保持前一方向
        
        # 找到方向变化的点
        direction_change_indices = [0]
        for i in range(1, len(direction_changes)):
            if direction_changes[i] != direction_changes[i-1] and direction_changes[i] != 0 and direction_changes[i-1] != 0:
                direction_change_indices.append(i)
        
        # 根据方向变化分割循环
        cycle_boundaries = [0]
        for idx in direction_change_indices[1:]:
            if len(cycle_boundaries) < segment:
                cycle_boundaries.append(idx)
        cycle_boundaries.append(len(self.voltage_current_data))
        
        # 从边界创建循环
        for i in range(len(cycle_boundaries) - 1):
            start_idx = cycle_boundaries[i]
            end_idx = cycle_boundaries[i + 1]
            
            cycle_data = self.voltage_current_data[start_idx:end_idx]
            if len(cycle_data) >= 2:
                cycles.append(cycle_data)
        
        # 如果循环数与期望不符，尝试配对方向扫
        if len(cycles) > expected_cycles:
            # 将相邻的两个方向扫作为一个完整循环
            paired_cycles = []
            for i in range(0, len(cycles) - 1, 2):
                forward = cycles[i]
                reverse = cycles[i + 1]
                # 合并正扫和反扫
                combined = forward + reverse
                if len(combined) > 1:
                    paired_cycles.append(combined)
            
            if paired_cycles:
                cycles = paired_cycles
        
        return cycles
    
    def _calculate_cycle_capacitance(self, cycle_num: int, cycle_data: List[Tuple[float, float]]) -> Optional[Dict]:
        """
        计算单个循环的电容
        
        Args:
            cycle_num: 循环编号
            cycle_data: [(voltage, current)]列表
            
        Returns:
            包含计算结果的字典，或None if error
        """
        if len(cycle_data) < 2:
            return None
        
        sensitivity = self.metadata.get('sensitivity', 1e-5)
        threshold = sensitivity * self.sensitivity_threshold_factor
        
        # 检查电流是否超出范围
        currents = [abs(i) for _, i in cycle_data]
        has_overflow = any(c > threshold for c in currents)
        
        if has_overflow:
            return {
                'cycle_num': cycle_num,
                'area': 0,
                'capacitance': 0,
                'is_outlier': True,
                'outlier_reason': '电流溢出',
                'warning': f'电流值超出{self.sensitivity_threshold_factor}x灵敏度范围，本循环数据被忽略'
            }
        
        # 将循环分为正扫和反扫
        forward_scan, reverse_scan = self._split_forward_reverse(cycle_data)
        
        if not forward_scan or not reverse_scan:
            return None
        
        # 计算面积（积分）
        area = self._calculate_area(forward_scan, reverse_scan)
        
        # 计算电容
        # 电容 = 面积 / (扫速 * 电压范围)
        scan_rate = self.metadata.get('scan_rate', 0.01)
        if scan_rate == 0:
            return None
        
        # 电压范围
        voltages = [v for v, _ in forward_scan]
        voltage_range = max(voltages) - min(voltages) if voltages else 1
        
        capacitance = area / (2*scan_rate * voltage_range)
        
        return {
            'cycle_num': cycle_num,
            'area': area,
            'capacitance': capacitance,
            'is_outlier': False,
            'outlier_reason': None,
            'warning': None
        }
    
    def _split_forward_reverse(self, cycle_data: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """
        将循环数据分为正扫和反扫
        
        Returns:
            (正扫数据, 反扫数据)
        """
        if len(cycle_data) < 2:
            return [], []
        
        # 找到最大电压点
        max_idx = 0
        max_voltage = cycle_data[0][0]
        
        for i, (v, _) in enumerate(cycle_data):
            if v > max_voltage:
                max_voltage = v
                max_idx = i
        
        # 正扫：从开始到最大点
        forward = cycle_data[:max_idx+1]
        # 反扫：从最大点到结尾
        reverse = cycle_data[max_idx:]
        
        return forward, reverse
    
    def _calculate_area(self, forward_scan: List[Tuple[float, float]], 
                        reverse_scan: List[Tuple[float, float]]) -> float:
        """
        计算正扫和反扫之间的面积
        使用梯形积分方法
        
        Args:
            forward_scan: 正扫数据
            reverse_scan: 反扫数据
            
        Returns:
            面积值
        """
        area = 0
        
        # 建立反扫数据的voltage->current映射
        reverse_dict = {round(v, 6): i for v, i in reverse_scan}
        
        # 对正扫中的每个点，计算与反扫的差异
        for i in range(len(forward_scan) - 1):
            v1, i1 = forward_scan[i]
            v2, i2 = forward_scan[i+1]
            
            # 查找反扫中对应的电流，使用舍入来处理浮点数精度
            v1_rounded = round(v1, 6)
            v2_rounded = round(v2, 6)
            
            if v1_rounded in reverse_dict and v2_rounded in reverse_dict:
                ir1 = reverse_dict[v1_rounded]
                ir2 = reverse_dict[v2_rounded]
                
                # 计算梯形面积：(i_forward - i_reverse) * dV
                # 使用中点值的平均
                dV = abs(v2 - v1)
                delta_i_avg = ((i1 - ir1) + (i2 - ir2)) / 2
                area += delta_i_avg * dV
        
        return abs(area)
    
    def _calculate_robust_average(self, values: List[float]) -> float:
        """
        计算鲁棒平均值（排除最离群的值）
        
        Args:
            values: 数值列表
            
        Returns:
            平均值
        """
        if len(values) <= self.outlier_count:
            return statistics.mean(values)
        
        # 按离群程度排序（使用z-score）
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0
        
        if stdev == 0:
            return mean
        
        # 计算z-score
        z_scores = [(abs(v - mean) / stdev, v) for v in values]
        z_scores.sort(reverse=True, key=lambda x: x[0])
        
        # 排除最离群的值
        remaining = [v for _, v in z_scores[self.outlier_count:]]
        
        return statistics.mean(remaining) if remaining else mean
    
    def _get_valid_capacitances(self, cycle_results: List[Dict]) -> List[float]:
        """
        获取有效的电容值（排除异常值）
        
        Args:
            cycle_results: 循环结果列表
            
        Returns:
            有效电容值列表
        """
        valid_capacitances = []
        for result in cycle_results:
            if not result.get('is_outlier', False) and result['capacitance'] > 0:
                valid_capacitances.append(result['capacitance'])
        return valid_capacitances


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法: python cv_analysis.py <数据文件路径>")
        print("示例: python cv_analysis.py test_cv_data.txt")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # 创建分析器
    analyzer = CVAnalyzer(sensitivity_threshold_factor=10, outlier_count=1)
    
    # 读取文件
    if not analyzer.read_file(file_path):
        sys.exit(1)
    
    # 执行分析
    if not analyzer.analyze():
        sys.exit(1)


if __name__ == "__main__":
    main()
