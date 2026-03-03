# -*- coding: utf-8 -*-
"""
绘图配置对话框
用于调整绘图的字体大小、加粗等属性和颜色循环配置
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QCheckBox, QPushButton, QScrollArea, QWidget, QComboBox, QDoubleSpinBox
)
from PySide6.QtCore import Qt
import random


class PlotConfigDialog(QDialog):
    """绘图配置对话框"""
    
    def __init__(self, config, parent=None, color_config=None):
        """
        初始化对话框
        
        Args:
            config: 当前的绘图配置字典
            parent: 父窗口
            color_config: 当前的颜色配置字典
        """
        super().__init__(parent)
        self.config = config.copy() if config else {}
        self.color_config = color_config.copy() if color_config else {}
        self.scale_factor = 1.5
        self.init_ui()
        self.load_config()
        self.load_color_config()
        
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
        
        # 第五行：颜色配置（跨两列）
        color_group = self._create_color_config_group()
        grid_layout.addWidget(color_group, 4, 0, 1, 2)  # row=4, col=0, rowspan=1, colspan=2
        
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
    
    def _create_color_config_group(self):
        """
        创建颜色配置组
        
        Returns:
            QGroupBox对象
        """
        group = QGroupBox("颜色配置 (Color Config)")
        # 设置组标题字体大小
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)
        
        layout = QVBoxLayout()
        
        # 颜色模式选择
        mode_layout = QHBoxLayout()
        mode_label = QLabel("颜色模式:")
        mode_label_font = mode_label.font()
        mode_label_font.setPointSize(int(mode_label_font.pointSize() * self.scale_factor))
        mode_label.setFont(mode_label_font)
        mode_layout.addWidget(mode_label)
        
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem("default (默认颜色)")
        self.color_mode_combo.addItem("xkcd (xkcd颜色)")
        combo_font = self.color_mode_combo.font()
        combo_font.setPointSize(int(combo_font.pointSize() * self.scale_factor))
        self.color_mode_combo.setFont(combo_font)
        self.color_mode_combo.setMinimumHeight(int(30 * self.scale_factor))
        self.color_mode_combo.currentTextChanged.connect(self._on_color_mode_changed)
        mode_layout.addWidget(self.color_mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 随机种子布局
        seed_layout = QHBoxLayout()
        seed_label = QLabel("随机种子:")
        seed_label_font = seed_label.font()
        seed_label_font.setPointSize(int(seed_label_font.pointSize() * self.scale_factor))
        seed_label.setFont(seed_label_font)
        seed_layout.addWidget(seed_label)
        
        self.seed_spinbox = QSpinBox()
        self.seed_spinbox.setMinimum(0)
        self.seed_spinbox.setMaximum(2147483647)
        self.seed_spinbox.setValue(42)
        seed_spinbox_font = self.seed_spinbox.font()
        seed_spinbox_font.setPointSize(int(seed_spinbox_font.pointSize() * self.scale_factor))
        self.seed_spinbox.setFont(seed_spinbox_font)
        self.seed_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.seed_spinbox.setEnabled(False)  # 初始禁用
        seed_layout.addWidget(self.seed_spinbox)
        
        # 随机种子按钮
        random_seed_btn = QPushButton("获取随机种子")
        random_seed_btn.setFont(seed_spinbox_font)
        random_seed_btn.setMinimumHeight(int(30 * self.scale_factor))
        random_seed_btn.setMaximumWidth(int(150 * self.scale_factor))
        random_seed_btn.clicked.connect(self._generate_random_seed)
        random_seed_btn.setEnabled(False)  # 初始禁用
        seed_layout.addWidget(random_seed_btn)
        self.random_seed_btn = random_seed_btn  # 保存引用
        
        # 启用随机复选框
        self.enable_random_checkbox = QCheckBox("启用随机")
        checkbox_font = self.enable_random_checkbox.font()
        checkbox_font.setPointSize(int(checkbox_font.pointSize() * self.scale_factor))
        self.enable_random_checkbox.setFont(checkbox_font)
        self.enable_random_checkbox.setMinimumHeight(int(30 * self.scale_factor))
        self.enable_random_checkbox.setChecked(False)
        self.enable_random_checkbox.setEnabled(False)  # 初始禁用
        self.enable_random_checkbox.stateChanged.connect(self._on_enable_random_changed)
        seed_layout.addWidget(self.enable_random_checkbox)
        seed_layout.addStretch()
        layout.addLayout(seed_layout)
        
        # DeltaE最小值布局
        delta_e_layout = QHBoxLayout()
        delta_e_label = QLabel("ΔE最小值:")
        delta_e_label_font = delta_e_label.font()
        delta_e_label_font.setPointSize(int(delta_e_label_font.pointSize() * self.scale_factor))
        delta_e_label.setFont(delta_e_label_font)
        delta_e_layout.addWidget(delta_e_label)
        
        self.delta_e_spinbox = QDoubleSpinBox()
        self.delta_e_spinbox.setMinimum(1.0)
        self.delta_e_spinbox.setMaximum(100.0)
        self.delta_e_spinbox.setValue(20.0)
        self.delta_e_spinbox.setSingleStep(0.5)
        delta_e_spinbox_font = self.delta_e_spinbox.font()
        delta_e_spinbox_font.setPointSize(int(delta_e_spinbox_font.pointSize() * self.scale_factor))
        self.delta_e_spinbox.setFont(delta_e_spinbox_font)
        self.delta_e_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.delta_e_spinbox.setEnabled(False)  # 初始禁用
        delta_e_layout.addWidget(self.delta_e_spinbox)
        delta_e_layout.addStretch()
        layout.addLayout(delta_e_layout)
        
        group.setLayout(layout)
        return group
    
    def _generate_random_seed(self):
        """生成随机种子"""
        random_seed = random.randint(0, 2147483647)
        self.seed_spinbox.setValue(random_seed)
    
    def _on_color_mode_changed(self, text):
        """处理颜色模式变化"""
        is_xkcd = "xkcd" in text
        self.seed_spinbox.setEnabled(is_xkcd)
        self.random_seed_btn.setEnabled(is_xkcd)
        self.enable_random_checkbox.setEnabled(is_xkcd)
        self._on_enable_random_changed(0)  # 更新deltaE的启用状态
    
    def _on_enable_random_changed(self, state):
        """处理随机功能启用状态变化"""
        is_enabled = self.enable_random_checkbox.isChecked()
        is_xkcd = "xkcd" in self.color_mode_combo.currentText()
        self.delta_e_spinbox.setEnabled(is_enabled and is_xkcd)
    
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
    
    def load_color_config(self):
        """加载颜色配置到UI控件"""
        if not self.color_config:
            return
        
        # 加载颜色模式
        mode = self.color_config.get('mode', 'default')
        if mode == 'xkcd':
            self.color_mode_combo.setCurrentIndex(1)  # xkcd
        else:
            self.color_mode_combo.setCurrentIndex(0)  # default
        
        # 加载随机种子
        random_seed = self.color_config.get('random_seed', 42)
        self.seed_spinbox.setValue(random_seed)
        
        # 加载deltaE最小值
        delta_e_min = self.color_config.get('delta_e_min', 10.0)
        self.delta_e_spinbox.setValue(delta_e_min)
        
        # 加载启用随机
        enable_random = self.color_config.get('enable_random', False)
        self.enable_random_checkbox.setChecked(enable_random)
    
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
    
    def get_color_config(self):
        """获取颜色配置"""
        color_mode = "xkcd" if "xkcd" in self.color_mode_combo.currentText() else "default"
        
        return {
            'mode': color_mode,
            'random_seed': self.seed_spinbox.value(),
            'delta_e_min': self.delta_e_spinbox.value(),
            'enable_random': self.enable_random_checkbox.isChecked()
        }
    
    def reset_defaults(self):
        """重置为默认值"""
        from config_manager import DEFAULT_CONFIG
        default_plot_config = DEFAULT_CONFIG['plot']
        default_color_config = DEFAULT_CONFIG.get('colors', {})
        
        # 重置绘图配置
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
        
        # 重置颜色配置
        if default_color_config:
            mode = default_color_config.get('mode', 'default')
            if mode == 'xkcd':
                self.color_mode_combo.setCurrentIndex(1)
            else:
                self.color_mode_combo.setCurrentIndex(0)
            
            self.seed_spinbox.setValue(default_color_config.get('random_seed', 42))
            self.delta_e_spinbox.setValue(default_color_config.get('delta_e_min', 10.0))
            self.enable_random_checkbox.setChecked(default_color_config.get('enable_random', False))
