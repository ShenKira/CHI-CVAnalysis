"""
CV分析工具 - 主窗口
核心GUI应用窗口，整合所有模块
"""

import sys
import os
import tempfile
import shutil

# 在导入matplotlib之前设置后端
os.environ['QT_API'] = 'pyside6'
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = ''

import matplotlib
matplotlib.use('Qt5Agg')

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from pathlib import Path

from cv_analysis import CVAnalyzer
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
    create_save_buttons_layout
)
from data_display import update_cycles_table, update_result_text
from plot_manager import plot_data, save_plot_png, save_plot_svg, copy_plot_to_clipboard


class CVAnalysisGUI(QMainWindow):
    """CV数据分析GUI应用"""
    
    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.cycles_data = []
        self.capacitances = []
        self.cycle_results = []
        self.file_path = None
        self.electrode_area = None
        self.temp_dir = tempfile.mkdtemp(prefix="cv_analysis_")
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("循环伏安分析工具 (CV Analysis Tool)")
        self.setGeometry(50, 50, 1500, 950)
        self.setStyleSheet(get_application_stylesheet())
        
        # 创建主窗口
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        
        # 文件选择区域
        file_layout, self.file_label, self.load_btn, self.area_input = create_file_selection_layout()
        self.load_btn.clicked.connect(self.load_file)
        self.area_input.valueChanged.connect(self.on_area_changed)
        main_layout.addLayout(file_layout)
        
        # 内容区域
        content_layout = QHBoxLayout()
        
        # 创建UI元素
        self.cycles_table = create_cycles_table()
        self.result_text = create_result_text_widget()
        self.figure, self.canvas, canvas_widget = create_matplotlib_canvas()
        
        # 左侧面板
        left_layout = create_left_panel_layout(self.cycles_table, self.result_text)
        
        # 右侧面板
        right_layout = create_right_panel_layout(canvas_widget)
        
        # 保存按钮
        save_layout, self.save_png_btn, self.save_svg_btn, self.copy_clipboard_btn = create_save_buttons_layout()
        self.save_png_btn.clicked.connect(self.save_plot_png)
        self.save_svg_btn.clicked.connect(self.save_plot_svg)
        self.copy_clipboard_btn.clicked.connect(self.copy_plot_to_clipboard)
        
        right_layout.addLayout(save_layout)
        
        # 配置按钮
        from PySide6.QtWidgets import QPushButton
        config_btn = QPushButton("绘图配置")
        config_btn.clicked.connect(self.open_plot_config)
        right_layout.addWidget(config_btn)
        
        # 添加左右面板到内容布局
        content_layout.addLayout(left_layout, stretch=1)
        content_layout.addLayout(right_layout, stretch=1)
        
        main_layout.addLayout(content_layout, stretch=1)
        main_widget.setLayout(main_layout)
        
        # 创建菜单栏
        self._create_menu_bar()
        
        # 状态栏
        self.statusBar().showMessage("就绪")
    
    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 配置菜单
        config_menu = menubar.addMenu("配置(&C)")
        
        # 导入配置
        import_config_action = config_menu.addAction("导入配置...")
        import_config_action.triggered.connect(self.import_config)
        
        # 导出配置
        export_config_action = config_menu.addAction("导出配置...")
        export_config_action.triggered.connect(self.export_config)
        
        config_menu.addSeparator()
        
        # 重置为默认配置
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
    
    def on_area_changed(self, value):
        """电极面积改变时的处理"""
        if value > 0:
            self.electrode_area = value
        else:
            self.electrode_area = None
        
        # 如果已经有数据，重新更新结果显示
        if self.capacitances:
            update_cycles_table(self.cycles_table, self.cycle_results, self.analyzer, self.electrode_area)
            update_result_text(self.result_text, self.cycle_results, self.analyzer, 
                             self.analyzer.metadata, self.electrode_area)
            # 绘制图表时传入配置
            plot_config = self.config_manager.get_plot_config()
            plot_data(self.figure, self.canvas, self.cycles_data, self.cycle_results, 
                     self.analyzer, self.electrode_area, config=plot_config)
    
    def load_file(self):
        """打开文件对话框选择CV数据文件"""
        from PySide6.QtWidgets import QFileDialog
        
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
                    self.cycle_results.append(result)
                    if not result.get('is_outlier', False) and result['capacitance'] > 0:
                        self.capacitances.append(result['capacitance'])
            
            if not self.cycle_results:
                QMessageBox.critical(self, "错误", "无法处理任何循环")
                self.statusBar().showMessage("错误：无法处理任何循环")
                return
            
            self.statusBar().showMessage("正在更新显示...")
            
            # 更新表格
            update_cycles_table(self.cycles_table, self.cycle_results, self.analyzer, self.electrode_area)
            
            # 更新结果文本
            update_result_text(self.result_text, self.cycle_results, self.analyzer, 
                             self.analyzer.metadata, self.electrode_area)
            
            # 绘制图表（传入配置）
            plot_config = self.config_manager.get_plot_config()
            plot_data(self.figure, self.canvas, self.cycles_data, self.cycle_results, 
                     self.analyzer, self.electrode_area, config=plot_config)
            
            # 启用保存按钮
            self.save_png_btn.setEnabled(True)
            self.save_svg_btn.setEnabled(True)
            self.copy_clipboard_btn.setEnabled(True)
            
            self.statusBar().showMessage(f"分析完成！共识别 {len(self.cycles_data)} 轮循环，{len(self.capacitances)} 轮有效")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"分析过程中出错: {str(e)}")
            self.statusBar().showMessage("错误：分析过程出错")
    
    def save_plot_png(self):
        """保存图表为PNG格式"""
        save_plot_png(self.figure, self.file_path, self, self.statusBar())
    
    def save_plot_svg(self):
        """保存图表为SVG格式"""
        save_plot_svg(self.figure, self.file_path, self, self.statusBar())
    
    def copy_plot_to_clipboard(self):
        """将图表复制到剪切板"""
        copy_plot_to_clipboard(self.figure, self.temp_dir, self, self.statusBar())
    
    def open_plot_config(self):
        """打开绘图配置对话框"""
        plot_config = self.config_manager.get_plot_config()
        dialog = PlotConfigDialog(plot_config, self)
        
        if dialog.exec():
            # 用户点击确定，保存配置
            new_config = dialog.get_config()
            self.config_manager.set_plot_config(new_config)
            
            # 如果有已加载的数据，重新绘制
            if self.cycles_data and self.cycle_results:
                self.statusBar().showMessage("应用新的绘图配置...")
                plot_data(self.figure, self.canvas, self.cycles_data, self.cycle_results,
                         self.analyzer, self.electrode_area, config=new_config)
                self.statusBar().showMessage("绘图配置已更新")
    
    def import_config(self):
        """导入配置文件"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "导入配置文件",
            "",
            "JSON文件 (*.json)"
        )
        
        if file_path:
            if self.config_manager.import_config(file_path):
                QMessageBox.information(self, "成功", "配置已导入并保存！")
                self.statusBar().showMessage("配置导入成功")
                
                # 重新绘制图表
                if self.cycles_data and self.cycle_results:
                    plot_config = self.config_manager.get_plot_config()
                    plot_data(self.figure, self.canvas, self.cycles_data, self.cycle_results,
                             self.analyzer, self.electrode_area, config=plot_config)
            else:
                QMessageBox.critical(self, "错误", "导入配置失败，请检查文件格式")
                self.statusBar().showMessage("配置导入失败")
    
    def export_config(self):
        """导出配置文件"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "导出配置文件",
            "cv_plot_config.json",
            "JSON文件 (*.json)"
        )
        
        if file_path:
            if self.config_manager.export_config(file_path):
                QMessageBox.information(self, "成功", f"配置已导出至\n{file_path}")
                self.statusBar().showMessage("配置导出成功")
            else:
                QMessageBox.critical(self, "错误", "导出配置失败")
                self.statusBar().showMessage("配置导出失败")
    
    def reset_config(self):
        """重置为默认配置"""
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要重置为默认配置吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.config_manager.reset_config()
            QMessageBox.information(self, "成功", "配置已重置为默认值")
            self.statusBar().showMessage("配置已重置")
            
            # 重新绘制图表
            if self.cycles_data and self.cycle_results:
                plot_config = self.config_manager.get_plot_config()
                plot_data(self.figure, self.canvas, self.cycles_data, self.cycle_results,
                         self.analyzer, self.electrode_area, config=plot_config)


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = CVAnalysisGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
