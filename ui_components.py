"""
UI组件和样式配置
包含所有的UI元素创建和样式设置
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTextEdit, QDoubleSpinBox
)
from PySide6.QtGui import QFont
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT


class NavigationToolbar(NavigationToolbar2QT):
    """兼容PySide6的NavigationToolbar"""
    pass


def get_application_stylesheet():
    """获取应用样式表"""
    return """
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
    """


def create_file_selection_layout():
    """创建文件选择区域"""
    file_layout = QHBoxLayout()
    
    file_label = QLabel("文件: ")
    file_label.setFont(QFont("Arial", 12))
    
    current_file_label = QLabel("未选择文件")
    current_file_label.setFont(QFont("Arial", 13))
    
    load_btn = QPushButton("导入CV数据文件")
    load_btn.setFont(QFont("Arial", 12))
    load_btn.setMinimumWidth(150)
    
    area_label = QLabel("电极面积 (cm²):")
    area_label.setFont(QFont("Arial", 12))
    
    area_input = QDoubleSpinBox()
    area_input.setFont(QFont("Arial", 12))
    area_input.setMinimum(0)
    area_input.setMaximum(10000)
    area_input.setSingleStep(0.001)
    area_input.setDecimals(4)
    area_input.setValue(0)
    area_input.setMaximumWidth(140)
    area_input.setToolTip("输入电极面积（可选），用于计算单位面积电容")
    
    file_layout.addWidget(file_label)
    file_layout.addWidget(current_file_label)
    file_layout.addStretch()
    file_layout.addWidget(area_label)
    file_layout.addWidget(area_input)
    file_layout.addWidget(load_btn)
    
    return file_layout, current_file_label, load_btn, area_input


def create_cycles_table():
    """创建循环结果表格"""
    cycles_table = QTableWidget()
    cycles_table.setColumnCount(4)
    cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", "电容 (mF)", "备注"])
    cycles_table.setFont(QFont("Arial", 12))
    cycles_table.horizontalHeader().setFont(QFont("Arial", 12, QFont.Bold))
    cycles_table.setMaximumWidth(500)
    cycles_table.verticalHeader().setDefaultSectionSize(32)
    
    return cycles_table


def create_result_text_widget():
    """创建结果文本显示区域"""
    result_text = QTextEdit()
    result_text.setFont(QFont("Courier", 12))
    result_text.setReadOnly(True)
    result_text.setMaximumWidth(500)
    result_text.setMaximumHeight(350)
    
    return result_text


def create_matplotlib_canvas():
    """创建matplotlib图表画布"""
    figure = Figure(figsize=(8, 6), dpi=100)
    canvas = FigureCanvas(figure)
    
    canvas_widget = QWidget()
    canvas_layout = QVBoxLayout()
    
    try:
        toolbar = NavigationToolbar(canvas, None)
        canvas_layout.addWidget(toolbar)
    except Exception as e:
        print(f"警告：无法创建NavigationToolbar: {e}")
    
    canvas_layout.addWidget(canvas)
    canvas_layout.setContentsMargins(0, 0, 0, 0)
    canvas_widget.setLayout(canvas_layout)
    
    return figure, canvas, canvas_widget


def create_left_panel_layout(cycles_table, result_text):
    """创建左侧面板布局（表格和结果）"""
    left_layout = QVBoxLayout()
    
    title1 = QLabel("各循环电容值结果:")
    title1.setFont(QFont("Arial", 13, QFont.Bold))
    left_layout.addWidget(title1)
    
    subtitle1 = QLabel("(每行代表一轮循环，2 Segments)")
    subtitle1.setFont(QFont("Arial", 11))
    left_layout.addWidget(subtitle1)
    
    left_layout.addWidget(cycles_table)
    
    title2 = QLabel("\n最终结果:")
    title2.setFont(QFont("Arial", 13, QFont.Bold))
    left_layout.addWidget(title2)
    
    left_layout.addWidget(result_text)
    
    return left_layout


def create_right_panel_layout(canvas_widget):
    """创建右侧面板布局（图表）"""
    right_layout = QVBoxLayout()
    
    graph_label = QLabel("V-I曲线图:")
    graph_label.setFont(QFont("Arial", 13, QFont.Bold))
    right_layout.addWidget(graph_label)
    
    right_layout.addWidget(canvas_widget)
    
    return right_layout


def create_save_buttons_layout():
    """创建保存按钮布局"""
    save_layout = QHBoxLayout()
    
    save_png_btn = QPushButton("保存为PNG")
    save_png_btn.setFont(QFont("Arial", 10))
    save_png_btn.setEnabled(False)
    
    save_svg_btn = QPushButton("保存为SVG")
    save_svg_btn.setFont(QFont("Arial", 10))
    save_svg_btn.setEnabled(False)
    
    copy_clipboard_btn = QPushButton("复制到剪切板")
    copy_clipboard_btn.setFont(QFont("Arial", 10))
    copy_clipboard_btn.setEnabled(False)
    
    save_layout.addStretch()
    save_layout.addWidget(save_png_btn)
    save_layout.addWidget(save_svg_btn)
    save_layout.addWidget(copy_clipboard_btn)
    
    return save_layout, save_png_btn, save_svg_btn, copy_clipboard_btn
