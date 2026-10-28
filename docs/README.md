# CVAnalysis v2 开发文档

完整用户说明请见仓库根目录 [README.md](../README.md)。本文只记录 v2 的架构、数据流和扩展约定。

## 分层

- `cvanalysis/domain`：dataclass 数据模型、单位换算、异常类型。所有物理量内部使用 SI 单位。
- `cvanalysis/io`：CHI 文本解析器 + 解析器注册表。解析器只负责文件 -> `CVRun`/`EISRun`/`CPRun`，不做统计和绘图。
- `cvanalysis/analysis`：纯 numpy/scipy 分析。CV 循环分割、积分、统计、扫速分析、Trasatti/Dunn；EIS 几何指标和等效电路拟合；CP 保持段拆分/补全与 GCD 容量/效率/IR/能量。结果对象带 `method`/`method_version`。
- `cvanalysis/plotting`：`PlotStyle`、内置预设、图例模板、CV/EIS/CP 渲染函数和导出；`axis_limits.py` 统一处理手动范围和单位换算，`ticks.py` 处理可选的 X/Y 刻度间隔统一。`export.py` 把最终排版推迟到范围和刻度确定之后，避免自动范围长标签留下大边距。渲染函数不依赖 Qt，可用 Agg 后端在无 GUI 环境测试。
  样式支持坐标区比例、X/Y 轴独立字号/字重、Arial 论文预设和用户覆盖；`plotting/legend.py` 负责数据级图例模板和每图覆盖的展开，渲染函数仍保持无 Qt 依赖。
- `cvanalysis/services`：数据集编排、设置迁移、项目保存/恢复、CSV 导出。
- `cvanalysis/ui`：Qt 工作区。`MainWindow` 只负责组装和信号连接；数据用 `QAbstractItemModel`，结果用 `QAbstractTableModel`；导入使用后台 `QThread`。
  快捷参数对话框区分“应用”（只写当前图 override）与“保存到配置”（写用户预设）；界面支持 `ui.scale` 高 DPI 缩放。
  数据集树勾选会通过 `_sync_following_tabs()` 更新 `PlotSpec.follow_dataset=True` 的图；每图通过 `PlotDataDialog` 自定义 run/Cycle（改变选择时关闭跟随）；`LegendTemplateDialog` 编辑数据级默认图例模板。
  分析面板保留 CV/EIS/CP/显示选项；CV/EIS/CP 结果表由 `ui.widgets.results_panel.ResultsPanel` 放在左下角。`ui.widgets.view_columns.ViewColumns` 统一管理树和表格：所有列可拖动，首次按内容适配，双击/表头右键重新适配；主窗口列宽保存在 `ui.column_widths`，分隔条尺寸保存在 `ui.dataset_splitter` / `ui.bottom_splitter`。当前图“坐标范围”页提供 EIS 阻抗/CV/CP 电流单位切换和强制统一 X/Y 刻度间隔；范围输入按显示单位读写，切换单位时由 `plotting/axis_limits.py` 保持物理范围。
- `cvanalysis/compat`：v1 `CVAnalyzer`/`EISAnalyzer` 薄适配层。根目录同名模块 re-export 这些类。

## 数据流

```text
文件 -> io.registry.load_files -> Dataset(CVRun/EISRun/CPRun)
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
- CP：保持段拆分/补全、GCD 循环配对、容量/效率/IR/能量、项目与 CSV 往返
- 设置：v1 迁移、未知字段保留、预设往返
- 绘图：所有图表类型和预设的 Agg smoke test、图例模板展开/覆盖/未知字段、手动 X/Y 范围（含 Bode/EIS 拟合双子图和 CP 双 Y 轴分栏）、Nyquist 高频过滤的自动范围与手动范围优先
- 项目：保存/恢复映射、图例模板持久化
- GUI：离屏导入、批量出图、自动 EIS 拟合、跟随勾选即时同步、每图数据选择、分隔条、真实鼠标拖列、列宽恢复、分析标签和参数恢复、右键复制 PNG/SVG 矢量图、线条与 marker 填充/边缘颜色覆盖

当前完整回归为 **202 项通过**。修正状态与新功能使用说明见 [PROJECT_REVIEW.md](PROJECT_REVIEW.md)。性能瓶颈、P0/P1 优化顺序、缓存失效规则和未来模块拆分见 [PERFORMANCE_OPTIMIZATION_PLAN.md](PERFORMANCE_OPTIMIZATION_PLAN.md)。

新增模块：`analysis/cp.py` 提供保持段拆分/补全与 GCD 指标，`plotting/cp_renderer.py` 提供 GCD 曲线与容量-循环图，`plotting/axis_limits.py` 统一处理全部图型的 X/Y 手动范围和多轴映射；`plotting/export.py` 的 `render_to_new_figure()` / `render_svg_bytes()` 供预览、PNG 复制、SVG 矢量复制和导出共用同一渲染流程；`ui/widgets/analysis_options_panel.py` 固定于底栏右侧，按当前 `PlotSpec` 显示参数；`ui/widgets/results_panel.py` 位于左下角，`ui/dialogs/plot_inspector_dialog.py` 和 `ui/widgets/plot_color_panel.py` 通过绘图区右键菜单编辑当前图。底栏尺寸存于 `ui.bottom_splitter`，不恢复 Qt dock 图。`plotting/paper.py` 保持导出画布和分辨率，按目标插入宽度计算缩放比例并反向补偿源图 pt 字号。`TaskThread` 对隔离快照执行耗时任务。项目格式 v2 内嵌数值数据并保存分析、拟合及样式快照，读取仍兼容 v1。
