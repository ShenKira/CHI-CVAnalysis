# tools

本目录用于工作区维护，不包含应用运行时代码。

完整规范见 [docs/WORKSPACE_HYGIENE.md](../docs/WORKSPACE_HYGIENE.md)。

## run_tests.ps1

每次运行分别使用 `.test_tmp/run_<guid>/` 和 `.test_tmp/cache_<guid>/`：

```powershell
.\tools\run_tests.ps1
```

- 固定使用 Qt 离屏模式；
- 每次测试使用独立 pytest cache，避免并行运行互相清理或覆盖；
- 不写 Python 字节码；
- 选择 conda Python 时，优先使用该环境的 DLL 搜索路径，与 `build.bat` 一致；结束后恢复调用方 PATH；
- 成功后删除 basetemp 与 pytest cache，失败时保留并打印路径。
- 清理由 PowerShell 在当前进程内完成，先验证目标，再逐项处理链接本身，不递归跟随链接。
- 不允许通过 `-PytestArgs` 覆盖 `--basetemp` 或 `cache_dir`；需特殊目录时直接调用 pytest 并自行管理。

根据改动先运行定向组，交付前再运行完整套件：

```powershell
.\tools\run_tests.ps1 -Suite Gui
.\tools\run_tests.ps1 -Suite Plotting
.\tools\run_tests.ps1 -Suite All -Durations 10
```

`Gui` 和 `Plotting` 是便于快速反馈的固定子集，不替代完整 `All`；需要更精确范围时继续用 `-PytestArgs`。`-Durations N` 列出最慢的 N 个测试，帮助定位性能回归。

传入额外 pytest 参数：

```powershell
.\tools\run_tests.ps1 -PytestArgs @('-k','liquid_glass','--tb=long')
```

保留 basetemp：

```powershell
.\tools\run_tests.ps1 -KeepTemp
```

`-KeepTemp` 同时保留本次的 basetemp 和 cache。历史共享 `.test_tmp/pytest_cache` 不会被测试脚本删除；清理由工作区维护流程单独处理。

## cleanup_workspace.py

默认是 dry-run，只列出候选路径：

```powershell
python tools\cleanup_workspace.py --profile safe
python tools\cleanup_workspace.py --profile builds
python tools\cleanup_workspace.py --profile deep
```

确认后加 `--apply`：

```powershell
python tools\cleanup_workspace.py --profile safe --apply
python tools\cleanup_workspace.py --profile builds --apply
```

### profile

- `safe`：`.test_tmp`、`.pytest_cache`、`__pycache__`、`build_cache` 可再生缓存。
- `builds`：`safe` 加历史构建目录和旧版 StandAlone ZIP；默认保留最新版本，最新 OneFile 保留，未压缩 StandAlone 仅在有同名 ZIP 时删除。
- `deep`：`builds` 加 `.opencode_cache` 中已知的中间实验输出；执行前必须核对 dry-run 清单。

### 安全措施

- 默认 dry-run，不删除任何东西；
- 只处理白名单路径，不按文件名大面积通配；
- 保护 `.cvproj`、`testdata/`、`config.json`、`themes.json`、源码和正式文档；
- 删除 `.test_tmp` 时先移除符号链接/junction 本身，不跟随目标；
- 失败时报告剩余大小和具体路径，不静默忽略。

## 约定

- 一次性脚本、截图、调试 JSON 放仓库根目录的 `.local/`，不要直接放根目录。
- `.local/`、`.test_tmp/`、`build_cache/` 和版本化构建目录都被 `.gitignore` 排除。
- 不要用 `git clean` 代替清理脚本。
