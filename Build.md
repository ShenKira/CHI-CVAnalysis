# Windows 构建与发布

当前发布版本：**2.1.0**（2026-11-17）。构建结果和验收记录见下文；历史版本的二进制与校验信息以 GitHub Release 为准。

## 构建环境

- Windows x64，Python 3.11.14（Anaconda `nuitka_pack`）。
- Nuitka 4.3.1，MSVC 14.5，PySide6 6.9.2。
- NumPy 2.4.2、SciPy 1.17.1、pandas 3.1.0、Matplotlib 3.10.8。
- 运行依赖以 `pyproject.toml` 为准；PySide6 限制 `<6.10`，避免已观察到的原生崩溃。

```powershell
# 可指定另一套已安装依赖和 Nuitka 的 Python
$env:CVANALYSIS_PYTHON = 'C:\path\to\env\python.exe'
cmd /c build.bat 2.1.0 all
# 也可分别使用 standalone / onefile
```

`build.bat` 默认版本为 2.1.0，先构建 StandAlone，再构建 OneFile。它自动把所选 Python 环境的 `Library/bin` 等目录加入 PATH，使用 MSVC、禁用 LTO，OneFile 不压缩。构建日志建议保存到被忽略的 `build_cache/logs/`。

## 产物与资源

- StandAlone：`CVAnalysis_StandAlone_v2.1.0/start_gui.dist/`，必须整体分发，不能只复制 EXE。
- OneFile：`CVAnalysis_OneFile_v2.1.0/CVAnalysis_v2.1.0.exe`，启动时解压至系统临时目录的独立子目录。
- 发布附件：StandAlone ZIP、OneFile EXE、`SHA256SUMS.txt`。GitHub 自动提供对应标签的源码 ZIP / tar.gz。
- 两种模式均嵌入 `cvanalysis/resources/icons/cvanalysis.ico`，并包含主题模板、图标源文件与 PyGlass MIT 许可/改编声明。
- EXE 未进行代码签名。分发与运行不要求修改系统防护设置。

## 本次验证结果

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

- 缺少 `ffi.dll` / `libexpat.dll`：确认 conda `Library/bin` 在 PATH 中。首次或环境变化后设置 `$env:CVANALYSIS_FORCE_DLL_CACHE='1'`，强制重建 DLL 依赖缓存。
- DLL 扫描缓存记录旧环境：使用独立 `build_cache`，核对打包 Python，不要复制其他 Python 版本的 DLL。
- 启动失败：诊断日志位于 `%LOCALAPPDATA%/CVAnalysis/logs/startup_error.log`，无可写目录时退回系统临时目录。不要仅凭 EXE 存在判断成功。
- Nuitka 版本更新提示不等于构建失败；发布时记录实际编译器与依赖版本，避免构建中途升级环境。
- 调试临时输出放 `.local/`；缓存和 EXE 不提交源码仓库。

## 发布顺序

先检查差异、隐私文件与完整回归，再构建和验证。提交源码后重新读取远端，确认 `main` / `v2` 可快进，使用普通推送，禁止强推。创建不可变的附注标签 `v2.1.0`，上传附件并核对 Release 下载链接及 SHA256。后续文档或测试维护使用新提交，不移动已发布标签。
