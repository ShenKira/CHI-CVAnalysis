# CVAnalysis v2 性能优化规划（P0/P1 交接文档）

> 面向后续接手的 LLM Agent / 开发者。本文是**规划文档**，不代表 P0/P1 已实现。
>
> 当前基线：2026-10-25。`tests_v2` 144 项通过，1 条既有多 CV tight-layout 警告。当前代码已包含 CV/EIS/CP 分析、CP/GCD、手动坐标范围、分类快捷菜单等功能。
>
> 开始修改前请先读：
> - 本地交接说明 `Vibe_Coding_Outline.md`（不纳入仓库）
> - 内部实现日志 `docs/IMPLEMENTATION_LOG.md`（不纳入仓库）
> - 本文
>
> 工作区保护：不要执行 `git clean`、`git reset --hard`，也不要用 Git 恢复已删除的旧版 GUI 文件。用户 `.cvproj`、`config.json`、测试数据和 PNG 属于工作区数据，除非用户明确要求，不要删除或覆盖。

---

## 1. 目标与非目标

### 目标

1. 优先解决会让 UI 冻结、内存峰值过高或大项目明显卡顿的 P0 问题。
2. 在不改变任何数值结果、项目格式、图例/布局输出的前提下优化 P1 重复计算。
3. 把优化能力拆成可复用模块，方便未来增加新的分析类型、run 类型、绘图类型和多轴/子图。
4. 为缓存、保存、重绘建立明确的正确性约束和回归测试，避免“缓存命中但结果过期”。

### 非目标

- 本阶段不重写数值算法。
- 不改变 `.cvproj` v2 的语义结构，除非同时提供兼容读取。
- 不把缓存持久化到项目文件。
- 不为了性能改变可见输出（字体、图例列数、坐标范围、排序、warnings 均需保持）。
- 不删除或回退现有 CP/GCD、axis limits、分类菜单功能。

---

## 2. 当前验证基线

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests_v2 -q
python -m compileall -q cvanalysis tests_v2 start_gui.py
```

基线结果：

- `tests_v2`: **144 项通过**
- 1 条既有 Matplotlib tight-layout 警告：`test_multi_cv_testdata_overlay_geometry`
- `compileall`: 通过

GUI 视觉验证可参考本轮做法：

```python
# Windows 平台，避免 offscreen 字体显示为方块
# 设置 QT_QPA_PLATFORM=windows
window.setAttribute(Qt.WA_DontShowOnScreen, True)
window.resize(1560, 960)
window.show()
window.grab().save("screenshot.png")
```

---

## 3. 已识别的性能瓶颈

### P0：主线程冻结、内存峰值或重复全图渲染

| 编号 | 瓶颈 | 主要证据 | 影响 |
|---|---|---|---|
| P0-1 | 项目保存同步执行，并且重复复制大数组 | `ui/main_window.py:1640`；`services/project_service.py:71-73`、`:106` | 保存时 UI 冻结；`asdict(run)` 先深拷贝 cycles 再丢弃，JSON `.tolist()` 再复制一次 |
| P0-2 | EIS 拟合前 deepcopy 整个 dataset | `ui/main_window.py:1286` | 大项目点击“拟合当前 EIS”前先在主线程复制所有 CV/CP/EIS 数组 |
| P0-3 | 修改当前图选项却重绘全部图 | `ui/main_window.py:104-105`、`:1207-1218`、`:1251-1276` | N 个标签页时单次操作成本约乘 N |
| P0-4 | 论文图例自动列数反复整图 draw | `plotting/paper.py:78-81`、`:125-149`、`:258` | 论文模式下一次重绘可能触发 8–10 次完整栅格化 |

### P1：重复分析、重复汇总、重复刷新

| 编号 | 瓶颈 | 主要证据 | 影响 |
|---|---|---|---|
| P1-1 | Dunn / Trasatti / 扫速点每次重绘都重算 | `plotting/cv_renderer.py:760`、`:908`；`analysis/cv.py:713-796` | 改坐标范围、样式、图例也会重算 |
| P1-2 | CP 分段和补全序列每次重绘重建 | `plotting/cp_renderer.py:183-184`；`analysis/cp.py:483`、`:518-520`、`:714` | 首次渲染 summary 和 series 各 build 一次；后续每次重绘再 build |
| P1-3 | 修改面积/质量后全量重新分析 | `ui/main_window.py:900`；`analysis/cv.py:500-514`；`services/dataset_service.py:62-70` | 只影响归一化，却重新做积分和全量刷新 |
| P1-4 | 结果表每次选择变化都全量 reset | `ui/main_window.py:679-692`；`ui/widgets/results_panel.py:153-259`；`ui/models/metric_table_model.py:19-24` | 大 run 数时重复格式化、清空选择、`resizeRowsToContents()` |

### 后续可考虑（不属于本轮必做）

- CV 叠加图 cycle 数/点数过大时没有降采样；见 `plotting/cv_renderer.py` 的 `draw_cv_overlay()`。
- 每个 `PlotTab` 都长期保留完整 Figure，隐藏标签页仍占内存。
- `dataset_tree_model.TreeNode.row()` 线性扫描兄弟节点；`visible_run_ids()` 反复遍历全部 run。
- `tree.expandAll()` 在大量 Cycle 数据下可能较慢。
- 解析器逐行 Python 循环；导入线程已隔离，优先级低于 P0/P1。

---

## 4. 正确性原则（必须先接受这些约束）

### 4.1 原始数据只读

建议在解析和项目加载后，对原始数组设置只读：

```python
array.setflags(write=False)
```

包括：

- CV: `potential`, `current`
- EIS: `freq`, `z_real`, `z_imag`, `z_mag`, `phase`
- CP: `time`, `potential`, `hold_time`, `hold_current`

当前代码中未发现对原始数组的原地写入，但实施后要补测试。只读约束是对象身份缓存安全的前提。

### 4.2 缓存只缓存纯分析结果

缓存不得包含：

- UI 控件状态
- 颜色、样式、坐标范围、图例开关
- 当前 tab 的临时布局
- 可被调用方修改的数组/列表

缓存值如果需要被 renderer 使用，应视为只读；renderer 不得原地修改缓存对象。warnings 也必须随结果一起缓存，否则命中缓存后图上警告会消失。

### 4.3 缓存只在 `PlotTab` 内

不要使用模块级全局缓存，避免：

- 两个项目之间串数据
- 测试之间互相污染
- 数据集替换后旧结果仍被命中

`PlotTab` 负责持有 `AnalysisCache`；`render_plot(..., analysis_cache=...)` 可选传入，默认不传则完全走原计算路径，保持测试和导出兼容。

### 4.4 缓存 key 必须覆盖所有影响结果的输入

仅靠 `id(run)` 不够。使用组合 fingerprint：

- `run_id`
- run 对象身份
- 原始数组对象身份
- `id(run.cycles)`
- `id(run.summary)`
- `area_cm2`, `mass_mg`
- `metadata.scan_rate`
- CP 额外：high/low limit、hold 时长、hold 数据身份
- 选择：run_ids 顺序、cycle_selection
- 选项：normalization、target_voltage、selected_scan_rate、complete_holds
- 算法版本/缓存 schema 版本

未来新增会改变结果的字段时，必须同步更新 key；没有 key 的新分析默认不缓存。

### 4.5 缓存不持久化

- 缓存只存在于当前进程的 `PlotTab` 中。
- 不写入 `.cvproj`。
- 不写入 `config.json`。
- 重启后重新计算。

---

## 5. 建议的模块拆分

```text
cvanalysis/
  analysis/
    cache.py                 # RunFingerprint、AnalysisCache、通用 key 工具
    cv.py                    # 增加 cv_scan_points_key / dunn_key 等纯 key 工厂
    cp.py                    # build_segments/completed series 缓存 key、summary key
  services/
    project_codec.py         # CV/EIS/CP encode/decode 注册表
    project_snapshot.py      # 保存快照、dirty generation、序列化 worker
    snapshots.py             # EIS 等轻量分析快照
    analysis_refresh.py      # NORMALIZATION/SUMMARY/SEGMENTATION/FULL 四级刷新
  ui/
    redraw.py                # PlotChange、依赖规则、待重绘队列
  plotting/
    paper_layout.py          # 论文图例列数缓存（也可暂时留在 paper.py）
    render_context.py        # 可选：统一传 cache/options/warnings
```

### 5.1 `analysis/cache.py`

建议接口示意：

```python
@dataclass(frozen=True)
class RunFingerprint:
    run_id: str
    instance_token: int
    raw_token: int
    cycles_token: int
    summary_token: int
    area_cm2: float | None
    mass_mg: float | None
    scan_rate: float | None

class AnalysisCache:
    def get(self, key): ...
    def put(self, key, value): ...
    def clear(self): ...
    def invalidate_run(self, run_id):  # 可选，主要用于释放内存
        ...
```

要求：

- `instance_token` 使用单调递增计数器或 run 创建 token，不要只用 `id()`；`id()` 只能作为辅助，并且 `PlotTab` 替换 dataset 时必须清空缓存。
- 缓存有容量上限；CP completed series 数组较大，单独限制条目数（建议 2–4 条）。
- 不缓存“计算失败”的结果；异常直接抛给原有错误处理。

### 5.2 `services/project_codec.py`

建议接口：

```python
class RunCodec(Protocol):
    kind: str
    persisted_fields: frozenset[str]
    runtime_only_fields: frozenset[str]

    def encode_data(self, run) -> dict: ...
    def decode_data(self, data: dict, source: Path | None): ...
```

注册 `cv` / `eis` / `cp`。

必须提供字段覆盖测试：

```python
assert (
    set(f.name for f in dataclasses.fields(run_type))
    - codec.persisted_fields
    - codec.runtime_only_fields
) == set()
```

这样未来给 run 增加字段时，如果没有加入 codec 或显式标记为运行时字段，测试会失败，防止项目保存静默丢字段。

### 5.3 `services/analysis_refresh.py`

定义刷新层级：

```python
class RefreshLevel(Enum):
    NORMALIZATION = auto()
    SUMMARY = auto()
    SEGMENTATION = auto()
    FULL = auto()
```

- `NORMALIZATION`：只影响面积/质量相关展示；不重新积分。
- `SUMMARY`：重算统计汇总。
- `SEGMENTATION`：重新分割、重算 metrics。
- `FULL`：完整重新分析。

统一入口：

```python
refresh_runs(dataset, run_ids, level, settings)
```

UI 不要直接调用 `analyze_cv_run()` / `analyze_cp_run()` 并假设 summary 是最新的。

### 5.4 `ui/redraw.py`

建议维护：

```python
pending_tabs: list[PlotTab]
tab.dirty: bool
```

- 修改 spec 后标记 dirty，并加入待重绘集合。
- 定时器统一 flush。
- 关闭 tab、替换 dataset、清空数据时清理待重绘集合。
- `_on_tab_changed()` 发现当前 tab dirty 时补绘。
- 这样即使未来新增“延迟重绘”操作，也不会出现切换标签页后画面过期。

---

## 6. P0 工作包

### P0-1 项目保存

#### 为什么不能只把 `save_project()` 放进 QThread

- Python `tolist()` / `json.dumps()` 仍会占用 GIL，后台线程不是无条件加速。
- 异步保存会带来 close/open 项目状态机、保存中编辑、保存失败恢复等问题。
- 因此建议分两步：先消除深拷贝和重复序列化，基准后再决定是否异步。

#### 步骤 A：同步路径安全优化（必须做）

1. 新增 `project_codec.py`；`project_service.py` 不再使用 `asdict(run)` 保存主流程。
2. 只提取持久化字段；明确排除 `summary`、`cycles`。
3. 原始数组只 `.tolist()` 一次；删除 JSON `default` 中的重复数组转换。
4. 保留 `_project_data_extra` / `_project_entry_extra` / `_project_extra` 未知字段。
5. 保持 `.cvproj` v2 读取兼容；不改变对旧项目的行为。

#### 步骤 B：后台保存（基准后可选）

1. 主线程创建轻量 `ProjectSnapshot`：
   - run 数据引用（原始数组只读）
   - params 值副本
   - visible/cycle selection 副本
   - PlotSpec 深拷贝
   - fits/styles 副本
   - dataset 名称和未知扩展字段
   - `dirty_generation`
2. `TaskThread` 中执行 codec encode + JSON 序列化 + 临时文件原子替换。
3. 保存期间禁止再次保存；关闭窗口需等待保存任务完成，不能 interrupt。
4. 保存成功时：
   - 若 `dirty_generation` 未变，才 `_mark_clean()`；
   - 若期间发生编辑，保留 `*`，只更新项目路径/写入磁盘。
5. 保存失败：保留旧文件、保留 dirty 状态、显示错误。

#### 正确性测试

- CV/EIS/CP + fits + styles + axis_limits 完整 round-trip。
- 未知字段保留。
- 旧 v1/v2 项目仍能加载。
- 保存失败不覆盖旧文件、临时文件清理。
- 保存中编辑不会被错误标记为已保存。

---

### P0-2 EIS 拟合快照

#### 实施

1. 新增 `snapshot_eis_runs(dataset, run_ids)`：
   - 只复制选中 EIS run 的数据和参数；
   - 保留相同的 `run_id`；
   - CV/CP 数据不进入快照。
2. 如果原始数组已只读，可共享数组引用，只复制 run 对象和 params。
3. `fit_selected_eis()` 使用该快照启动 `TaskThread`。
4. `fit_eis_runs()`、`filter_eis_run()` 算法不改。

#### 正确性测试

- 新旧实现拟合参数、R²、RMSE、残差、warnings 完全一致。
- 多个 EIS run 的 `run_id` 和结果顺序一致。
- 修改/删除非 EIS 数据不影响拟合。

---

### P0-3 重绘范围

#### 安全策略

- **当前图选项、坐标范围**：只重绘当前 tab，使用待重绘集合捕获目标 tab。
- **勾选/Cycle 可见性**：只重绘 `follow_dataset=True` 的图（现有 `_sync_following_tabs()`）。
- **修改面积/质量**：只重绘引用了对应 run 的图。
- **修改图例模板**：只重绘引用了对应 run 的图。
- **EIS 拟合完成**：重绘包含拟合 run 的 EIS 图与拟合图。
- **导入、拖动排序、删除、设置重新分割**：暂保留全量重绘，避免 `{file_n}` 顺序遗漏。

#### 关键实现细节

1. `_on_options_changed()` 在修改 spec 时记录目标 tab，而不是只记录“当前 tab”。
2. 定时器回调 flush `pending_tabs`；如果 tab 已关闭则跳过。
3. 给 `PlotTab` 增加 `dirty` 标志；切换标签时如果 dirty 就补绘。
4. 未来新增会改变文件的导入逻辑时，要额外检查 `{file_n}`：
   - 新增 CV 可能插在 EIS/CP 之前，改变已有文件序号。
   - 若无文件序号变化，才允许只重绘跟随图。

#### 正确性测试

- 修改当前图选项时只重绘当前图；快速切换标签也不会漏绘。
- 勾选只重绘 follow 图。
- 修改参数只重绘引用 run 的图。
- 导入/排序/删除按上述安全策略重绘。
- 非当前 dirty 图切换回来时自动补绘。

---

### P0-4 论文图例列数缓存

#### 实施

1. 在 Figure 上挂小型 per-figure cache（或 `paper_layout.py` 内以 figure 为键）。
2. 只缓存自动列数 `ncols`；不缓存最终 bbox。
3. key 包含：
   - `tuple(labels)`
   - requested columns
   - loc / anchor / usable width fraction
   - figure DPI、figure 像素尺寸、目标 axes bbox 宽度
   - `style.legend_size`、`style.font_family`
   - 图内/图外、单轴/多轴、EIS fit 标记
4. 最终 legend bbox 仍用真实 legend 测量一次，保持布局结果一致。
5. 可复用同一 `RendererAgg`（按 figure 尺寸/DPI 缓存），减少 renderer 分配。
6. 不采用近似字体宽度，除非 golden test 证明像素级一致。

#### 正确性测试

- 所有内置预设、单轴/双轴、自动/手动列数、图内/图外：
  - 优化前后 `ncols` 完全一致；
  - 最终 legend bbox 完全一致或在极小 epsilon 内。
- 图尺寸、字体、标签、样式变化后缓存 miss。
- 重复重绘时 `figure.draw()` 调用次数减少。

---

## 7. P1 工作包

### P1-1 分析结果缓存

#### 缓存项与 key

| 缓存项 | key 至少包含 |
|---|---|
| CV scan points | run fingerprints、run 顺序、cycle_selection、resolved target、current_mode |
| Dunn current decomposition | scan points key + normalization + selected_scan_rate |
| Dunn fraction vs rate | scan points key + normalization |
| Trasatti | scan points key + normalization |
| CP segments | CP raw/hold tokens、metadata limits、hold durations |
| CP completed series | CP segments key + `complete_holds` |
| CP summary | CP segments key + area/mass + algorithm version |

#### 实现要求

1. `render_plot()` 增加可选 `analysis_cache`；`PlotTab` 持有缓存。
2. `render_to_new_figure()` 导出默认不复用 tab 缓存，保证导出独立。
3. `CV` 侧缓存 `collect_scan_rate_points()` 和 Dunn 结果；Trasatti 可以直接复用 points。
4. `CP` 侧把 `build_segments(warn=False)` 做成纯函数；warnings 由 `analyze_cp_run()` 统一登记。
5. `analyze_cp_run()` 使用私有 `_summary_key`；参数/segments 变化时自动重算，不能只依赖 `force=True`。
6. 缓存结果只读；warnings 一起缓存；renderer 不得修改缓存对象。
7. 设置环境变量 `CVANALYSIS_DISABLE_ANALYSIS_CACHE=1` 可完全关闭，用于排查。

#### 正确性测试

- 缓存结果 vs 强制 fresh 计算，数值、warnings、图元数据一致。
- 修改 normalization、cycle_selection、target、selected_scan_rate、complete_holds、面积/质量后必须 miss。
- 修改颜色/坐标范围/图例开关时允许 hit，输出只变化样式。
- 数据集替换、删除 run、项目加载后不会串缓存。
- 两个内容相同但对象不同的数据集不会共享错误结果。

---

### P1-2 参数修改快路径

#### 实施

1. `set_electrode_params(dataset, params, run_ids)` 作为唯一入口。
2. CV：只 `summarize_run()`，复用已有 `run.cycles` 和积分结果。
3. CP：复用已有 segments/holds，只重建 cycles/summary。
4. EIS：跳过重算（EIS metrics 不依赖 params）。
5. 任何缺失 summary/cycles 的 run 自动升级为完整分析。
6. 缓存 key 包含 params，自动 miss；不要在缓存命中时跳过参数变化。

#### 正确性测试

- 修改面积/质量后，与完整重新分析逐字段比较，CV/CP 归一化值完全一致。
- EIS metrics 前后不变。
- 部分 run 修改时其他 run 的结果不被误改。
- 项目加载后的 params 与 summary 一致。

---

### P1-3 结果表增量刷新

#### 实施

1. `MetricTableModel.set_data()` 内容相同直接返回。
2. 行数不变时只更新 rows/colors 并发 `dataChanged`；行数变化才 `beginResetModel/endResetModel`。
3. `ResultsPanel` 用格式化后字符串 rows 和 colors 做比较；避免 NaN 比较问题。
4. 行数或内容变化时才 `resizeRowsToContents()`。
5. 选择变化只刷新对应表，不刷新三张表全部数据。

#### 正确性测试

- 选择/勾选/取消勾选后表格内容、颜色、排序、滚动位置正确。
- summary 更新后对应单元格更新。
- `dataChanged` 路径与 reset 路径最终显示值一致。

---

## 8. 重绘/失效事件矩阵

| 操作 | 重绘范围 | 备注 |
|---|---|---|
| 当前图分析参数/坐标范围/样式 | 当前 tab | 用待重绘集合，不能只依赖当前索引 |
| 勾选 run / Cycle | `follow_dataset=True` 的图 | 现有 `_sync_following_tabs()` |
| 导入新文件 | 暂全量或 follow + `{file_n}` 差异分析 | 新增 CV 可能改变 EIS/CP 文件序号 |
| 拖动文件排序 | 全部 | `{file_n}` 与绘图顺序均可能变化 |
| 删除/清空数据 | 全部 | 文件序号可能变化 |
| 修改面积/质量 | 引用目标 run 的图 | summary/legend 影响；EIS metrics 不重算 |
| 修改数据图例模板 | 引用目标 run 的图 | `{file_n}` 本身未变，但标签变化 |
| EIS 拟合完成 | 包含目标 EIS run 的图 + 拟合图 | 不重绘无关图 |
| 设置/分析参数 force 重算 | 全部 | 分割/统计可能全局变化 |
| 切换标签页 | 当前 tab；若 dirty 则补绘 | 防止延迟重绘遗漏 |

---

## 9. 缓存一致性检查清单

- [ ] 原始数组已只读
- [ ] 缓存只在 `PlotTab`，不跨数据集
- [ ] key 包含所有影响结果的输入
- [ ] warnings 随结果缓存
- [ ] 缓存结果不被 renderer 修改
- [ ] key 包含算法/缓存 schema 版本
- [ ] 缓存有容量上限
- [ ] 没有把颜色/坐标范围/图例开关放进分析 key
- [ ] CP `complete_holds`、params、hold 数据变化能正确 miss
- [ ] CV cycle_selection、summary、cycles、params 变化能正确 miss
- [ ] `run.summary` 自身有 key，不能无条件复用
- [ ] 缓存命中路径与无缓存路径有差分测试

---

## 10. 测试计划

### 新增/扩展测试

1. `tests_v2/test_analysis_cache.py`
   - key miss/hit
   - 参数/选择/设置变化
   - fresh vs cached 差分
   - cache 容量与清理

2. `tests_v2/test_project_codec.py`
   - 三种 run 的 encode/decode 字段完整性
   - 未知字段、v1/v2 兼容
   - 项目 round-trip
   - 保存失败/dirty generation（若实现异步）

3. `tests_v2/test_redraw_scope.py`
   - 当前图 option 只重绘当前图
   - pending target 在切换标签后不丢
   - follow 图/run 引用图/fit 图的依赖关系
   - 非当前 dirty 图切换时补绘

4. `tests_v2/test_paper_layout_cache.py`
   - 全预设/双轴/图内图外列数一致
   - bbox 对比
   - 缓存 miss 条件

5. `tests_v2/test_analysis_refresh.py`
   - NORMALIZATION 与 FULL 结果一致
   - 缺少 summary 时自动升级
   - EIS 不被不必要重算

6. `tests_v2/test_results_incremental.py`
   - reset vs dataChanged 等价
   - NaN/颜色/行高

### 必须保持通过的既有测试

- `test_cv_analysis.py`
- `test_eis_analysis.py`
- `test_plotting.py`
- `test_paper_legend.py`
- `test_project.py`
- `test_project_save.py`
- `test_gui_smoke.py`
- `test_cp_analysis.py`
- `test_axis_limits.py`
- `test_review_revision.py`
- `test_settings.py`
- `test_testdata_regression.py`

### 全量命令

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests_v2 -q
python -m compileall -q cvanalysis tests_v2 start_gui.py
```

---

## 11. 性能基准建议

不要只依赖“感觉更快”。建议建立独立基准脚本（可放 `tests_v2` 之外或临时目录，不提交不稳定时间断言）：

1. 合成数据：
   - 20 个 CV run，每个 20–100 cycle
   - 5 个 EIS run，每个 100 点
   - 5 个 CP run，每个 20k 点、5 个 hold
   - 10 个 PlotTab，其中包含 Dunn/Bode/CP capacity 和论文布局
2. 记录：
   - `save_project_file()` 耗时、内存峰值
   - `fit_selected_eis()` 主线程阻塞时间
   - `PlotTab.redraw()` 次数和时间
   - `paper.finish_paper()` 的 `figure.draw()` 次数
   - Dunn/CP cache 命中率
   - 结果表刷新耗时
3. 对比优化前后：
   - 必须同时比较输出结果（图元、warnings、project JSON 结构、CSV 值），不能只看耗时。

---

## 12. 实施顺序（建议）

1. 加入原始数组只读约束 + 缓存/刷新模块骨架；跑全量测试。
2. P0-1 同步保存 codec 优化；补 project codec 测试。
3. P0-2 EIS 轻量快照。
4. P0-3 当前图/引用图重绘 + dirty 兜底；补重绘范围测试。
5. P0-4 论文图例列数缓存；补 golden 测试。
6. P1-1 分析缓存；逐个分析接入，差分测试。
7. P1-2 参数归一化快路径。
8. P1-3 结果表增量刷新。
9. 基准、全量回归、视觉验证、更新实现日志。

每个阶段都可独立提交/回滚；不要把 P0 和 P1 全部塞进一次大改。

---

## 13. 需要确认的决策

1. **项目保存是否异步？**
   - 推荐先做同步 codec 优化 + 基准；
   - 若仍冻结，再做后台保存，并完整处理 close/open 状态机与 dirty generation。
   - 注意 GIL，后台 Python 序列化不一定完全消除卡顿。

2. **是否允许原始数组只读？**
   - 推荐允许；当前代码未发现原地写原始数组。
   - 这是缓存安全最重要的前提。

3. **典型项目规模？**
   - run 数、每 run cycle 数、点数、同时打开标签页数。
   - 如果规模不大，P1-1 缓存的收益可能低于维护成本。

4. **论文图例是否要求像素级完全一致？**
   - 推荐要求完全一致：缓存列数 + 最终真实 bbox 测量，不做近似字体测量。

---

## 14. 交接注意事项

- 先读本地交接说明 `Vibe_Coding_Outline.md`（不纳入仓库）的“关键不变量”和“容易踩的坑”。
- 不要为了性能改变：
  - `PlotSpec.run_ids == []` 的语义（无选择，不是全部）
  - `cycle_selection` 的缺失/空列表语义
  - `follow_dataset` 的同步规则
  - CP `complete_holds` 与 `include_holds` 的语义
  - `axis_limits` 的 key 映射和空值=自动规则
  - 论文图例的列数/字号/bbox
- 修改缓存/刷新后，必须更新本文和内部实现日志 `docs/IMPLEMENTATION_LOG.md`（不纳入仓库）。
- 如果发现本文与代码冲突，以当前代码和最新实现日志为准，然后修正本文。
