"""
电化学分析工具 - 主窗口
核心GUI应用窗口，整合所有模块
支持CV和EIS数据，自动根据文件头判断类型
"""

import sys
import os
import tempfile
import shutil
import functools

# 在导入matplotlib之前设置后端
os.environ['QT_API'] = 'pyside6'
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = ''

import matplotlib
matplotlib.use('Qt5Agg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFileDialog, QCheckBox, QLabel, QPushButton,
    QButtonGroup, QSplitter,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
from pathlib import Path

from cv_analysis import CVAnalyzer
from eis_analysis import EISAnalyzer
from config_manager import ConfigManager
from plot_config_dialog import PlotConfigDialog
from ui_components import (
    get_application_stylesheet,
    create_file_selection_layout,
    create_cycles_table,
    create_result_text_widget,
    create_matplotlib_canvas,
    create_left_panel_layout,
    create_right_panel_layout,
    create_save_buttons_layout,
    create_eis_left_panel_layout,
)
from data_display import update_cycles_table, update_result_text, update_eis_result_text
from plot_manager import plot_data, plot_eis, save_plot_png, save_plot_svg, copy_plot_to_clipboard


class CVAnalysisGUI(QMainWindow):
    """电化学数据分析GUI应用"""

    def __init__(self):
        super().__init__()
        # CV state
        self.analyzer = None
        self.cycles_data = []
        self.capacitances = []
        self.cycle_results = []
        self.file_path = None
        self.file_paths = []
        self.is_multi_file = False
        self.electrode_area = None
        self.temp_dir = tempfile.mkdtemp(prefix="cv_analysis_")
        self.plot_selections = []

        # EIS state
        self.eis_analyzer = None
        self.eis_data = []
        self.eis_plot_mode = 'nyquist'  # 'nyquist' or 'bode'

        # current mode: 'cv' or 'eis' (auto-detected from file)
        self.current_mode = None

        # aspect ratio
        self.aspect_ratio = 'free'  # 'free', '1:1', '4:3', '16:9'

        # 初始化配置管理器
        self.config_manager = ConfigManager()

        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("电化学分析工具 (Electrochemistry Analysis Tool)")
        self.setGeometry(50, 50, 1500, 950)
        self.setStyleSheet(get_application_stylesheet())

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()

        # ── 文件选择栏 ─────────────────────────────────────
        file_layout, self.file_label, self.load_btn, self.area_input, self.area_label, self.multi_file_cb = create_file_selection_layout()
        self.load_btn.setText("导入数据文件")
        self.load_btn.clicked.connect(self.load_file)
        self.area_input.valueChanged.connect(self.on_area_changed)
        # initially hide electrode area (shown only for CV)
        self.area_label.setVisible(False)
        self.area_input.setVisible(False)
        main_layout.addLayout(file_layout)

        # ── 内容区域: 左面板 + 右面板 (可拖动调节比例) ──────
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)

        # --- 左面板: CV 和 EIS 各自的面板 ---
        self.cycles_table = create_cycles_table()
        self.results_table = create_result_text_widget()
        cv_left_layout, self.reorder_btn = create_left_panel_layout(self.cycles_table, self.results_table)
        self.reorder_btn.setCheckable(True)
        self.reorder_btn.setChecked(False)
        self.reorder_btn.toggled.connect(self._on_reorder)
        self.cv_left_widget = QWidget()
        self.cv_left_widget.setLayout(cv_left_layout)
        self.cv_left_widget.setVisible(False)

        self.eis_results_table = create_result_text_widget()
        self.eis_left_widget = QWidget()
        self.eis_left_widget.setLayout(create_eis_left_panel_layout(self.eis_results_table))
        self.eis_left_widget.setVisible(False)

        # left container — holds CV/EIS panel widgets
        left_container = QVBoxLayout()
        left_container.setContentsMargins(0, 0, 0, 0)
        left_container.addWidget(self.cv_left_widget)
        left_container.addWidget(self.eis_left_widget)
        left_widget = QWidget()
        left_widget.setLayout(left_container)
        left_widget.setMinimumWidth(300)
        content_splitter.addWidget(left_widget)

        # --- 右面板: 共享绘图区域 ---
        self.figure, self.canvas, canvas_widget = create_matplotlib_canvas()
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._on_plot_context_menu)

        right_layout, self.config_btn = create_right_panel_layout(canvas_widget)

        # aspect ratio buttons
        ratio_layout = QHBoxLayout()
        ratio_label = QLabel("比例:")
        ratio_label.setFont(QFont("Arial", 9))
        ratio_layout.addWidget(ratio_label)

        self._ratio_keys = ['free', '1:1', '4:3', '16:9']
        self._ratio_labels = {'free': '自由', '1:1': '1:1', '4:3': '4:3', '16:9': '16:9'}
        self._ratio_btn_group = QButtonGroup(self)
        self._ratio_btn_group.setExclusive(True)
        self._ratio_buttons = {}
        for idx, key in enumerate(self._ratio_keys):
            btn = QPushButton(self._ratio_labels[key])
            btn.setFont(QFont("Arial", 9))
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            self._ratio_btn_group.addButton(btn, idx)
            self._ratio_buttons[key] = btn
            ratio_layout.addWidget(btn)
        self._ratio_buttons['free'].setChecked(True)
        self._ratio_btn_group.idClicked.connect(self._on_ratio_btn_clicked)

        ratio_layout.addStretch()

        # config button
        self.config_btn.clicked.connect(self.open_plot_config)
        ratio_layout.addWidget(self.config_btn)
        right_layout.addLayout(ratio_layout)

        # display toggles (default ON, reset on restart)
        toggle_layout = QHBoxLayout()
        self.show_axes_cb = QCheckBox("坐标轴数值/标签")
        self.show_axes_cb.setFont(QFont("Arial", 9))
        self.show_axes_cb.setChecked(True)
        self.show_axes_cb.stateChanged.connect(self._on_display_toggle)
        toggle_layout.addWidget(self.show_axes_cb)

        self.show_legend_cb = QCheckBox("图例与标签")
        self.show_legend_cb.setFont(QFont("Arial", 9))
        self.show_legend_cb.setChecked(True)
        self.show_legend_cb.stateChanged.connect(self._on_display_toggle)
        toggle_layout.addWidget(self.show_legend_cb)

        toggle_layout.addStretch()
        right_layout.addLayout(toggle_layout)

        # save buttons
        save_layout, self.save_png_btn, self.save_svg_btn, self.copy_clipboard_btn = create_save_buttons_layout()
        self.save_png_btn.clicked.connect(self.save_plot_png)
        self.save_svg_btn.clicked.connect(self.save_plot_svg)
        self.copy_clipboard_btn.clicked.connect(self.copy_plot_to_clipboard)
        right_layout.addLayout(save_layout)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        content_splitter.addWidget(right_widget)
        content_splitter.setSizes([500, 1000])
        main_layout.addWidget(content_splitter, stretch=1)

        main_widget.setLayout(main_layout)

        # 创建菜单栏
        self._create_menu_bar()

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        config_menu = menubar.addMenu("配置(&C)")

        import_config_action = config_menu.addAction("导入配置...")
        import_config_action.triggered.connect(self.import_config)

        export_config_action = config_menu.addAction("导出配置...")
        export_config_action.triggered.connect(self.export_config)

        config_menu.addSeparator()

        reset_config_action = config_menu.addAction("重置为默认配置")
        reset_config_action.triggered.connect(self.reset_config)

    def closeEvent(self, event):
        """关闭应用时清理临时目录"""
        try:
            if hasattr(self, 'temp_dir') and Path(self.temp_dir).exists():
                shutil.rmtree(self.temp_dir)
        except:
            pass
        super().closeEvent(event)

    # ═══════════════════════════════════════════════════════════════════
    #  File loading & auto-detection
    # ═══════════════════════════════════════════════════════════════════

    def load_file(self):
        """打开文件对话框，自动判断CV或EIS"""
        file_dialog = QFileDialog()

        if self.multi_file_cb.isChecked():
            file_paths, _ = file_dialog.getOpenFileNames(
                self,
                "选择数据文件（可多选）",
                "",
                "文本文件 (*.txt);;所有文件 (*.*)"
            )
            if not file_paths:
                return

            for fp in file_paths:
                file_type = self._detect_file_type(fp)
                if file_type != 'cv':
                    QMessageBox.critical(
                        self, "错误",
                        f"多文件模式下仅支持CV文件。\n无效文件: {Path(fp).name}"
                    )
                    return
            self._load_cv_files(file_paths)
        else:
            file_path, _ = file_dialog.getOpenFileName(
                self,
                "选择数据文件",
                "",
                "文本文件 (*.txt);;所有文件 (*.*)"
            )

            if not file_path:
                return

            file_type = self._detect_file_type(file_path)

            if file_type == 'cv':
                self._load_cv_file(file_path)
            elif file_type == 'eis':
                self._load_eis_file(file_path)
            else:
                QMessageBox.warning(self, "警告", "无法识别文件类型。\n文件需包含 'Cyclic Voltammetry' 或 'A.C. Impedance' 标记。")

    @staticmethod
    def _detect_file_type(file_path):
        """读取文件前50行判断类型: 'cv', 'eis', 或 None"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                head = f.read(4096)
            if 'Cyclic Voltammetry' in head:
                return 'cv'
            if 'A.C. Impedance' in head:
                return 'eis'
        except:
            pass
        return None

    def _switch_to_mode(self, mode):
        """切换显示模式（内部方法，不触发文件加载）"""
        if mode == self.current_mode:
            return
        self.current_mode = mode

        if mode == 'cv':
            self.cv_left_widget.setVisible(True)
            self.eis_left_widget.setVisible(False)
            # show electrode area for CV
            self._set_area_visible(True)
        else:
            self.cv_left_widget.setVisible(False)
            self.eis_left_widget.setVisible(True)
            self._set_area_visible(False)

    def _set_area_visible(self, visible):
        """显示/隐藏电极面积输入"""
        self.area_label.setVisible(visible)
        self.area_input.setVisible(visible)

    # ═══════════════════════════════════════════════════════════════════
    #  CV workflow
    # ═══════════════════════════════════════════════════════════════════

    def _load_cv_file(self, file_path):
        """加载CV文件"""
        self._switch_to_mode('cv')
        self.is_multi_file = False
        self.file_paths = []
        self.file_path = file_path
        self.file_label.setText(Path(file_path).name)
        self._analyze_cv_file()

    def _load_cv_files(self, file_paths):
        """加载多个CV文件"""
        self._switch_to_mode('cv')
        self.is_multi_file = True
        self.file_paths = file_paths
        self.file_path = None
        count = len(file_paths)
        self.file_label.setText(f"已选择 {count} 个文件")
        self.file_label.setToolTip('\n'.join(str(Path(p).name) for p in file_paths))
        self._analyze_cv_files()

    def _analyze_cv_files(self):
        """分析多个CV文件，合并所有循环并连续编号"""
        if not self.file_paths:
            return

        try:
            self.statusBar().showMessage("正在分析多个CV文件...")

            combined_cycles_data = []
            combined_cycle_results = []
            combined_capacitances = []
            combined_plot_selections = []
            global_cycle_num = 0
            last_analyzer = None

            for fp in self.file_paths:
                analyzer = CVAnalyzer(sensitivity_threshold_factor=10, outlier_count=1)
                if not analyzer.read_file(fp):
                    QMessageBox.critical(self, "错误", f"无法读取文件: {Path(fp).name}")
                    self.statusBar().showMessage("错误：无法读取文件")
                    return

                cycles_data = analyzer._split_into_cycles()
                if not cycles_data:
                    QMessageBox.critical(self, "错误", f"无法从文件分割循环数据: {Path(fp).name}")
                    self.statusBar().showMessage("错误：无法分割循环数据")
                    return

                for cycle_data in cycles_data:
                    global_cycle_num += 1
                    result = analyzer._calculate_cycle_capacitance(global_cycle_num, cycle_data)
                    if result is not None:
                        combined_cycles_data.append(cycle_data)
                        combined_cycle_results.append(result)
                        if not result.get('is_outlier', False) and result['capacitance'] > 0:
                            combined_capacitances.append(result['capacitance'])
                        combined_plot_selections.append(True)

                last_analyzer = analyzer

            if not combined_cycle_results:
                QMessageBox.critical(self, "错误", "无法处理任何循环")
                self.statusBar().showMessage("错误：无法处理任何循环")
                return

            self.analyzer = last_analyzer
            self.cycles_data = combined_cycles_data
            self.cycle_results = combined_cycle_results
            self.capacitances = combined_capacitances
            self.plot_selections = combined_plot_selections

            update_cycles_table(self.cycles_table, self.cycle_results, self.analyzer, self.electrode_area)
            self._add_plot_checkboxes()
            update_result_text(self.results_table, self.cycle_results, self.analyzer,
                             self.analyzer.metadata, self.electrode_area,
                             is_multi_file=self.is_multi_file)
            self._update_plot_with_selection()

            self.save_png_btn.setEnabled(True)
            self.save_svg_btn.setEnabled(True)
            self.copy_clipboard_btn.setEnabled(True)
            self.config_btn.setEnabled(True)

            total_cycles = len(self.cycles_data)
            valid_count = len(self.capacitances)
            file_count = len(self.file_paths)
            self.statusBar().showMessage(f"分析完成！{file_count} 个文件，共识别 {total_cycles} 轮循环，{valid_count} 轮有效")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"分析过程中出错: {str(e)}")
            self.statusBar().showMessage("错误：分析过程出错")

    def _analyze_cv_file(self):
        """分析CV文件"""
        if not self.file_path:
            return

        try:
            self.statusBar().showMessage("正在分析CV文件...")

            self.analyzer = CVAnalyzer(sensitivity_threshold_factor=10, outlier_count=1)
            if not self.analyzer.read_file(self.file_path):
                QMessageBox.critical(self, "错误", "无法读取CV文件")
                self.statusBar().showMessage("错误：无法读取CV文件")
                return

            self.cycles_data = self.analyzer._split_into_cycles()
            if not self.cycles_data:
                QMessageBox.critical(self, "错误", "无法分割循环数据")
                self.statusBar().showMessage("错误：无法分割循环数据")
                return

            self.capacitances = []
            self.cycle_results = []
            self.plot_selections = []

            for cycle_num, cycle_data in enumerate(self.cycles_data, 1):
                result = self.analyzer._calculate_cycle_capacitance(cycle_num, cycle_data)
                if result is not None:
                    self.cycle_results.append(result)
                    if not result.get('is_outlier', False) and result['capacitance'] > 0:
                        self.capacitances.append(result['capacitance'])
                    self.plot_selections.append(True)

            if not self.cycle_results:
                QMessageBox.critical(self, "错误", "无法处理任何循环")
                self.statusBar().showMessage("错误：无法处理任何循环")
                return

            update_cycles_table(self.cycles_table, self.cycle_results, self.analyzer, self.electrode_area)
            self._add_plot_checkboxes()
            update_result_text(self.results_table, self.cycle_results, self.analyzer,
                             self.analyzer.metadata, self.electrode_area,
                             is_multi_file=self.is_multi_file)
            self._update_plot_with_selection()

            self.save_png_btn.setEnabled(True)
            self.save_svg_btn.setEnabled(True)
            self.copy_clipboard_btn.setEnabled(True)
            self.config_btn.setEnabled(True)

            self.statusBar().showMessage(f"分析完成！共识别 {len(self.cycles_data)} 轮循环，{len(self.capacitances)} 轮有效")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"分析过程中出错: {str(e)}")
            self.statusBar().showMessage("错误：分析过程出错")

    def _add_plot_checkboxes(self):
        """在表格中添加绘图复选框"""
        for row in range(self.cycles_table.rowCount()):
            self.cycles_table.removeCellWidget(row, 4)

        for row in range(len(self.plot_selections)):
            checkbox = QCheckBox()
            checkbox.setChecked(self.plot_selections[row])
            checkbox.stateChanged.connect(lambda state, r=row: self._on_plot_selection_changed(r, state))

            container = QWidget()
            layout = QVBoxLayout()
            layout.addWidget(checkbox)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            container.setLayout(layout)
            self.cycles_table.setCellWidget(row, 4, container)

    def _on_plot_selection_changed(self, row, state):
        """处理绘图选择状态变化"""
        if row < len(self.plot_selections):
            self.plot_selections[row] = (state == 2)
            if self.cycles_data and self.cycle_results:
                self._update_plot_with_selection()

    def _on_reorder(self, checked):
        """重排序：将当前勾选的Cycle重新从1开始编号"""
        if not self.cycles_data or not self.cycle_results:
            return
        self._update_plot_with_selection()

    def _update_plot_with_selection(self):
        """根据选择状态更新图表"""
        selected_cycles_data = []
        selected_cycle_results = []
        selected_cycle_numbers = []
        reorder = self.reorder_btn.isChecked()

        for i, selected in enumerate(self.plot_selections):
            if selected and i < len(self.cycles_data) and i < len(self.cycle_results):
                selected_cycles_data.append(self.cycles_data[i])
                selected_cycle_results.append(self.cycle_results[i])
                selected_cycle_numbers.append(i + 1)

        # 重排序：将勾选的Cycle从1开始重新编号
        if reorder:
            selected_cycle_numbers = list(range(1, len(selected_cycle_numbers) + 1))

        plot_config = self.config_manager.get_plot_config()
        plot_config['axis_config'] = self.config_manager.get_axis_config()
        plot_config['grid_config'] = self.config_manager.get_grid_config()
        plot_config['tick_config'] = self.config_manager.get_tick_config()
        color_config = self.config_manager.get_color_config()
        plot_data(self.figure, self.canvas, selected_cycles_data, selected_cycle_results,
                 self.analyzer, self.electrode_area, config=plot_config,
                 selected_cycle_numbers=selected_cycle_numbers, color_config=color_config,
                 is_multi_file=self.is_multi_file)
        self._apply_aspect_ratio()
        self._apply_display_settings()

    def on_area_changed(self, value):
        """电极面积改变时的处理"""
        if value > 0:
            self.electrode_area = value
        else:
            self.electrode_area = None

        if self.capacitances:
            update_cycles_table(self.cycles_table, self.cycle_results, self.analyzer, self.electrode_area)
            self._add_plot_checkboxes()
            update_result_text(self.results_table, self.cycle_results, self.analyzer,
                             self.analyzer.metadata, self.electrode_area,
                             is_multi_file=self.is_multi_file)
            self._update_plot_with_selection()

    # ═══════════════════════════════════════════════════════════════════
    #  EIS workflow
    # ═══════════════════════════════════════════════════════════════════

    def _load_eis_file(self, file_path):
        """加载EIS文件"""
        self._switch_to_mode('eis')
        self.file_path = file_path
        self.file_label.setText(Path(file_path).name)
        self._analyze_eis_file()

    def _analyze_eis_file(self):
        """分析EIS文件"""
        if not self.file_path:
            return

        try:
            self.statusBar().showMessage("正在分析EIS文件...")

            self.eis_analyzer = EISAnalyzer()
            if not self.eis_analyzer.read_file(self.file_path):
                QMessageBox.critical(self, "错误", "无法读取EIS文件")
                self.statusBar().showMessage("错误：无法读取EIS文件")
                return

            self.eis_data = self.eis_analyzer.eis_data
            if not self.eis_data:
                QMessageBox.critical(self, "错误", "未找到EIS数据")
                self.statusBar().showMessage("错误：未找到EIS数据")
                return

            update_eis_result_text(self.eis_results_table, self.eis_analyzer)
            self._update_eis_plot()

            self.save_png_btn.setEnabled(True)
            self.save_svg_btn.setEnabled(True)
            self.copy_clipboard_btn.setEnabled(True)
            self.config_btn.setEnabled(True)

            self.statusBar().showMessage(f"EIS分析完成！共 {len(self.eis_data)} 个数据点")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"EIS分析过程中出错: {str(e)}")
            self.statusBar().showMessage("错误：EIS分析过程出错")

    def _update_eis_plot(self):
        """根据当前EIS绘图模式更新图表"""
        if not self.eis_data:
            return
        eis_config = self.config_manager.get_eis_plot_config()
        plot_cfg = self.config_manager.get_plot_config()
        plot_cfg['axis_config'] = self.config_manager.get_axis_config()
        plot_cfg['grid_config'] = self.config_manager.get_grid_config()
        plot_cfg['tick_config'] = self.config_manager.get_tick_config()
        plot_cfg['_show_legend'] = self.show_legend_cb.isChecked()
        global_lw = plot_cfg.get('line_width', 2.0)
        plot_eis(
            self.figure, self.canvas, self.eis_data,
            self.eis_analyzer, self.eis_plot_mode, config=eis_config,
            global_line_width=global_lw, plot_config=plot_cfg,
        )
        self._apply_aspect_ratio()
        self._apply_display_settings()

    def _on_plot_context_menu(self, pos):
        """右键菜单 — EIS模式下切换 Nyquist / Bode"""
        if self.current_mode != 'eis' or not self.eis_data:
            return

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)

        nyquist_action = menu.addAction("Z'-Z'' (Nyquist)")
        nyquist_action.setCheckable(True)
        nyquist_action.setChecked(self.eis_plot_mode == 'nyquist')

        bode_action = menu.addAction("Phase Angle-Freq (Bode)")
        bode_action.setCheckable(True)
        bode_action.setChecked(self.eis_plot_mode == 'bode')

        action = menu.exec(self.canvas.mapToGlobal(pos))

        if action == nyquist_action:
            self.eis_plot_mode = 'nyquist'
            self._update_eis_plot()
        elif action == bode_action:
            self.eis_plot_mode = 'bode'
            self._update_eis_plot()

    # ═══════════════════════════════════════════════════════════════════
    #  Aspect ratio
    # ═══════════════════════════════════════════════════════════════════

    def _on_ratio_btn_clicked(self, btn_id):
        """QButtonGroup idClicked 信号处理"""
        if 0 <= btn_id < len(self._ratio_keys):
            self._set_aspect_ratio(self._ratio_keys[btn_id])

    def _set_aspect_ratio(self, key):
        """设置绘图比例"""
        self.aspect_ratio = key
        btn = self._ratio_buttons.get(key)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self._apply_aspect_ratio()

    def _apply_aspect_ratio(self):
        """将当前比例应用到绘图 — 通过 set_box_aspect 或手动定位控制坐标轴视觉比例"""
        if not self.figure.axes:
            return

        # 先执行 tight_layout，再设置 aspect ratio，避免 tight_layout 重置 box_aspect
        try:
            self.figure.tight_layout()
        except Exception:
            pass

        # set_box_aspect(height/width): controls the visual shape of the axes box
        ratio_map = {'free': None, '1:1': 1.0, '4:3': 3.0 / 4.0, '16:9': 9.0 / 16.0}
        box_ratio = ratio_map.get(self.aspect_ratio)

        # 锁定figure尺寸，防止resizeEvent覆盖set_box_aspect的效果
        self.canvas._lock_figure_size = (box_ratio is not None)

        for ax in self.figure.axes:
            try:
                ax.set_box_aspect(box_ratio)  # None = auto
            except Exception:
                pass

        # 备用方案：如果 set_box_aspect 未生效（Nuitka 环境），手动调整 axes 位置
        if box_ratio is not None:
            try:
                sample_ax = self.figure.axes[0]
                actual = sample_ax.get_box_aspect()
                if actual is None or abs(actual - box_ratio) > 0.01:
                    self._apply_aspect_ratio_by_position(box_ratio)
            except Exception:
                self._apply_aspect_ratio_by_position(box_ratio)

        self.canvas.draw()
        self.canvas.flush_events()

    def _apply_aspect_ratio_by_position(self, box_ratio):
        """备用方案：通过手动设置 axes 位置实现比例控制（Nuitka 兼容）"""
        fig_w, fig_h = self.figure.get_size_inches()
        fig_aspect = fig_w / fig_h
        for ax in self.figure.axes:
            pos = ax.get_position()
            cur_w = pos.x1 - pos.x0
            cur_h = pos.y1 - pos.y0
            if cur_h <= 0:
                continue
            # 像素宽高比 = (归一化宽/归一化高) * (图宽/图高)
            cur_pixel_aspect = (cur_w / cur_h) * fig_aspect
            if cur_pixel_aspect > box_ratio:
                new_w = cur_h * (box_ratio / fig_aspect)
                new_h = cur_h
            else:
                new_w = cur_w
                new_h = cur_w * (fig_aspect / box_ratio)
            cx = pos.x0 + cur_w / 2
            cy = pos.y0 + cur_h / 2
            ax.set_position([cx - new_w / 2, cy - new_h / 2, new_w, new_h])

    # ═══════════════════════════════════════════════════════════════════
    #  Display toggles
    # ═══════════════════════════════════════════════════════════════════

    def _on_display_toggle(self):
        """处理显示开关变化"""
        # re-render current plot with updated visibility
        if self.current_mode == 'cv' and self.cycles_data and self.cycle_results:
            self._update_plot_with_selection()
        elif self.current_mode == 'eis' and self.eis_data:
            self._update_eis_plot()

    def _apply_display_settings(self):
        """在绘图完成后，根据开关状态隐藏坐标轴文字、图例等（仅隐藏，显示由重绘完成）"""
        show_axes = self.show_axes_cb.isChecked()
        show_legend = self.show_legend_cb.isChecked()

        # figure.axes already includes all axes (main + twins)
        for ax in self.figure.axes:
            # 仅在关闭时隐藏文字，开启时不干预（由重绘自然恢复）
            if not show_axes:
                ax.tick_params(axis='both', labelbottom=False, labelleft=False,
                               labelright=False, labeltop=False)
                if ax.xaxis.label:
                    ax.xaxis.label.set_visible(False)
                if ax.yaxis.label:
                    ax.yaxis.label.set_visible(False)

            # 图例
            leg = ax.get_legend()
            if leg:
                leg.set_visible(show_legend)

            # text annotations (ax.text elements)
            for txt in ax.texts:
                txt.set_visible(show_legend)

        self.canvas.draw()

    # ═══════════════════════════════════════════════════════════════════
    #  Save / export / config
    # ═══════════════════════════════════════════════════════════════════

    def save_plot_png(self):
        """保存图表为PNG格式"""
        save_plot_png(self.figure, self.file_path, self, self.statusBar(), is_multi_file=self.is_multi_file, file_paths=self.file_paths)

    def save_plot_svg(self):
        """保存图表为SVG格式"""
        save_plot_svg(self.figure, self.file_path, self, self.statusBar(), is_multi_file=self.is_multi_file, file_paths=self.file_paths)

    def copy_plot_to_clipboard(self):
        """将图表复制到剪切板"""
        copy_plot_to_clipboard(self.figure, self.temp_dir, self, self.statusBar())

    def open_plot_config(self):
        """打开绘图配置对话框"""
        plot_config = self.config_manager.get_plot_config()
        color_config = self.config_manager.get_color_config()
        eis_config = self.config_manager.get_eis_plot_config()
        axis_config = self.config_manager.get_axis_config()
        grid_config = self.config_manager.get_grid_config()
        tick_config = self.config_manager.get_tick_config()
        dialog = PlotConfigDialog(plot_config, self, color_config, eis_config=eis_config,
                                  axis_config=axis_config, grid_config=grid_config,
                                  tick_config=tick_config)

        if dialog.exec():
            new_config = dialog.get_config()
            new_color_config = dialog.get_color_config()
            new_eis_config = dialog.get_eis_config()
            new_axis_config = dialog.get_axis_config()
            new_grid_config = dialog.get_grid_config()
            new_tick_config = dialog.get_tick_config()
            self.config_manager.set_plot_config(new_config)
            self.config_manager.set_color_config(new_color_config)
            self.config_manager.set_eis_plot_config(new_eis_config)
            self.config_manager.set_axis_config(new_axis_config)
            self.config_manager.set_grid_config(new_grid_config)
            self.config_manager.set_tick_config(new_tick_config)

            if self.current_mode == 'cv' and self.cycles_data and self.cycle_results:
                self.statusBar().showMessage("应用新的绘图配置...")
                self._update_plot_with_selection()
                self.statusBar().showMessage("绘图配置已更新")
            elif self.current_mode == 'eis' and self.eis_data:
                self._update_eis_plot()
                self.statusBar().showMessage("绘图配置已更新")

    def import_config(self):
        """导入配置文件"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "导入配置文件", "", "JSON文件 (*.json)")
        if file_path:
            if self.config_manager.import_config(file_path):
                QMessageBox.information(self, "成功", "配置已导入并保存！")
                self.statusBar().showMessage("配置导入成功")
                if self.cycles_data and self.cycle_results:
                    self._update_plot_with_selection()
            else:
                QMessageBox.critical(self, "错误", "导入配置失败，请检查文件格式")
                self.statusBar().showMessage("配置导入失败")

    def export_config(self):
        """导出配置文件"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(self, "导出配置文件", "cv_plot_config.json", "JSON文件 (*.json)")
        if file_path:
            if self.config_manager.export_config(file_path):
                QMessageBox.information(self, "成功", f"配置已导出至\n{file_path}")
                self.statusBar().showMessage("配置导出成功")
            else:
                QMessageBox.critical(self, "错误", "导出配置失败")
                self.statusBar().showMessage("配置导出失败")

    def reset_config(self):
        """重置为默认配置"""
        reply = QMessageBox.question(self, "确认", "确定要重置为默认配置吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config_manager.reset_config()
            QMessageBox.information(self, "成功", "配置已重置为默认值")
            self.statusBar().showMessage("配置已重置")
            if self.cycles_data and self.cycle_results:
                self._update_plot_with_selection()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = CVAnalysisGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
