# CVAnalysis v2

电化学工作站数据分析工作区，面向 CHI660E 导出的 CV 与 EIS 数据，支持多文件批量分析、扫速/电位相关分析、EIS 等效电路拟合，以及日常分析和 IEEE 论文风格绘图预设。

[中文](#中文) | [English](#english)

---

## 中文

### 1. 主要功能

- **多文件数据集**：一次导入多个 CV / EIS / CP 文件；单个文件失败不会中断整批导入。
- **长文件名处理**：文件名超过显示上限时自动缩短，完整文件名、路径、扫速/窗口等细节显示在左侧详情区。
- **循环级控制**：数据集树中可勾选文件或单个循环；勾选会即时更新开启“跟随勾选”的图。
- **每图独立数据选择**：图标签页顶部“数据 (N)...”可选择本图绘制的文件和 CV 循环；修改数据选择后自动停止跟随，勾选“跟随勾选”可恢复即时同步。
- **图例模板**：可为数据设置默认别名模板（如 `{file_n}-{cycle_n}`），也可在当前图单独覆盖；模板支持文件序号 `{file_n}`、文件内原始循环号 `{cycle_n}`，以及 `{File_Name}`、`{Scan_Rate}`、`{CV_Window}`、`{Cycle_Number}`、`{Low_Freq}` 等字段。
- **可拖拽布局与列宽**：数据集、左下角 CV/EIS/CP 结果表、日志和右侧当前图设置之间均可拖动分隔条；数据树、结果表和每图数据对话框的所有列均可拖动，双击列边界或右键表头可自动适配。窗口几何、分隔比例和列宽会被记住。
- **当前图自定义选项**：分析参数、坐标范围和论文排版固定在主窗口右下方，底栏默认约 400 px 高；左侧结果表、中间日志和右侧设置可拖动调整宽度并记住。切换图时设置跟随切换。电容–扫速支持一次函数、坐标直线、幂律和不拟合；X/Y 轴可分别自动、线性或对数选择，误差棒和拟合线独立开关。
- **手动坐标范围**：所有图均可分别指定 X/Y 最小值和最大值，留空表示自动。单图显示一个范围栏目；Bode、EIS 拟合等双子图分别显示上下图栏目；CP 容量-循环的左右双 Y 轴也分开设置，右轴只设 Y 范围并与左轴共享 X。范围随项目保存，导出 PNG/PDF/SVG/TIFF 时同样生效。Nyquist 图的手动范围优先于等比例坐标；未设置范围时，仅当 Z'/Z'' 跨度比不超过约 4:1 才强制等比例，避免高频过滤后出现大面积空白。
- **显示单位与标尺**：EIS 阻抗可在自动、Ω、kΩ、MΩ、mΩ 间切换（按面积归一化时为 Ω·cm² 系列）；CV/CP 电流可在自动、A、mA、µA、nA、pA 间切换。单位选择位于“坐标范围”页，范围输入会显示当前单位；切换单位并应用后，已有手动范围按物理值自动换算。对数轴的 X/Y 主刻度可分别选择默认、科学计数法（10 的幂）或小数，设置作用于当前图中相应方向的全部对数轴，并随项目保存。单坐标轴图可勾选“强制 X/Y 刻度间隔一致”，让两轴使用相同主刻度步长；间隔可留空自动选择，也可手动输入数值（如 100），避免某一轴刻度过密。手动间隔随显示单位自动换算。
- **紧凑排版**：最终坐标范围、单位和刻度确定后才执行统一排版，避免自动范围的长刻度标签在切换到手动范围后留下大块左边距；论文图内/图外图例重排幂等，不会重复叠加图例。
- **上/右边框刻度**：显示上/右边框时可分别关闭上边框刻度或右边框刻度；边框隐藏时对应刻度自动隐藏，主刻度和次刻度同时生效。
- **论文缩放补偿**：输入图片占版心宽度比例（0.5/0.33/0.25）、版心宽度和正文字号（默认 10 pt）。按“论文目标字号 ÷ 插入缩放比例”计算源图字体；占比严格小于 0.33 时，为保证固定画布可排版，所有图中文字再缩至计算值的 80%。界面显示源图字号和论文实际字号，详见 [修正报告](docs/PROJECT_REVIEW.md)。
- **图例布局**：可设自动、图内或图外，自动外置阈值默认 0.5；图例列数可自动适配或手动设为 1–8 列。外置图例根据坐标轴结构安排在底部、顶部或拟合图右侧，多坐标轴共享并合并重复图例项。
- **多选与清空**：支持 Ctrl/Shift 多选、全选、删除选中和一键清空当前数据集（不删除源文件）。
- **CV 快速分析**：电容-扫速曲线、固定电位电流-扫速、b 值、Trasatti 电荷分解、Dunn 电流分解，以及不同扫速下的贡献占比柱状图。
- **面积/质量归一化**：支持 F/cm²、F/g、mA/cm²、A/g、C/cm²、C/g。
- **EIS 快捷分析**：自动估算 Rs、Rct、f_peak、Cdl、τ、低频 |Z|、1 Hz 相位；支持 Nyquist/Bode 和频率范围过滤。
- **EIS 拟合**：自动推荐模型，支持 `Rs-(Rct||CPE)`、`Rs-(Rct||C)`、`Rs-CPE`、`Rs-C`，输出参数、标准误、R²、RMSE 和残差图。
- **CP / GCD 分析**：支持 CHI Chronopotentiometry 的 `Time/sec, Potential/V` 主区和可选 `Hold Time/sec, Current/A` 保持段。GCD 电位-时间图可选自动补全高/低电位保持平台；容量-循环图显示充电/放电容量和库仑效率，并汇总比容量、IR 降、能量和功率指标。保持段容量是否计入可单独开关。
- **绘图预设**：日常分析、IEEE 单栏、IEEE 双栏、演示/组会、论文/学位论文；IEEE/论文样式默认 Arial，支持用户预设保存和 JSON 导入/导出。
- **快捷绘图参数**：非默认预设会弹出参数窗口，可调坐标区比例、线宽、X/Y 轴字体、图例/注释/网格、上/右边框及其刻度等；支持“应用（仅当前图）”和“保存到配置（覆盖/另存为）”。
- **绘图区右键菜单**：检测当前图实际使用的颜色（含线条及标记填充/边缘，文字颜色在最后），可修改当前图颜色、画布比例、元素样式，或按比例适应标签页；可复制当前图像（PNG）或当前矢量图（SVG，可粘贴到 Word/PowerPoint/Illustrator 等）。预览默认按比例居中适配且不裁切。柱状图等还会提供柱宽、透明度等控件。
- **统一画布基准**：所有预设使用 3.2 in 逻辑高度，画布宽度由宽高比计算。预览与导出共用逻辑宽高比；界面缩放只改变预览 DPI，不改变画布布局。
- **项目与导出**：`.cvproj` 项目保存/恢复；PNG/PDF/SVG/TIFF 图像导出；PNG/TIFF 导出时可单独设置 72–1200 DPI，PDF/SVG 的矢量图元可无损缩放，DPI 只影响其中的栅格图层；分析结果 CSV 批量导出。
- **高 DPI**：界面基础字号 11pt，并提供界面缩放倍数设置（0.8–1.6），适配高分辨率屏幕。
- **绘图交互**：matplotlib 缩放/平移工具栏、图例/坐标轴/注释开关、循环重编号。
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

- 自 v2.0.0 起，`main` 为 v2 工作区；v1 代码存档在 `v1-archive` 分支和 `v1.1` / `v1.2.3` / `v1.3.0` tags。
- 已有 v1 克隆：没有本地修改时执行 `git pull --ff-only`；有修改时先提交到自己的分支或备份，再更新；不确定时直接重新 clone。
- 旧 GUI 已移除；v1 `config.json` 会自动迁移为 v2 配置。

### 3. 基本工作流

1. **导入**：点击“导入数据文件”，可多选 CV/EIS/CP 文件。坏文件会记录到日志，不影响其他文件。
2. **查看数据集**：左侧数据集树显示短文件名、扫速、电压窗口、循环数和统计值；完整文件名/路径和细节显示在树下方。
   - 勾选文件/循环会即时更新右侧所有开启“跟随勾选”的图；Ctrl/Shift 多选；支持全选、删除选中、清空数据。
   - 双击文件或右键“绘制”会创建一个只包含该数据的独立图，默认不跟随勾选。
   - 右键还可设置电极面积/活性物质质量、设置数据图例模板或删除数据。
   - 可拖动一个或多个文件，在同一 CV/EIS/CP 分组内重新排序；勾选、循环选择和当前图的数据选择保留。绘图顺序与文件序号同步更新，顺序随项目保存。
   - 拖动树和下方详情区之间的分隔条可调整占比。
3. **每图选择数据**：图标签页顶部“数据 (N)...”打开数据选择对话框，可勾选本图要绘制的文件和 Cycle，可批量设置本图图例模板；只影响当前图。修改数据选择后会自动关闭“跟随勾选”；仅修改图例模板时保持跟随。需要恢复即时同步时重新勾选图顶部的“跟随勾选”。
4. **设置图例别名**：在数据集树右键选择“设置数据图例模板...”，或使用“工具 → 设置数据图例模板...”。例如：
   - `{CV_Voltage}-{Cycle_Number}` → `1.5V-1`、`1.5V-2` ...
   - `{Sample_Name}-{Scan_Rate}` → `样品A-0.01V/s`
   - `{file_n}-{cycle_n}` → 第 2 个文件的第 3 个循环显示为 `2-3`。
   - `{file_n}` 按数据集树当前顺序从 1 开始，CV 后接 EIS；同一源文件的多组数据共用序号。单张图只选择部分文件时，仍使用整个数据集的文件序号。
   - 字段大小写不敏感；CV 叠加图中模板包含 `{cycle_n}` 或 `{Cycle_Number}` 时会逐循环显示图例，否则每个数据只显示一个图例。
   - 勾选“显示时重编号循环”后，`{Cycle_Number}` 在每个数据内从 1 开始连续编号。
   - `{cycle_n}` 始终使用文件内原始循环号，不受筛选循环或显示重编号影响。
   - 数据级模板作为默认值；单张图可在“数据...”对话框中覆盖，留空则继承默认值。
5. **快速分析**：右侧“分析与参数”面板顶部选择归一化，CV/EIS/CP 标签提供相应参数和分析按钮，“显示”管理图例、坐标轴和注释。CP 标签可设置“电位-时间自动补全保持区间”和“容量计入恒压保持段”。顶部工具栏的“CV 分析 / EIS 分析 / CP / GCD 分析”为分类下拉菜单。CV/EIS/CP 结果表位于左下角、数据树下方；表格首次按内容适配，之后保留手动列宽。“适配列宽”按钮可重新适配当前结果表，“视图 → 重置布局”可恢复默认布局和列宽。
    - 右下角“当前图”面板的“坐标范围”页可手动设置 X/Y 范围，并在页首切换 EIS 阻抗或 CV/CP 电流单位；范围输入会标注当前单位。多个子图或双 Y 轴会分成独立栏目；留空即自动，对数轴必须输入正数。修改后点击“应用到当前图”，单位切换会自动换算已有范围。
6. **切换预设**：顶部“预设”下拉框切换日常/IEEE 等风格；“应用到全部”统一所有图。选择非日常预设时会弹出当前图的快速参数窗口（坐标区比例、线宽、X/Y 轴字体、图例/注释/网格等）。
   - “应用”：立即生效，只影响当前图，不写入配置。
   - “保存到配置”：先应用，再选择覆盖当前预设或另存为新预设；覆盖前会提醒。内置预设被覆盖时会创建同名用户覆盖，删除用户覆盖即可恢复内置样式。
7. **EIS 拟合**：选择 EIS 文件和频率范围，模型选“自动”或指定模型，点击“拟合当前 EIS”。拟合结果、残差和参数显示在新标签页与结果表。
8. **导出**：每个图标签页可单独导出 PNG/PDF/SVG/TIFF；文件菜单可批量导出分析 CSV。
9. **保存项目**：`Ctrl+S` 直接保存当前 `.cvproj`；新项目首次保存或使用“项目另存为...”时选择路径（`Ctrl+Shift+S`）。保存数据源路径、电极参数、显示选择、每图数据选择、跟随勾选状态、图例模板、绘图标签和预设。有未保存修改时窗口标题带 `*`，关闭、清空数据或打开其他项目前会提示保存。

### 4. 内置绘图预设

| 预设 | 用途 | 主要特点 |
|---|---|---|
| 日常分析 | 快速查看 | 较大字号、网格、统计注释 |
| IEEE 单栏 | 期刊单栏 | 8 pt、刻度朝内、无网格、PNG 600 dpi |
| IEEE 双栏 | 期刊双栏 | 9 pt、无网格、色盲友好配色、PNG 600 dpi |
| 演示/组会 | PPT | 大字号、粗线、网格 |
| 论文/学位论文 | 论文插图 | 6 in 宽、12 pt、细网格、色盲友好配色 |

预设可编辑并保存为用户预设；支持 JSON 导入/导出，便于课题组共享统一样式。旧项目和预设的宽高会保留比例并归一到 3.2 in 高；不再提供手动输入画布宽高。IEEE 单栏/双栏和论文样式默认使用 Arial（Helvetica 缺失时回退 DejaVu Sans），轴标签/刻度/图例使用常规字重，标题只在启用时显示。快捷参数窗口中的“应用”不写配置，“保存到配置”才持久化；覆盖会二次确认。

### 5. 算法说明

#### CV

- 循环分割：优先使用电位拐点 + prominence 过滤的稳健算法；设置中可切换为 v1 兼容算法。首个循环若从非极限电位起始会被标记为不完整并警告，但默认仍参与统计。
- 循环面积：正扫/反扫分支插值后梯形积分。
- 循环电容：`C = Area / (2 × scan_rate × ΔV)`，与 v1 公式一致。
- 统计：有效循环平均、标准差、变异系数。默认按偏离程度固定裁剪 1 个循环（旧版兼容）；设置中可改为 z-score 阈值模式，只排除 `|z|` 超过阈值的循环。
- 固定电位电流：在目标电位处对正扫/反扫分支插值，取循环中位数。
- b 值：`log|i| = b log v + log a`，支持 2 个及以上扫速，建议至少 3 个。当前图可切换电流来源：正扫支路、反扫支路或旧版平均绝对电流（默认，兼容旧项目）。
- Trasatti：`q = q_cap + k v^(-1/2)`，其中 `q = C × 实际积分窗口宽度`（缺失时回退文件窗口）。不同文件窗口不一致时只警告，不静默丢弃；同时给出 `q–v^(1/2)` 外推的 `q_total` 和 `q_outer/q_total`（保留旧的低扫速占比字段）。
- Dunn：对正扫支路在共同电位窗口逐点拟合 `i(V) = k1 v + k2 v^(1/2)`，以 `i/√v` 对 `√v` 做标准线性化回归。两个 Dunn 图共用按电容/扩散分量绝对面积之和计算的占比。
  - “Dunn 电流分解”图的横轴是电位，纵轴是电流（总电流/电容电流/扩散电流），指定扫速下查看。
  - “贡献占比-扫速”图积分共同电位窗口内两个拟合分量的绝对面积，再按两者之和归一化为互补的 0–100% 堆叠柱。若两个拟合分量在部分电位相互抵消，这表示分量幅值构成，不等同于净实测电流面积的百分比。

电容–扫速拟合模式含义：一次函数在原始数据上拟合 `C = m·v + b`，轴类型只改变显示；坐标直线会按所选 X/Y 轴变换拟合，使最终图像中的线保持直线；幂律拟合 `C = a·vⁿ`。拟合图例按最终图形显示为 `Fitted Line` 或 `Fitted Curve`。各轴“自动”模式在数据全为正且范围跨 20 倍以上时选择对数轴，其余使用线性轴；纵轴自动模式还会检查误差棒下界。选项中会显示当前自动解析结果。幂律与对数-对数轴下的坐标直线数学上等价。

> 扫速分析要求各文件电压窗口一致或高度重叠；Dunn 至少需要两个不同扫速，建议三个以上。

#### EIS

- Rs：高频端最小实部估计；拟合时作为独立参数。
- Rct：半圆峰值 `2 × max(-Z'')` 的几何估计，或由拟合给出。
- f_peak：`-Z''` 最大值对应频率。
- Cdl：`1 / (2π f_peak Rct)`（几何估计）；CPE 模型使用有效电容换算。
- 拟合模型：
  - `Rs-(Rct||CPE)`：`Z = Rs + 1 / (1/Rct + Q(jω)^n)`
  - `Rs-(Rct||C)`：理想 RC 半圆
  - `Rs-CPE`：阻塞电极/超电容，`Z = Rs + 1/(Q(jω)^n)`
  - `Rs-C`：理想串联电容
- 自动模型：检测到完整半圆时推荐 `Rs-(Rct||CPE)`，否则推荐 `Rs-CPE`。
- 拟合使用相对残差和软 L1 损失，报告 R²、RMSE、参数标准误和警告。低频扩散尾部明显时，建议限定拟合频率范围或使用 `Rs-CPE`。
- EIS 阻抗只支持面积归一化（Ω·cm² 系列）；选择质量归一化会回退原始阻抗并给出警告。面积归一化时图内 Rs/Rct 注释同样换算为 Ω·cm²。

#### CP / GCD

- CHI Chronopotentiometry 主区为 `Time/sec, Potential/V`；可选 `Hold Time/sec, Current/A` 块记录高/低电位保持期间的电流，保持时间不一定包含在主时间轴内。
- 活动电流段：用电位极值（prominence 过滤）分段并合并同一方向的小噪声段；充电/放电方向默认按“电位上升=充电”判断（适用于正极/全电池；负电极半电池需要外部统一符号），电流幅值优先取 `Cathodic Current`/`Anodic Current`。
- “自动补全保持区间”：按保持电流正负匹配段的结束限值，将保持段插入电位-时间曲线，并把平台吸附到高/低限值（仅在 5% 窗口内）。保持段数量与分段数相等时，先验证顺序映射的极性；矛盾时按段末电位重匹配，找不到同极性记录时不再强行回退。原始数据不被修改，补全只用于绘图/分析派生序列。
- GCD 循环：充电段后紧邻的放电段组成一个循环；开头单独放电段不计入。
- 容量：默认 `Q = |I| × t` 只统计恒流活动段；开启“容量计入恒压保持段”后加上保持段电流积分。
- 比容量：`Q_dis / m`（换算为 mAh/g）；面积容量：`Q_dis / A`（mAh/cm²）；库仑效率：`Q_dis / Q_chg × 100%`。
- IR 降：放电初段的最大电位台阶；能量：`∫V·I dt`，可换算 Wh/kg 与 W/kg。
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

- EIS 自动 Rct/Cdl 是几何估计；非理想半圆应以拟合结果为准。
- `Rs-CPE` 的 Rs 在缺少足够高频数据时可能不可辨识，界面会回退到高频最小实部并给出警告。
- CP 默认按“电位上升=充电”解释；负电极半电池的充电/放电标签和库仑效率会反过来，当前版本不提供方向切换 UI。
- EIS 阻抗不支持质量归一化；选择后会回退原始阻抗并警告。
- Dunn/Trasatti 需要多个扫速和一致电压窗口；不一致时界面会警告，Trasatti 的 q 使用实际积分窗口宽度。
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
- Existing v1 clones without local changes can run `git pull --ff-only`; commit or back up local changes first, or simply re-clone.
- The legacy GUI is removed; v1 `config.json` is migrated automatically.

### Main capabilities

- Multi-file CV/EIS/CP import with shortened filenames, full-file details, per-run/per-cycle visibility, multi-select, delete-selected and clear-all.
- CV: capacitance vs scan rate, current at fixed potential, b-value, Trasatti charge separation, Dunn current decomposition, and contribution percentage bars vs scan rate.
- Normalization by electrode area or active mass.
- EIS: Rs/Rct/f_peak/Cdl/τ estimates, Nyquist/Bode plots, frequency filtering.
- EIS fitting: `Rs-(Rct||CPE)`, `Rs-(Rct||C)`, `Rs-CPE`, `Rs-C`; automatic model recommendation, parameter errors, R², RMSE and residual plots.
- CP/GCD: CHI `Chronopotentiometry` import, optional hold-current block, optional hold-plateau completion in potential-time curves, capacity/specific capacity vs cycle, Coulombic efficiency, IR drop, energy and power metrics.
- Categorized quick-analysis menus in the toolbar and menu bar: CV, EIS and CP/GCD.
- Plot presets: daily, IEEE single column, IEEE double column, presentation, thesis; IEEE/thesis use Arial. Non-default presets open a quick parameter dialog with apply vs save-to-config semantics, aspect ratio, per-axis fonts, top/right border ticks and display toggles.
- Manual X/Y limits for every plot, stored per project and applied to screen previews and exports. Separate sections are shown for Bode/fit subplots and for the secondary Y axis in CP capacity plots; empty values mean auto, and log axes require positive limits. On Nyquist plots manual limits take precedence over equal aspect; automatic equal aspect is used only when the Z'/Z'' span ratio is within about 4:1.
- Display units and tick scale: EIS impedance can be fixed to auto, Ω, kΩ, MΩ or mΩ (area-normalized variants use Ω·cm²); CV/CP current can be fixed to auto, A, mA, µA, nA or pA. The selector lives on the axis-range page, range fields show the active unit, and switching units converts existing manual limits to preserve the physical range. Logarithmic X and Y major ticks can independently use the default format, powers of ten, or decimal numbers; the choice applies across subplots and is saved with the project. Single-axis plots can force identical X/Y major-tick intervals; leave the interval empty for automatic selection or enter a numeric value such as 100. Manual intervals follow display-unit changes.
- Compact layout: the final layout runs only after limits, units and ticks are fixed, so long auto-range tick labels no longer leave a large left margin after switching to manual limits. Paper-mode legend rebuilding is idempotent and never stacks duplicate figure legends.
- Top/right spine ticks can be disabled independently while keeping the spines visible; hiding a spine also hides its ticks (major and minor).
- Plot-canvas context menu: detect used colors (line colors plus marker fill/edge, text colors last), edit current-plot colors, canvas aspect ratio, element styles, or fit the image to the tab; copy the current plot as PNG or as an SVG vector image for Word/PowerPoint/Illustrator; contextual controls include bar width and opacity.
- `.cvproj` projects with `Ctrl+S` quick save and `Ctrl+Shift+S` Save As, PNG/PDF/SVG/TIFF export, CSV summary export.
- High-DPI UI with an adjustable 0.8-1.6 interface scale.

### Compatibility

- v1 `config.json` is migrated automatically; v1 top-level style fields are mirrored.
- Old CLI/API entry points `cv_analysis.py` and `eis_analysis.py` are preserved through `cvanalysis.compat`.
- The old GUI and its UI modules were removed during the v2 cleanup; use the backup if the legacy GUI is required.

### Scientific notes

- CV capacitance uses `C = Area / (2 × scan_rate × ΔV)`, matching v1.
- Scan-rate analyses require multiple files with compatible potential windows. Trasatti warnings are additive; legacy low-rate fractions remain available.
- b-value current source defaults to the legacy average absolute current; choose forward/reverse branch explicitly for fixed-potential single-branch analysis.
- CP charge/discharge direction defaults to potential-rise = charge and is not configurable in the UI; negative-electrode half-cells require external sign handling.
- EIS impedance supports area normalization only; mass normalization falls back to raw impedance with a warning.
- EIS geometric metrics are estimates; use fitting for non-ideal spectra and inspect fit quality.
