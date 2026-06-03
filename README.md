# 电化学作图工具

一个本地桌面电化学原始数据作图应用。当前版本支持上传 `.csv`、`.txt`、`.tsv`、`.dat` 文本数据文件，自动识别常见列名，并绘制：

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

这是桌面应用，不需要浏览器或本地网页服务。

运行环境需要 Python、Tkinter 和 Pillow。Windows 上的 Python 通常自带 Tkinter；如果缺少 Pillow，可执行：

```powershell
python -m pip install pillow
```

## 使用流程

1. 选择原始数据文件。
2. 选择图表类型。
3. 点击 Render。
4. 点击 Choose output location 选择输出位置。
5. 点击 Export PNG 保存图像。

## 当前数据识别规则

应用会根据列名和文件结构自动匹配绘图需要的数据。例如：

- EIS：`Z'`、`Zre`、`real`、`Z''`、`Zim`、`imag`
- 长循环/倍率：`cycle`、`capacity`、`discharge capacity`、`coulombic efficiency`
- 电压-比容量/dQdV：`voltage`、`potential`、`capacity`
- CV：`potential`、`current`
- GITT：`time`、`voltage`
- 蓝电/类似分层 CSV：自动识别“循环号 / 工步号 / 数据序号”三层结构，分别提取循环汇总、工步汇总和逐点数据。

真实仪器导出的原始文件格式可能差异很大。后续可以把你的样例数据放到项目中，再补充更精准的识别和清洗逻辑，包括 Excel 文件、多段表头、单位换算、充放电段识别、循环筛选和批量出图。

## GitHub 同步

本项目同步到：

```text
https://github.com/DownSlowly86/Electrochemical-plotting-tool
```

本地安装 Git 后，也可以在项目目录执行：

```powershell
git init
git branch -M main
git remote add origin https://github.com/DownSlowly86/Electrochemical-plotting-tool.git
git add .
git commit -m "Initial electrochemical plotting tool"
git push -u origin main
```
