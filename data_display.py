"""
数据展示模块
处理循环结果表格、统计结果文本的更新和单位选择
"""

from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtGui import QFont
import statistics


def get_capacitance_unit(cycle_results, capacitances, analyzer, electrode_area, use_specific=False):
    """
    根据有效电容值（排除异常值）自动选择单位
    如果use_specific=True，根据单位面积容值选择单位
    否则根据原始电容值选择单位
    返回值: (单位字符, 转换因子(从F), 单位显示名称)
    """
    if not capacitances:
        return ('nF', 1e9, 'nF')
    
    # 获取有效的电容值（排除异常值）
    valid_capacitances = analyzer._get_valid_capacitances(cycle_results)
    
    if not valid_capacitances:
        # 如果没有有效值，回退到所有值
        valid_capacitances = capacitances
    
    if use_specific and electrode_area and electrode_area > 0:
        # 基于单位面积容值选择单位
        specific_capacitances = [cap / electrode_area for cap in valid_capacitances]
        min_specific_nF = min(specific_capacitances) * 1e9  # 转换为nF
        
        if min_specific_nF > 1000 * 1000:  # > 1000µF
            return ('mF', 1000, 'mF')
        elif min_specific_nF > 1000:  # > 1000nF
            return ('µF', 1e6, 'µF')
        else:
            return ('nF', 1e9, 'nF')
    else:
        # 基于原始电容值选择单位
        min_cap_nF = min(valid_capacitances) * 1e9  # 转换为nF
        
        if min_cap_nF > 1000 * 1000:  # > 1000µF
            return ('mF', 1000, 'mF')
        elif min_cap_nF > 1000:  # > 1000nF
            return ('µF', 1e6, 'µF')
        else:
            return ('nF', 1e9, 'nF')


def update_cycles_table(cycles_table, cycle_results, analyzer, electrode_area):
    """更新循环结果表格"""
    cycles_table.setRowCount(len(cycle_results))
    
    # 获取有效的电容值
    valid_capacitances = analyzer._get_valid_capacitances(cycle_results)
    capacitances = [r['capacitance'] for r in cycle_results if r['capacitance'] > 0]
    
    # 获取电容单位
    cap_unit, cap_factor, cap_display = get_capacitance_unit(
        cycle_results,
        capacitances,
        analyzer,
        electrode_area,
        use_specific=(electrode_area is not None and electrode_area > 0)
    )
    
    # 更新表格列标题
    if electrode_area and electrode_area > 0:
        cycles_table.setColumnCount(4)
        cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"单位面积容 ({cap_display}/cm²)", "备注"])
    else:
        cycles_table.setColumnCount(4)
        cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"电容 ({cap_display})", "备注"])
    
    for row, result in enumerate(cycle_results):
        cycle_num = result['cycle_num']
        area = result['area']
        capacitance = result['capacitance']
        
        # 循环号
        item = QTableWidgetItem(str(cycle_num))
        item.setFont(QFont("Arial", 11))
        cycles_table.setItem(row, 0, item)
        
        # 面积（4位有效数字科学计数法）
        area_str = f"{area:.4e}" if area != 0 else "0.0000e+00"
        item = QTableWidgetItem(area_str)
        item.setFont(QFont("Arial", 11))
        cycles_table.setItem(row, 1, item)
        
        # 电容或单位面积电容
        if electrode_area and electrode_area > 0:
            # 显示单位面积电容
            if capacitance > 0:
                specific_cap = (capacitance / electrode_area) * cap_factor
                cap_str = f"{specific_cap:.6g}"
            else:
                cap_str = "—"
        else:
            # 显示普通电容（根据单位转换）
            if capacitance > 0:
                cap_value = capacitance * cap_factor
                cap_str = f"{cap_value:.6g}"
            else:
                cap_str = "—"
        
        item = QTableWidgetItem(cap_str)
        item.setFont(QFont("Arial", 11))
        cycles_table.setItem(row, 2, item)
        
        # 备注列 - 显示异常原因
        remark_str = ""
        if result.get('is_outlier', False):
            remark_str = result.get('outlier_reason', '数据异常')
        
        item = QTableWidgetItem(remark_str)
        item.setFont(QFont("Arial", 11))
        cycles_table.setItem(row, 3, item)
    
    cycles_table.resizeColumnsToContents()


def update_result_text(result_text, cycle_results, analyzer, metadata, electrode_area):
    """更新最终结果文本"""
    text = ""
    
    # 实验参数
    text += "实验参数:\n"
    if 'init_e' in metadata:
        text += f"  初始电压: {metadata['init_e']} V\n"
    if 'high_e' in metadata:
        text += f"  最高电压: {metadata['high_e']} V\n"
    if 'low_e' in metadata:
        text += f"  最低电压: {metadata['low_e']} V\n"
    if 'scan_rate' in metadata:
        text += f"  扫描速率: {metadata['scan_rate']} V/s\n"
    if 'sensitivity' in metadata:
        text += f"  灵敏度: {metadata['sensitivity']:.0e} A/V\n"
    if electrode_area and electrode_area > 0:
        text += f"  电极面积: {electrode_area:.4f} cm²\n"
    
    text += "\n" + "="*40 + "\n"
    text += "最终统计结果:\n"
    text += "-"*40 + "\n"
    
    # 获取有效的电容值（排除异常值）
    valid_capacitances = analyzer._get_valid_capacitances(cycle_results)
    total_cycles = len(cycle_results)
    valid_cycles = len(valid_capacitances)
    excluded_cycles = total_cycles - valid_cycles
    
    text += f"总循环数: {total_cycles}\n"
    text += f"有效循环数: {valid_cycles}\n"
    if excluded_cycles > 0:
        text += f"被排除的循环数: {excluded_cycles}\n"
    text += f"被排除离群值数: {analyzer.outlier_count}\n"
    
    if len(valid_capacitances) > 1:
        avg_capacitance = analyzer._calculate_robust_average(valid_capacitances)
        
        if electrode_area and electrode_area > 0:
            # 显示单位面积电容
            specific_cap = avg_capacitance / electrode_area
            text += f"\n平均电容: {avg_capacitance:.6e} F\n"
            text += f"           {avg_capacitance*1000:.6f} mF\n"
            text += f"\n单位面积电容: {specific_cap:.6e} F/cm²\n"
            text += f"             {specific_cap*1000:.6f} mF/cm²\n"
            text += f"             {specific_cap*1e6:.6f} µF/cm²\n"
            
            min_specific = min(valid_capacitances) / electrode_area
            max_specific = max(valid_capacitances) / electrode_area
            text += f"最小值(面积): {min_specific*1000:.6f} mF/cm²\n"
            text += f"最大值(面积): {max_specific*1000:.6f} mF/cm²\n"
            
            std_dev = statistics.stdev(valid_capacitances) if len(valid_capacitances) > 1 else 0
            std_specific = std_dev / electrode_area
            text += f"标准差(面积): {std_specific*1000:.6f} mF/cm²\n"
            text += f"变异系数: {(std_dev/avg_capacitance)*100:.2f}%\n"
        else:
            # 显示普通电容
            text += f"\n平均电容: {avg_capacitance:.6e} F\n"
            text += f"           {avg_capacitance*1000:.6f} mF\n"
            text += f"最小值: {min(valid_capacitances)*1000:.6f} mF\n"
            text += f"最大值: {max(valid_capacitances)*1000:.6f} mF\n"
            
            std_dev = statistics.stdev(valid_capacitances) if len(valid_capacitances) > 1 else 0
            text += f"标准差: {std_dev:.6e} F\n"
            text += f"        {std_dev*1000:.6f} mF\n"
            text += f"变异系数: {(std_dev/avg_capacitance)*100:.2f}%\n"
    elif len(valid_capacitances) == 1:
        if electrode_area and electrode_area > 0:
            specific_cap = valid_capacitances[0] / electrode_area
            text += f"\n电容值: {valid_capacitances[0]:.6e} F\n"
            text += f"       {valid_capacitances[0]*1000:.6f} mF\n"
            text += f"\n单位面积电容: {specific_cap:.6e} F/cm²\n"
            text += f"             {specific_cap*1000:.6f} mF/cm²\n"
        else:
            text += f"\n电容值: {valid_capacitances[0]:.6e} F\n"
            text += f"       {valid_capacitances[0]*1000:.6f} mF\n"
    else:
        text += "\n警告: 没有有效的循环数据可用于统计\n"
    
    result_text.setText(text)
