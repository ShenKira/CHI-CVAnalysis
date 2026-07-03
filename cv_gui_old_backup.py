import sys
import os

# 在导入matplotlib之前设置后端
os.environ['QT_API'] = 'pyside6'
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = ''

import matplotlib
# 设置matplotlib使用Qt5Agg后端
matplotlib.use('Qt5Agg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
# 为了兼容PySide6，我们需要处理NavigationToolbar
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

# 创建兼容PySide6的NavigationToolbar包装
class NavigationToolbar(NavigationToolbar2QT):
    """兼容PySide6的NavigationToolbar"""
    pass

from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QTableWidget, QTableWidgetItem,
    QTextEdit, QSplitter, QMessageBox, QLineEdit, QDoubleSpinBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from pathlib import Path
from cv_analysis import CVAnalyzer
import statistics
import tempfile
import shutil
from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication as QtApp


class CVAnalysisGUI(QMainWindow):
    """CV数据分析GUI应用"""
    
    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.cycles_data = []
        self.capacitances = []
        self.cycle_results = []
        self.file_path = None
        self.electrode_area = None  # 电极面积，单位cm²
        self.temp_dir = tempfile.mkdtemp(prefix="cv_analysis_")  # 临时目录用于图片
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("循环伏安分析工具 (CV Analysis Tool)")
        self.setGeometry(50, 50, 1500, 950)
        
        # 设置应用样式
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
            QTableWidget {
                background-color: white;
                gridline-color: #ddd;
            }
            QTextEdit {
                background-color: white;
                color: #333;
            }
            QLabel {
                color: #333;
            }
        """)
        
        # 主窗口
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout()
        
        # 1. 文件操作区域
        file_layout = QHBoxLayout()
        self.file_label = QLabel("未选择文件")
        self.file_label.setFont(QFont("Arial", 13))
        
        self.load_btn = QPushButton("导入CV数据文件")
        self.load_btn.setFont(QFont("Arial", 12))
        self.load_btn.clicked.connect(self.load_file)
        self.load_btn.setMinimumWidth(150)
        
        # 添加电极面积输入
        area_label = QLabel("电极面积 (cm²):")
        area_label.setFont(QFont("Arial", 12))
        self.area_input = QDoubleSpinBox()
        self.area_input.setFont(QFont("Arial", 12))
        self.area_input.setMinimum(0)
        self.area_input.setMaximum(10000)
        self.area_input.setSingleStep(0.001)
        self.area_input.setDecimals(4)
        self.area_input.setValue(0)  # 默认为0（不使用）
        self.area_input.setMaximumWidth(140)
        self.area_input.setToolTip("输入电极面积（可选），用于计算单位面积电容")
        self.area_input.valueChanged.connect(self.on_area_changed)
        
        file_label = QLabel("文件: ")
        file_label.setFont(QFont("Arial", 12))
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_label)
        file_layout.addStretch()
        file_layout.addWidget(area_label)
        file_layout.addWidget(self.area_input)
        file_layout.addWidget(self.load_btn)
        
        main_layout.addLayout(file_layout)
        
        # 2. 内容区域（分两部分：左边是结果表格，右边是绘图）
        content_layout = QHBoxLayout()
        
        # 左边：结果展示
        left_layout = QVBoxLayout()
        title1 = QLabel("各循环电容值结果:")
        title1.setFont(QFont("Arial", 13, QFont.Bold))
        left_layout.addWidget(title1)
        
        subtitle1 = QLabel("(每行代表一轮循环，2 Segments)")
        subtitle1.setFont(QFont("Arial", 11))
        left_layout.addWidget(subtitle1)
        
        # 循环结果表格
        self.cycles_table = QTableWidget()
        self.cycles_table.setColumnCount(4)
        self.cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", "电容 (mF)", "备注"])
        self.cycles_table.setFont(QFont("Arial", 12))
        self.cycles_table.horizontalHeader().setFont(QFont("Arial", 12, QFont.Bold))
        self.cycles_table.setMaximumWidth(500)
        self.cycles_table.verticalHeader().setDefaultSectionSize(32)
        left_layout.addWidget(self.cycles_table)
        
        # 最终结果区域
        title2 = QLabel("\n最终结果:")
        title2.setFont(QFont("Arial", 13, QFont.Bold))
        left_layout.addWidget(title2)
        self.result_text = QTextEdit()
        self.result_text.setFont(QFont("Courier", 12))
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumWidth(500)
        self.result_text.setMaximumHeight(350)
        left_layout.addWidget(self.result_text)
        
        # 右边：绘图区域
        right_layout = QVBoxLayout()
        graph_label = QLabel("V-I曲线图:")
        graph_label.setFont(QFont("Arial", 13, QFont.Bold))
        right_layout.addWidget(graph_label)
        
        # 创建matplotlib图表容器
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        
        # 创建canvas容器
        canvas_widget = QWidget()
        canvas_layout = QVBoxLayout()
        
        # 创建工具栏 - 为了避免PySide6和PyQt5的兼容性问题，改为创建简单的工具栏
        try:
            toolbar = NavigationToolbar(self.canvas, self)  # 使用self而不是canvas_widget
        except Exception as e:
            # 如果NavigationToolbar创建失败，跳过
            print(f"警告：无法创建NavigationToolbar: {e}")
            toolbar = None
        
        if toolbar is not None:
            canvas_layout.addWidget(toolbar)

        canvas_layout.addWidget(self.canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_widget.setLayout(canvas_layout)
        
        right_layout.addWidget(canvas_widget)
        
        # 保存按钮
        save_layout = QHBoxLayout()
        self.save_png_btn = QPushButton("保存为PNG")
        self.save_png_btn.setFont(QFont("Arial", 10))
        self.save_png_btn.clicked.connect(self.save_plot_png)
        self.save_png_btn.setEnabled(False)
        
        self.save_svg_btn = QPushButton("保存为SVG")
        self.save_svg_btn.setFont(QFont("Arial", 10))
        self.save_svg_btn.clicked.connect(self.save_plot_svg)
        self.save_svg_btn.setEnabled(False)
        
        self.copy_clipboard_btn = QPushButton("复制到剪切板")
        self.copy_clipboard_btn.setFont(QFont("Arial", 10))
        self.copy_clipboard_btn.clicked.connect(self.copy_plot_to_clipboard)
        self.copy_clipboard_btn.setEnabled(False)
        
        save_layout.addStretch()
        save_layout.addWidget(self.save_png_btn)
        save_layout.addWidget(self.save_svg_btn)
        save_layout.addWidget(self.copy_clipboard_btn)
        
        right_layout.addLayout(save_layout)
        
        # 添加左右两个区域到内容布局
        content_layout.addLayout(left_layout, stretch=1)
        content_layout.addLayout(right_layout, stretch=1)
        
        main_layout.addLayout(content_layout, stretch=1)
        
        main_widget.setLayout(main_layout)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
    
    def closeEvent(self, event):
        """关闭应用时清理临时目录"""
        try:
            if hasattr(self, 'temp_dir') and Path(self.temp_dir).exists():
                shutil.rmtree(self.temp_dir)
        except:
            pass
        super().closeEvent(event)
    
    def on_area_changed(self, value):
        """电极面积改变时的处理"""
        if value > 0:
            self.electrode_area = value
        else:
            self.electrode_area = None
        
        # 如果已经有数据，重新更新结果显示（包括表格和图表，因为单位可能会改变）
        if self.capacitances:
            self.update_cycles_table()
            self.update_result_text()
            self.plot_data()
    
    def load_file(self):
        """打开文件对话框选择CV数据文件"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "选择CV数据文件",
            "",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            self.file_path = file_path
            self.file_label.setText(Path(file_path).name)
            self.analyze_file()
    
    def analyze_file(self):
        """分析选中的文件"""
        if not self.file_path:
            return
        
        try:
            self.statusBar().showMessage("正在分析文件...")
            
            # 创建分析器
            self.analyzer = CVAnalyzer(sensitivity_threshold_factor=10, outlier_count=1)
            
            # 读取文件
            if not self.analyzer.read_file(self.file_path):
                QMessageBox.critical(self, "错误", "无法读取文件")
                self.statusBar().showMessage("错误：无法读取文件")
                return
            
            self.statusBar().showMessage("正在分割循环数据...")
            
            # 获取数据
            self.cycles_data = self.analyzer._split_into_cycles()
            
            if not self.cycles_data:
                QMessageBox.critical(self, "错误", "无法分割循环数据")
                self.statusBar().showMessage("错误：无法分割循环数据")
                return
            
            self.statusBar().showMessage("正在计算电容值...")
            
            # 计算每个循环的电容
            self.capacitances = []
            self.cycle_results = []
            
            for cycle_num, cycle_data in enumerate(self.cycles_data, 1):
                result = self.analyzer._calculate_cycle_capacitance(cycle_num, cycle_data)
                if result is not None:
                    # 收集所有结果，包括异常值
                    self.cycle_results.append(result)
                    # 只将非异常的电容值加入capacitances
                    if not result.get('is_outlier', False) and result['capacitance'] > 0:
                        self.capacitances.append(result['capacitance'])
            
            if not self.cycle_results:
                QMessageBox.critical(self, "错误", "无法处理任何循环")
                self.statusBar().showMessage("错误：无法处理任何循环")
                return
            
            self.statusBar().showMessage("正在更新显示...")
            
            # 更新表格
            self.update_cycles_table()
            
            # 更新结果文本
            self.update_result_text()
            
            # 绘制图表
            self.plot_data()
            
            # 启用保存按钮
            self.save_png_btn.setEnabled(True)
            self.save_svg_btn.setEnabled(True)
            self.copy_clipboard_btn.setEnabled(True)
            
            self.statusBar().showMessage(f"分析完成！共识别 {len(self.cycles_data)} 轮循环，{len(self.capacitances)} 轮有效")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"分析过程中出错: {str(e)}")
            self.statusBar().showMessage("错误：分析过程出错")
    
    def get_capacitance_unit(self, use_specific=False):
        """
        根据有效电容值（排除异常值）自动选择单位
        如果use_specific=True，根据单位面积容值选择单位
        否则根据原始电容值选择单位
        返回值: (单位字符, 转换因子(从F), 单位显示名称)
        """
        if not self.capacitances:
            return ('nF', 1e9, 'nF')
        
        # 获取有效的电容值（排除异常值）
        valid_capacitances = self.analyzer._get_valid_capacitances(self.cycle_results)
        
        if not valid_capacitances:
            # 如果没有有效值，回退到所有值
            valid_capacitances = self.capacitances
        
        if use_specific and self.electrode_area and self.electrode_area > 0:
            # 基于单位面积容值选择单位
            specific_capacitances = [cap / self.electrode_area for cap in valid_capacitances]
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
    
    def update_cycles_table(self):
        """更新循环结果表格"""
        self.cycles_table.setRowCount(len(self.cycle_results))
        
        # 获取电容单位 - 当有电极面积时，根据单位面积容值选择单位
        cap_unit, cap_factor, cap_display = self.get_capacitance_unit(
            use_specific=(self.electrode_area is not None and self.electrode_area > 0)
        )
        
        # 更新表格列标题 - 添加备注列
        if self.electrode_area and self.electrode_area > 0:
            self.cycles_table.setColumnCount(4)
            self.cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"单位面积容 ({cap_display}/cm²)", "备注"])
        else:
            self.cycles_table.setColumnCount(4)
            self.cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", f"电容 ({cap_display})", "备注"])
        
        for row, result in enumerate(self.cycle_results):
            cycle_num = result['cycle_num']
            area = result['area']
            capacitance = result['capacitance']
            
            # 循环号
            item = QTableWidgetItem(str(cycle_num))
            item.setFont(QFont("Arial", 11))
            self.cycles_table.setItem(row, 0, item)
            
            # 面积（4位有效数字科学计数法）
            area_str = f"{area:.4e}" if area != 0 else "0.0000e+00"
            item = QTableWidgetItem(area_str)
            item.setFont(QFont("Arial", 11))
            self.cycles_table.setItem(row, 1, item)
            
            # 电容或单位面积电容
            if self.electrode_area and self.electrode_area > 0:
                # 显示单位面积电容
                if capacitance > 0:
                    specific_cap = (capacitance / self.electrode_area) * cap_factor
                    cap_str = f"{specific_cap:.6g}"  # 使用通用格式
                else:
                    cap_str = "—"  # 异常值显示为—
            else:
                # 显示普通电容（根据单位转换）
                if capacitance > 0:
                    cap_value = capacitance * cap_factor
                    cap_str = f"{cap_value:.6g}"  # 使用通用格式显示
                else:
                    cap_str = "—"  # 异常值显示为—
            
            item = QTableWidgetItem(cap_str)
            item.setFont(QFont("Arial", 11))
            self.cycles_table.setItem(row, 2, item)
            
            # 备注列 - 显示异常原因
            remark_str = ""
            if result.get('is_outlier', False):
                remark_str = result.get('outlier_reason', '数据异常')
            
            item = QTableWidgetItem(remark_str)
            item.setFont(QFont("Arial", 11))
            self.cycles_table.setItem(row, 3, item)
        
        self.cycles_table.resizeColumnsToContents()
    
    def update_result_text(self):
        """更新最终结果文本"""
        text = ""
        
        # 实验参数
        text += "实验参数:\n"
        if 'init_e' in self.analyzer.metadata:
            text += f"  初始电压: {self.analyzer.metadata['init_e']} V\n"
        if 'high_e' in self.analyzer.metadata:
            text += f"  最高电压: {self.analyzer.metadata['high_e']} V\n"
        if 'low_e' in self.analyzer.metadata:
            text += f"  最低电压: {self.analyzer.metadata['low_e']} V\n"
        if 'scan_rate' in self.analyzer.metadata:
            text += f"  扫描速率: {self.analyzer.metadata['scan_rate']} V/s\n"
        if 'sensitivity' in self.analyzer.metadata:
            text += f"  灵敏度: {self.analyzer.metadata['sensitivity']:.0e} A/V\n"
        if self.electrode_area and self.electrode_area > 0:
            text += f"  电极面积: {self.electrode_area:.4f} cm²\n"
        
        text += "\n" + "="*40 + "\n"
        text += "最终统计结果:\n"
        text += "-"*40 + "\n"
        
        # 获取有效的电容值（排除异常值）
        valid_capacitances = self.analyzer._get_valid_capacitances(self.cycle_results)
        total_cycles = len(self.cycle_results)
        valid_cycles = len(valid_capacitances)
        excluded_cycles = total_cycles - valid_cycles
        
        text += f"总循环数: {total_cycles}\n"
        text += f"有效循环数: {valid_cycles}\n"
        if excluded_cycles > 0:
            text += f"被排除的循环数: {excluded_cycles}\n"
        text += f"被排除离群值数: {self.analyzer.outlier_count}\n"
        
        if len(valid_capacitances) > 1:
            avg_capacitance = self.analyzer._calculate_robust_average(valid_capacitances)
            
            if self.electrode_area and self.electrode_area > 0:
                # 显示单位面积电容
                specific_cap = avg_capacitance / self.electrode_area
                text += f"\n平均电容: {avg_capacitance:.6e} F\n"
                text += f"           {avg_capacitance*1000:.6f} mF\n"
                text += f"\n单位面积电容: {specific_cap:.6e} F/cm²\n"
                text += f"             {specific_cap*1000:.6f} mF/cm²\n"
                text += f"             {specific_cap*1e6:.6f} µF/cm²\n"
                
                min_specific = min(valid_capacitances) / self.electrode_area
                max_specific = max(valid_capacitances) / self.electrode_area
                text += f"最小值(面积): {min_specific*1000:.6f} mF/cm²\n"
                text += f"最大值(面积): {max_specific*1000:.6f} mF/cm²\n"
                
                std_dev = statistics.stdev(valid_capacitances) if len(valid_capacitances) > 1 else 0
                std_specific = std_dev / self.electrode_area
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
            if self.electrode_area and self.electrode_area > 0:
                specific_cap = valid_capacitances[0] / self.electrode_area
                text += f"\n电容值: {valid_capacitances[0]:.6e} F\n"
                text += f"       {valid_capacitances[0]*1000:.6f} mF\n"
                text += f"\n单位面积电容: {specific_cap:.6e} F/cm²\n"
                text += f"             {specific_cap*1000:.6f} mF/cm²\n"
            else:
                text += f"\n电容值: {valid_capacitances[0]:.6e} F\n"
                text += f"       {valid_capacitances[0]*1000:.6f} mF\n"
        else:
            text += "\n警告: 没有有效的循环数据可用于统计\n"
        
        self.result_text.setText(text)
    
    def plot_data(self):
        """绘制V-I曲线图"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        
        # 设置matplotlib字体以支持Times New Roman
        plt.rcParams['font.family'] = 'Times New Roman'
        plt.rcParams['font.size'] = 12
        
        # 定义颜色列表（支持更多循环）
        if len(self.cycles_data) <= 10:
            colors = plt.cm.tab10(range(len(self.cycles_data)))
        elif len(self.cycles_data) <= 20:
            colors = plt.cm.tab20(range(len(self.cycles_data)))
        else:
            colors = plt.cm.hsv([(i / len(self.cycles_data)) for i in range(len(self.cycles_data))])
        
        # 计算所有数据的最大电流值（单位：A）
        max_current_A = 0
        for cycle_data in self.cycles_data:
            for _, current in cycle_data:
                max_current_A = max(max_current_A, abs(current))
        
        # 自动选择单位
        # 将A转换为nA（乘以1e9）
        max_current_nA = max_current_A * 1e9
        
        if max_current_nA > 2000:  # 如果最大值 > 2000nA
            if max_current_nA > 2000 * 1000:  # 如果最大值 > 2000uA（2000000nA）
                # 使用mA
                scale_factor = 1000  # A to mA
                unit_str = 'mA'
            else:
                # 使用uA
                scale_factor = 1e6  # A to uA
                unit_str = 'µA'
        else:
            # 使用nA
            scale_factor = 1e9  # A to nA
            unit_str = 'nA'
        
        # 绘制每个循环的数据
        for cycle_num, cycle_data in enumerate(self.cycles_data):
            voltages = [v for v, _ in cycle_data]
            currents = [i * scale_factor for _, i in cycle_data]  # 按选定的单位转换
            
            ax.plot(voltages, currents, color=colors[cycle_num], 
                   label=f'Cycle {cycle_num+1}', linewidth=2.0, alpha=0.85, marker=None)
        
        # 设置标签和标题（使用Times New Roman字体和较大字号）
        ax.set_xlabel('Voltage (V)', fontsize=16, fontname='Times New Roman', fontweight='bold')
        ax.set_ylabel(f'Current ({unit_str})', fontsize=16, fontname='Times New Roman', fontweight='bold')
        ax.set_title('CV Test - V-I Curve', fontsize=18, fontname='Times New Roman', fontweight='bold', pad=20)
        
        # 设置刻度标签字体和大小
        ax.tick_params(labelsize=13)
        for label in ax.get_xticklabels():
            label.set_fontname('Times New Roman')
            label.set_fontsize(13)
        for label in ax.get_yticklabels():
            label.set_fontname('Times New Roman')
            label.set_fontsize(13)
        
        # 设置图例
        legend = ax.legend(fontsize=11, loc='best', framealpha=0.95, 
                          fancybox=True, shadow=True, ncol=2)
        for text in legend.get_texts():
            text.set_fontname('Times New Roman')
            text.set_fontsize(11)
        
        # 添加文字注释（右下角）
        # 获取有效的电容值（排除异常值）
        valid_capacitances = self.analyzer._get_valid_capacitances(self.cycle_results)
        
        if len(valid_capacitances) > 1:
            avg_cap = self.analyzer._calculate_robust_average(valid_capacitances)
            std_dev = statistics.stdev(valid_capacitances)
        elif len(valid_capacitances) == 1:
            avg_cap = valid_capacitances[0]
            std_dev = 0
        else:
            # 没有有效值，使用所有值（不应该出现这种情况）
            avg_cap = self.capacitances[0] if self.capacitances else 0
            std_dev = 0
        
        # 获取电容单位 - 当有电极面积时，根据单位面积容值选择单位
        cap_unit, cap_factor, cap_display = self.get_capacitance_unit(
            use_specific=(self.electrode_area is not None and self.electrode_area > 0)
        )
        
        # 格式化电容值显示
        if self.electrode_area and self.electrode_area > 0:
            # 使用单位面积容值
            avg_cap_display = (avg_cap / self.electrode_area) * cap_factor
            std_dev_display = (std_dev / self.electrode_area) * cap_factor
        else:
            # 使用原始容值
            avg_cap_display = avg_cap * cap_factor
            std_dev_display = std_dev * cap_factor
        
        # 创建注释文本
        annotation_text = f'Capacitance = {avg_cap_display:.6g} {cap_display}\nSD = {std_dev_display:.6g} {cap_display}'
        
        # 在右下角添加文字注释
        ax.text(0.98, 0.05, annotation_text, transform=ax.transAxes,
                fontsize=12, verticalalignment='bottom', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                fontname='Times New Roman', fontweight='bold')
        
        # 添加网格
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # 调整布局
        self.figure.tight_layout()
        self.canvas.draw()
        
        # 启用复制按钮
        self.copy_clipboard_btn.setEnabled(True)
    
    def save_plot_png(self):
        """保存图表为PNG格式"""
        if not self.file_path:
            return
        
        file_dialog = QFileDialog()
        output_path, _ = file_dialog.getSaveFileName(
            self,
            "保存PNG文件",
            Path(self.file_path).stem + "_cv_curve.png",
            "PNG文件 (*.png)"
        )
        
        if output_path:
            try:
                self.statusBar().showMessage(f"正在保存PNG文件...")
                self.figure.savefig(output_path, dpi=300, bbox_inches='tight', format='png')
                self.statusBar().showMessage(f"PNG已保存: {Path(output_path).name}")
                QMessageBox.information(self, "成功", f"图表已保存为PNG\n{output_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存PNG失败: {str(e)}")
                self.statusBar().showMessage("错误：保存PNG失败")
    
    def save_plot_svg(self):
        """保存图表为SVG格式"""
        if not self.file_path:
            return
        
        file_dialog = QFileDialog()
        output_path, _ = file_dialog.getSaveFileName(
            self,
            "保存SVG文件",
            Path(self.file_path).stem + "_cv_curve.svg",
            "SVG文件 (*.svg)"
        )
        
        if output_path:
            try:
                self.statusBar().showMessage(f"正在保存SVG文件...")
                self.figure.savefig(output_path, bbox_inches='tight', format='svg')
                self.statusBar().showMessage(f"SVG已保存: {Path(output_path).name}")
                QMessageBox.information(self, "成功", f"图表已保存为SVG\n{output_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存SVG失败: {str(e)}")
                self.statusBar().showMessage("错误：保存SVG失败")
    
    def copy_plot_to_clipboard(self):
        """将图表复制到剪切板"""
        if not self.file_path:
            return
        
        try:
            self.statusBar().showMessage("正在复制图表到剪切板...")
            
            # 生成临时文件路径
            temp_image_path = Path(self.temp_dir) / "cv_curve_temp.png"
            
            # 保存为PNG
            self.figure.savefig(str(temp_image_path), dpi=300, bbox_inches='tight', format='png')
            
            # 加载图片并复制到剪切板
            image = Image.open(str(temp_image_path))
            
            # 获取系统剪切板
            clipboard = QtApp.clipboard()
            pixmap = QPixmap(str(temp_image_path))
            clipboard.setPixmap(pixmap)
            
            self.statusBar().showMessage("图表已复制到剪切板")
            QMessageBox.information(self, "成功", "图表已复制到剪切板！")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制到剪切板失败: {str(e)}")
            self.statusBar().showMessage("错误：复制失败")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = CVAnalysisGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
