# CVAnalysis GUI 设计规范

> 适用范围：`cvanalysis/ui/` 桌面工作区。  
> 不适用范围：`cvanalysis/plotting/` 的论文图、数据颜色、白底画布和导出结果。  
> 参考：`awesome-design-md-main/design-md/apple/DESIGN.md`（Apple 网页设计分析）。本文件只吸收其“安静、层级、克制”的原则，不照搬网页尺寸和组件。

## 1. 设计目标

CVAnalysis 是科研数据工具，不是营销页面。目标是在高密度数据、长时间操作和多种分析模式之间保持：

- **内容优先**：数据集、图表、结果表是主角，界面 chrome 退后。
- **一个主操作**：每个上下文只有一个蓝色主按钮；危险操作使用独立语义。
- **可预期的范围**：用户始终能知道当前操作作用于选中行、勾选数据还是整个数据集。
- **轻量但有层次**：用表面色、hairline 和留白分层，而不是到处加边框和阴影。
- **可扩展**：新分析、新数据模式、新设置应能通过现有模式增加，不新增一套特例。

视觉关键词：**安静的科学仪器**。浅灰工作区、白色数据表面、石墨色文字、单一蓝色主操作、语义状态色、细线分隔、软圆角。

## 2. 与 Apple 规范的关系

采用：

- UI 退后，让数据和图表成为视觉中心。
- 一个主强调色，主/次/危险按钮有明确层级。
- 用表面色差和 1px hairline 建立层级。
- 2px 可见焦点环。
- 400/600 两档字重，4/8px 微网格。
- 圆角克制：结构边界保持平直，连续按钮组、菜单和浮动工具栏使用玻璃胶囊。

不采用：

- 营销页的低密度、80px 段落留白、44px 触控目标。
- 17px 正文、40–56px 展示标题、负字距。
- 全站大卡片圆角、厚阴影和深浅全宽色块。
- 所有按钮都蓝色；在桌面对话框中这会让取消和危险操作失去层级。
- 用 UI 主题改变科学图表的颜色、字体或导出画布。

菜单栏、按钮组、应用下拉和画布上的导航工具栏可使用 Liquid Glass。菜单栏沿用 Qt 的菜单交互与原有动画配置；材质只采样应用内部的局部背景，文字和交互保持清晰，系统关闭透明效果或启用高对比度时回退实色。

当前图样式的颜色页将图形与文字分组，在面板内选择颜色并显式应用。旧项目的 `analysis_options.color_overrides` 仍先按原语义应用；新增的 `color_overrides_by_role.graphics` / `text` 在其后独立作用于对应对象，同一 RGB 可在两个分组中分别设置。重绘、项目序列化和导出共用该规则；未知配置字段保留。较旧版本不识别新的分类映射，不能完整呈现新设置。

## 3. 设计令牌

颜色只存在于 `cvanalysis/default_themes.json` 和用户 `themes.json`。布局、间距、圆角、字体尺寸在 `cvanalysis/ui/tokens.py`。**不要把颜色硬编码到 UI 代码中，也不要把布局 token 放进用户主题。**

### 3.1 颜色角色

| 角色 | 用途 |
|---|---|
| `background` / `surface` / `surface_alt` | 窗口、数据表面、表头/悬停 |
| `surface_sunken` | 按下、禁用、只读区域 |
| `text` / `text_secondary` / `text_tertiary` | 主文字、次级文字、提示 |
| `border` / `border_light` / `border_control` | 装饰分隔、弱分隔、可交互控件边界 |
| `primary` / `primary_hover` / `primary_pressed` | 主操作 |
| `primary_text` | 主操作文字 |
| `focus` | 2px 焦点环 |
| `selection_bg` / `selection_text` | 选中行/单元格 |
| `error` / `warning` / `success` / `info` | 语义状态，不能互相替代 |
| `error_bg` / `warning_bg` / `success_bg` / `info_bg` | 状态底色 |
| `scrollbar` / `scrollbar_hover` | 滚动条 |
| `splitter` / `splitter_hover` | 分割条 |
| `tooltip_*` | 工具提示 |

默认主题保留蓝色主操作；K-ON 主题使用奶油/暖色表面，主操作使用 Mugi 蓝 `#3869b2`，红色只用于错误/危险，避免全界面处于“报警状态”。

### 3.2 字体

- 字体栈：`Microsoft YaHei UI` → `Segoe UI Variable Text` → `Segoe UI` → `Microsoft YaHei` → `Noto Sans CJK SC` → `Arial`。
- 正文 11pt（随 UI scale 调整），表格 10–10.5pt，面板标题 12–13pt。
- 只用 400 和 600；不使用 300 细体。
- 字号被限制在 9–14pt，避免 0.8 倍缩放过小或 1.6 倍过大。
- 中文不使用负字距；不使用 Inter/SF Pro 替代 CJK 字体。
- 数值列优先使用 tabular numerals（Qt 支持时）或等宽数字。

### 3.3 间距与尺寸

| Token | 值（scale=1.0） |
|---|---:|
| 间距 | 4 / 8 / 12 / 16px |
| 控件高度 | 24px 内容 + padding；约 36–38px 总高 |
| 表格行高 | 22px 最小，随 scale 调整 |
| 主按钮 | 高度约 38px |
| 分割条命中区 | 8px |
| 颜色 swatch | 26×26px，最小 24×24 |

### 3.4 圆角

| 用途 | 半径 |
|---|---:|
| 输入框、小按钮、swatch | 4–6px |
| 普通按钮、工具按钮、菜单项、标签页顶部 | 6px |
| 分组卡片、面板、外框、对话框内卡片 | 8px |
| 大号主操作按钮 | 胶囊（按实际高度计算半圆） |
| 状态 chip / 徽章 | 999px |

规则：

- **绘图 canvas 永远保持矩形**，不裁切 matplotlib 输出；只有 canvas 外层 frame 可以 8px 圆角。
- 表格/树只给外层容器圆角，不给行/单元格圆角。
- 主窗口顶层圆角交给 Windows 11 DWM，不自己 `setMask()`。
- 分割条不圆角。

## 4. 布局与控件模式

### 4.1 主窗口

- 左：数据集树 + 详情。
- 中：图文档标签页。
- 右：当前分析/参数。
- 下：CV/EIS/CP 结果、日志、当前图设置（水平三栏，可调整）。
- 底栏默认约为窗口高度的 30%，最大 320px；小屏优先保证图表面积。
- 窗口首次尺寸按屏幕可用区域计算，最小 900×600；保存的窗口超出屏幕时自动收敛到可用区域。
- 左侧/右侧 dock 与底栏三列共享边界；拖动后同步，宽度和列宽随设置保存。

### 4.2 图标签页

图标签页直接显示画布；顶部居中为可收起的 Matplotlib 玻璃工具栏，默认收起以减少遮挡。

- 画布右键提供本图数据与图例、分析/论文选项、样式、预设、图片比例、复制、导出和恢复默认。
- 新图使用相符的选中行或勾选数据。现有图的复选框由左侧实时编辑，标签页各自保存文件及循环范围。
- 标签页标题带首个数据名和 `+N`，同名图可区分；完整数据列表放在 tooltip。
- 双击图标签在标签栏中编辑自定义名称，Enter 或失焦提交，Esc 取消；右键可重命名或恢复自动名称，空名称恢复自动名称。名称按图保存，tooltip 保留完整名称、图类型与数据列表。
- 标签页使用右省略 + 滚动按钮，不能把第一个标签裁成半截。

### 4.3 按钮层级

- **primary**：每个上下文最多一个，例如“应用到当前图”、对话框“确定”、快速样式“应用（当前图）”。
- **secondary**：普通操作、取消、关闭、分析快捷按钮。
- **danger**：删除选中、清空数据、危险确认。红色只用于危险。
- **pill**：用于大号主操作及连续玻璃按钮组；单个导航按钮采用圆形反馈。

使用 `apply_button_role(button, "primary"|"secondary"|"danger", pill=False)`，不要在每个文件重复写 QSS 属性。

### 4.4 输入与分组

- 输入框、spin、combo 使用 1px `border_control`；焦点使用 2px `focus`。
- 设置项使用 `QGroupBox` 作为软圆角卡片；不要在外层再套一层带边框的容器。
- 长设置页必须放入 `QScrollArea`，按钮固定在滚动区外。
- 设置对话框使用分类/滚动，而不是无限拉长单列；新增设置优先放入已有分组，不新建窗口。
- 所有对话框使用 `fit_dialog()`，并根据屏幕可用区域收敛尺寸。

### 4.5 表格、树、结果

- 工作区表格/树使用方形结构边界和 1px hairline；表头使用 `surface_alt`。
- 行高 22px 起，随 UI scale 调整；不要给行/单元格做圆角。
- 选中态使用 `selection_bg`/`selection_text`；失去焦点时使用 `selection_inactive_bg`。
- 数值列右对齐，文本列左对齐；单位放在表头或值内，保持一致。
- 数据集树复选框支持三态：全选、部分选中、未选。父节点显示真实状态，不能“有任一子项勾选就显示全选”。
- 数据树标题显示当前图类型。复选框作用于当前图的兼容数据。其他数据行仍可选中、查看或用于新建图。
- 结果面板标签缩短为 `CV` / `EIS` / `CP/GCD`，避免底栏宽度不足时截断。

### 4.6 菜单、工具栏、提示

- 菜单项 6px 圆角；分隔线使用 hairline。
- 工具栏不是按钮仓库：核心导入/保存/分析/预设/导出保留；破坏性操作放到菜单或有明确标签的溢出菜单。
- 工具提示使用 `tooltip_*` 和 6px 圆角；提示文字使用 `text_tertiary`，不能低于 AA 对比度。
- 标准按钮通过 `QTranslator` 加载 Qt 中文翻译；自定义按钮使用中文文案。
- 分析和绘图诊断通过非模态弹窗及底部日志呈现。警告和错误使用主题的 `error` 角色，详细信息较多时在弹窗详情和日志中保留。

### 4.7 图表画布

- UI 主题只影响画布外框、标签页、工具栏和状态提示。
- `cvanalysis/plotting/` 的 `PlotStyle`、颜色循环、白底、字体、DPI 和导出流程保持不变。
- 复制/导出必须继续走 `render_to_new_figure()` / `render_svg_bytes()` / `render_plot()`。
- 画布保留数据与图注，诊断不参与图内布局或出图。导出和复制产生的诊断返回 GUI 通道。
- 不要对 `FigureCanvasQTAgg` 做圆角裁切或主题着色。

## 5. 状态与交互约定

- **新图范围**：树中选中行优先；没有选中行时使用勾选/可见数据。`AnalysisPanel` 显示“新图范围（选中行/勾选数据）”。
- **切换标签**：回填该图保存的文件或循环选择。无图时恢复工作区勾选。单图导入自动加入同类文件，多图导入默认未勾选。
- **Dunn 柱状图**：基准和布局随图保存。拟合总净电荷基准默认堆叠，实测净电荷基准默认并排，允许手动覆盖。
- **三态复选框**：run 有部分 cycle 选中时为 partially checked；没有任何 cycle 选中时 run 为 unchecked，且不进入 `visible_run_ids("cv")`。
- **预设切换**：只应用预设，不自动弹模态窗口；保留当前图 override。需要微调时显式点击“微调当前图...”。
- **应用到全部**：只应用预设，不复制当前图的 override。
- **EIS 频率校验**：频率错误只阻止 EIS 绘图/拟合；不要阻塞显示、归一化、CP 等无关选项。`options()` 对非法频率返回 `None`，错误信息留在 EIS 区域。
- **当前图设置**：分析/论文选项、样式/颜色、轴标签、图片比例、复制和导出都在同一菜单入口；底部“当前图”面板负责暂存式应用。
- **空/错误/忙碌**：错误就地显示；长任务显示进度并允许取消；不要用空对话框报告“没有数据”，优先禁用动作并给出 tooltip。
- **键盘**：所有可交互控件有可见焦点；主操作支持 Enter/默认按钮；常用打开/保存/导出/关闭保留快捷键。

## 6. 扩展指南

### 新增分析类型

1. 在 `analysis/` 增加纯函数/结果对象。
2. 在 `plotting/` 增加 renderer 或 `PlotSpec.kind` 分支。
3. 在 `AnalysisPanel` 用现有按钮/列表模式增加入口；不要复制一套窗口。
4. 在 `MainWindow._request_plot` 使用明确的 `run_ids`/scope。
5. 在 `tests_v2` 增加分析、绘图和 GUI 冒烟测试。

### 新增 GUI 设置

- 默认分析参数 → `SettingsDialog` 的“默认分析参数”组。
- 当前图临时设置 → `AnalysisOptionsPanel` 或当前图设置菜单。
- 全局外观 → `SettingsDialog` 的 GUI 设置组 / 主题 JSON。
- 长内容必须进滚动区；不要继续把单列对话框拉长。

### 新增主题颜色角色

1. 同时更新 `cvanalysis/default_themes.json` 的 `default` 和 `kon`。
2. 在 `theme.py` QSS 中使用 `__ROLE_NAME__`。
3. 更新 `tests_v2/test_theme.py` / `test_design_system.py` 的契约测试。
4. 保留旧用户 `themes.json` 的显式自定义值；缺失角色按同 id 的内置主题回退。

### 新增布局尺寸

- 放进 `UiTokens`，不要在 QSS 和 Python 布局里各写一套 magic number。
- 固定像素只用于真正不随缩放变化的元素（圆角、1px 线）。
- 对话尺寸通过 `fit_dialog()`，不要直接 `resize(920, 600)`。

## 7. 无障碍与平台

- 正常文字对比度 ≥ 4.5:1；大号文字 ≥ 3:1；焦点/控件边界 ≥ 3:1。
- 点击目标至少 24×24px；主操作约 38px 高。
- 焦点环 2px，不能只靠颜色变化。
- 中文字体必须显式 fallback；测试 `μ`、`Ω`、`²`、`³`、`−`、`–`、`·` 和中文标点。
- 在 Windows 100/125/150/200% 与 UI scale 0.8/1.0/1.3/1.6 交叉验证。
- 高对比度模式下不要覆盖系统 palette；必要时提供“重置外观”。

## 8. Do / Don't

### Do

- 先改 token，再改组件；先用一个通用模式覆盖多个页面。
- 用 `theme_color()` / `apply_theme_role()` / `apply_button_role()`。
- 用表面色和 hairline 分层。
- 保留一个主操作，危险操作明确标红。
- 给长设置页加滚动区和固定 footer。
- 新增功能先问“这是新数据范围、新分析、还是新视图？”再决定放树/图/结果/设置。

### Don't

- 不要在 UI 代码里硬编码十六进制颜色。
- 不要把 UI 主题色带进 `PlotStyle`、renderer 或导出图。
- 不要给每个 group box、tab pane、table 都加边框，形成“盒子套盒子”。
- 不要给表格行/单元格、绘图 canvas 做圆角。
- 不要用 pill 包住所有按钮。
- 不要让一个非法 EIS 频率阻塞所有设置。
- 不要让“当前图设置”同时存在于四个语义不同的入口。
- 不要在过渡期复制整套 `MainWindow`；单代码库、单 UI、必要时回滚。

## 9. 文件地图

| 路径 | 责任 |
|---|---|
| `cvanalysis/ui/tokens.py` | 字体、控制高度、间距、圆角、缩放 |
| `cvanalysis/ui/layout.py` | 首次窗口尺寸、对话框 fit |
| `cvanalysis/ui/theme.py` | 语义 QSS、颜色替换、按钮角色 |
| `cvanalysis/default_themes.json` | 内置 default / K-ON 颜色 |
| `cvanalysis/ui/app.py` | 字体、Qt 中文翻译、全局 stylesheet |
| `cvanalysis/ui/main_window.py` | 工作区壳、dock、图标签页、范围与动作编排 |
| `cvanalysis/ui/widgets/plot_tab.py` | 图标签页头、菜单、canvas 宿主 |
| `cvanalysis/ui/widgets/analysis_panel.py` | 分析动作与范围提示 |
| `cvanalysis/ui/widgets/analysis_options_panel.py` | 当前图暂存式设置 |
| `cvanalysis/ui/models/dataset_model.py` | 树、三态勾选、可见性 |
| `cvanalysis/ui/dialogs/*.py` | 设置/预设/检查器/数据选择等问题对话框 |
| `cvanalysis/plotting/*` | **不属于 GUI 主题范围**；保持科研图表输出不变 |

## 10. 维护检查清单

- [ ] 修改 QSS 后，`application_stylesheet()` 无未替换的 `__TOKEN__`。
- [ ] 新增颜色角色同时存在于 default 和 K-ON。
- [ ] 新增按钮使用 `apply_button_role`，没有重复 QSS。
- [ ] 新对话框使用 `fit_dialog()`，长内容有滚动区。
- [ ] 三态勾选、切换标签回填、多图导入及当前图未应用设置有回归测试。
- [ ] `tests_v2` 全量通过，图表及导出保持科学口径，诊断可在弹窗和底栏红字查看。
- [ ] 在 1366×768、1560×960、1920×1080 与 0.8/1.0/1.6 UI scale 下检查无裁切。
- [ ] `.opencode_cache/`、`KON!/`、用户 `.cvproj`、`config.json`、`themes.json` 和构建产物不进入 Git。
