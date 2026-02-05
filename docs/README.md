# CV Analysis Tool - 循环伏安数据分析工具

[English](#english) | [中文](#中文)

## 中文

### 📋 项目简介

**CV Analysis Tool** 是一个功能全面的循环伏安（Cyclic Voltammetry, CV）实验数据分析工具，主要用于处理和分析由CHI660E电化学工作站导出的CV实验数据。该工具提供了友好的图形化用户界面，可以自动计算电容值、进行统计分析，并生成高质量的数据可视化图表。

**主要特性：**
- ✅ 自动解析CHI660E导出的CV数据文件
- ✅ 智能计算每轮循环的面积和电容值
- ✅ 离群值自动检测和排除
- ✅ 实时数据可视化（V-I曲线）
- ✅ 多格式图表导出（PNG、SVG）
- ✅ 完整的统计分析和数据汇总
- ✅ 可自定义的绘图配置
- ✅ 跨平台支持（Windows、macOS、Linux）

### 🚀 快速开始

#### 系统要求
- Python 3.8+
- pip 包管理器

#### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/ShenKira/CHI-CVAnalysis.git
cd CHI-CVAnalysis
```

2. **创建虚拟环境**（可选但推荐）
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **运行应用**
```bash
python start_gui.py
```

### 📖 使用指南

#### 基本操作

1. **启动应用**
   ```bash
   python start_gui.py
   ```
   
2. **导入数据文件**
   - 点击界面中的"导入CV数据文件"按钮
   - 选择CHI660E导出的txt格式数据文件
   - 应用将自动解析并提取CV实验数据

3. **查看分析结果**
   - **左侧面板**：显示每一轮循环的详细数据
     - 循环编号
     - 循环面积（单位：C，库伦）
     - 电容值（单位：mF，毫法）
   - **下方文本区域**：显示完整的实验参数和统计结果
     - 初始电压、最高/最低电压
     - 扫描速率、电极面积、灵敏度等
     - 有效循环数、平均电容值、标准差等

4. **数据可视化**
   - **右侧图表**：实时显示所有循环的V-I曲线
   - 每个循环用不同颜色区分
   - 包含图例、坐标轴标签和网格线

5. **导出结果**
   - **保存为PNG**：导出高分辨率图像（300 dpi）
   - **保存为SVG**：导出矢量图，便于后续编辑

#### 关键参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `sensitivity_threshold_factor` | 电流超出多少倍灵敏度时发出警告 | 10 |
| `outlier_count` | 排除最离群值的个数 | 1 |
| `electrode_area` | 电极面积（cm²） | 0.01 |

这些参数可以在初始化 `CVAnalyzer` 类时修改。

### 📊 项目结构

```
CV-Analysis-Tool/
├── cv_analysis.py              # 核心分析模块 - 数据处理和计算
├── cv_gui.py                   # GUI主窗口 - PySide6主应用
├── start_gui.py                # 启动脚本 - 程序入口
├── config_manager.py           # 配置管理器 - 处理config.json
├── plot_manager.py             # 绘图管理器 - V-I曲线绘制和导出
├── data_display.py             # 数据展示模块 - UI数据更新
├── plot_config_dialog.py       # 绘图配置对话框 - 字体样式设置
├── ui_components.py            # UI组件库 - 可复用UI元素
├── config.json                 # 配置文件 - 绘图样式配置
├── requirements.txt            # 依赖列表
├── tests/                      # 测试目录
│   └── test_cv_data.txt       # 测试数据样本
├── docs/                       # 文档目录
│   └── README.md              # 详细文档
└── README.md                  # 本文件
```

### 🔧 核心功能模块

#### CVAnalyzer（cv_analysis.py）
负责核心数据分析：
- 解析CHI660E导出的txt数据文件
- 提取电势和电流数据
- 计算每个循环的面积和电容值
- 进行离群值检测和排除
- 生成统计结果

#### CVAnalysisGUI（cv_gui.py）
主图形用户界面：
- 整合所有模块的功能
- 提供文件导入对话框
- 实时显示分析结果
- 管理用户交互

#### PlotManager（plot_manager.py）
数据可视化和导出：
- 绘制V-I曲线图
- 支持多循环彩色区分
- 导出为PNG（300 dpi）
- 导出为SVG矢量格式
- 复制图表到剪贴板

#### ConfigManager（config_manager.py）
配置文件管理：
- 读取和保存config.json
- 管理绘图样式参数
- 自动创建默认配置

### 📦 依赖说明

```
PySide6>=6.4.0        # GUI框架
matplotlib>=3.5.0     # 数据可视化
Pillow>=9.0.0         # 图像处理
numpy>=1.21.0         # 数值计算
```

### ⚙️ 数据要求

导入的txt数据文件需要满足以下条件：
1. ✓ 包含"Cyclic Voltammetry"字样（用于识别为CV实验）
2. ✓ 包含"Potential/V, Current/A"表头
3. ✓ 电势和电流数据格式正确
4. ✓ 至少包含一个完整的循环（2个Segments）

### 📈 分析算法

#### 面积计算
- 使用梯形积分法计算闭合循环的面积
- 单位为库伦（C）

#### 电容值计算
$$C = \frac{A}{v \times A_{electrode}}$$

其中：
- $A$ = 循环面积（C）
- $v$ = 扫描速率（V/s）
- $A_{electrode}$ = 电极面积（cm²）
- 结果单位：mF（毫法）

#### 离群值排除
- 使用Z-score统计方法
- 自动排除偏离平均值最远的值
- 可配置排除个数

#### 灵敏度检验
- 检查电流是否超过灵敏度范围
- 警告并排除超限循环
- 可配置灵敏度阈值倍数

### 🎨 自定义配置

编辑 `config.json` 修改绘图样式：

```json
{
  "plot": {
    "title": {
      "fontsize": 20,
      "bold": true
    },
    "xlabel": {
      "fontsize": 14,
      "bold": false
    },
    "ylabel": {
      "fontsize": 14,
      "bold": false
    },
    "legend": {
      "fontsize": 12,
      "bold": false
    }
  }
}
```

### 📝 数据导出

支持多种格式导出分析结果图表：

| 格式 | 分辨率 | 用途 | 文件大小 |
|------|--------|------|---------|
| PNG | 300 dpi | 文档、演示、网页 | 中等 |
| SVG | 矢量 | 编辑、出版、高清 | 小 |

### 🐛 故障排除

| 问题 | 解决方案 |
|------|--------|
| `ModuleNotFoundError: No module named 'PySide6'` | 运行 `pip install -r requirements.txt` |
| 无法打开文件 | 确保文件编码为UTF-8，包含CV数据 |
| 图表显示不完整 | 检查matplotlib后端配置 |
| 字体显示不正确 | 确保系统安装了Times New Roman字体 |

### 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本仓库
2. 创建特性分支：`git checkout -b feature/AmazingFeature`
3. 提交更改：`git commit -m 'Add some AmazingFeature'`
4. 推送到分支：`git push origin feature/AmazingFeature`
5. 开启Pull Request

### 📄 许可证

本项目采用MIT许可证。详见 [LICENSE](LICENSE) 文件。

### 📧 联系方式

- 问题报告：[GitHub Issues](https://github.com/ShenKira/CHI-CVAnalysis/issues)
- GitHub: [ShenKira](https://github.com/ShenKira)

### 🙏 致谢

感谢所有贡献者和使用者的支持！

---

## English

### 📋 Project Overview

**CV Analysis Tool** is a comprehensive cyclic voltammetry (CV) experimental data analysis application, primarily designed to process and analyze CV data exported from CHI660E electrochemical workstations. The tool provides a user-friendly graphical interface for automatic calculation of capacitance values, statistical analysis, and generation of high-quality data visualizations.

**Key Features:**
- ✅ Automatic parsing of CHI660E exported CV data files
- ✅ Intelligent calculation of area and capacitance for each cycle
- ✅ Automatic outlier detection and exclusion
- ✅ Real-time data visualization (V-I curves)
- ✅ Multi-format figure export (PNG, SVG)
- ✅ Comprehensive statistical analysis and data summary
- ✅ Customizable plot configuration
- ✅ Cross-platform support (Windows, macOS, Linux)

### 🚀 Quick Start

#### System Requirements
- Python 3.8+
- pip package manager

#### Installation

1. **Clone the repository**
```bash
git clone https://github.com/ShenKira/CHI-CVAnalysis.git
cd CHI-CVAnalysis
```

2. **Create virtual environment** (optional but recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run the application**
```bash
python start_gui.py
```

### 📖 User Guide

#### Basic Operations

1. **Launch the application**
   ```bash
   python start_gui.py
   ```
   
2. **Import data file**
   - Click "Import CV Data File" button
   - Select a txt file exported from CHI660E
   - The app will automatically parse and extract CV data

3. **View analysis results**
   - **Left panel**: Details for each cycle
     - Cycle number
     - Cycle area (unit: C, Coulombs)
     - Capacitance (unit: mF, milliFarads)
   - **Bottom text area**: Complete experiment parameters and statistics
     - Initial voltage, max/min voltage
     - Scan rate, electrode area, sensitivity
     - Valid cycles, average capacitance, standard deviation

4. **Data visualization**
   - **Right plot**: Real-time V-I curves for all cycles
   - Different colors for different cycles
   - Includes legend, axis labels, and grid

5. **Export results**
   - **Save as PNG**: High-resolution image (300 dpi)
   - **Save as SVG**: Vector format for further editing

#### Key Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `sensitivity_threshold_factor` | Factor for sensitivity threshold warning | 10 |
| `outlier_count` | Number of outliers to exclude | 1 |
| `electrode_area` | Electrode area (cm²) | 0.01 |

### 📊 Project Structure

```
CV-Analysis-Tool/
├── cv_analysis.py              # Core analysis module
├── cv_gui.py                   # GUI main window
├── start_gui.py                # Application entry point
├── config_manager.py           # Configuration manager
├── plot_manager.py             # Plot manager
├── data_display.py             # Data display module
├── plot_config_dialog.py       # Plot config dialog
├── ui_components.py            # UI components library
├── config.json                 # Configuration file
├── requirements.txt            # Dependency list
├── tests/                      # Test directory
└── docs/                       # Documentation
```

### 📦 Dependencies

```
PySide6>=6.4.0        # GUI framework
matplotlib>=3.5.0     # Data visualization
Pillow>=9.0.0         # Image processing
numpy>=1.21.0         # Numerical computing
```

### ⚙️ Data Requirements

Imported txt data files must meet the following conditions:
1. ✓ Contains "Cyclic Voltammetry" string
2. ✓ Contains "Potential/V, Current/A" header
3. ✓ Correct potential and current data format
4. ✓ At least one complete cycle (2 Segments)

### 📈 Analysis Algorithms

#### Area Calculation
- Trapezoid integration for enclosed cycle area
- Unit: Coulombs (C)

#### Capacitance Calculation
$$C = \frac{A}{v \times A_{electrode}}$$

Where:
- $A$ = Cycle area (C)
- $v$ = Scan rate (V/s)
- $A_{electrode}$ = Electrode area (cm²)
- Result unit: mF (milliFarads)

#### Outlier Exclusion
- Z-score statistical method
- Automatic exclusion of values farthest from mean
- Configurable exclusion count

#### Sensitivity Check
- Monitors if current exceeds sensitivity range
- Warns and excludes over-limit cycles
- Configurable sensitivity threshold factor

### 🎨 Custom Configuration

Edit `config.json` to customize plot styles:

```json
{
  "plot": {
    "title": {
      "fontsize": 20,
      "bold": true
    },
    "xlabel": {
      "fontsize": 14,
      "bold": false
    },
    "ylabel": {
      "fontsize": 14,
      "bold": false
    },
    "legend": {
      "fontsize": 12,
      "bold": false
    }
  }
}
```

### 📝 Data Export

Support multiple format exports:

| Format | Resolution | Purpose | File Size |
|--------|------------|---------|-----------|
| PNG | 300 dpi | Documents, presentations, web | Medium |
| SVG | Vector | Editing, publishing, high-quality | Small |

### 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'PySide6'` | Run `pip install -r requirements.txt` |
| Cannot open file | Ensure file is UTF-8 encoded and contains CV data |
| Incomplete plot display | Check matplotlib backend configuration |
| Font display incorrect | Ensure Times New Roman font is installed |

### 🤝 Contributing

Issues and pull requests are welcome!

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/AmazingFeature`
3. Commit your changes: `git commit -m 'Add some AmazingFeature'`
4. Push to the branch: `git push origin feature/AmazingFeature`
5. Open a Pull Request

### 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

### 📧 Contact

- Bug reports: [GitHub Issues](https://github.com/ShenKira/CHI-CVAnalysis/issues)
- GitHub: [ShenKira](https://github.com/ShenKira)

### 🙏 Acknowledgments

Thank you to all contributors and users for your support!
