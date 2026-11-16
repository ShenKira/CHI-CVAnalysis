# CVAnalysis Windows 图标候选

三版候选均使用内置 image_gen 生成，PNG 原始画布为 1254×1254、RGBA 透明背景。用户已选用后续白底黑曲线版作为应用默认方向，正式 ICO 位于 `cvanalysis/resources/icons/cvanalysis.ico`，运行时与构建配置已接入。

| 版本 | 图形与隐含主题 | 文件 |
|---|---|---|
| A 曲线拨片 | CV 回线、拨片轮廓、暖金与酒红；音乐元素最明显 | `a-pick-loop.png` / `a-pick-loop.ico` |
| B 薄荷电极 | 电极与 CV 回线；奶油白、薄荷绿、蓝及少量粉色呼应现有 K-ON 主题 | `b-mint-electrodes.png` / `b-mint-electrodes.ico` |
| C 午夜回线 | 深色底与白色 CV 回线，五条色彩呼应轻音部配色；建议作为正式应用图标方向 | `c-midnight-loop.png` / `c-midnight-loop.ico` |

`comparison.png` 提供大图及浅色/深色背景下 16/24/32/48/64 像素的实际大小对照。

每个 ICO 内含 16、20、24、32、40、48、64、96、128、256 像素十个尺寸，已使用 Pillow 重新打开并验证所有尺寸。原始透明通道保留。未进行 Windows 资源管理器图标缓存和安装包显示验收。

候选图标的配色参考项目现有 K-ON 主题色，未使用角色图像或现成作品标志。

## 选择后的接入

新增 C 白底黑曲线对照稿：`c-porcelain-loop.png` / `c-porcelain-loop.ico`；对照图为 `c-dark-light-comparison.png`。以 C 原图经 image_gen 编辑生成，保留五色条及基本几何。透明边缘仍有少量生成碎边，属于待选型稿；选定白色方向后应精修边缘再设置为正式应用图标。ICO 含相同十种尺寸，已验证可读取。

应用窗口已通过 `QApplication.setWindowIcon(QIcon(...))` 使用正式 ICO；Nuitka 构建已添加 `--windows-icon-from-ico` 并把运行时图标列为数据资源。现有发布产物需要重新构建才会采用该图标。
