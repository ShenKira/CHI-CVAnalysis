# -*- coding: utf-8 -*-
"""
绘图配置对话框
用于调整绘图的字体大小、加粗等属性
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QCheckBox, QPushButton, QScrollArea, QWidget
)
from PySide6.QtCore import Qt


class PlotConfigDialog(QDialog):
    """绘图配置对话框"""
    
    def __init__(self, config, parent=None):
        """
        初始化对话框
        
        Args:
            config: 当前的绘图配置字典
            parent: 父窗口
        """
        super().__init__(parent)
        self.config = config.copy() if config else {}
        self.scale_factor = 1.5
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("绘图配置")
        self.setGeometry(100, 100, int(500 * self.scale_factor), int(500 * self.scale_factor))
        
        main_layout = QVBoxLayout()
        
        # 创建滚动区域以容纳所有控件
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # 使用网格布局实现两列
        grid_layout = QGridLayout()
        
        # 第一行：标题配置（跨两列）
        title_group = self._create_config_group("标题 (Title)", "title")
        grid_layout.addWidget(title_group, 0, 0, 1, 2)  # row=0, col=0, rowspan=1, colspan=2
        
        # 第二行：X轴标签 | Y轴标签
        xlabel_group = self._create_config_group("X轴标签 (X Label)", "xlabel")
        ylabel_group = self._create_config_group("Y轴标签 (Y Label)", "ylabel")
        grid_layout.addWidget(xlabel_group, 1, 0)
        grid_layout.addWidget(ylabel_group, 1, 1)
        
        # 第三行：X轴刻度 | Y轴刻度
        xtick_group = self._create_config_group("X轴刻度数字 (X Tick)", "xtick")
        ytick_group = self._create_config_group("Y轴刻度数字 (Y Tick)", "ytick")
        grid_layout.addWidget(xtick_group, 2, 0)
        grid_layout.addWidget(ytick_group, 2, 1)
        
        # 第四行：图注 | 左下角文字
        legend_group = self._create_config_group("图注 (Legend)", "legend")
        text_group = self._create_config_group("左下角文字 (Text)", "text")
        grid_layout.addWidget(legend_group, 3, 0)
        grid_layout.addWidget(text_group, 3, 1)
        
        scroll_layout.addLayout(grid_layout)
        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        
        main_layout.addWidget(scroll)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 重置按钮
        reset_btn = QPushButton("重置为默认")
        reset_btn.clicked.connect(self.reset_defaults)
        # 放大按钮字体和高度
        btn_font = reset_btn.font()
        btn_font.setPointSize(int(btn_font.pointSize() * self.scale_factor))
        reset_btn.setFont(btn_font)
        reset_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # 确定按钮
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_font = ok_btn.font()
        ok_font.setPointSize(int(ok_font.pointSize() * self.scale_factor))
        ok_btn.setFont(ok_font)
        ok_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(ok_btn)
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_font = cancel_btn.font()
        cancel_font.setPointSize(int(cancel_font.pointSize() * self.scale_factor))
        cancel_btn.setFont(cancel_font)
        cancel_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def _create_config_group(self, title, key):
        """
        创建配置组
        
        Args:
            title: 组标题
            key: 配置键名
            
        Returns:
            QGroupBox对象
        """
        group = QGroupBox(title)
        # 设置组标题字体大小
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)
        
        layout = QVBoxLayout()
        
        # 字体大小
        size_layout = QHBoxLayout()
        label = QLabel("字体大小:")
        # 放大标签字体
        label_font = label.font()
        label_font.setPointSize(int(label_font.pointSize() * self.scale_factor))
        label.setFont(label_font)
        size_layout.addWidget(label)
        
        size_spinbox = QSpinBox()
        size_spinbox.setMinimum(6)
        size_spinbox.setMaximum(32)
        size_spinbox.setObjectName(f"{key}_fontsize")
        # 放大spinbox字体
        spinbox_font = size_spinbox.font()
        spinbox_font.setPointSize(int(spinbox_font.pointSize() * self.scale_factor))
        size_spinbox.setFont(spinbox_font)
        # 增加spinbox高度
        size_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        size_layout.addWidget(size_spinbox)
        size_layout.addStretch()
        layout.addLayout(size_layout)
        
        # 加粗选项
        bold_checkbox = QCheckBox("加粗")
        bold_checkbox.setObjectName(f"{key}_bold")
        # 放大checkbox字体
        checkbox_font = bold_checkbox.font()
        checkbox_font.setPointSize(int(checkbox_font.pointSize() * self.scale_factor))
        bold_checkbox.setFont(checkbox_font)
        # 增加checkbox高度
        bold_checkbox.setMinimumHeight(int(30 * self.scale_factor))
        layout.addWidget(bold_checkbox)
        
        group.setLayout(layout)
        return group
    
    def load_config(self):
        """加载配置到UI控件"""
        for key, value in self.config.items():
            if isinstance(value, dict):
                # 字体大小
                fontsize = value.get('fontsize', 10)
                size_spinbox = self.findChild(QSpinBox, f"{key}_fontsize")
                if size_spinbox:
                    size_spinbox.setValue(fontsize)
                
                # 加粗
                bold = value.get('bold', False)
                bold_checkbox = self.findChild(QCheckBox, f"{key}_bold")
                if bold_checkbox:
                    bold_checkbox.setChecked(bold)
    
    def get_config(self):
        """获取当前配置"""
        config = {}
        
        for key in ['title', 'xlabel', 'ylabel', 'xtick', 'ytick', 'legend', 'text']:
            size_spinbox = self.findChild(QSpinBox, f"{key}_fontsize")
            bold_checkbox = self.findChild(QCheckBox, f"{key}_bold")
            
            if size_spinbox and bold_checkbox:
                config[key] = {
                    'fontsize': size_spinbox.value(),
                    'bold': bold_checkbox.isChecked()
                }
        
        return config
    
    def reset_defaults(self):
        """重置为默认值"""
        from config_manager import DEFAULT_CONFIG
        default_plot_config = DEFAULT_CONFIG['plot']
        
        for key in ['title', 'xlabel', 'ylabel', 'xtick', 'ytick', 'legend', 'text']:
            if key in default_plot_config:
                fontsize = default_plot_config[key].get('fontsize', 10)
                bold = default_plot_config[key].get('bold', False)
                
                size_spinbox = self.findChild(QSpinBox, f"{key}_fontsize")
                bold_checkbox = self.findChild(QCheckBox, f"{key}_bold")
                
                if size_spinbox:
                    size_spinbox.setValue(fontsize)
                if bold_checkbox:
                    bold_checkbox.setChecked(bold)
