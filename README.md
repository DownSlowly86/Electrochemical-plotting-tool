# 电化学作图工具

一个本地桌面电化学原始数据作图应用。当前版本：`v0.2`。

当前版本支持上传 `.csv`、`.txt`、`.tsv`、`.dat` 文本数据文件，自动识别常见列名，并绘制：

- EIS 奈奎斯特图
- 电池长循环图
- 电压-比容量图
- dQ/dV 图
- 倍率性能图
- CV 图
- GITT 图

## 运行

```powershell
powershell -ExecutionPolicy Bypass -File .\run_desktop_app.ps1
```

这是桌面应用，不需要浏览器或本地网页服务。启动脚本会优先运行 `desktop_app_v0_2.py`。

运行环境需要 Python、Tkinter 和 Pillow。Windows 上的 Python 通常自带 Tkinter；如果缺少 Pillow，可执行：

```powershell
python -m pip install pillow
```

## 使用流程

1. 选择原始数据文件。
2. 选择图表类型。
3. 选择单栏或双栏图像尺寸。
4. 点击 Render。
5. 点击 Export PNG (600 dpi) 或 Export SVG 保存图像。

## 当前数据识别规则

应用会根据列名和文件结构自动匹配绘图需要的数据。例如：

- EIS：`Z'`、`Zre`、`real`、`Z''`、`Zim`、`imag`
- 长循环/倍率：`cycle`、`capacity`、`discharge capacity`、`coulombic efficiency`
- 电压-比容量/dQdV：`voltage`、`potential`、`capacity`
- CV：`potential`、`current`
- GITT：`time`、`voltage`
- 蓝电/类似分层 CSV：自动识别“循环号 / 工步号 / 数据序号”三层结构，分别提取循环汇总、工步汇总和逐点数据。
- CHI EIS 文本：自动跳过实验参数说明，从 `Freq/Hz, Z'/ohm, Z"/ohm...` 表头开始读取，并用 `Z'` 与 `-Z''` 绘制奈奎斯特图。

## 图像格式

导出风格参考 Nature 系列期刊最终图件要求：

- 单栏宽度 89 mm，双栏宽度 183 mm。
- 字体采用 Arial/Helvetica 风格。
- 坐标轴使用黑色细线，少装饰、无网格。
- 曲线使用色盲友好配色和开放圆点。
- PNG 按 600 dpi 导出。
- SVG 作为可编辑矢量图导出，适合后续排版。

## GitHub 同步

本项目同步到：

```text
https://github.com/DownSlowly86/Electrochemical-plotting-tool
```

## 发布新版本

仓库已配置 GitHub Actions 发布流程：`.github/workflows/release.yml`。

后续需要发布新版本时，可以在 GitHub 仓库页面进入 `Actions`，选择 `Release`，点击 `Run workflow`，输入版本号，例如 `v0.3.0`。流程会自动打包桌面应用，并在 GitHub 的 `Releases` 页面创建一个新版本。

也可以通过推送 `v*` 格式的标签触发发布，例如 `v0.3.0`。

Release 附件会包含：

- `desktop_app_v0_2.py`
- `desktop_app.py`
- `run_desktop_app.ps1`
- `README.md`
- `examples/` 示例数据
