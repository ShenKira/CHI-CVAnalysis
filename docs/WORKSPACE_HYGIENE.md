# 工作区整理与临时文件管理

更新：2026-11-17。本文约定 CVAnalysis 工作区的目录边界、缓存保留周期和清理方式，避免一次性脚本、测试产物和旧构建再次堆满根目录。

## 1. 原则

- 不移动或删除用户数据、源码、测试、正式文档和本地交接资料。
- 清理只针对可再生缓存、历史构建和明确允许的实验中间产物。
- 所有删除操作默认 dry-run；确认清单后才使用 `--apply`。
- 禁止使用 `git clean`、`git reset --hard` 或通配删除来“顺手清理”。
- `.gitignore` 只是安全网，不是存储策略；被忽略的文件仍会占用磁盘。

## 2. 受保护内容

以下内容不得删除、覆盖或随意移动：

- 源码：`cvanalysis/`、`tests_v2/`、`start_gui.py`、`cv_analysis.py`、`eis_analysis.py`
- 正式文档：`README.md`、`Build.md`、`docs/`、`DESIGN.md`
- 本地交接资料：`AGENTS.md`、`.agent/`
- 用户数据：用户测量数据、项目文件及分析导出
- 用户配置：`config.json`、`themes.json`
- 构建记录和发布说明：`Build.md`、`build_cache/logs/`
- `.opencode_cache/` 中的源码快照、补丁、许可证、handoff ZIP 和文档引用的截图

## 3. 目录约定

```text
CVAnalysis/
├─ cvanalysis/              # 生产代码
├─ tests_v2/                # 测试
├─ docs/                    # 正式开发文档
├─ AGENTS.md                # 本地 Agent 入口，Git 忽略
├─ .agent/                  # 本地交接资料，Git 忽略
├─ .local/                  # 一次性脚本、截图、临时 JSON，Git 忽略
├─ .test_tmp/               # pytest basetemp，测试结束后清理
├─ build_cache/             # Nuitka 缓存与构建日志
├─ releases/                # 可选：最新发布包，Git 忽略
├─ tools/                   # 清理和测试脚本
├─ testdata/                # 用户数据
└─ *.cvproj / config.json / themes.json / 用户图片
```

一次性工作使用 `.local/<日期>-<任务名>/`。任务结束后清理可再生文件。清理前先核对文档引用，本地分析复算和构建日志等保留项由 `.local/README.md` 索引。

## 4. 保留周期

| 目录 | 内容 | 保留策略 |
|---|---|---|
| `.local/` | 一次性脚本、截图、调试 JSON | 任务结束即删；最长 7 天 |
| `.agent/` | 本地 Agent 交接资料 | 长期保留，不自动清理；跨机器交接显式授权 |
| `.test_tmp/` | pytest basetemp | 测试成功自动删除；失败保留供排查 |
| `__pycache__/`、`.pytest_cache/` | Python/pytest 缓存 | 随时可删 |
| `build_cache/` | Nuitka 缓存和日志 | 缓存可删；`logs/` 保留最近约 90 天或 20 个日志 |
| `CVAnalysis_*_v*/` | 构建产物 | 只保留最新版本 ZIP + OneFile；旧版本清理或移出仓库 |
| `.opencode_cache/` | 本地实验和交接资料 | 核心资料长期保留；中间截图/输出按需归档，建议总配额 100 MB |
| `temp/` | 旧临时资料 | 不再新增；逐步迁移或归档 |

## 5. 日常命令

### 5.1 运行测试

```powershell
.\tools\run_tests.ps1
```

脚本会：

- 在 `.test_tmp/run_<guid>/` 和 `.test_tmp/cache_<guid>/` 分别创建本次独立 basetemp 与 pytest cache；
- 设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`；
- 脚本通过 pytest 参数覆盖 `cache_dir`，避免并行测试互相删除缓存；直接运行 pytest 时仍使用 `pyproject.toml` 的 `.test_tmp/pytest_cache`；
- 测试成功时仅删除本次 basetemp 和 cache；失败或 `-KeepTemp` 时保留并打印路径。清理不跟随链接。

`-Suite Gui` 和 `-Suite Plotting` 提供快速定向组，不能替代默认的完整 `-Suite All`；`-Durations 10` 报告最慢测试。脚本拒绝在 `-PytestArgs` 中覆盖 basetemp 或 cache 路径。

附加 pytest 参数：

```powershell
.\tools\run_tests.ps1 -PytestArgs @('-k','liquid_glass','--tb=long')
```

### 5.2 清理缓存

先 dry-run：

```powershell
python tools\cleanup_workspace.py --profile safe
```

确认后执行：

```powershell
python tools\cleanup_workspace.py --profile safe --apply
```

清理旧构建：

```powershell
python tools\cleanup_workspace.py --profile builds
python tools\cleanup_workspace.py --profile builds --apply
```

`builds` 默认保留最新版本；最新版本的 OneFile 目录保留，未压缩 StandAlone 仅在有同名 ZIP 时删除。可用 `--keep-latest N` 调整保留版本数，或用 `--keep-unpacked-standalone` 保留解压版。

深度清理 `.opencode_cache` 中间产物：

```powershell
python tools\cleanup_workspace.py --profile deep
```

`deep` 会列出已知的可再生实验输出；执行前必须人工核对清单，不要直接套用到新目录。

## 6. 构建产物策略

1. 每次发布后只保留最新版本的 `CVAnalysis_StandAlone_v<ver>.zip` 和 `CVAnalysis_OneFile_v<ver>/`。
2. 旧版本在确认哈希已记录、且不再需要运行后删除；旧版 `CVAnalysis_StandAlone_v<ver>.zip` 也按同一 `--keep-latest` 规则清理，不要长期保留多个几百 MB 的解压目录和 ZIP。
3. `build_cache/clcache/` 可在发布完成后清理；下次构建会重新生成，首次构建会变慢。
4. `build_cache/logs/` 作为构建记录保留；不要和缓存一起无条件删除。
5. 删除构建产物前核对 `Build.md` 中的 SHA256 和实际文件。

## 7. `.opencode_cache/` 规则

- 只保留“每个实验一份最终产物 + README”。
- 中间截图、`design_check*`、`design_full*`、`capture-debug`、`empty-*` 等不长期保留。
- 文档引用的文件必须保留：`glass_demo/screenshots/production/`、`mainline_plan_review/`、`glass_demo/glass_menu.py`、handoff ZIP、源码快照、补丁和许可证。
- 新实验不要再默认写入 `.opencode_cache/`；临时验证放 `.local/`，稳定成果再归档。
- 建议每月检查一次总大小，超过 100 MB 时按上述规则清理。

