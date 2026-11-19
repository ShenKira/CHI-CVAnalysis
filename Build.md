# Windows 构建与发布

当前发布版本：**2.2.0**（2026-11-19）。构建结果和验收记录见下文；历史版本的二进制与校验信息以 GitHub Release 为准。

当前工作区约定：仅在用户明确要求时启动 Nuitka 打包。源码测试和交接文档更新使用现有 Python 环境。本地验证构建的编号与公开发布标签分开记录。

## 构建环境

- Windows x64，Python 3.11.14（Anaconda `nuitka_pack`）。
- Nuitka 4.3.1，MSVC 14.5，PySide6 6.9.2。
- NumPy 2.4.2、SciPy 1.17.1、pandas 3.1.0、Matplotlib 3.10.8。
- 运行依赖以 `pyproject.toml` 为准；PySide6 限制 `<6.10`，避免已观察到的原生崩溃。

```powershell
# 可指定另一套已安装依赖和 Nuitka 的 Python
$env:CVANALYSIS_PYTHON = 'C:\path\to\env\python.exe'
cmd /c build.bat 2.2.0 all
# 也可分别使用 standalone / onefile
```

`build.bat` 默认版本为 2.2.0，先构建 StandAlone，再构建 OneFile。它自动把所选 Python 环境的 `Library/bin` 等目录加入 PATH，使用 MSVC、禁用 LTO，OneFile 不压缩。构建日志建议保存到被忽略的 `build_cache/logs/`。

## 产物与资源

- StandAlone：`CVAnalysis_StandAlone_v2.2.0/start_gui.dist/`，必须整体分发，不能只复制 EXE。
- OneFile：`CVAnalysis_OneFile_v2.2.0/CVAnalysis_v2.2.0.exe`，启动时解压至系统临时目录的独立子目录。
- 发布附件：StandAlone ZIP、OneFile EXE、`SHA256SUMS.txt`。GitHub 自动提供对应标签的源码 ZIP / tar.gz。
- 两种模式均嵌入 `cvanalysis/resources/icons/cvanalysis.ico`，并包含主题模板、图标源文件与 PyGlass MIT 许可/改编声明。
- EXE 未进行代码签名。分发与运行不要求修改系统防护设置。

## v2.2.0 正式发布验证

- 开发环境（Python 3.13.9）完整回归：568 passed，141.41 s，退出码 0。
- 打包环境（Python 3.11.14）完整回归：568 passed，139.99 s，退出码 0。
- StandAlone ZIP：1041 个文件逐字节核对（解压后 339,607,214 bytes），运行时 `config.json` / `themes.json` 未分发；README/LICENSE 已补齐。
- StandAlone：隔离配置下离屏启动 15 秒，进程存活，`config.json` / `themes.json` 已生成，启动错误日志为空。
- OneFile：隔离配置下冷启动 30 秒，加载器与子进程均存活，配置/主题已生成，启动错误日志为空。

| 产物 | 字节数 | SHA256 |
|---|---:|---|
| StandAlone EXE | 130029568 | `6b87208b62f4974b028ab53068e913a14253323d7d7c8857c52d7d9b21615c4b` |
| StandAlone ZIP | 125679799 | `37bf3b45e8fd55592c76d624795ff514df44c81bbaf7c6f72a391e939d840e79` |
| OneFile EXE | 339955200 | `1675a25ed2a73cc89fd4bf37c9a4557b74c82dcbca2eb30f45dce4dac2a52f19` |

两种 EXE 的 Windows 文件版本为 `2.2.0.0`，均含与源 ICO 一致的 10 个图标尺寸（1 个图标组、10 个 RT_ICON 条目）。

## v2.1.0 正式发布验证（历史）

- 开发环境（Python 3.13.9）完整回归：541 passed，132.58 s，退出码 0。
- 打包环境（Python 3.11.14）完整回归：541 passed，178.51 s，退出码 0；测试隔离后两次完整运行均通过（另一次 204.19 s）。
- 回归中发现 GUI 窗口只关闭未销毁导致状态跨测试残留；测试现使用会话级 QApplication、每项窗口销毁与 Qt 状态还原。打包环境先前两次原生访问冲突的日志保留在本地，隔离后完整通过。
- StandAlone ZIP：1039 个构建文件逐字节校验，运行时 `config.json` / `themes.json` 未分发。
- StandAlone：主窗口及预设下拉完成桌面观察；从 ZIP 解压的程序在隔离配置下离屏持续运行 15 秒，无启动错误，随后结束测试进程。
- OneFile：隔离配置下冷启动，25 秒后加载器与子进程均存活，配置/主题已生成，无启动错误；随后结束本次测试进程。

| 产物 | 字节数 | SHA256 |
|---|---:|---|
| StandAlone EXE | 129579008 | `428b9ae62d45c5f20ad31c08e2e1d7f24e206fb4ffa334e602d6f01ebda763af` |
| StandAlone ZIP | 125498059 | `ef1bedd1946852bb7b47085107140459c1a5985c40174878cec47ea5de67d84f` |
| OneFile EXE | 339504640 | `f80d562e64578809627792020bb7d56d8b6720e66f8168e486a22ceba16f9991` |

两种 EXE 的 Windows 文件版本为 `2.1.0.0`，均含与源 ICO 完全一致的 10 个图标尺寸。

## 验证

```powershell
.\tools\run_tests.ps1 -Durations 20
# 在实际打包 Python 上也运行完整套件
.\tools\run_tests.ps1 -Python "$env:USERPROFILE\.conda\envs\nuitka_pack\python.exe"
```

发布前检查：

1. 所有版本字段一致：`cvanalysis/__init__.py`、`pyproject.toml`、`CITATION.cff`、`build.bat`。
2. 完整回归退出码为零；定向测试不能代替完整回归。
3. 验证 EXE Windows 版本资源、图标、SHA256；核对主题/许可和 Qt 平台插件。
4. 在隔离配置目录启动两种程序，验证窗口创建、正常退出及启动日志；首次 OneFile 解压可能较慢。
5. StandAlone ZIP 解压后路径和字节与构建目录一致。
6. 真实 Windows 桌面的交互、不同缩放及打印/导出需人工验收，离屏测试不能证明这些体验。

## 常见构建问题

- “复制 SVG”与导出 SVG 通过 Matplotlib 按格式动态加载渲染后端。构建脚本在两种打包模式中显式包含 `matplotlib.backends.backend_svg`。验收时复制一张有数据的图，检查剪贴板的 `image/svg+xml` 内容。

- 缺少 `ffi.dll` / `libexpat.dll`：确认 conda `Library/bin` 在 PATH 中。首次或环境变化后设置 `$env:CVANALYSIS_FORCE_DLL_CACHE='1'`，强制重建 DLL 依赖缓存。
- DLL 扫描缓存记录旧环境：使用独立 `build_cache`，核对打包 Python，不要复制其他 Python 版本的 DLL。
- 启动失败：诊断日志位于 `%LOCALAPPDATA%/CVAnalysis/logs/startup_error.log`，无可写目录时退回系统临时目录。不要仅凭 EXE 存在判断成功。
- Nuitka 版本更新提示不等于构建失败；发布时记录实际编译器与依赖版本，避免构建中途升级环境。
- 调试临时输出放 `.local/`；缓存和 EXE 不提交源码仓库。

## 发布顺序

获准发布后，检查差异、隐私文件和完整回归，再构建并验收对应版本。提交源码后核对远端 `main` / `v2` 的快进条件，使用普通推送。新发布创建与版本对应的附注标签，再核对附件下载链接和 SHA-256。既有标签包括 `v2.1.0`、`v2.2.0`，应保留其原始指向。
