# 测试与发布验证

使用 `tools/run_tests.ps1`，在需要时先安装开发依赖 `python -m pip install -e ".[dev]"`。Python 3.11+；GUI 测试使用 Qt offscreen。测试数据以合成为主，`test_testdata_regression.py` 的两项真实数据回归在没有本地 `testdata/` 时跳过；私人测量数据不进入 Git。

## 选择测试

```powershell
# 精确文件或 node ID；替换默认目标
.\tools\run_tests.ps1 -Targets @('tests_v2/test_safe_template_format.py')
# 便于交互开发的固定子集
.\tools\run_tests.ps1 -Suite Gui
.\tools\run_tests.ps1 -Suite Plotting
.\tools\run_tests.ps1 -Suite Release
# 交付前完整运行一次，包含全部已收集场景
.\tools\run_tests.ps1 -Durations 10
```

按改动选受影响范围，再做一次完整回归。不要机械地串行执行 Gui、Plotting、Release 和 All，重复覆盖同一批测试。失败、后续改动或未解决的风险才需要扩大/重跑。`-Targets` 接受文件和 `file.py::test_name`，`-PytestArgs` 用于 `-k` / `-m` 等选项；仅把文件追加到全套目录后不会缩小 pytest 收集范围。

`Release` 包含元数据一致性、隔离构建/加载真实 wheel 的资源检查，以及窗口图标检查。EXE 的资源、ZIP、启动和 GitHub 附件校验另见 [Build](../Build.md)。只有离屏通过不能证明桌面效果。

## 隔离和稳定性

- 每次使用独立 basetemp/cache；成功删除本次目录，失败保留；不写字节码，不跟随链接清理，不允许参数覆盖隔离目录。
- 选 conda Python 时优先使用该环境的 DLL，结束恢复 PATH。
- `conftest.py` 保持会话级 QApplication，每项结束销毁新增窗口树、处理 DeferredDelete，并还原 Qt 样式、字体、图标、调色板、主题、动画和翻译器。`close()` 通常只隐藏 QWidget，不能代替销毁。
- 不复用可变 MainWindow/Dataset 作为会话 fixture。纯函数测试直接调用业务层；需要动作、信号或持久化才建完整窗口。运行中的 worker 由测试自己等待结束，清理层会报告遗留任务，不能强制销毁来掩盖问题。
- 等待实际信号、状态或最终几何，设置有限超时；不因时序波动无限增加固定 sleep，不忽略原生异常退出码。

## 覆盖重点与维护

单元测试验证解析、物理量和安全模板的边界；渲染测试验证真实值/位置/边界与导出；集成测试验证信号、每图暂存输入和项目映射。相同状态下的无操作检查可合并进已有完整场景，保留所有断言；避免为重复断言再建一套窗口。不同物理量、失败分支和安全边界应独立保留。

本轮增加版本字段交叉核对、真实 wheel 资源和隔离安装加载、模板宽度/精度/字段数/输出上限，以及外部 TeX 命令拒绝场景；重复的小数格式改测大写形式，空标签页关闭检查合并到关闭最后一页的场景。

## 记录

2.1.0 发布基线为 541 项：开发环境隔离前 465.16 s，隔离后 132.58 s；打包环境隔离后完整运行 204.19 / 178.51 s，均退出码 0。隔离前打包环境发生两次布局事件处理访问冲突，保留了失败日志。用时来自同机不同负载，不能视为严格性能基准。

2026-11-17 发布后维护：549 passed，开发环境 175.24 s、打包环境 180.52 s，均退出码 0；含两项本地真实数据回归。新增 wheel 集成检查在开发环境全套中为 19.54 s，其余新增安全边界为轻量单元场景。该检查保留在 All 和 Release 组，日常使用受影响的精确目标。

本地测试数量会因真实数据是否存在而表现为通过/跳过；不要为追求固定 passed 数字增加重复测试。当前最慢项目用 `-Durations` 实测后再优化。
