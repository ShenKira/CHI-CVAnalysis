"""
UI组件和样式配置
包含所有的UI元素创建和样式设置
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QDoubleSpinBox, QHeaderView, QAbstractItemView, QSizePolicy,
    QCheckBox,
)
from PySide6.QtGui import QFont
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvasBase
from matplotlib.backends.backend_qt import NavigationToolbar2QT


class NavigationToolbar(NavigationToolbar2QT):
    """兼容PySide6的NavigationToolbar"""
    pass


class AspectRatioCanvas(_FigureCanvasBase):
    """FigureCanvas subclass that auto-resizes figure to fill the widget."""

    def __init__(self, figure):
        super().__init__(figure)
        self._resizing = False
        self._lock_figure_size = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def resizeEvent(self, event):
        """Override to keep figure size in sync with widget size."""
        super().resizeEvent(event)
        if self._resizing or self._lock_figure_size:
            return
        self._resizing = True
        try:
            w, h = self.width(), self.height()
            if w >= 10 and h >= 10:
                dpi = self.figure.dpi
                self.figure.set_size_inches(w / dpi, h / dpi)
        finally:
            self._resizing = False


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

    multi_file_cb = QCheckBox("多文件")
    multi_file_cb.setFont(QFont("Arial", 12))
    multi_file_cb.setToolTip("允许同时选择多个CV文件，合并绘图并连续编号")
    
    file_layout.addWidget(file_label)
    file_layout.addWidget(current_file_label)
    file_layout.addStretch()
    file_layout.addWidget(area_label)
    file_layout.addWidget(area_input)
    file_layout.addWidget(multi_file_cb)
    file_layout.addWidget(load_btn)
    
    return file_layout, current_file_label, load_btn, area_input, area_label, multi_file_cb


def create_cycles_table():
    """创建循环结果表格"""
    cycles_table = QTableWidget()
    cycles_table.setColumnCount(5)
    cycles_table.setHorizontalHeaderLabels(["循环", "面积 (C)", "电容 (mF)", "备注", "绘图"])
    cycles_table.setFont(QFont("Arial", 12))
    cycles_table.horizontalHeader().setFont(QFont("Arial", 12, QFont.Weight.Bold))
    cycles_table.verticalHeader().setDefaultSectionSize(32)
    
    return cycles_table


def create_result_text_widget():
    """创建结果表格显示区域"""
    results_table = QTableWidget()
    results_table.setColumnCount(2)
    results_table.setHorizontalHeaderLabels(["参数", "值"])
    results_table.setFont(QFont("Arial", 11))
    results_table.horizontalHeader().setFont(QFont("Arial", 11, QFont.Weight.Bold))
    results_table.setMaximumHeight(350)
    results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    results_table.setSelectionMode(QAbstractItemView.NoSelection)
    results_table.verticalHeader().setVisible(False)
    results_table.verticalHeader().setDefaultSectionSize(26)
    results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    return results_table


def create_matplotlib_canvas():
    """创建matplotlib图表画布"""
    figure = Figure(figsize=(8, 6), dpi=100)
    canvas = AspectRatioCanvas(figure)
    
    canvas_widget = QWidget()
    canvas_layout = QVBoxLayout()
    
    try:
        toolbar = NavigationToolbar(canvas, None)
        canvas_layout.addWidget(toolbar)
    except Exception as e:
        print(f"警告：无法创建NavigationToolbar: {e}")
    
    canvas_layout.addWidget(canvas, stretch=1)
    canvas_layout.setContentsMargins(0, 0, 0, 0)
    canvas_widget.setLayout(canvas_layout)
    canvas_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    return figure, canvas, canvas_widget


def create_left_panel_layout(cycles_table, results_table):
    """创建左侧面板布局（表格和结果）"""
    left_layout = QVBoxLayout()

    title1 = QLabel("各循环电容值结果:")
    title1.setFont(QFont("Arial", 13, QFont.Weight.Bold))
    left_layout.addWidget(title1)

    subtitle1 = QLabel("(每行代表一轮循环，2 Segments)")
    subtitle1.setFont(QFont("Arial", 11))
    left_layout.addWidget(subtitle1)

    left_layout.addWidget(cycles_table)

    # 重排序按钮
    reorder_btn = QPushButton("重排序")
    reorder_btn.setFont(QFont("Arial", 10))
    reorder_btn.setFixedHeight(30)
    reorder_btn.setToolTip("将当前勾选的Cycle重新从1开始编号")
    left_layout.addWidget(reorder_btn)

    title2 = QLabel("\n最终结果:")
    title2.setFont(QFont("Arial", 13, QFont.Weight.Bold))
    left_layout.addWidget(title2)

    left_layout.addWidget(results_table)

    return left_layout, reorder_btn


def create_right_panel_layout(canvas_widget):
    """创建右侧面板布局（图表）"""
    right_layout = QVBoxLayout()
    
    # 创建V-I曲线图标签和配置按钮的水平布局
    graph_header_layout = QHBoxLayout()
    
    graph_label = QLabel("V-I曲线图:")
    graph_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
    graph_header_layout.addWidget(graph_label)
    
    # 添加伸缩空间使标签在左侧，按钮在右侧
    graph_header_layout.addStretch()
    
    # 创建配置按钮（稍后在cv_gui.py中连接信号）
    config_btn = QPushButton("绘图配置")
    config_btn.setFont(QFont("Arial", 9))
    config_btn.setFixedWidth(90)  # 缩小按钮宽度
    #config_btn.setEnabled(False)  # 初始禁用，等数据加载后启用
    graph_header_layout.addWidget(config_btn)
    
    right_layout.addLayout(graph_header_layout)
    
    right_layout.addWidget(canvas_widget)
    
    return right_layout, config_btn


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


def create_eis_left_panel_layout(eis_results_table):
    """创建EIS左侧面板布局（元数据表格）"""
    left_layout = QVBoxLayout()

    title = QLabel("EIS 实验信息:")
    title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
    left_layout.addWidget(title)

    subtitle = QLabel("(A.C. Impedance 数据)")
    subtitle.setFont(QFont("Arial", 11))
    left_layout.addWidget(subtitle)

    left_layout.addWidget(eis_results_table)
    left_layout.addStretch()

    return left_layout
