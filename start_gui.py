#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CV分析工具 - 简化版启动脚本
用于快速测试和启动GUI
"""

import sys
import os

# 确保当前目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_gui():
    """启动GUI应用"""
    try:
        from PySide6.QtWidgets import QApplication
        from cv_gui import CVAnalysisGUI
        
        print("启动CV数据分析工具...")
        app = QApplication.instance() or QApplication(sys.argv)
        window = CVAnalysisGUI()
        window.show()
        
        print("应用已启动，窗口正在显示...")
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"错误：无法启动应用")
        print(f"详情：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_gui()
