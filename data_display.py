"""
数据展示模块
处理循环结果表格、统计结果文本的更新和单位选择
"""

from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtGui import QFont, QBrush, QColor
import statistics


def _add_section_header(table, title):
    """插入一个分组标题行（加粗灰色背景）"""
    row = table.rowCount()
    table.setRowCount(row + 1)
    header = QTableWidgetItem(f"  {title}")
    header.setFont(QFont("Arial", 11, QFont.Weight.Bold))
    header.setBackground(QColor("#e8e8e8"))
    header.setForeground(QBrush(QColor("#333")))
    table.setItem(row, 0, header)
    # 第二列也设灰色背景
    empty = QTableWidgetItem()
    empty.setBackground(QColor("#e8e8e8"))
    table.setItem(row, 1, empty)


def _add_row(table, key, value):
    """插入一个参数行"""
    row = table.rowCount()
    table.setRowCount(row + 1)
    item_key = QTableWidgetItem(key)
    item_key.setFont(QFont("Arial", 11))
    table.setItem(row, 0, item_key)
    item_val = QTableWidgetItem(str(value))
    item_val.setFont(QFont("Arial", 11))
    table.setItem(row, 1, item_val)


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
    
    # 更新表格列标题（现在有5列）
    if electrode_area and electrode_area > 0:
        cycles_table.setColumnCount(5)
        cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"单位面积容 ({cap_display}/cm²)", "备注", "绘图"])
    else:
        cycles_table.setColumnCount(5)
        cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"电容 ({cap_display})", "备注", "绘图"])
    
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


def update_result_text(results_table, cycle_results, analyzer, metadata, electrode_area, is_multi_file=False):
    """更新最终结果表格"""
    results_table.setRowCount(0)

    if not is_multi_file:
        # --- 实验参数（多文件模式下不显示）---
        _add_section_header(results_table, "实验参数")
        if 'init_e' in metadata:
            _add_row(results_table, "  初始电压", f"{metadata['init_e']} V")
        if 'high_e' in metadata:
            _add_row(results_table, "  最高电压", f"{metadata['high_e']} V")
        if 'low_e' in metadata:
            _add_row(results_table, "  最低电压", f"{metadata['low_e']} V")
        if 'scan_rate' in metadata:
            _add_row(results_table, "  扫描速率", f"{metadata['scan_rate']} V/s")
        if 'sensitivity' in metadata:
            _add_row(results_table, "  灵敏度", f"{metadata['sensitivity']:.0e} A/V")
        if electrode_area and electrode_area > 0:
            _add_row(results_table, "  电极面积", f"{electrode_area:.4f} cm²")

    # --- 循环统计 ---
    valid_capacitances = analyzer._get_valid_capacitances(cycle_results)
    total_cycles = len(cycle_results)
    valid_cycles = len(valid_capacitances)
    excluded_cycles = total_cycles - valid_cycles

    _add_section_header(results_table, "循环统计")
    _add_row(results_table, "  总循环数", str(total_cycles))
    _add_row(results_table, "  有效循环数", str(valid_cycles))
    if excluded_cycles > 0:
        _add_row(results_table, "  被排除的循环数", str(excluded_cycles))
    _add_row(results_table, "  被排除离群值数", str(analyzer.outlier_count))

    outlier_cycles = analyzer._get_outlier_cycles(cycle_results)
    if outlier_cycles:
        _add_row(results_table, "  被排除轮次", ', '.join(str(c) for c in outlier_cycles))

    if not is_multi_file:
        # --- 电容结果（多文件模式下不显示）---
        _add_section_header(results_table, "电容结果")

        if len(valid_capacitances) > 1:
            avg_capacitance = analyzer._calculate_robust_average(valid_capacitances)
            std_dev = statistics.stdev(valid_capacitances)
            cv_pct = (std_dev / avg_capacitance) * 100

            if electrode_area and electrode_area > 0:
                specific_cap = avg_capacitance / electrode_area
                min_specific = min(valid_capacitances) / electrode_area
                max_specific = max(valid_capacitances) / electrode_area
                std_specific = std_dev / electrode_area

                _add_row(results_table, "  平均电容", f"{avg_capacitance:.6e} F = {avg_capacitance*1000:.6f} mF")
                _add_row(results_table, "  单位面积电容", f"{specific_cap*1000:.6f} mF/cm² = {specific_cap*1e6:.6f} µF/cm²")
                _add_row(results_table, "  最小值", f"{min_specific*1000:.6f} mF/cm²")
                _add_row(results_table, "  最大值", f"{max_specific*1000:.6f} mF/cm²")
                _add_row(results_table, "  标准差", f"{std_specific*1000:.6f} mF/cm²")
                _add_row(results_table, "  变异系数", f"{cv_pct:.2f}%")
            else:
                _add_row(results_table, "  平均电容", f"{avg_capacitance:.6e} F = {avg_capacitance*1000:.6f} mF")
                _add_row(results_table, "  最小值", f"{min(valid_capacitances)*1000:.6f} mF")
                _add_row(results_table, "  最大值", f"{max(valid_capacitances)*1000:.6f} mF")
                _add_row(results_table, "  标准差", f"{std_dev:.6e} F = {std_dev*1000:.6f} mF")
                _add_row(results_table, "  变异系数", f"{cv_pct:.2f}%")
        elif len(valid_capacitances) == 1:
            if electrode_area and electrode_area > 0:
                specific_cap = valid_capacitances[0] / electrode_area
                _add_row(results_table, "  电容值", f"{valid_capacitances[0]:.6e} F = {valid_capacitances[0]*1000:.6f} mF")
                _add_row(results_table, "  单位面积电容", f"{specific_cap*1000:.6f} mF/cm² = {specific_cap*1e6:.6f} µF/cm²")
            else:
                _add_row(results_table, "  电容值", f"{valid_capacitances[0]:.6e} F = {valid_capacitances[0]*1000:.6f} mF")
        else:
            _add_row(results_table, "  警告", "没有有效的循环数据可用于统计")

    results_table.resizeColumnsToContents()


def update_eis_result_text(results_table, eis_analyzer):
    """更新EIS实验信息表格"""
    results_table.setRowCount(0)

    metadata = eis_analyzer.metadata

    # --- 实验参数 ---
    _add_section_header(results_table, "实验参数")
    if 'init_e' in metadata:
        _add_row(results_table, "  初始电压", f"{metadata['init_e']} V")
    if 'high_freq' in metadata:
        _add_row(results_table, "  高频", f"{metadata['high_freq']:.3e} Hz")
    if 'low_freq' in metadata:
        _add_row(results_table, "  低频", f"{metadata['low_freq']:.3e} Hz")
    if 'amplitude' in metadata:
        _add_row(results_table, "  振幅", f"{metadata['amplitude']:.3e} V")
    if 'quiet_time' in metadata:
        _add_row(results_table, "  静置时间", f"{metadata['quiet_time']} s")

    # --- 数据统计 ---
    _add_section_header(results_table, "数据统计")
    _add_row(results_table, "  数据点数", str(eis_analyzer.get_data_count()))

    freq_range = eis_analyzer.get_freq_range()
    if freq_range:
        _add_row(results_table, "  频率范围", f"{freq_range[0]:.3e} ~ {freq_range[1]:.3e} Hz")

    if eis_analyzer.eis_data:
        z_reals = [d['z_real'] for d in eis_analyzer.eis_data]
        z_imags = [d['z_imag'] for d in eis_analyzer.eis_data]
        _add_row(results_table, "  Z' 范围", f"{min(z_reals):.3e} ~ {max(z_reals):.3e} Ω")
        _add_row(results_table, "  Z'' 范围", f"{min(z_imags):.3e} ~ {max(z_imags):.3e} Ω")

    results_table.resizeColumnsToContents()
