# -*- coding: utf-8 -*-
"""
绘图配置对话框
用于调整绘图的字体大小、加粗等属性、颜色循环配置、EIS曲线样式和线宽
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QSpinBox, QCheckBox, QPushButton, QScrollArea, QWidget, QComboBox,
    QDoubleSpinBox, QColorDialog,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt
import random


class PlotConfigDialog(QDialog):
    """绘图配置对话框"""

    def __init__(self, config, parent=None, color_config=None, eis_config=None,
                 axis_config=None, grid_config=None, tick_config=None):
        super().__init__(parent)
        self.config = config.copy() if config else {}
        self.color_config = color_config.copy() if color_config else {}
        self.eis_config = eis_config.copy() if eis_config else {}
        self.axis_config = axis_config.copy() if axis_config else {}
        self.grid_config = grid_config.copy() if grid_config else {}
        self.tick_config = tick_config.copy() if tick_config else {}
        self.scale_factor = 1.5
        self.init_ui()
        self.load_config()
        self.load_color_config()
        self.load_eis_config()
        self.load_axis_grid_tick_config()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("绘图配置")
        self.setGeometry(100, 100, int(500 * self.scale_factor), int(550 * self.scale_factor))

        main_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()

        grid_layout = QGridLayout()

        # Row 0: 标题
        title_group = self._create_config_group("标题 (Title)", "title")
        grid_layout.addWidget(title_group, 0, 0, 1, 2)

        # Row 1: X轴标签 | Y轴标签
        xlabel_group = self._create_config_group("X轴标签 (X Label)", "xlabel")
        ylabel_group = self._create_config_group("Y轴标签 (Y Label)", "ylabel")
        grid_layout.addWidget(xlabel_group, 1, 0)
        grid_layout.addWidget(ylabel_group, 1, 1)

        # Row 2: X轴刻度 | Y轴刻度
        xtick_group = self._create_config_group("X轴刻度数字 (X Tick)", "xtick")
        ytick_group = self._create_config_group("Y轴刻度数字 (Y Tick)", "ytick")
        grid_layout.addWidget(xtick_group, 2, 0)
        grid_layout.addWidget(ytick_group, 2, 1)

        # Row 3: 图注 | 左下角文字
        legend_group = self._create_config_group("图注 (Legend)", "legend")
        text_group = self._create_config_group("左下角文字 (Text)", "text")
        grid_layout.addWidget(legend_group, 3, 0)
        grid_layout.addWidget(text_group, 3, 1)

        # Row 4: 全局线宽（跨两列）
        lw_group = self._create_line_width_group()
        grid_layout.addWidget(lw_group, 4, 0, 1, 2)

        # Row 5: CV颜色配置（跨两列）
        color_group = self._create_color_config_group()
        grid_layout.addWidget(color_group, 5, 0, 1, 2)

        # Row 6: EIS绘图配置（跨两列）
        eis_group = self._create_eis_config_group()
        grid_layout.addWidget(eis_group, 6, 0, 1, 2)

        # Row 7: 坐标轴轴线 | 网格线
        axis_group = self._create_axis_config_group()
        grid_layout.addWidget(axis_group, 7, 0)
        grid_group = self._create_grid_config_group()
        grid_layout.addWidget(grid_group, 7, 1)

        # Row 8: 刻度线（跨两列）
        tick_group = self._create_tick_config_group()
        grid_layout.addWidget(tick_group, 8, 0, 1, 2)

        scroll_layout.addLayout(grid_layout)
        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)

        main_layout.addWidget(scroll)

        # 按钮
        button_layout = QHBoxLayout()

        reset_btn = QPushButton("重置为默认")
        reset_btn.clicked.connect(self.reset_defaults)
        btn_font = reset_btn.font()
        btn_font.setPointSize(int(btn_font.pointSize() * self.scale_factor))
        reset_btn.setFont(btn_font)
        reset_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(reset_btn)

        button_layout.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        ok_font = ok_btn.font()
        ok_font.setPointSize(int(ok_font.pointSize() * self.scale_factor))
        ok_btn.setFont(ok_font)
        ok_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_font = cancel_btn.font()
        cancel_font.setPointSize(int(cancel_font.pointSize() * self.scale_factor))
        cancel_btn.setFont(cancel_font)
        cancel_btn.setMinimumHeight(int(40 * self.scale_factor))
        button_layout.addWidget(cancel_btn)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    # ── Font config group ──────────────────────────────────────────────

    def _create_config_group(self, title, key):
        group = QGroupBox(title)
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QVBoxLayout()

        size_layout = QHBoxLayout()
        label = QLabel("字体大小:")
        label_font = label.font()
        label_font.setPointSize(int(label_font.pointSize() * self.scale_factor))
        label.setFont(label_font)
        size_layout.addWidget(label)

        size_spinbox = QSpinBox()
        size_spinbox.setMinimum(6)
        size_spinbox.setMaximum(32)
        size_spinbox.setObjectName(f"{key}_fontsize")
        spinbox_font = size_spinbox.font()
        spinbox_font.setPointSize(int(spinbox_font.pointSize() * self.scale_factor))
        size_spinbox.setFont(spinbox_font)
        size_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        size_layout.addWidget(size_spinbox)
        size_layout.addStretch()
        layout.addLayout(size_layout)

        bold_checkbox = QCheckBox("加粗")
        bold_checkbox.setObjectName(f"{key}_bold")
        checkbox_font = bold_checkbox.font()
        checkbox_font.setPointSize(int(checkbox_font.pointSize() * self.scale_factor))
        bold_checkbox.setFont(checkbox_font)
        bold_checkbox.setMinimumHeight(int(30 * self.scale_factor))
        layout.addWidget(bold_checkbox)

        group.setLayout(layout)
        return group

    # ── Line width group ───────────────────────────────────────────────

    def _create_line_width_group(self):
        group = QGroupBox("全局线宽 (Line Width)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QHBoxLayout()

        lbl = QLabel("线宽:")
        lbl_font = lbl.font()
        lbl_font.setPointSize(int(lbl_font.pointSize() * self.scale_factor))
        lbl.setFont(lbl_font)
        layout.addWidget(lbl)

        self.line_width_spinbox = QDoubleSpinBox()
        self.line_width_spinbox.setRange(0.5, 10.0)
        self.line_width_spinbox.setSingleStep(0.5)
        self.line_width_spinbox.setDecimals(1)
        self.line_width_spinbox.setValue(2.0)
        lw_font = self.line_width_spinbox.font()
        lw_font.setPointSize(int(lw_font.pointSize() * self.scale_factor))
        self.line_width_spinbox.setFont(lw_font)
        self.line_width_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.line_width_spinbox.setObjectName("line_width")
        layout.addWidget(self.line_width_spinbox)

        layout.addStretch()
        group.setLayout(layout)
        return group

    # ── CV color config group ──────────────────────────────────────────

    def _create_color_config_group(self):
        group = QGroupBox("CV 颜色配置 (Color Config)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QVBoxLayout()

        mode_layout = QHBoxLayout()
        mode_label = QLabel("颜色模式:")
        mode_label_font = mode_label.font()
        mode_label_font.setPointSize(int(mode_label_font.pointSize() * self.scale_factor))
        mode_label.setFont(mode_label_font)
        mode_layout.addWidget(mode_label)

        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem("default (默认颜色)")
        self.color_mode_combo.addItem("xkcd (xkcd颜色)")
        self.color_mode_combo.addItem("custom (自定义)")
        combo_font = self.color_mode_combo.font()
        combo_font.setPointSize(int(combo_font.pointSize() * self.scale_factor))
        self.color_mode_combo.setFont(combo_font)
        self.color_mode_combo.setMinimumHeight(int(30 * self.scale_factor))
        self.color_mode_combo.currentTextChanged.connect(self._on_color_mode_changed)
        mode_layout.addWidget(self.color_mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

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
        self.seed_spinbox.setEnabled(False)
        seed_layout.addWidget(self.seed_spinbox)

        random_seed_btn = QPushButton("获取随机种子")
        random_seed_btn.setFont(seed_spinbox_font)
        random_seed_btn.setMinimumHeight(int(30 * self.scale_factor))
        random_seed_btn.setMaximumWidth(int(150 * self.scale_factor))
        random_seed_btn.clicked.connect(self._generate_random_seed)
        random_seed_btn.setEnabled(False)
        seed_layout.addWidget(random_seed_btn)
        self.random_seed_btn = random_seed_btn

        self.enable_random_checkbox = QCheckBox("启用随机")
        checkbox_font = self.enable_random_checkbox.font()
        checkbox_font.setPointSize(int(checkbox_font.pointSize() * self.scale_factor))
        self.enable_random_checkbox.setFont(checkbox_font)
        self.enable_random_checkbox.setMinimumHeight(int(30 * self.scale_factor))
        self.enable_random_checkbox.setChecked(False)
        self.enable_random_checkbox.setEnabled(False)
        self.enable_random_checkbox.stateChanged.connect(self._on_enable_random_changed)
        seed_layout.addWidget(self.enable_random_checkbox)
        seed_layout.addStretch()
        layout.addLayout(seed_layout)

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
        self.delta_e_spinbox.setEnabled(False)
        delta_e_layout.addWidget(self.delta_e_spinbox)
        delta_e_layout.addStretch()
        layout.addLayout(delta_e_layout)

        # ── 自定义颜色网格 (20个颜色选择器) ──
        self._custom_color_container = QWidget()
        custom_layout = QVBoxLayout()
        custom_layout.setContentsMargins(0, 0, 0, 0)

        custom_title = QLabel("自定义颜色序列 (点击修改):")
        ct_font = custom_title.font()
        ct_font.setPointSize(int(ct_font.pointSize() * self.scale_factor))
        custom_title.setFont(ct_font)
        custom_layout.addWidget(custom_title)

        self._custom_color_btns = []
        self._custom_color_hexes = []
        grid = QGridLayout()
        grid.setSpacing(4)
        for i in range(20):
            row, col = divmod(i, 5)
            btn = QPushButton()
            btn.setFixedSize(int(36 * self.scale_factor), int(28 * self.scale_factor))
            btn.setObjectName(f"custom_color_{i}")
            btn.clicked.connect(lambda checked, idx=i: self._pick_custom_color(idx))
            grid.addWidget(btn, row, col)
            self._custom_color_btns.append(btn)
            self._custom_color_hexes.append("#000000")  # placeholder

        custom_layout.addLayout(grid)
        self._custom_color_container.setLayout(custom_layout)
        self._custom_color_container.setVisible(False)
        layout.addWidget(self._custom_color_container)

        group.setLayout(layout)
        return group

    # ── EIS config group (with color palette picker) ───────────────────

    _MARKER_STYLES = [
        ("o", "圆形 ●"),
        ("s", "方形 ■"),
        ("^", "上三角 ▲"),
        ("v", "下三角 ▼"),
        ("D", "菱形 ◆"),
        ("*", "星形 ★"),
        ("+", "十字 +"),
        ("x", "叉号 ×"),
        ("p", "五边形 ⬟"),
        ("h", "六边形 ⬡"),
    ]

    def _create_eis_config_group(self):
        group = QGroupBox("EIS 绘图配置 (EIS Plot)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QVBoxLayout()

        for mode_key, mode_label in [("nyquist", "Nyquist (Z'-Z'')"), ("bode", "Bode (Phase-Freq)")]:
            sub = QGroupBox(mode_label)
            sub_font = sub.font()
            sub_font.setPointSize(int(sub_font.pointSize() * self.scale_factor))
            sub.setFont(sub_font)

            sub_layout = QGridLayout()

            # Row 0: color picker button
            lbl_color = QLabel("曲线颜色:")
            lbl_color.setFont(sub_font)
            sub_layout.addWidget(lbl_color, 0, 0)

            color_btn = QPushButton()
            color_btn.setObjectName(f"eis_{mode_key}_color_btn")
            color_btn.setFixedSize(int(80 * self.scale_factor), int(30 * self.scale_factor))
            color_btn.clicked.connect(lambda checked, mk=mode_key: self._pick_eis_color(mk))
            sub_layout.addWidget(color_btn, 0, 1)

            # hidden label to store hex value
            color_hex_label = QLabel("#1f77b4")
            color_hex_label.setObjectName(f"eis_{mode_key}_color_hex")
            color_hex_label.setVisible(False)
            sub_layout.addWidget(color_hex_label, 0, 2)

            # Row 0: marker style
            lbl_marker = QLabel("Marker:")
            lbl_marker.setFont(sub_font)
            sub_layout.addWidget(lbl_marker, 0, 3)

            combo_marker = QComboBox()
            combo_marker.setFont(sub_font)
            combo_marker.setMinimumHeight(int(30 * self.scale_factor))
            for code, name in self._MARKER_STYLES:
                combo_marker.addItem(name, code)
            combo_marker.setObjectName(f"eis_{mode_key}_marker")
            sub_layout.addWidget(combo_marker, 0, 4)

            # Row 1: marker size
            lbl_size = QLabel("Marker大小:")
            lbl_size.setFont(sub_font)
            sub_layout.addWidget(lbl_size, 1, 0)

            spin_size = QSpinBox()
            spin_size.setFont(sub_font)
            spin_size.setRange(1, 20)
            spin_size.setMinimumHeight(int(30 * self.scale_factor))
            spin_size.setObjectName(f"eis_{mode_key}_marker_size")
            sub_layout.addWidget(spin_size, 1, 1)

            # Row 1: |Z| color picker (Bode only)
            if mode_key == 'bode':
                lbl_z_color = QLabel("|Z| 颜色:")
                lbl_z_color.setFont(sub_font)
                sub_layout.addWidget(lbl_z_color, 1, 3)

                z_color_btn = QPushButton()
                z_color_btn.setObjectName("eis_bode_z_color_btn")
                z_color_btn.setFixedSize(int(80 * self.scale_factor), int(30 * self.scale_factor))
                z_color_btn.clicked.connect(lambda checked: self._pick_eis_color('bode_z'))
                sub_layout.addWidget(z_color_btn, 1, 4)

                z_color_hex = QLabel("#2ca02c")
                z_color_hex.setObjectName("eis_bode_z_color_hex")
                z_color_hex.setVisible(False)
                sub_layout.addWidget(z_color_hex, 1, 5)

                # Row 2: 特征频率竖线颜色
                lbl_cf_color = QLabel("特征频率线颜色:")
                lbl_cf_color.setFont(sub_font)
                sub_layout.addWidget(lbl_cf_color, 2, 0)

                cf_color_btn = QPushButton()
                cf_color_btn.setObjectName("eis_bode_char_freq_color_btn")
                cf_color_btn.setFixedSize(int(80 * self.scale_factor), int(30 * self.scale_factor))
                cf_color_btn.clicked.connect(lambda checked: self._pick_eis_color('bode_char_freq'))
                sub_layout.addWidget(cf_color_btn, 2, 1)

                cf_color_hex = QLabel("#d62728")
                cf_color_hex.setObjectName("eis_bode_char_freq_color_hex")
                cf_color_hex.setVisible(False)
                sub_layout.addWidget(cf_color_hex, 2, 2)

                # Row 2: 特征频率竖线粗细
                lbl_cf_lw = QLabel("特征频率线粗细:")
                lbl_cf_lw.setFont(sub_font)
                sub_layout.addWidget(lbl_cf_lw, 2, 3)

                spin_cf_lw = QDoubleSpinBox()
                spin_cf_lw.setFont(sub_font)
                spin_cf_lw.setRange(0.5, 10.0)
                spin_cf_lw.setSingleStep(0.5)
                spin_cf_lw.setDecimals(1)
                spin_cf_lw.setMinimumHeight(int(30 * self.scale_factor))
                spin_cf_lw.setObjectName("eis_bode_char_freq_line_width")
                sub_layout.addWidget(spin_cf_lw, 2, 4)

            sub.setLayout(sub_layout)
            layout.addWidget(sub)

        group.setLayout(layout)
        return group

    def _pick_eis_color(self, mode_key):
        """打开调色盘选择EIS曲线颜色"""
        hex_label = self.findChild(QLabel, f"eis_{mode_key}_color_hex")
        btn = self.findChild(QPushButton, f"eis_{mode_key}_color_btn")

        current_hex = hex_label.text() if hex_label else "#1f77b4"
        current_color = QColor(current_hex)

        color = QColorDialog.getColor(current_color, self, f"选择 {mode_key} 曲线颜色")
        if color.isValid():
            hex_val = color.name()
            if hex_label:
                hex_label.setText(hex_val)
            if btn:
                btn.setStyleSheet(f"background-color: {hex_val}; border: 1px solid #888;")

    # ── Axis / Grid / Tick config groups ──────────────────────────────

    def _create_axis_config_group(self):
        group = QGroupBox("坐标轴轴线 (Axis Spines)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QHBoxLayout()

        lbl = QLabel("轴线粗细:")
        lbl_font = lbl.font()
        lbl_font.setPointSize(int(lbl_font.pointSize() * self.scale_factor))
        lbl.setFont(lbl_font)
        layout.addWidget(lbl)

        self.axis_linewidth_spinbox = QDoubleSpinBox()
        self.axis_linewidth_spinbox.setRange(0.5, 10.0)
        self.axis_linewidth_spinbox.setSingleStep(0.5)
        self.axis_linewidth_spinbox.setDecimals(1)
        self.axis_linewidth_spinbox.setValue(1.5)
        sp_font = self.axis_linewidth_spinbox.font()
        sp_font.setPointSize(int(sp_font.pointSize() * self.scale_factor))
        self.axis_linewidth_spinbox.setFont(sp_font)
        self.axis_linewidth_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.axis_linewidth_spinbox.setObjectName("axis_linewidth")
        layout.addWidget(self.axis_linewidth_spinbox)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _create_grid_config_group(self):
        group = QGroupBox("网格线 (Grid)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QGridLayout()

        # Row 0: 颜色
        lbl_color = QLabel("网格颜色:")
        lbl_color.setFont(title_font)
        layout.addWidget(lbl_color, 0, 0)

        self.grid_color_btn = QPushButton()
        self.grid_color_btn.setObjectName("grid_color_btn")
        self.grid_color_btn.setFixedSize(int(80 * self.scale_factor), int(30 * self.scale_factor))
        self.grid_color_btn.clicked.connect(lambda: self._pick_grid_color())
        layout.addWidget(self.grid_color_btn, 0, 1)

        self.grid_color_hex = QLabel("#cccccc")
        self.grid_color_hex.setObjectName("grid_color_hex")
        self.grid_color_hex.setVisible(False)
        layout.addWidget(self.grid_color_hex, 0, 2)

        # Row 1: 粗细
        lbl_lw = QLabel("网格粗细:")
        lbl_lw.setFont(title_font)
        layout.addWidget(lbl_lw, 1, 0)

        self.grid_linewidth_spinbox = QDoubleSpinBox()
        self.grid_linewidth_spinbox.setRange(0.1, 5.0)
        self.grid_linewidth_spinbox.setSingleStep(0.2)
        self.grid_linewidth_spinbox.setDecimals(1)
        self.grid_linewidth_spinbox.setValue(0.8)
        sp_font = self.grid_linewidth_spinbox.font()
        sp_font.setPointSize(int(sp_font.pointSize() * self.scale_factor))
        self.grid_linewidth_spinbox.setFont(sp_font)
        self.grid_linewidth_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.grid_linewidth_spinbox.setObjectName("grid_linewidth")
        layout.addWidget(self.grid_linewidth_spinbox, 1, 1)

        layout.setColumnStretch(2, 1)
        group.setLayout(layout)
        return group

    def _pick_grid_color(self):
        current_hex = self.grid_color_hex.text()
        color = QColorDialog.getColor(QColor(current_hex), self, "选择网格颜色")
        if color.isValid():
            hex_val = color.name()
            self.grid_color_hex.setText(hex_val)
            self.grid_color_btn.setStyleSheet(f"background-color: {hex_val}; border: 1px solid #888;")

    def _create_tick_config_group(self):
        group = QGroupBox("刻度线 (Ticks)")
        title_font = group.font()
        title_font.setPointSize(int(title_font.pointSize() * self.scale_factor))
        group.setFont(title_font)

        layout = QGridLayout()

        # Row 0: 方向
        lbl_dir = QLabel("方向:")
        lbl_dir.setFont(title_font)
        layout.addWidget(lbl_dir, 0, 0)

        self.tick_dir_combo = QComboBox()
        self.tick_dir_combo.addItem("朝内 (in)", "in")
        self.tick_dir_combo.addItem("朝外 (out)", "out")
        self.tick_dir_combo.addItem("双向 (inout)", "inout")
        combo_font = self.tick_dir_combo.font()
        combo_font.setPointSize(int(combo_font.pointSize() * self.scale_factor))
        self.tick_dir_combo.setFont(combo_font)
        self.tick_dir_combo.setMinimumHeight(int(30 * self.scale_factor))
        self.tick_dir_combo.setObjectName("tick_direction")
        layout.addWidget(self.tick_dir_combo, 0, 1)

        # Row 0: 粗细
        lbl_tw = QLabel("刻度粗细:")
        lbl_tw.setFont(title_font)
        layout.addWidget(lbl_tw, 0, 2)

        self.tick_width_spinbox = QDoubleSpinBox()
        self.tick_width_spinbox.setRange(0.5, 5.0)
        self.tick_width_spinbox.setSingleStep(0.5)
        self.tick_width_spinbox.setDecimals(1)
        self.tick_width_spinbox.setValue(1.5)
        sp_font = self.tick_width_spinbox.font()
        sp_font.setPointSize(int(sp_font.pointSize() * self.scale_factor))
        self.tick_width_spinbox.setFont(sp_font)
        self.tick_width_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.tick_width_spinbox.setObjectName("tick_width")
        layout.addWidget(self.tick_width_spinbox, 0, 3)

        # Row 1: 长度
        lbl_tl = QLabel("刻度长度:")
        lbl_tl.setFont(title_font)
        layout.addWidget(lbl_tl, 1, 0)

        self.tick_length_spinbox = QDoubleSpinBox()
        self.tick_length_spinbox.setRange(1.0, 20.0)
        self.tick_length_spinbox.setSingleStep(1.0)
        self.tick_length_spinbox.setDecimals(1)
        self.tick_length_spinbox.setValue(6.0)
        sp_font2 = self.tick_length_spinbox.font()
        sp_font2.setPointSize(int(sp_font2.pointSize() * self.scale_factor))
        self.tick_length_spinbox.setFont(sp_font2)
        self.tick_length_spinbox.setMinimumHeight(int(30 * self.scale_factor))
        self.tick_length_spinbox.setObjectName("tick_length")
        layout.addWidget(self.tick_length_spinbox, 1, 1)

        group.setLayout(layout)
        return group

    # ── Load / Get / Reset ─────────────────────────────────────────────

    def _generate_random_seed(self):
        random_seed = random.randint(0, 2147483647)
        self.seed_spinbox.setValue(random_seed)

    def _on_color_mode_changed(self, text):
        is_xkcd = "xkcd" in text
        is_custom = "custom" in text
        self.seed_spinbox.setEnabled(is_xkcd)
        self.random_seed_btn.setEnabled(is_xkcd)
        self.enable_random_checkbox.setEnabled(is_xkcd)
        self._on_enable_random_changed(0)
        self._custom_color_container.setVisible(is_custom)

    def _pick_custom_color(self, idx):
        """打开调色盘选择自定义颜色"""
        current = QColor(self._custom_color_hexes[idx])
        color = QColorDialog.getColor(current, self, f"选择颜色 #{idx + 1}")
        if color.isValid():
            hex_val = color.name()
            self._custom_color_hexes[idx] = hex_val
            self._custom_color_btns[idx].setStyleSheet(
                f"background-color: {hex_val}; border: 1px solid #888;")

    def _on_enable_random_changed(self, state):
        is_enabled = self.enable_random_checkbox.isChecked()
        is_xkcd = "xkcd" in self.color_mode_combo.currentText()
        self.delta_e_spinbox.setEnabled(is_enabled and is_xkcd)

    def load_config(self):
        """加载绘图配置到UI控件"""
        for key, value in self.config.items():
            if isinstance(value, dict):
                fontsize = value.get('fontsize', 10)
                size_spinbox = self.findChild(QSpinBox, f"{key}_fontsize")
                if size_spinbox:
                    size_spinbox.setValue(fontsize)

                bold = value.get('bold', False)
                bold_checkbox = self.findChild(QCheckBox, f"{key}_bold")
                if bold_checkbox:
                    bold_checkbox.setChecked(bold)

        # line width
        lw = self.config.get('line_width', 2.0)
        if self.line_width_spinbox:
            self.line_width_spinbox.setValue(lw)

    def load_color_config(self):
        if not self.color_config:
            return

        mode = self.color_config.get('mode', 'default')
        if mode == 'xkcd':
            self.color_mode_combo.setCurrentIndex(1)
        elif mode == 'custom':
            self.color_mode_combo.setCurrentIndex(2)
        else:
            self.color_mode_combo.setCurrentIndex(0)

        self.seed_spinbox.setValue(self.color_config.get('random_seed', 42))
        self.delta_e_spinbox.setValue(self.color_config.get('delta_e_min', 10.0))
        self.enable_random_checkbox.setChecked(self.color_config.get('enable_random', False))

        # 加载自定义颜色
        custom = self.color_config.get('custom_colors', [])
        for i in range(20):
            hex_val = custom[i] if i < len(custom) else '#000000'
            self._custom_color_hexes[i] = hex_val
            self._custom_color_btns[i].setStyleSheet(
                f"background-color: {hex_val}; border: 1px solid #888;")

    def load_eis_config(self):
        if not self.eis_config:
            return

        for mode_key in ('nyquist', 'bode'):
            mode_cfg = self.eis_config.get(mode_key, {})

            # color — set button background and hidden hex label
            hex_val = mode_cfg.get('color', '#1f77b4')
            btn = self.findChild(QPushButton, f"eis_{mode_key}_color_btn")
            hex_label = self.findChild(QLabel, f"eis_{mode_key}_color_hex")
            if btn:
                btn.setStyleSheet(f"background-color: {hex_val}; border: 1px solid #888;")
            if hex_label:
                hex_label.setText(hex_val)

            # marker
            combo_marker = self.findChild(QComboBox, f"eis_{mode_key}_marker")
            if combo_marker:
                idx = combo_marker.findData(mode_cfg.get('marker', 'o'))
                if idx >= 0:
                    combo_marker.setCurrentIndex(idx)

            # marker size
            spin_size = self.findChild(QSpinBox, f"eis_{mode_key}_marker_size")
            if spin_size:
                spin_size.setValue(mode_cfg.get('marker_size', 5))

        # |Z| color (Bode only)
        bode_cfg = self.eis_config.get('bode', {})
        z_hex = bode_cfg.get('z_color', '#2ca02c')
        z_btn = self.findChild(QPushButton, "eis_bode_z_color_btn")
        z_label = self.findChild(QLabel, "eis_bode_z_color_hex")
        if z_btn:
            z_btn.setStyleSheet(f"background-color: {z_hex}; border: 1px solid #888;")
        if z_label:
            z_label.setText(z_hex)

        # 特征频率竖线 (Bode only)
        cf_hex = bode_cfg.get('char_freq_line_color', '#d62728')
        cf_btn = self.findChild(QPushButton, "eis_bode_char_freq_color_btn")
        cf_label = self.findChild(QLabel, "eis_bode_char_freq_color_hex")
        if cf_btn:
            cf_btn.setStyleSheet(f"background-color: {cf_hex}; border: 1px solid #888;")
        if cf_label:
            cf_label.setText(cf_hex)

        cf_lw_spin = self.findChild(QDoubleSpinBox, "eis_bode_char_freq_line_width")
        if cf_lw_spin:
            cf_lw_spin.setValue(bode_cfg.get('char_freq_line_width', 1.5))

    def load_axis_grid_tick_config(self):
        """加载坐标轴/网格/刻度配置到UI控件"""
        # 坐标轴轴线粗细
        axis_lw = self.axis_config.get('linewidth', 1.5)
        if self.axis_linewidth_spinbox:
            self.axis_linewidth_spinbox.setValue(axis_lw)

        # 网格线
        grid_color = self.grid_config.get('color', '#cccccc')
        if self.grid_color_btn:
            self.grid_color_btn.setStyleSheet(f"background-color: {grid_color}; border: 1px solid #888;")
        if self.grid_color_hex:
            self.grid_color_hex.setText(grid_color)
        grid_lw = self.grid_config.get('linewidth', 0.8)
        if self.grid_linewidth_spinbox:
            self.grid_linewidth_spinbox.setValue(grid_lw)

        # 刻度线
        tick_dir = self.tick_config.get('direction', 'in')
        if self.tick_dir_combo:
            idx = self.tick_dir_combo.findData(tick_dir)
            if idx >= 0:
                self.tick_dir_combo.setCurrentIndex(idx)
        tick_w = self.tick_config.get('width', 1.5)
        if self.tick_width_spinbox:
            self.tick_width_spinbox.setValue(tick_w)
        tick_l = self.tick_config.get('length', 6)
        if self.tick_length_spinbox:
            self.tick_length_spinbox.setValue(tick_l)

    def get_config(self):
        config = {}
        for key in ['title', 'xlabel', 'ylabel', 'xtick', 'ytick', 'legend', 'text']:
            size_spinbox = self.findChild(QSpinBox, f"{key}_fontsize")
            bold_checkbox = self.findChild(QCheckBox, f"{key}_bold")
            if size_spinbox and bold_checkbox:
                config[key] = {
                    'fontsize': size_spinbox.value(),
                    'bold': bold_checkbox.isChecked()
                }
        # line width
        if self.line_width_spinbox:
            config['line_width'] = self.line_width_spinbox.value()
        return config

    def get_color_config(self):
        text = self.color_mode_combo.currentText()
        if "xkcd" in text:
            color_mode = "xkcd"
        elif "custom" in text:
            color_mode = "custom"
        else:
            color_mode = "default"
        return {
            'mode': color_mode,
            'random_seed': self.seed_spinbox.value(),
            'delta_e_min': self.delta_e_spinbox.value(),
            'enable_random': self.enable_random_checkbox.isChecked(),
            'custom_colors': list(self._custom_color_hexes),
        }

    def get_eis_config(self):
        result = {}
        for mode_key in ('nyquist', 'bode'):
            combo_marker = self.findChild(QComboBox, f"eis_{mode_key}_marker")
            spin_size = self.findChild(QSpinBox, f"eis_{mode_key}_marker_size")
            hex_label = self.findChild(QLabel, f"eis_{mode_key}_color_hex")

            entry = {
                'color': hex_label.text() if hex_label else '#1f77b4',
                'marker': combo_marker.currentData() if combo_marker else 'o',
                'marker_size': spin_size.value() if spin_size else 5,
                'line_style': '-',
                'line_width': 1.5,
            }

            if mode_key == 'bode':
                z_hex = self.findChild(QLabel, "eis_bode_z_color_hex")
                entry['z_color'] = z_hex.text() if z_hex else '#2ca02c'

                cf_hex = self.findChild(QLabel, "eis_bode_char_freq_color_hex")
                entry['char_freq_line_color'] = cf_hex.text() if cf_hex else '#d62728'

                cf_lw_spin = self.findChild(QDoubleSpinBox, "eis_bode_char_freq_line_width")
                entry['char_freq_line_width'] = cf_lw_spin.value() if cf_lw_spin else 1.5

            result[mode_key] = entry
        return result

    def get_axis_config(self):
        return {
            'linewidth': self.axis_linewidth_spinbox.value() if self.axis_linewidth_spinbox else 1.5,
        }

    def get_grid_config(self):
        return {
            'color': self.grid_color_hex.text() if self.grid_color_hex else '#cccccc',
            'linewidth': self.grid_linewidth_spinbox.value() if self.grid_linewidth_spinbox else 0.8,
        }

    def get_tick_config(self):
        return {
            'direction': self.tick_dir_combo.currentData() if self.tick_dir_combo else 'in',
            'width': self.tick_width_spinbox.value() if self.tick_width_spinbox else 1.5,
            'length': self.tick_length_spinbox.value() if self.tick_length_spinbox else 6.0,
        }

    def reset_defaults(self):
        from config_manager import DEFAULT_CONFIG
        default_plot_config = DEFAULT_CONFIG['plot']
        default_color_config = DEFAULT_CONFIG.get('colors', {})

        # reset font configs
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

        # reset line width
        if self.line_width_spinbox:
            self.line_width_spinbox.setValue(default_plot_config.get('line_width', 2.0))

        # reset CV color config
        if default_color_config:
            mode = default_color_config.get('mode', 'default')
            if mode == 'xkcd':
                self.color_mode_combo.setCurrentIndex(1)
            elif mode == 'custom':
                self.color_mode_combo.setCurrentIndex(2)
            else:
                self.color_mode_combo.setCurrentIndex(0)
            self.seed_spinbox.setValue(default_color_config.get('random_seed', 42))
            self.delta_e_spinbox.setValue(default_color_config.get('delta_e_min', 10.0))
            self.enable_random_checkbox.setChecked(default_color_config.get('enable_random', False))

            # reset custom colors
            default_custom = default_color_config.get('custom_colors', [])
            for i in range(20):
                hex_val = default_custom[i] if i < len(default_custom) else '#000000'
                self._custom_color_hexes[i] = hex_val
                self._custom_color_btns[i].setStyleSheet(
                    f"background-color: {hex_val}; border: 1px solid #888;")

        # reset EIS config
        default_eis_config = DEFAULT_CONFIG.get('eis_plot', {})
        for mode_key in ('nyquist', 'bode'):
            mode_cfg = default_eis_config.get(mode_key, {})

            hex_val = mode_cfg.get('color', '#1f77b4')
            btn = self.findChild(QPushButton, f"eis_{mode_key}_color_btn")
            hex_label = self.findChild(QLabel, f"eis_{mode_key}_color_hex")
            if btn:
                btn.setStyleSheet(f"background-color: {hex_val}; border: 1px solid #888;")
            if hex_label:
                hex_label.setText(hex_val)

            combo_marker = self.findChild(QComboBox, f"eis_{mode_key}_marker")
            if combo_marker:
                idx = combo_marker.findData(mode_cfg.get('marker', 'o'))
                if idx >= 0:
                    combo_marker.setCurrentIndex(idx)

            spin_size = self.findChild(QSpinBox, f"eis_{mode_key}_marker_size")
            if spin_size:
                spin_size.setValue(mode_cfg.get('marker_size', 5))

        # reset |Z| color (Bode)
        bode_default = default_eis_config.get('bode', {})
        z_hex = bode_default.get('z_color', '#2ca02c')
        z_btn = self.findChild(QPushButton, "eis_bode_z_color_btn")
        z_label = self.findChild(QLabel, "eis_bode_z_color_hex")
        if z_btn:
            z_btn.setStyleSheet(f"background-color: {z_hex}; border: 1px solid #888;")
        if z_label:
            z_label.setText(z_hex)

        # reset 特征频率竖线 (Bode)
        cf_hex = bode_default.get('char_freq_line_color', '#d62728')
        cf_btn = self.findChild(QPushButton, "eis_bode_char_freq_color_btn")
        cf_label = self.findChild(QLabel, "eis_bode_char_freq_color_hex")
        if cf_btn:
            cf_btn.setStyleSheet(f"background-color: {cf_hex}; border: 1px solid #888;")
        if cf_label:
            cf_label.setText(cf_hex)
        cf_lw_spin = self.findChild(QDoubleSpinBox, "eis_bode_char_freq_line_width")
        if cf_lw_spin:
            cf_lw_spin.setValue(bode_default.get('char_freq_line_width', 1.5))

        # reset 坐标轴轴线
        default_axis = DEFAULT_CONFIG.get('axis', {})
        if self.axis_linewidth_spinbox:
            self.axis_linewidth_spinbox.setValue(default_axis.get('linewidth', 1.5))

        # reset 网格线
        default_grid = DEFAULT_CONFIG.get('grid', {})
        grid_hex = default_grid.get('color', '#cccccc')
        if self.grid_color_btn:
            self.grid_color_btn.setStyleSheet(f"background-color: {grid_hex}; border: 1px solid #888;")
        if self.grid_color_hex:
            self.grid_color_hex.setText(grid_hex)
        if self.grid_linewidth_spinbox:
            self.grid_linewidth_spinbox.setValue(default_grid.get('linewidth', 0.8))

        # reset 刻度线
        default_tick = DEFAULT_CONFIG.get('tick', {})
        if self.tick_dir_combo:
            idx = self.tick_dir_combo.findData(default_tick.get('direction', 'in'))
            if idx >= 0:
                self.tick_dir_combo.setCurrentIndex(idx)
        if self.tick_width_spinbox:
            self.tick_width_spinbox.setValue(default_tick.get('width', 1.5))
        if self.tick_length_spinbox:
            self.tick_length_spinbox.setValue(default_tick.get('length', 6))
