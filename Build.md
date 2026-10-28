# CVAnalysis v2 Build 交接说明

> 状态（2026-10-28）：v2.0.0 的 **StandAlone** 与 **OneFile** 均已构建成功并通过启动验证。
> 本文记录已验证环境、关键根因、构建命令和验证方法，供下一位接手构建/发布的 Agent 或开发者使用。

## 1. 已验证产物

| 产物 | 路径 | 大小 | SHA256 |
| --- | --- | ---: | --- |
| StandAlone | `CVAnalysis_StandAlone_v2.0.0\start_gui.dist\CVAnalysis_v2.0.0.exe` | 126,188,032 | `993591DA1154980C15FCBD039F68D89D33CBC613F451503CD049EF2EF0D6D9C4` |
| OneFile | `CVAnalysis_OneFile_v2.0.0\CVAnalysis_v2.0.0.exe` | 335,910,912 | `E61C02B0F2E469A302791FF3A74B65EABD695994DC2E5437BC592C799E56AAE2` |

- 重新构建后大小和 SHA256 会变化，发布前重新记录。
- StandAlone 是推荐分发形式；OneFile 是单文件，启动时解压到 `%TEMP%\CVAnalysis\onefile_*`。
- 两个 exe 均未签名，仍可能触发 Windows SmartScreen 或杀毒软件误报；正式分发建议代码签名。

## 2. 已验证构建环境

- Python：3.11.14（Anaconda），`%USERPROFILE%\.conda\envs\nuitka_pack\python.exe`
- Nuitka：4.3.1
- 编译器：MSVC 14.5（VS 18 BuildTools，Nuitka `--msvc=latest` 自动探测）
- PySide6：6.9.2（**必须 `<6.10`**；6.10.2 会在图例对话框触发原生崩溃）
- NumPy：2.4.2
- SciPy：1.17.1
- pandas：3.1.0
- matplotlib：3.10.8
- pytest / pytest-qt：9.2.0 / 4.5.0（仅开发测试）
- 构建选项：`--enable-plugin=pyside6`、`--lto=no`、`--onefile-no-compression`

源码测试基线（`nuitka_pack` 环境）：

```text
202 passed, 2 warnings
```

两条警告仍是既有的 Matplotlib tight-layout 警告。

## 3. 关键根因与修复（必读）

### 3.1 Anaconda `Library\bin` 未加入 PATH，导致 standalone 缺少 `ffi.dll` / `libexpat.dll`

**现象：**

- StandAlone 或 OneFile 启动立即退出，退出码 `0xC0000409`（`FAST_FAIL_FATAL_APP_EXIT`）。
- `%LOCALAPPDATA%\CVAnalysis\logs\startup_error.log` 中崩溃在 `numpy._core._internal` → `ctypes` → `_ctypes`。
- 设置 `PYTHONVERBOSE=1` 后可看到：

```text
import _ctypes ...
# destroy ctypes
Fatal Python error: Aborted
```

**原因：**

- `_ctypes.pyd` 依赖 `ffi.dll`；`pyexpat.pyd` 依赖 `libexpat.dll`。
- Anaconda 把这些 DLL 放在 `%CONDA_PREFIX%\Library\bin`。
- 之前 `build.bat` 直接调用 `python.exe -m nuitka`，没有像 `conda activate` 那样把 `Library\bin` 加入 PATH。
- Nuitka 的 DLL 依赖扫描因此漏掉这些 DLL；旧的 DLL 依赖缓存还可能继续保留“未找到”的结果。

**修复：**

- `build.bat` 在调用 Nuitka 前，把 conda 环境的以下目录前置到 PATH：
  - `%PYTHON_ENV%`
  - `%PYTHON_ENV%\Library\mingw-w64\bin`
  - `%PYTHON_ENV%\Library\usr\bin`
  - `%PYTHON_ENV%\Library\bin`
  - `%PYTHON_ENV%\Scripts`
  - `%PYTHON_ENV%\bin`
- 首次在 PATH/Nuitka/Python 变化后构建时，设置 `CVANALYSIS_FORCE_DLL_CACHE=1`，强制刷新 DLL 依赖缓存。
- `build.bat` 在 StandAlone 构建后检查 `start_gui.dist\ffi.dll`，缺失则失败。
- 已验证 StandAlone 中包含：`ffi.dll`、`libexpat.dll`、`libssl-3-x64.dll`、`libcrypto-3-x64.dll`、`liblzma.dll`、`libbz2.dll`、`sqlite3.dll`。

如果未来仍然缺少 `ffi.dll`，可显式加入：

```bat
--include-data-files="%PYTHON_ENV%\Library\bin\ffi.dll=."
```

但应先确认 PATH 修复和依赖缓存刷新没有生效，避免与依赖扫描重复。

### 3.2 NumPy 2.4 移除了 `np.trapz`

`getattr(np, "trapezoid", np.trapz)` 会先求值 `np.trapz`，而 NumPy 2.4 已删除该别名，导致模块导入直接失败。

已修复：

- `cvanalysis/analysis/cp.py`
- `cvanalysis/analysis/cv.py`
- `cvanalysis/compat/legacy_cv.py`

统一使用：

```python
try:
    _trapz = np.trapezoid
except AttributeError:
    _trapz = np.trapz
```

### 3.3 PySide6 6.10.2 原生崩溃

PySide6 6.10.2 在 `LegendTemplateDialog` 构造时连接 `textChanged` 信号会触发 access violation；同一测试在 6.9.2 下通过。

已处理：

- `nuitka_pack` 环境使用 PySide6 6.9.2。
- `requirements.txt` 和 `pyproject.toml` 固定为 `PySide6>=6.6,<6.10`。

相关 Nuitka 上游问题：

- `#4004`：PySide6 信号连接问题，4.3/4.3.1 已修复。
- `#4102`：Nuitka 4.3.1 + PySide6 退出阶段断言，Factory 4.4 已修复。
- 如果打包后出现退出崩溃，可考虑 Nuitka Factory 或调整 PySide6 版本；当前 6.9.2 构建已验证可用。

### 3.4 Defender / clcache

- Defender 可能锁定 `build_cache\clcache` 或 exe，Nuitka 会自动重试；日志中可能出现 `Disable Anti-Virus` 警告。
- 历史上 OneFile 解压出的 `main.dll` 曾被误判并删除：`Trojan:Win32/Wacatac.H!ml`。
- 建议在构建机以管理员 PowerShell 添加排除项：

```powershell
$root = (Resolve-Path .).Path
Add-MpPreference -ExclusionPath "$root\build_cache"
Add-MpPreference -ExclusionPath "$root\CVAnalysis_OneFile_v2.0.0"
Add-MpPreference -ExclusionPath "$root\CVAnalysis_StandAlone_v2.0.0"
Add-MpPreference -ExclusionPath "$env:TEMP\CVAnalysis"
Add-MpPreference -ExclusionProcess "CVAnalysis_v2.0.0.exe"
Add-MpPreference -ExclusionProcess "cl.exe"
```

- 未签名 exe 仍可能触发 SmartScreen；正式分发建议代码签名，必要时向 Microsoft 提交 OneFile 误报。

## 4. build.bat 当前行为

- 用法：

```bat
build.bat                  :: 默认 2.0.0，构建 StandAlone + OneFile
build.bat 2.0.0 all
build.bat 2.0.0 standalone
build.bat 2.0.0 onefile
```

- 优先使用 `nuitka_pack` 环境，可用 `CVANALYSIS_PYTHON` 覆盖 Python 路径。
- 先构建 StandAlone，再构建 OneFile。
- 自动把 conda 环境路径加入 PATH。
- 设置 `CVANALYSIS_FORCE_DLL_CACHE=1` 时追加 `--force-dll-dependency-cache-update`。
- OneFile 使用 `--onefile-no-compression` 和固定解压目录：

```text
{TEMP}/CVAnalysis/onefile_{PID}_{TIME_US}_{RANDOM}
```

- 构建后检查 exe 是否存在；StandAlone 额外检查 `ffi.dll`。
- 写入公司、产品、文件版本和版权信息；失败返回非零退出码；不自动 `pause`。

## 5. 常用命令

```powershell
# 常规构建（缓存已热）
cmd /c build.bat 2.0.0 standalone
cmd /c build.bat 2.0.0 onefile
cmd /c build.bat 2.0.0 all

# 首次在 PATH / Nuitka / Python 变化后构建
$env:CVANALYSIS_FORCE_DLL_CACHE = '1'
cmd /c build.bat 2.0.0 all
Remove-Item Env:CVANALYSIS_FORCE_DLL_CACHE
```

建议把构建输出重定向到 `build_cache\logs\`，便于排查 Defender / DLL 问题：

```powershell
cmd /c build.bat 2.0.0 all *> "build_cache\logs\build_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
```

## 6. 验证清单

1. exe 存在，版本资源为 `2.0.0.0`，记录大小和 SHA256。
2. StandAlone 关键文件存在：
   - `ffi.dll`
   - `libexpat.dll`
   - `_ctypes.pyd`
   - `PySide6\qt-plugins\platforms\qwindows.dll`
   - `matplotlib\mpl-data\matplotlibrc`
3. 离屏启动 StandAlone：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
Start-Process -FilePath "CVAnalysis_StandAlone_v2.0.0\start_gui.dist\CVAnalysis_v2.0.0.exe" -PassThru
# 等待 30 秒，确认进程未退出
```

4. 对比 `%LOCALAPPDATA%\CVAnalysis\logs\startup_error.log` 运行前后的长度；最终产物不应新增崩溃记录。
5. OneFile 启动后检查：
   - `%TEMP%\CVAnalysis\onefile_*` 已解压。
   - 进程保持运行。
   - Defender 没有新增误杀记录。
6. 手工验证：打开用户项目副本、绘图、EIS 拟合、CP 分析、CSV/图片导出。
7. 源码回归：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests_v2 -q
```

## 7. 已知问题 / 注意事项

- 完整 pytest 在当前环境可能在打印 `202 passed` 后以 `-1073741819` 退出（测试进程 teardown 问题）；单独的应用启动/退出测试退出码为 0，不阻塞打包。
- Nuitka anti-bloat 会提示未包含 `PIL.ImageTk`、pandas numba、pandas plotting；应用直接使用 matplotlib，当前构建已验证绘图可用。
- 应用首次运行会在 exe 同目录创建 `config.json`；这是用户配置，不要提交。
- 旧 `startup_error.log` 中可能保留修复前中间构建的 `ImportError` 记录；以最终产物的新增日志为准。
- OneFile 约 336 MB，StandAlone exe 约 126 MB；体积和未签名 exe 的误报风险需要在发布时确认。
- 如果在没有 Anaconda 的干净机器上分发，使用 StandAlone 文件夹形式；OneFile 解压目录已包含所需 DLL。

## 8. Git / GitHub 同步注意

- `.gitignore` 已排除：
  - `build_cache/`、`CVAnalysis_OneFile_v*/`、`CVAnalysis_StandAlone_v*/`、`*.build/`、`*.dist/`、`*.onefile-build/`
  - `config.json`、`testdata/`、`*.cvproj`、根目录测量数据/图片
  - `.pytest_cache/`、`.test_tmp/`、`__pycache__/`、`.vscode/`、`temp/`、日志、缓存、虚拟环境
  - 本地交接文件 `README_LOCAL.md`、`Vibe_Coding_Outline.md`、`docs/IMPLEMENTATION_LOG.md`
- `README_LOCAL.md` 保存本机环境、构建记录和交接说明，已忽略，不随 GitHub 同步。
- `tests_v2/fixtures/test_EIS.txt` 已改为合成 EIS 数据，避免包含本机测量路径；不要换回真实数据文件头。
- 不要提交构建输出、`config.json`、`testdata/`、用户 `.cvproj` 或导出图片。
- 不要执行 `git clean` / `git reset --hard`；用户数据就在工作区。
- `config.json` 已在 Git 索引中标记删除并加入 `.gitignore`；提交时确认它不再被跟踪。
- 远端为 `origin https://github.com/ShenKira/CHI-CVAnalysis.git`。v1 已冻结；推荐保留 v1 tags，并用 `v1-archive` 分支 + `v2` 分支同步。
- 推荐同步方式（**不 force-push**）：提交 v2 → 从 `origin/main` 建 `v1-archive` → 用 `git merge --allow-unrelated-histories --no-ff -s ours origin/main` 保留 v2 文件树并把 v1.3.0 作为第二父提交 → 推送 `main`、`v2` 和 `v2.0.0` tag。
- 本仓库本地 v1.1 与远端 v1.3.0 是**两段 unrelated history**；不加 `--allow-unrelated-histories` 会报 `refusing to merge unrelated histories`。
- 示例流程（确认 diff 后执行）：

```powershell
git add -A
git status --short
git commit -m "CVAnalysis v2.0.0: rewrite workspace and verified Nuitka builds"

git fetch origin
git branch v1-archive origin/main
git push origin v1-archive

git merge --allow-unrelated-histories --no-ff -s ours origin/main -m "Merge v1.3.0 archive into v2.0.0; keep v2 tree"
git branch v2

git push origin main v2
git tag -a v2.0.0 -m "CVAnalysis v2.0.0"
git push origin v2.0.0
```

- 如果 `main` 有 branch protection，先推送 `v2` 分支，再从 `v2` 向 `main` 开 PR；不要 force-push。
- 组员更新：无本地修改时 `git pull --ff-only`；有本地修改先备份/提交，或重新 clone。
- `update_detailed.md` 是本地 release notes 草稿，已忽略；复制到 GitHub Release。
- 如果私有数据曾经进入历史提交，仅从当前树删除不会清除历史；这种情况需要单独的历史清理（如 `git filter-repo`），执行前先确认。

## 9. 下一步

1. 在构建机加入 Defender 排除项，减少 clcache 锁定和 OneFile 误杀。
2. 完成 StandAlone / OneFile 的人工功能验收（导入、绘图、EIS、CP、导出）。
3. 正式分发前考虑代码签名。
4. 每次重新构建后更新产物大小、SHA256 和验证记录。
