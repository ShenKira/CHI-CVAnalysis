# CVAnalysis v2

电化学工作站数据分析工作区，面向 CHI660E 导出的 CV 与 EIS 数据，支持多文件批量分析、扫速/电位相关分析、EIS 等效电路拟合，以及日常分析和 IEEE 论文风格绘图预设。

[中文](#中文) | [English](#english)

---

## 中文

### 1. 主要功能

- **多文件数据集**：一次导入多个 CV / EIS / CP 文件；单个文件失败不会中断整批导入。
- **LSV 与 I‑T**：支持 CHI 的线性扫描伏安及电流–时间文件。右侧对应分析页可绘图；当前图的分析参数中可输入 LSV 电压窗口端点，或选择“负电流显示为零”，截零仅影响当前图，不修改或过滤原始数据与原始数据点 CSV。I‑T 可输入参考时间，在最接近的实测点标记电流并绘制水平线。参考点标注可选择时间与电流、仅电流或自定义格式；格式支持 `{time}`、`{current}`、`{unit}` 和 `{name}`，数值可按有效数字、固定小数或科学计数法显示，电流单位可自动选择或手动指定。标注位置可自动避让，也可逐条按绘图区的 X/Y 百分比指定并选择显示引线。支持面积/质量归一化和原始数据点 CSV 导出。
- **LSV / I‑T 参考面积与参考电容**：当前图可输入整张图共用的参考面积（cm²）或参考电容（F/mF/µF/nF/pF），将 Y 轴显示为电流/面积（A/cm² 系列）或电流/电容（A/F 系列；分母跟随参考电容输入单位，例如 µF + nA 显示为 nA/µF）。参考模式使用原始电流并覆盖全局面积/质量归一化；无效参考值会提示并回退为原始电流。轴单位、参考点标注和图片导出同步使用当前显示方式，原始数据和 CSV 不变。
- **I‑T 图例字段**：可使用 `{IT_Potential}`、`{IT_Run_Time}`、`{IT_Sample_Interval}`、`{IT_Quiet_Time}` 和 `{Points}`；输入 `{ }` 可让该曲线不显示图例条目，留空输入框则继续继承默认模板。
- **当前图选项浮窗**：双击右下角“当前图”标题可在独立窗口编辑，关闭窗口或点击原位置的“返回工作区”后恢复面板；尚未应用的输入保留。
- **长文件名处理**：文件名超过显示上限时自动缩短；同类型文件名相似且较长时，整组使用 `#文件序号 + 电位/扫速` 紧凑图例，避免 1.5 V / 2.5 V 被截成同名。完整文件名、路径和扫速/窗口仍显示在左侧详情区。
- **循环级控制**：数据集树中可勾选文件或单个循环，实时更新当前图。每个标签页独立保存文件和循环选择。
- **标签页命名**：双击图标签直接编辑名称，Enter 或失焦时保存，Esc 取消。标签右键可重命名或恢复自动名称，清空名称也会恢复自动名称。名称随项目保存，图内标题单独设置。
- **每图独立数据选择**：画布右键“本图数据与图例...”或“工具 → 当前图数据与图例...”可选择该图绘制的文件、CV 循环及图例模板。
- **图例模板与别名**：可为数据设置默认别名模板（如 `{file_n}-{cycle_n}`），也可在当前图单独覆盖，或为单个数据设置“图例/别名”。模板支持文件序号 `{file_n}`、文件内原始循环号 `{cycle_n}`、人工别名 `{Alias}`，以及 `{File_Name}`、`{Scan_Rate}`、`{CV_Window}`、`{Cycle_Number}`、`{Low_Freq}` 等字段。左树“图例/别名”列显示人工别名或自动紧凑/缩写结果；模板优先于别名。CV 叠加图默认每个数据的循环图例上限为 10；超过时按连续循环范围自动合并（例如 500 个循环显示为 `Cycle 1-50`、`Cycle 51-100`……），可在“分析参数”的“循环图例上限”中调整，设为 0 可恢复逐循环图例。
- **可拖拽布局与列宽**：数据集、左下角 CV/EIS/CP 结果表、日志和右侧当前图设置之间均可拖动分隔条；数据树、结果表和每图数据对话框的所有列均可拖动，双击列边界或右键表头可自动适配。窗口几何、分隔比例和列宽会被记住。
- **当前图自定义选项**：分析参数、坐标范围和论文排版固定在主窗口右下方，底栏默认约 400 px 高；左侧结果表、中间日志和右侧设置可拖动调整宽度并记住。切换图时设置跟随切换。电容–扫速支持一次函数、坐标直线、幂律和不拟合；X/Y 轴可分别自动、线性或对数选择，误差棒和拟合线独立开关。
- **现代玻璃界面**：顶部菜单栏、按钮组、下拉列表及右键菜单采用局部 Liquid Glass 材质。系统高对比度或明确关闭透明时回退实色。
- **手动坐标范围**：所有图均可分别指定 X/Y 最小值和最大值，留空表示自动。单图显示一个范围栏目；Bode、EIS 拟合等双子图分别显示上下图栏目；CP 容量-循环的左右双 Y 轴也分开设置，右轴只设 Y 范围并与左轴共享 X。范围随项目保存，导出 PNG/PDF/SVG/TIFF 时同样生效。Nyquist 图的手动范围优先于等比例坐标；未设置范围时，仅当 Z'/Z'' 跨度比不超过约 4:1 才强制等比例，避免高频过滤后出现大面积空白。
- **显示单位与标尺**：EIS 阻抗、CV/LSV/I‑T 电流、CV 电容和 Trasatti 电荷均可在“坐标范围”页自动选择或手动指定合适前缀；新建 LSV/I‑T 图默认自动选择，旧图保留原始单位，用户可自行切换。CP 容量–循环图在分析参数中选择单位，新图默认自动选择。范围输入会显示当前单位；同一物理量的单位前缀变化时自动换算，切换为不兼容的物理量或无法安全换算时清空对应轴的手动范围。旧工程未记录范围单位时，首次按打开时当前显示的单位解释，无法追溯保存时的单位。轴标签可用 `{unit}` 随单位变化。对数轴的 X/Y 主刻度可分别选择默认、科学计数法或小数。单坐标轴图可统一 X/Y 主刻度的**数值间隔**；两轴物理单位不同时只表示数字相同。
- **紧凑排版**：最终坐标范围、单位和刻度确定后才执行统一排版，避免自动范围的长刻度标签在切换到手动范围后留下大块左边距；论文图内/图外图例重排幂等，不会重复叠加图例。
- **上/右边框刻度**：显示上/右边框时可分别关闭上边框刻度或右边框刻度；边框隐藏时对应刻度自动隐藏，主刻度和次刻度同时生效。
- **论文缩放补偿**：输入图片占版心宽度比例（0.5/0.33/0.25）、版心宽度和正文字号（默认 10 pt）。按“论文目标字号 ÷ 插入缩放比例”计算源图字体；占比严格小于 0.33 时，为保证固定画布可排版，所有图中文字再缩至计算值的 80%。界面显示源图字号和论文实际字号，详见 [修正报告](docs/PROJECT_REVIEW.md)。
- **论文线宽补偿**：在「当前图 → 论文尺寸与字号」的图例设置下启用线宽补偿。自动模式在图片占版心 ≥ 0.5 时使用全宽（×1.00），较小时使用半宽（×0.60）。也可固定选用全宽、半宽，或通过滑条与输入框指定 ×0.10–×2.00。曲线、边框、刻度、网格和辅助线按插入比例补偿。样式面板显示基准值，预览标出修正系数、源图线宽和论文线宽。设置随图保存，点大小、刻度长度和柱宽沿用各自设置。
- **图例布局**：可设自动、图内或图外，自动外置阈值默认 0.5；图例列数可按可用宽度/高度自动适配或手动设为 1–8 列。普通图例过宽时会自动移到图外并保留轴标题空间；外置图例根据坐标轴结构安排在底部、顶部或拟合图右侧，多坐标轴共享并按曲线身份去重，不会因短标签相同而丢曲线。
- **多选与清空**：支持 Ctrl/Shift 多选、全选、删除选中和一键清空当前数据集（不删除源文件）。
- **CV 快速分析**：电容-扫速曲线、固定电位电流-扫速、b 值、Trasatti 电荷分解、Dunn 电流分解，以及不同扫速下的贡献占比柱状图。
- **面积/质量归一化**：支持 F/cm²、F/g、mA/cm²、A/g、C/cm²、C/g。
- **EIS 快捷分析**：自动估算 Rs、Rct、f_peak、Cdl、τ、低频 |Z|、1 Hz 相位；支持 Nyquist/Bode 和频率范围过滤。
- **EIS 拟合**：自动推荐模型，支持 `Rs-(Rct||CPE)`、`Rs-(Rct||C)`、`Rs-CPE`、`Rs-C`，输出参数、标准误、R²、RMSE 和残差图。
- **CP / GCD 分析**：支持 CHI Chronopotentiometry 的 `Time/sec, Potential/V` 主区和可选 `Hold Time/sec, Current/A` 保持段。GCD 电位-时间图可选自动补全高/低电位保持平台；容量-循环图可显示电荷容量或按实测段电位差计算的电容（Q/ΔV），可选充电、放电、两者或算术平均。百分比支持手动参考值、各文件各自指定循环参考，或跨文件统一参考循环；各文件按循环会为每个文件分别归一化，可能出现多个 100% 点，需要单一基准时应选择统一参考循环，此时所选文件的 Cycle 必须位于当前显示范围内，充放电分别以该 Cycle 的对应值为 100%，平均曲线以该 Cycle 的平均值为 100%。当前图分析参数可自动或手动选择 Ah、C、F 系列及相应的面积/质量归一化单位。手动参考值使用所显示的物理单位，可输入科学计数法或选择倍率；自动前缀随数据变化时参考值仍保持原来的物理量。默认以不同颜色区分容量和库伦效率。
- **CP 多文件拼接**：工作区已有多个 CP 数据时，使用“拼接已加载 CP 容量-循环”基于左侧选中/勾选的 CP 数据直接创建拼接图，不会重新打开文件对话框。每个文件可设置参与拼接的 Cycle 起止范围；X 轴可选择连续重编号（1..M）或按实际累计编号（保留被排除循环造成的空号）。拼接图把充电、放电、平均和库伦效率分别合并为一条连续曲线，图例沿用该图的容量曲线图例设置。拼接只影响当前图及图片导出，不修改原始数据、分析结果表或 CSV。
- **CP 保持段与图例**：导入时若检测到保持段电流或保持时间配置，会在状态栏、日志和 CP 结果表备注中说明；未记录保持段电流本身不作为警告。容量–循环图的“显示图例”开关独立控制容量与库伦效率曲线的图例，并可分别编辑充电、放电、平均值和库伦效率的文字。内容支持 `{label}`、`{name}`、`{quantity}` 和 `{unit}`，留空使用默认文字，输入 `{ }` 隐藏该图例项。
- **绘图预设**：日常分析、IEEE 单栏、IEEE 双栏、演示/组会、论文/学位论文；IEEE/论文样式默认 Arial，支持用户预设保存和 JSON 导入/导出。
- **快捷绘图参数**：选择预设直接应用，不再强制弹窗；工具栏“微调当前图”可打开参数窗口，调整坐标区比例、线宽、X/Y 轴字体、图例/注释/网格、上/右边框及其刻度等，支持“应用（仅当前图）”和“保存到配置（覆盖/另存为）”。
- **绘图区右键菜单**：可修改当前图颜色、画布比例和元素样式，或按比例适应标签页；可复制当前图像（PNG）或当前矢量图（SVG，可粘贴到 Word/PowerPoint/Illustrator 等）。在“当前图设置”的颜色页中，图形与文字色块分开选择，通过内嵌调色盘、常用色或十六进制颜色值调整。旧项目颜色覆盖继续按原有方式显示。
- **统一画布基准**：所有预设使用 3.2 in 逻辑高度，画布宽度由宽高比计算。预览与导出共用逻辑宽高比；界面缩放只改变预览 DPI，不改变画布布局。
- **项目与导出**：`.cvproj` 项目保存/恢复；PNG/PDF/SVG/TIFF 图像导出；PNG/TIFF 导出时可单独设置 72–1200 DPI，PDF/SVG 的矢量图元可无损缩放，DPI 只影响其中的栅格图层；分析结果 CSV 批量导出。含 LSV/I‑T 的项目使用 v3 格式，旧版程序无法打开；已有 CV/EIS/CP 项目仍可读取并保持 v2 格式。
- **GUI 设置与设计系统**：工具 → 设置 → GUI 设置管理界面主题、缩放倍数、Liquid Glass / 实色及局部动画。主题颜色由 `themes.json` 管理，缺失时自动从内置模板创建。右侧“分析与参数”面板的控件、标签页和下拉项悬浮提示使用 Liquid Glass 浮层，系统透明关闭或高对比度时回退实色。设计 token、组件规则和扩展约定见 [DESIGN.md](DESIGN.md)。
- **绘图交互**：Matplotlib 缩放/平移工具栏悬浮于画布顶部，默认收起，点击“⋯”展开；鼠标坐标显示 4 位有效数字，必要时采用科学计数法。图例/坐标轴/注释开关和循环重编号位于当前图选项。
- **日志与错误处理**：导入、解析、拟合、导出和异常统一记录到日志面板和旋转日志文件。

### 2. 安装与启动

要求 **Python 3.11+**。

```bash
pip install -r requirements.txt
python start_gui.py
```

测试：

```bash
pytest tests_v2
```

Nuitka 打包使用 `build.bat`，入口为 `start_gui.py`；构建环境、命令和故障排查见 [Build.md](Build.md)。

如果窗口化启动失败且没有错误弹窗，可查看启动日志（路径和诊断方法见 [Build.md](Build.md)）。应用不再恢复 Qt 保存的 dock 图，只恢复窗口几何、分隔条尺寸和列宽，以避免旧的停靠布局导致启动访问冲突。仍可设置 `CVANALYSIS_DISABLE_LAYOUT_RESTORE=1` 跳过窗口几何恢复。

### 2.1 版本与升级

- 当前版本 **v2.3.0**：Dunn v5 支持按支路的电位选区、拟合/实测 100% 基准、闭合差/残差/抵消诊断与三份 CSV 导出；CP/GCD 增加 CHI 采样网格校验、电位切换时序与 CE 范围；新增图标签重命名与论文线宽补偿。2.2.0 的 Dunn 双基准、左侧实时勾选、b 值/Trasatti、CP/GCD 完整性与 EIS 几何估计继续保留。
- 文本模板支持 `{value:.2f}` 等受限格式，指定精度时保留末尾零；先替换已知变量，再解析 `$...$` 数学公式和公式外的 `\n`。不执行 Python 表达式或外部 TeX。
- 已有 v1 克隆：没有本地修改时执行 `git pull --ff-only`；有修改时先提交到自己的分支或备份，再更新；不确定时直接重新 clone。
- 旧 GUI 已移除；v1 `config.json` 会自动迁移为 v2 配置。

### 3. 基本工作流

1. **导入**：点击“导入数据文件”，可多选 CV/EIS/CP 文件。坏文件会记录到日志，不影响其他文件。
2. **查看数据集**：左侧数据集树显示短文件名、图例/别名、扫速/频率/电流、窗口/频率、循环/点数和状态；平均电容、Rs、容量等分析指标只在左下结果表显示。完整文件名/路径和细节显示在树下方。
   - 勾选文件/循环会更新当前图。切换标签恢复该图的勾选，父节点显示全选/部分选中/未选三态。其他类型的文件仍可点击查看详情、通过右键新建对应图表。新建图优先使用相符的选中行，否则使用相应的勾选范围。Ctrl/Shift 多选；支持全选、删除选中、清空数据。
   - 只有一张图时，新导入且类型匹配的文件自动加入该图。有多张图时，新文件默认不勾选，可在任意标签页单独加入。
   - 双击文件或右键“绘制”会创建一个只包含该数据的独立图。
   - 右键还可设置电极面积/活性物质质量、设置数据图例模板、设置图例/别名或删除数据。双击“图例/别名”列也可编辑。
   - 可拖动一个或多个文件，在同一 CV/EIS/CP 分组内重新排序；勾选、循环选择和当前图的数据选择保留。绘图顺序与文件序号同步更新，顺序随项目保存。
   - 拖动树和下方详情区之间的分隔条可调整占比。
   - 左下 CV 结果和 CP / GCD 结果表中，双击文件/数据行可展开每个循环的电容、C/A、C/m、容量、库伦效率和 IR 降；再次双击收起。
3. **每图选择数据 / 设置**：右键画布选择“本图数据与图例...”可勾选该图的文件和 Cycle、设置图例模板；也可从“工具 → 当前图数据与图例...”进入。分析与论文选项位于右下角“当前图”面板；画布右键提供样式/颜色/轴标签、预设、图片比例、复制、导出和恢复默认。

分析与绘图警告显示在非模态弹窗及底部中间的红字日志。预览、复制和导出的图像仅包含数据和图注。
4. **设置图例模板/别名**：在数据集树右键选择“设置数据图例模板...”或“设置图例/别名...”，也可使用“工具”菜单。模板优先于别名；模板中可用 `{Alias}` 引用别名。例如：
   - `{CV_Voltage}-{Cycle_Number}` → `1.5V-1`、`1.5V-2` ...
   - `{Sample_Name}-{Scan_Rate}` → `样品A-0.01V/s`
   - `{file_n}-{cycle_n}` → 第 2 个文件的第 3 个循环显示为 `2-3`。
   - `{file_n}` 按数据集树当前顺序从 1 开始，CV 后接 EIS；同一源文件的多组数据共用序号。单张图只选择部分文件时，仍使用整个数据集的文件序号。
   - 字段大小写不敏感；CV 叠加图中模板包含 `{cycle_n}` 或 `{Cycle_Number}` 时会逐循环显示图例，否则每个数据只显示一个图例。
   - 勾选“显示时重编号循环”后，`{Cycle_Number}` 在每个数据内从 1 开始连续编号。
   - `{cycle_n}` 始终使用文件内原始循环号，不受筛选循环或显示重编号影响。
   - 数据级模板作为默认值；单张图可在“数据...”对话框中覆盖，留空则继承默认值。输入 `{ }` 可显式隐藏对应数据的图例，曲线本身仍保留；对于多组数据合成一组结果的分析图，所有参与数据均设置 `{ }` 时隐藏整张图的结果图例。容量–循环图按“显示图例”开关及该图独立的曲线图例设置显示，不受数据级 `{ }` 隐藏影响。
5. **快速分析**：右侧“分析与参数”面板顶部选择归一化，CV/EIS/CP 标签提供相应参数和分析按钮，“显示”管理图例、坐标轴和注释。CP 标签可设置“电位-时间自动补全保持区间”和“容量计入恒压保持段”，并提供“拼接已加载 CP...”入口。顶部工具栏的“CV 分析 / EIS 分析 / CP / GCD 分析”为分类下拉菜单。CV/EIS/CP 结果表位于左下角、数据树下方；表格首次按内容适配，之后保留手动列宽。“适配列宽”按钮可重新适配当前结果表，“视图 → 重置布局”可恢复默认布局和列宽。
   - 工作区已有多个 CP 数据时，选中或勾选至少两个 CP 文件后使用“拼接已加载 CP...”即可直接建图，不需要再次导入；若只想使用已加载文件中的部分循环，可在随后打开的拼接设置或“当前图 → 分析参数”中调整。
   - CP 容量–循环图的“分析参数”页可启用跨文件拼接、选择连续/累计 Cycle 编号、设置每个文件的拼接范围，并选择统一 100% 参考文件与 Cycle。统一参考 Cycle 只列出当前显示范围内的循环。
    - 右下角“当前图”面板的“坐标范围”页可手动设置 X/Y 范围，并在页首切换 EIS 阻抗或 CV/CP 电流单位；范围输入会标注当前单位。多个子图或双 Y 轴会分成独立栏目；留空即自动，对数轴必须输入正数。修改后点击“应用到当前图”，单位切换会自动换算已有范围。
    - 右键图区选择“当前图设置...”，在“元素与样式”页可用双列紧凑布局调整字号、线宽和显示开关，并为当前图单独填写 X/Y 轴标签。标签留空使用当前文本预设，输入一个或多个空格表示空标签；覆盖随项目保存。
6. **切换预设**：顶部“预设”下拉框切换日常/IEEE 等风格，切换后直接应用并保留当前图已有 override；“应用到全部”只统一预设，不复制某一图的 override。需要微调时点击“微调当前图...”。
   - “应用（当前图）”：立即生效，只影响当前图，不写入配置。
   - “保存到配置”：先应用，再选择覆盖当前预设或另存为新预设；覆盖前会提醒。内置预设被覆盖时会创建同名用户覆盖，删除用户覆盖即可恢复内置样式。
7. **EIS 拟合**：选择 EIS 文件和频率范围，模型选“自动”或指定模型，点击“拟合当前 EIS”。拟合结果、残差和参数显示在新标签页与结果表。
8. **导出**：每个图标签页可单独导出 PNG/PDF/SVG/TIFF；文件菜单可批量导出分析 CSV。
9. **关闭当前标签页 / 项目**：`Ctrl+W` 关闭当前图标签页，只移除该图，不关闭项目；`Ctrl+Shift+W` 关闭当前项目并返回空白工作区，应用不退出、不删除源数据或 `.cvproj`。关闭项目前如有未保存修改会提示保存；后台任务运行中会提示等待，不强制终止线程。
10. **保存项目**：`Ctrl+S` 直接保存当前 `.cvproj`；新项目首次保存或使用“项目另存为...”时选择路径（`Ctrl+Shift+S`）。保存数据源路径、电极参数、显示选择、每图数据选择、图例模板、人工别名、绘图标签和预设。旧项目中的跟随标记会被忽略，已保存的每图数据选择保留。有未保存修改时窗口标题带 `*`，关闭项目、清空数据或打开其他项目前会提示保存。

### 4. 内置绘图预设

| 预设 | 用途 | 主要特点 |
|---|---|---|
| 日常分析 | 快速查看 | 较大字号、网格、统计注释 |
| IEEE 单栏 | 期刊单栏 | 8 pt、刻度朝内、无网格、PNG 600 dpi |
| IEEE 双栏 | 期刊双栏 | 9 pt、无网格、色盲友好配色、PNG 600 dpi |
| 演示/组会 | PPT | 大字号、粗线、网格 |
| 论文/学位论文 | 论文插图 | 6 in 宽、12 pt、细网格、色盲友好配色 |

预设可编辑并保存为用户预设；支持 JSON 导入/导出，便于课题组共享统一样式。旧项目和预设的宽高会保留比例并归一到 3.2 in 高；不再提供手动输入画布宽高。IEEE 单栏/双栏和论文样式默认使用 Arial（Helvetica 缺失时回退 DejaVu Sans），轴标签/刻度/图例使用常规字重，标题只在启用时显示。快捷参数窗口中的“应用”不写配置，“保存到配置”才持久化；覆盖会二次确认。

#### 图内文字与文本预设

- “工具 → 预设管理...”的第二页“文本预设”管理全部图内固定文字：轴标签、默认标题、分析注释、固定图例文字和后缀。
- 默认文字不再散落在渲染代码中，而是保存在 `config.json` 的 `text_presets`：
  - `text_presets.active` 指定当前文本预设；
  - `text_presets.presets.default.values` 是可直接编辑的默认文字；
  - 用户可新建、编辑、导入、导出和删除自定义文本预设。
- 切换活动文本预设会应用到所有已打开图；每图通过右键“当前图设置...”填写的 X/Y 轴标签覆盖优先，不会被清空。
- 文本值留空表示使用内置默认；输入一个或多个空格表示空文字。支持 Unicode 上下标和 Matplotlib mathtext（如 `$v^{-1/2}$`、`$R_{ct}$`），程序会保留 mathtext 花括号。
- 图内诊断警告和“无数据/请先拟合”等提示不属于文本预设，保持现有中文诊断输出。
- 文本预设属于应用配置，不写入 `.cvproj`；项目只保存每图轴标签覆盖，文本预设变化在下次打开图或切换活动预设时生效。

### 5. 算法说明

#### CV

- 循环分割：优先使用电位拐点 + prominence 过滤的稳健算法；设置中可切换为 v1 兼容算法。首个循环若从非极限电位起始会被标记为不完整并警告，但默认仍参与统计。
- 循环面积在正反扫实测重叠区间积分。重复转折电位保留对应支路的实测点，单个共用转折点归入进入该转折点的支路。
- 循环电容：`C = Area / (2 × scan_rate × ΔV)`，与 v1 公式一致。
- 统计：有效循环平均、标准差、变异系数。默认按偏离程度固定裁剪 1 个循环（旧版兼容）；设置中可改为 z-score 阈值模式，只排除 `|z|` 超过阈值的循环。
- 固定电位电流：在目标电位处对正扫/反扫分支插值，取循环中位数。
- b 值按 `log|i| = b log v + log a` 回归。新图默认正扫，当前图可切换反扫或正反扫幅值平均。旧图保留以前的选项。不同有效扫速少于两个时只显示数据点。
- Trasatti 先对每个有效循环算电荷，再汇总同一文件。同扫速数据取平均，每个不同扫速等权回归。对 `q–1/√v` 外推得到 `q_outer`，对 `1/q–√v` 外推后取截距倒数得到 `q_total`。图中分别注明相对于外推总电荷和最低实测扫速电荷的比值。电位窗口检查比较实际积分上下限。
- Dunn 分析在当前图设置中选择正扫（默认）或反扫。两张图使用各扫速共同覆盖的电位区间，可通过「电位选区…」拖动或输入边界。所选支路以 `i/√v` 对 `√v` 逐电位做线性回归，斜率为 `k1`，截距为 `k2`。每个文件取有效选中循环的电流中位数，同扫速文件按所选单位归一化后等权平均，每个不同扫速参与一次拟合。自动选择排除标记为部分的循环，手动选中的部分循环会提示并参与覆盖区检查。[Wang 等，式（7）–（8）与图 7](https://doi.org/10.1021/jp074464w)
  - “Dunn 电流分解”叠加实测总电流、拟合总电流、电容和扩散分量。阴影覆盖零线与电容电流之间的区域。选取两次测量之间的扫速时仅显示预测曲线。
  - 创建任一 Dunn 图时，弹窗可选择整张图的 100% 基准。默认用两个拟合分量的净电荷之和，另一模式用该扫速的实测支路净电荷。当前图设置中可切换并保存。各分量均按同一电位窗口积分 `Q = ∫i dt`，保留电流符号。分量异号时可能出现负值或超过 100%，所选分母接近抵消时留空。非实测扫速仅拟合模式可以计算占比。
  - “贡献占比-扫速”可在当前图设置中选择并排、堆叠或随基准自动。自动模式下，拟合基准默认堆叠，扩散在下、电容在上。实测基准默认并排。堆叠时异号分量分别在零线两侧绘制。实测基准下两项合计偏离 100% 反映积分后的拟合偏差。电容项包含双电层和可能的赝电容响应。
  - Dunn 方法版本 5 保留原采样电位和选区端点，并检查组内中位数引入的局部拐点。每档扫速提供拟合与实测电荷、闭合差、原电流相对 RMS 残差和净电荷抵消比例。闭合差超过 ±3% 会提示。净值低于相应绝对积分的 10% 提示抵消，低于 0.1% 的分母留空。这些是显示和报告规则，两个百分比基准由用户选定。
  - 文件 → 导出分析 CSV 可输出 `dunn_summary.csv`、`dunn_points.csv` 和 `dunn_inputs.csv`，以图索引关联逐扫速汇总、逐电位系数与分量、参与文件和循环。没有选区字段的历史图沿用共同窗口，缺少百分比基准时使用拟合净电荷。旧图重新计算后可能因积分网格和循环筛选更新而出现数值变化。

电容–扫速拟合模式含义：一次函数在原始数据上拟合 `C = m·v + b`，轴类型只改变显示；坐标直线会按所选 X/Y 轴变换拟合，使最终图像中的线保持直线；幂律拟合 `C = a·vⁿ`。拟合方程的文本模板可使用 `{unit}` 引用当前电容显示单位，默认方程不强制增加系数单位。拟合图例按最终图形显示为 `Fitted Line` 或 `Fitted Curve`。各轴“自动”模式在数据全为正且范围跨 20 倍以上时选择对数轴，其余使用线性轴；纵轴自动模式还会检查误差棒下界。选项中会显示当前自动解析结果。幂律与对数-对数轴下的坐标直线数学上等价。

> 扫速分析要求各文件电压窗口一致或高度重叠；Dunn 至少需要两个不同扫速，建议三个以上。

#### EIS

- Rs 从高频端的有效实部估计，或由指定电路拟合给出。
- Rct 和几何 Cdl 需要频段覆盖近似理想单弧两侧。其他谱形的几何参数留空，可通过适用的电路拟合估计。
- f_peak：`-Z''` 最大值对应频率。
- Cdl：`1 / (2π f_peak Rct)`（几何估计）；CPE 模型使用有效电容换算。
- 拟合模型：
  - `Rs-(Rct||CPE)`：`Z = Rs + 1 / (1/Rct + Q(jω)^n)`
  - `Rs-(Rct||C)`：理想 RC 半圆
  - `Rs-CPE`：阻塞电极/超电容，`Z = Rs + 1/(Q(jω)^n)`
  - `Rs-C`：理想串联电容
- 自动模型在检测到覆盖两侧的单弧时选用 `Rs-(Rct||CPE)`。频段或弧形不足时由用户选择模型或调整频段。
- 拟合使用相对残差和软 L1 损失，报告 R²、RMSE、参数标准误和警告。低频扩散尾部明显时，建议限定拟合频率范围或使用 `Rs-CPE`。
- EIS 阻抗只支持面积归一化（Ω·cm² 系列）；选择质量归一化会回退原始阻抗并给出警告。面积归一化时图内 Rs/Rct 注释同样换算为 Ω·cm²。

#### CP / GCD

- CHI Chronopotentiometry 主区为 `Time/sec, Potential/V`；可选 `Hold Time/sec, Current/A` 块记录高/低电位保持期间的电流，保持时间不一定包含在主时间轴内。
- 活动电流段：用电位极值（prominence 过滤）分段并合并同一方向的小噪声段；充电/放电方向默认按“电位上升=充电”判断（适用于正极/全电池；负电极半电池需要外部统一符号），电流幅值优先取 `Cathodic Current`/`Anodic Current`。
- “自动补全保持区间”：按保持电流正负匹配段的结束限值，将保持段插入电位-时间曲线，并把平台吸附到高/低限值（仅在 5% 窗口内）。保持段数量与分段数相等时，先验证顺序映射的极性；矛盾时按段末电位重匹配，找不到同极性记录时不再强行回退。原始数据不被修改，补全只用于绘图/分析派生序列。
- GCD 循环：充电段后紧邻的放电段组成一个循环；开头单独放电段不计入。
- 容量：默认 `Q = |I| × t` 只统计恒流活动段；开启“容量计入恒压保持段”后加上保持段电流积分。
- 比容量：`Q_dis / m`（换算为 mAh/g）；面积容量：`Q_dis / A`（mAh/cm²）；库仑效率：`Q_dis / Q_chg × 100%`。
- 导入 CHI CP 时按原文本数字精度逐行校验采样网格。网格通过后用于容量、效率、能量和电位–时间曲线。项目保留源时间列及恢复依据。网格校验确认已保存样点的时间，循环是否完整另行判断。
- 电位切换模式按反转前后的样点限定切换时间。相邻充放电段共用同一切换时刻。稳定估计略超出区间时取最近端点，局部窗口结果不一致时取区间中点。缺少可验证的边界或边界区间重叠时按采样点计时。逐循环表和 CSV 标明计时方法，能定界时提供 CE 范围。能量按实测采样点积分。
- IR 降由电流切换两侧的局部电压趋势外推到同一时刻估算。存在电位保持段、采样点不足或局部线性外推不可靠时，IR 降留空，弹窗和底部日志按原因汇总。缺少某方向恒流设定时，相关容量和效率留空。循环完整性按电位限值或定时时长检查，部分或未确认循环保留编号与状态，并排除在完整循环统计之外。能量按活动段的 `∫V·I dt` 计算，可换算 Wh/kg 与 W/kg。
- 保持段记录不足或无法匹配时只显示警告，不强行补全；建议在图中结合原始电位-时间曲线核对。

### 6. 兼容性与清理说明

- **配置**：首次运行会自动把 v1 `config.json` 迁移为 v2，并生成 `config.json.v1.bak`（`.gitignore` 已排除）。
- **v1 字段镜像**：`config.json` 仍保留 `plot`、`colors`、`eis_plot`、`axis`、`grid`、`tick` 顶层字段，便于旧配置工具读取。
- **旧数据**：继续支持 CHI660E 逗号/Tab/空格/带引号 CSV，并增加编码回退。
- **旧 CLI / Python API**：
  ```bash
  python cv_analysis.py <CV文件>
  python eis_analysis.py <EIS文件>
  ```
  `CVAnalyzer`、`EISAnalyzer` 仍可从根目录模块导入，内部由 `cvanalysis.compat` 适配。
- **旧 GUI 已移除**：`cv_gui.py`、`plot_manager.py`、`data_display.py`、`ui_components.py`、`plot_config_dialog.py`、`config_manager.py`、`start_gui_legacy.py` 已清理，旧版本请从备份获取。v2 只维护当前工作区 GUI。
- **项目/预设格式**：均带版本号；未知字段保留，新增字段有默认值。

### 7. 项目结构

```text
cvanalysis/
  domain/       数据模型、SI 单位、异常
  io/           CHI 解析器、解析器注册表
  analysis/     CV/EIS/CP 分析、等效电路拟合、GCD 指标
  plotting/     样式预设、xkcd 颜色、CV/EIS/CP 渲染、导出
  services/     数据集、设置迁移、项目、CSV 导出
  ui/           工作区窗口、模型、控件、对话框、worker
  compat/       v1 CVAnalyzer/EISAnalyzer 适配器
cv_analysis.py      # v1 CLI / API 兼容入口
eis_analysis.py     # v1 EIS CLI / API 兼容入口
start_gui.py        # v2 GUI 入口
tests_v2/           # 单元测试、绘图 smoke、GUI smoke
docs/               # 开发文档
build.bat           # Nuitka 打包脚本
```

### 8. 已知限制

- EIS 几何 Rct/Cdl 只适用于覆盖两侧的近似理想单弧。选择等效电路拟合时，结果表和 CSV 标明模型及拟合频段。
- `Rs-CPE` 的 Rs 在缺少足够高频数据时可能不可辨识。拟合 Rs 接近零时保留原拟合值并提示核对模型及频段，几何 Rs 单独按高频有效实部估计。
- CP 默认按“电位上升=充电”解释；负电极半电池的充电/放电标签和库仑效率会反过来，当前版本不提供方向切换 UI。
- EIS 阻抗不支持质量归一化；选择后会回退原始阻抗并警告。
- Dunn/Trasatti 需要多个扫速。Dunn 使用所选支路的共同实测窗口，Trasatti 按各有效循环的实测面积算电荷，再检查不同数据的积分上下限。
- EIS 拟合对频率范围敏感；拟合前建议先检查 Nyquist/Bode 形态并关注 R²/RMSE 警告。

### 9. License

MIT，详见 [LICENSE](LICENSE)。

---

## English

### Overview

CVAnalysis v2 is a layered Qt workspace for CHI660E CV/EIS/CP data. It supports multi-file datasets, cycle-level visualization, scan-rate analyses, rapid EIS metrics and equivalent-circuit fitting, GCD capacity/efficiency analysis with optional hold-interval completion, and one-click switching between daily-analysis and IEEE paper plot presets.

### Install and run

```bash
pip install -r requirements.txt
python start_gui.py
pytest tests_v2
```

Python 3.11+ is required. Packaging uses `build.bat` (Nuitka); see [Build.md](Build.md) for build details and troubleshooting.

### Version and upgrade

- Starting with v2.0.0, `main` contains the v2 workspace; v1 is archived in the `v1-archive` branch and tags `v1.1`, `v1.2.3`, `v1.3.0`.
- Current release **v2.3.0** adds Dunn v5 with per-branch potential ROIs, fitted/measured 100% bases, closure/RMS/cancellation diagnostics and three CSV tables; CHI CP sampling-grid validation, potential-switch timing and CE ranges; plot-tab renaming and paper line-width compensation. The 2.2.0 Dunn dual-basis, live dataset-checkbox sync, b-value/Trasatti corrections, CP/GCD completeness and EIS geometry estimates remain.
- Existing v1 clones without local changes can run `git pull --ff-only`; commit or back up local changes first, or simply re-clone.
- The legacy GUI is removed; v1 `config.json` is migrated automatically.

### Main capabilities

- Multi-file CV/EIS/CP import with shortened filenames and file details. Dataset checkboxes update the active plot, and each tab restores its own file and cycle selection. New imports are unchecked when several plots are open.
- Plot tabs can be renamed in place: double-click a tab, press Enter or leave the field to commit, Esc to cancel; the context menu can rename or restore the automatic name. Names are stored per plot, separate from the in-figure title.
- CV: capacitance vs scan rate, current at fixed potential, b-value, Trasatti charge separation, Dunn current decomposition, and contribution percentage bars vs scan rate.
- Dunn v5 supports a per-branch potential ROI (drag or type endpoints), fitted/measured 100% bases, and reports fitted/measured charge, closure error, relative RMS residual and net-to-absolute charge ratios. It exports `dunn_summary.csv`, `dunn_points.csv` and `dunn_inputs.csv`; Dunn contribution plots use measured scan-rate categories on X.
- Normalization by electrode area or active mass.
- EIS: Rs/Rct/f_peak/Cdl/τ estimates, Nyquist/Bode plots, frequency filtering.
- EIS fitting: `Rs-(Rct||CPE)`, `Rs-(Rct||C)`, `Rs-CPE`, `Rs-C`; automatic model recommendation, parameter errors, R², RMSE and residual plots.
- CP/GCD: CHI `Chronopotentiometry` import, optional hold-current block, optional hold-plateau completion in potential-time curves, capacity/specific capacity vs cycle, Coulombic efficiency, IR drop, energy and power metrics. The CHI sampling grid is validated against the printed time values; capacity, CE and IR calculations can use the verified grid, and per-cycle results report the potential-switch timing method and CE range. IR drop is left blank with a reason when hold intervals, sampling or local linearity prevent a stable estimate.
- Categorized quick-analysis menus in the toolbar and menu bar: CV, EIS and CP/GCD.
- Plot presets: daily, IEEE single column, IEEE double column, presentation, thesis; IEEE/thesis use Arial. Non-default presets open a quick parameter dialog with apply vs save-to-config semantics, aspect ratio, per-axis fonts, top/right border ticks and display toggles.
- Manual X/Y limits for every plot, stored per project and applied to screen previews and exports. Separate sections are shown for Bode/fit subplots and for the secondary Y axis in CP capacity plots; empty values mean auto, and log axes require positive limits. On Nyquist plots manual limits take precedence over equal aspect; automatic equal aspect is used only when the Z'/Z'' span ratio is within about 4:1.
- Display units and tick scale: choose automatic or manual prefixes for EIS impedance, CV/LSV/I-T current, CV capacitance, Trasatti charge and CP capacity/capacitance. Existing LSV/I-T plots retain their original unit until changed. Compatible unit switches convert manual ranges; incompatible quantities or invalid conversions clear the affected range. Legacy ranges without unit metadata are initially interpreted in the unit displayed when the project is opened. Axis label overrides can use `{unit}`. Log axes support default, scientific or decimal ticks; unified X/Y tick intervals mean equal numerical intervals, including when the physical units differ.
- Compact layout: the final layout runs only after limits, units and ticks are fixed, so long auto-range tick labels no longer leave a large left margin after switching to manual limits. Paper-mode legend rebuilding is idempotent and never stacks duplicate figure legends.
- Paper-mode line-width compensation: auto/full/half/manual coefficients from ×0.10 to ×2.00 scale curves, spines, ticks, grids and guides for the insertion width; the preview shows the coefficient and the source/paper line widths.
- Top/right spine ticks can be disabled independently while keeping the spines visible; hiding a spine also hides its ticks (major and minor).
- Plot-canvas context menu: detect used colors (line colors plus marker fill/edge, text colors last), edit current-plot colors, canvas aspect ratio, element styles, or fit the image to the tab; copy the current plot as PNG or as an SVG vector image for Word/PowerPoint/Illustrator; contextual controls include bar width and opacity.
- `.cvproj` projects with `Ctrl+S` quick save and `Ctrl+Shift+S` Save As, PNG/PDF/SVG/TIFF export, CSV summary export.
- Analysis and rendering diagnostics appear in a non-modal dialog and in red in the workspace log. Plot previews, clipboard images and image exports contain data and plot annotations.
- `Ctrl+W` closes the active plot tab without closing the project; `Ctrl+Shift+W` closes the current project and returns to an empty workspace, preserving application layout/settings and prompting for unsaved changes.
- High-DPI UI with an adjustable 0.8-1.6 interface scale. The GUI uses a token-based design system with soft rounded controls, pill-shaped large primary actions, JSON colour themes and Qt Chinese translations; see [DESIGN.md](DESIGN.md).

### Compatibility

- v1 `config.json` is migrated automatically; v1 top-level style fields are mirrored.
- Old CLI/API entry points `cv_analysis.py` and `eis_analysis.py` are preserved through `cvanalysis.compat`.
- The old GUI and its UI modules were removed during the v2 cleanup; use the backup if the legacy GUI is required.

### Scientific notes

- CV integrates the measured overlap of the two branches. The mean branch charge is `Area / (2 × scan_rate)` per cycle. Trasatti fits `q` against `1/√v` for the outer charge and `1/q` against `√v` for reciprocal total charge. The measured low-rate ratio is labelled separately.
- New b-value plots use the forward sweep by default. Existing projects can retain the average absolute current of both branches. b-value and Trasatti fits require at least two distinct valid rates.
- Dunn v5 uses signed component charge, a per-branch potential ROI within the common measured window, and fitted/measured net-charge bases. It reports closure error, relative current RMS residual and net-to-absolute charge ratios; older plots without ROI fields keep the common window and fitted basis but may change numerically after recalculation.
- CP charge/discharge direction defaults to potential-rise = charge and is not configurable in the UI; negative-electrode half-cells require external sign handling.
- EIS impedance supports area normalization only; mass normalization falls back to raw impedance with a warning.
- CP validates the CHI time grid, uses potential-switch timing intervals when they can be bounded, and reports sampled/estimated/bounded methods plus CE ranges. Missing current, unconfirmed completeness and unstable switch extrapolation can leave metrics blank in results and CSV.
- EIS reports geometric Rct/Cdl only for approximately ideal arcs with both sides covered. Fitted metrics identify the circuit and frequency range.
