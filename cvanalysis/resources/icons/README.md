# Application icon

`cvanalysis.ico` 是当前选定的白底黑曲线版 Windows 图标，来源于项目候选目录中的 `c-porcelain-loop.ico`，包含 16、20、24、32、40、48、64、96、128、256 像素十个尺寸。

运行时从包内相对路径加载，源码运行与安装包均不依赖当前工作目录。`pyproject.toml` 将 ICO 包含在 wheel/sdist 中；`build.bat` 为 StandAlone 和 OneFile 共用 EXE 图标及数据资源参数。

原始 PNG 在 `assets/icons/concepts-20261116/`。此轮按用户选择直接采用现有白底候选；生成稿透明边缘的已知碎边尚未精修。
