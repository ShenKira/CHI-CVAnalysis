# -*- coding: utf-8 -*-
"""
绘图和导出管理模块
处理V-I曲线绘制和各种格式的保存导出
支持通过config.json配置字体样式
"""

import matplotlib.pyplot as plt
import statistics
from pathlib import Path
from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication as QtApp
from PySide6.QtWidgets import QMessageBox, QFileDialog
from data_display import get_capacitance_unit


def _apply_font_config(config):
    """
    应用字体配置到matplotlib
    
    Args:
        config: 绘图配置字典
    """
    plt.rcParams['font.family'] = 'Times New Roman'


def _get_font_weight(bold):
    """获取字体权重"""
    return 'bold' if bold else 'normal'


def plot_data(figure, canvas, cycles_data, cycle_results, analyzer, electrode_area, config=None):
    """绘制V-I曲线图"""
    # 默认配置
    if config is None:
        config = {
            'title': {'fontsize': 14, 'bold': True},
            'xlabel': {'fontsize': 12, 'bold': False},
            'ylabel': {'fontsize': 12, 'bold': False},
            'xtick': {'fontsize': 10, 'bold': False},
            'ytick': {'fontsize': 10, 'bold': False},
            'legend': {'fontsize': 10, 'bold': False},
            'text': {'fontsize': 9, 'bold': False}
        }
    
    # 应用字体配置
    _apply_font_config(config)
    
    figure.clear()
    ax = figure.add_subplot(111)
    
    # 设置matplotlib字体以支持Times New Roman
    plt.rcParams['font.family'] = 'Times New Roman'
    plt.rcParams['font.size'] = 12
    
    # 定义颜色列表（支持更多循环）
    if len(cycles_data) <= 10:
        colors = plt.cm.tab10(range(len(cycles_data)))
    elif len(cycles_data) <= 20:
        colors = plt.cm.tab20(range(len(cycles_data)))
    else:
        colors = plt.cm.hsv([(i / len(cycles_data)) for i in range(len(cycles_data))])
    
    # 计算所有数据的最大电流值（单位：A）
    max_current_A = 0
    for cycle_data in cycles_data:
        for _, current in cycle_data:
            max_current_A = max(max_current_A, abs(current))
    
    # 自动选择单位
    max_current_nA = max_current_A * 1e9
    
    if max_current_nA > 2000:
        if max_current_nA > 2000 * 1000:
            scale_factor = 1000  # A to mA
            unit_str = 'mA'
        else:
            scale_factor = 1e6  # A to uA
            unit_str = 'µA'
    else:
        scale_factor = 1e9  # A to nA
        unit_str = 'nA'
    
    # 绘制每个循环的数据
    for cycle_num, cycle_data in enumerate(cycles_data):
        voltages = [v for v, _ in cycle_data]
        currents = [i * scale_factor for _, i in cycle_data]
        
        ax.plot(voltages, currents, color=colors[cycle_num], 
               label=f'Cycle {cycle_num+1}', linewidth=2.0, alpha=0.85, marker=None)
    
    # 获取配置（如果config不存在就用默认值）
    title_cfg = config.get('title', {'fontsize': 14, 'bold': True})
    xlabel_cfg = config.get('xlabel', {'fontsize': 12, 'bold': False})
    ylabel_cfg = config.get('ylabel', {'fontsize': 12, 'bold': False})
    xtick_cfg = config.get('xtick', {'fontsize': 10, 'bold': False})
    ytick_cfg = config.get('ytick', {'fontsize': 10, 'bold': False})
    legend_cfg = config.get('legend', {'fontsize': 10, 'bold': False})
    text_cfg = config.get('text', {'fontsize': 9, 'bold': False})
    
    # 设置标签和标题
    ax.set_xlabel('Voltage (V)', 
                 fontsize=xlabel_cfg.get('fontsize', 12), 
                 fontname='Times New Roman', 
                 fontweight=_get_font_weight(xlabel_cfg.get('bold', False)))
    ax.set_ylabel(f'Current ({unit_str})', 
                 fontsize=ylabel_cfg.get('fontsize', 12), 
                 fontname='Times New Roman', 
                 fontweight=_get_font_weight(ylabel_cfg.get('bold', False)))
    ax.set_title('CV Test - V-I Curve', 
                fontsize=title_cfg.get('fontsize', 14), 
                fontname='Times New Roman', 
                fontweight=_get_font_weight(title_cfg.get('bold', True)), 
                pad=20)
    
    # 设置刻度标签字体和大小
    ax.tick_params(labelsize=xtick_cfg.get('fontsize', 10))
    for label in ax.get_xticklabels():
        label.set_fontname('Times New Roman')
        label.set_fontsize(xtick_cfg.get('fontsize', 10))
        label.set_fontweight(_get_font_weight(xtick_cfg.get('bold', False)))
    for label in ax.get_yticklabels():
        label.set_fontname('Times New Roman')
        label.set_fontsize(ytick_cfg.get('fontsize', 10))
        label.set_fontweight(_get_font_weight(ytick_cfg.get('bold', False)))
    
    # 设置图例
    legend = ax.legend(fontsize=legend_cfg.get('fontsize', 10), 
                      loc='best', framealpha=0.95, 
                      fancybox=True, shadow=True, ncol=2)
    for text in legend.get_texts():
        text.set_fontname('Times New Roman')
        text.set_fontsize(legend_cfg.get('fontsize', 10))
        text.set_fontweight(_get_font_weight(legend_cfg.get('bold', False)))
    
    # 获取有效的电容值（排除异常值）
    valid_capacitances = analyzer._get_valid_capacitances(cycle_results)
    capacitances = [r['capacitance'] for r in cycle_results if r['capacitance'] > 0]
    
    if len(valid_capacitances) > 1:
        avg_cap = analyzer._calculate_robust_average(valid_capacitances)
        std_dev = statistics.stdev(valid_capacitances)
    elif len(valid_capacitances) == 1:
        avg_cap = valid_capacitances[0]
        std_dev = 0
    else:
        avg_cap = capacitances[0] if capacitances else 0
        std_dev = 0
    
    # 获取电容单位
    cap_unit, cap_factor, cap_display = get_capacitance_unit(
        cycle_results,
        capacitances,
        analyzer,
        electrode_area,
        use_specific=(electrode_area is not None and electrode_area > 0)
    )
    
    # 格式化电容值显示
    if electrode_area and electrode_area > 0:
        avg_cap_display = (avg_cap / electrode_area) * cap_factor
        std_dev_display = (std_dev / electrode_area) * cap_factor
    else:
        avg_cap_display = avg_cap * cap_factor
        std_dev_display = std_dev * cap_factor
    
    # 创建注释文本
    if electrode_area and electrode_area > 0:
        annotation_text = f'Areal Capacitance = {avg_cap_display:.6g} {cap_display}/cm²\nSD = {std_dev_display:.6g} {cap_display}/cm²'
    else:
        annotation_text = f'Capacitance = {avg_cap_display:.6g} {cap_display}\nSD = {std_dev_display:.6g} {cap_display}'
    
    # 在右下角添加文字注释
    ax.text(0.98, 0.05, annotation_text, transform=ax.transAxes,
            fontsize=text_cfg.get('fontsize', 9), 
            verticalalignment='bottom', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            fontname='Times New Roman', 
            fontweight=_get_font_weight(text_cfg.get('bold', False)))
    
    # 添加网格
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # 调整布局
    figure.tight_layout()
    canvas.draw()


def save_plot_png(figure, file_path, parent_widget, status_bar):
    """保存图表为PNG格式"""
    if not file_path:
        return
    
    file_dialog = QFileDialog()
    output_path, _ = file_dialog.getSaveFileName(
        parent_widget,
        "保存PNG文件",
        Path(file_path).stem + "_cv_curve.png",
        "PNG文件 (*.png)"
    )
    
    if output_path:
        try:
            status_bar.showMessage("正在保存PNG文件...")
            figure.savefig(output_path, dpi=300, bbox_inches='tight', format='png')
            status_bar.showMessage(f"PNG已保存: {Path(output_path).name}")
            QMessageBox.information(parent_widget, "成功", f"图表已保存为PNG\n{output_path}")
        except Exception as e:
            QMessageBox.critical(parent_widget, "错误", f"保存PNG失败: {str(e)}")
            status_bar.showMessage("错误：保存PNG失败")


def save_plot_svg(figure, file_path, parent_widget, status_bar):
    """保存图表为SVG格式"""
    if not file_path:
        return
    
    file_dialog = QFileDialog()
    output_path, _ = file_dialog.getSaveFileName(
        parent_widget,
        "保存SVG文件",
        Path(file_path).stem + "_cv_curve.svg",
        "SVG文件 (*.svg)"
    )
    
    if output_path:
        try:
            status_bar.showMessage("正在保存SVG文件...")
            figure.savefig(output_path, bbox_inches='tight', format='svg')
            status_bar.showMessage(f"SVG已保存: {Path(output_path).name}")
            QMessageBox.information(parent_widget, "成功", f"图表已保存为SVG\n{output_path}")
        except Exception as e:
            QMessageBox.critical(parent_widget, "错误", f"保存SVG失败: {str(e)}")
            status_bar.showMessage("错误：保存SVG失败")


def copy_plot_to_clipboard(figure, temp_dir, parent_widget, status_bar):
    """将图表复制到剪切板"""
    try:
        status_bar.showMessage("正在复制图表到剪切板...")
        
        # 生成临时文件路径
        temp_image_path = Path(temp_dir) / "cv_curve_temp.png"
        
        # 保存为PNG
        figure.savefig(str(temp_image_path), dpi=300, bbox_inches='tight', format='png')
        
        # 加载图片并复制到剪切板
        image = Image.open(str(temp_image_path))
        
        # 获取系统剪切板
        clipboard = QtApp.clipboard()
        pixmap = QPixmap(str(temp_image_path))
        clipboard.setPixmap(pixmap)
        
        status_bar.showMessage("图表已复制到剪切板")
        QMessageBox.information(parent_widget, "成功", "图表已复制到剪切板！")
        
    except Exception as e:
        QMessageBox.critical(parent_widget, "错误", f"复制到剪切板失败: {str(e)}")
        status_bar.showMessage("错误：复制失败")
