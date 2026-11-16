# CVAnalysis v2 开发文档

完整用户说明请见仓库根目录 [README.md](../README.md)。本文只记录 v2 的架构、数据流和扩展约定。

工作区目录、缓存保留和清理规则见 [工作区整理与临时文件管理](WORKSPACE_HYGIENE.md)。以下说明描述正式源码的当前行为。

## 分层

- `cvanalysis/domain`：dataclass 数据模型、单位换算、异常类型。所有物理量内部使用 SI 单位。
- `cvanalysis/io`：CHI 文本解析器 + 解析器注册表。解析器只负责文件 -> `CVRun`/`EISRun`/`CPRun`/`SweepRun`，不做统计和绘图。
- `cvanalysis/analysis`：纯 numpy/scipy 分析。CV 循环分割、积分、统计、扫速分析、Trasatti/Dunn；EIS 几何指标和等效电路拟合；CP 保持段拆分/补全与 GCD 容量/效率/IR/能量；`cp_series.py` 提供 CP 拼接/统一基准的共享 Cycle 数值。结果对象带 `method`/`method_version`。
- `cvanalysis/plotting`：`PlotStyle`、内置预设、图例模板、CV/EIS/CP/LSV/I-T 渲染函数和导出；`axis_limits.py` 统一处理手动范围和单位换算，`ticks.py` 处理可选的 X/Y 刻度间隔统一。`sweep_renderer.py` 支持 LSV/I-T 的全局归一化或每图参考面积/参考电容（A/cm²、动态 A/电容单位），`export.py` 把最终排版推迟到范围和刻度确定之后，避免自动范围长标签留下大边距。渲染函数不依赖 Qt，可用 Agg 后端在无 GUI 环境测试。
  样式支持坐标区比例、X/Y 轴独立字号/字重、Arial 论文预设和用户覆盖；`plotting/legend.py` 负责数据级图例模板、每图覆盖、人工别名和相似文件名紧凑决策，渲染函数仍保持无 Qt 依赖。普通图例由 `plotting/paper.py::fit_standard_legends()` 在最终排版阶段测量，必要时移到图外并保留轴标题空间。
- `cvanalysis/services`：数据集编排、设置迁移、项目保存/恢复、CSV 导出。
- `cvanalysis/ui`：Qt 工作区。`MainWindow` 只负责组装和信号连接；数据树和结果树使用 `QAbstractItemModel`；导入使用后台 `QThread`。
  `ui/tokens.py` 统一字体、间距、控件高度和圆角；`ui/layout.py` 负责首次窗口尺寸与对话框屏幕适配；`ui/theme.py` 生成带语义角色的 QSS 和按钮层级。设计规则见根目录 [DESIGN.md](../DESIGN.md)。
  快捷参数对话框区分“应用”（只写当前图 override）与“保存到配置”（写用户预设）；选择预设只应用预设、保留 override，不再强制弹窗。
  GUI 主题由 `appearance.py` 从 `default_themes.json` / 用户 `themes.json` 加载；旧主题文件缺失的新角色按同 id 内置主题回退。主题、缩放、材质和局部动画统一放在“GUI 设置”；`ui/glass/` 管理局部材质、下拉、按钮组、右侧分析面板 Liquid Glass 悬浮提示和悬浮工具栏。下拉弹窗必须使用 `LiquidComboView` 并保持 popup 不透明皮肤，避免 Windows 动画黑背景。
  数据集树勾选确定新图范围；已有图使用独立的 run/Cycle 快照，通过 `PlotDataDialog` 修改。旧项目的 `follow_dataset` 字段加载时忽略，已保存的选择继续保留。`LegendTemplateDialog` 编辑数据级默认图例模板，`LegendAliasDialog` 编辑单 run 人工别名。左树列已精简为名称、图例/别名、扫速/频率/电流、窗口/频率、循环/点数、状态；分析指标只在左下结果面板显示。
  分析面板保留 CV/EIS/CP/LSV/I-T/显示选项；CV/EIS/CP 结果表由 `ui.widgets.results_panel.ResultsPanel` 放在左下角。CV/CP 结果表是两级树，双击 run 行展开每个 cycle 的电容、归一化值、容量、效率和 IR 降。`ui.widgets.view_columns.ViewColumns` 统一管理树和表格：所有列可拖动，首次按内容适配，双击/表头右键重新适配；主窗口列宽保存在 `ui.column_widths`，分隔条尺寸保存在 `ui.dataset_splitter` / `ui.bottom_splitter`。当前图“坐标范围”页提供 EIS 阻抗/CV/CP 电流单位切换和强制统一 X/Y 刻度间隔；范围输入按显示单位读写，切换单位时由 `plotting/axis_limits.py` 保持物理范围。LSV/I-T 分析参数支持每图参考面积/参考电容与动态 A/cm²、A/电容单位。
- `cvanalysis/compat`：v1 `CVAnalyzer`/`EISAnalyzer` 薄适配层。根目录同名模块 re-export 这些类。

## 数据流

```text
文件 -> io.registry.load_files -> Dataset(CVRun/EISRun/CPRun/SweepRun)
     -> services.dataset_service.refresh_analysis -> CVRunSummary / EISMetrics / CPRunSummary
     -> ui.models.DatasetTreeModel
     -> PlotSpec + PlotStyle + legend.effective_template -> plotting.render_plot -> Figure
     -> PlotTab / export
```

## 配置兼容

`config.json` 同时保存：

- v2：`schema_version`、`analysis`、`eis`、`presets`、`plotting`、`ui`
- v1 镜像：`plot`、`colors`、`eis_plot`、`axis`、`grid`、`tick`

保存时 v1 镜像由当前激活的 v2 预设生成，便于旧配置工具/旧版本读取。迁移前生成 `config.json.v1.bak`。未知字段保留。旧 GUI 及其 UI 模块已从仓库清理，兼容入口只保留 `cv_analysis.py` / `eis_analysis.py` 及其 `cvanalysis.compat` 适配器。

## 扩展点

- 新文件格式：实现 `io.base.DataParser` 并加入 `io.registry.DEFAULT_PARSERS`。
- 新分析：在 `analysis` 中增加纯函数/结果 dataclass，在 `ui.widgets.AnalysisPanel` 增加按钮，在 `PlotSpec.kind` / renderer 注册新的绘图类型。
- 新等效电路：在 `analysis.fitting.MODEL_SPECS` 注册模型、初值和参数名，UI 自动列出。
- 新绘图预设：在 `plotting.presets.BUILTIN_PRESETS` 添加 `PlotStyle`，或存为用户预设 JSON。
- 新导出格式：在 `plotting.export.export_figure` 支持的 matplotlib 格式中添加 UI 过滤器。

## 测试

`tests_v2` 包含：

- 解析器：逗号/Tab/空格/引号/坏文件继续导入
- CV：循环分割、面积/电容、b 值、Trasatti、Dunn
- EIS：几何指标、RC 拟合、频率过滤
- CP：保持段拆分/补全、GCD 循环配对、容量/效率/IR/能量、多文件拼接与统一参考、项目与 CSV 往返
- LSV/I‑T：参考时间标注、参考面积/参考电容、动态 A/cm² 与 A/电容单位、裁剪和项目往返
- 设置：v1 迁移、未知字段保留、预设往返、主题 JSON 创建与主题/缩放保存
- 主题：默认/K-ON 调色板、非法主题回退、GUI 设置和主窗口应用
- 绘图：所有图表类型和预设的 Agg smoke test、图例模板展开/覆盖/未知字段、相似长文件名紧凑标签、人工别名、图例边界、手动 X/Y 范围（含 Bode/EIS 拟合双子图和 CP 双 Y 轴分栏）、Nyquist 高频过滤的自动范围与手动范围优先
- Cap-scan：线性/幂律/坐标直线拟合、自动对数坐标、论文图例
- 项目：保存/恢复映射、图例模板和人工别名持久化、选项往返、CP run_id 映射
- GUI：离屏导入、批量出图、自动 EIS 拟合、每图数据快照、玻璃控件和悬浮工具栏、右侧 Liquid Glass tooltip、下拉弹窗不透明皮肤、分隔条对齐、真实鼠标拖列、列宽恢复、固定底栏/旧布局迁移、分析标签和参数恢复、右键复制 PNG/SVG 矢量图、线条与 marker 填充/边缘颜色覆盖

2026-11-17 发布后维护完整回归为 549 项通过（开发环境 175.24 s、打包环境 180.52 s，均退出码 0；发布基线见 Build）；真实 Windows 桌面的 GUI 和打包程序仍需单独验收。覆盖策略、精确目标及 GUI/绘图/Release 定向组见 [测试指南](TESTING.md) 和 [tools/README.md](../tools/README.md)，定向组不替代完整套件。历史 `test_review_revision.py` 已按领域拆分/合并后退役。GUI 主题颜色由 `cvanalysis/default_themes.json` 提供默认模板，用户目录缺失 `themes.json` 时自动创建；主题与缩放统一在“工具 → 设置 → GUI 设置”中管理。GUI 设计 token 与扩展规则见 [DESIGN.md](../DESIGN.md)。[PROJECT_REVIEW.md](PROJECT_REVIEW.md) 和 [PERFORMANCE_OPTIMIZATION_PLAN.md](PERFORMANCE_OPTIMIZATION_PLAN.md) 是历史审查及规划，并非当前状态。

I-T 多参考线由 `plotting/it_references.py`、`sweep_renderer.py` 和 `ui/dialogs/it_reference_dialog.py` 负责；参考时间的逐数据标签显示状态和位置在项目加载时按 run_id 重映射。受限变量格式、MathText 和换行语义见 [TEXT_MARKUP_PLAN.md](TEXT_MARKUP_PLAN.md) 语法规则，核心是 `plotting/template_format.py`；不执行用户 Python 或外部 TeX。

新增模块：`analysis/cp.py` 提供保持段拆分/补全与 GCD 指标，`analysis/cp_series.py` 提供 CP 拼接/统一基准的共享 Cycle 数值，`plotting/cp_renderer.py` 提供 GCD 曲线与容量-循环图，`plotting/sweep_renderer.py` 提供 LSV/I-T 绘图与参考面积/参考电容；`plotting/axis_limits.py` 统一处理全部图型的 X/Y 手动范围和多轴映射；`plotting/export.py` 的 `render_to_new_figure()` / `render_svg_bytes()` 供预览、PNG 复制、SVG 矢量复制和导出共用同一渲染流程；`ui/widgets/analysis_options_panel.py` 固定于底栏右侧，按当前 `PlotSpec` 显示参数；`ui/dialogs/cp_concat_dialog.py` 管理 CP 拼接顺序/范围；`ui/glass/tooltips.py` 提供右侧分析面板 Liquid Glass tooltip。`ui/widgets/results_panel.py` 位于左下角，`ui/dialogs/plot_inspector_dialog.py` 和 `ui/widgets/plot_color_panel.py` 通过绘图区右键菜单编辑当前图。底栏尺寸存于 `ui.bottom_splitter`，不恢复 Qt dock 图。`plotting/paper.py` 保持导出画布和分辨率，按目标插入宽度计算缩放比例并反向补偿源图 pt 字号。`TaskThread` 对隔离快照执行耗时任务。项目格式 v2 内嵌数值数据并保存分析、拟合及样式快照，读取仍兼容 v1；含 LSV/I-T 的项目使用 v3。
