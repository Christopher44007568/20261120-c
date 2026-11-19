# 动态 L2 球谐光照探针

一个无外部依赖的浏览器 / Node.js 演示：把动态点光源投影到 9 系数 × RGB 的 L2 SH，向邻近探针做反弹传播，并用连续双线性插值避免物体跨越探针单元时的颜色跳变。

## 快速开始

```bash
npm test       # 算法、脏区一致性、连续性、帧预算测试
npm run bench  # 生成基准与探针 CSV / JSON / Markdown 报告
npm start      # http://localhost:8080
```

浏览器演示可以切换“按需脏区 / 逐帧全量”，调整更新间隔、物体速度与显示阻尼，点击任意探针查看其 9×3 个 SH 系数、亮度与误差。

## 实现要点

- 光源投影：解析点光衰减后乘 L2 实球谐基与余弦卷积系数，得到 RGB 交错的 27 个浮点数/探针。
- 邻域传播：每个探针在直接光照后向四邻域做 2 次反弹传播，强度 0.18。
- 按需更新：记录灯光移动、颜色、强度变化；只有越过阈值并到达间隔时，才重建“旧位置 ∪ 新位置”影响范围的脏矩形。
- 连续显示：目标 SH 场先用 65 ms 指数阻尼追随，再按四探针双线性权重混合系数并求辐照度。权重从 0 到 1 时不会直接切换探针系数。
- 误差：每个探针输出显示亮度、当前全量参考亮度、绝对误差、按场景平均亮度归一化的百分比误差，以及 SH 对解析 Lambert 的投影误差。
- 计时：Node 压力基准使用高分辨率时钟，分别记录系数重建、阻尼、插值与帧总计。

## 输出文件

- `artifacts/report.md`：完整中文实验报告、按帧/按需对比、频率权衡和连续性判定。
- `artifacts/probes.csv`：每个探针的 `c00`…`c22` RGB 系数、亮度、误差和投影误差。
- `artifacts/probes.json`：与 CSV 对应的结构化数据。
- `artifacts/continuity.csv`：逐帧对象 RGB、亮度、插值权重、边界事件、跳变量和更新时间。
- `artifacts/frequency.csv`：不同更新间隔的耗时与画质数据。
- `artifacts/benchmark.json`：页面读取的基准汇总。
- `artifacts/demo.png`：无头浏览器实际加载后的界面截图。

## 目录

```text
index.html            浏览器演示
styles.css            界面样式
src/sh.js             SH 基、投影、辐照度求值
src/probe-grid.js     探针场、传播、脏区重建、插值
src/simulation.js     动态灯光轨迹、更新调度、指标
src/benchmark.js      压力基准与报告导出
src/main.js           Canvas 可视化与检查器
test/sh-probes.test.js
```

界面中文字体使用按实际用字裁剪的 Noto Sans SC 子集（`assets/noto-sans-sc-ui.woff2`），许可见 `assets/OFL-NotoSansSC.txt`，不依赖操作系统字体。

## 权衡结论

逐帧全量更新适合做画质基准，但会每帧重建所有探针。按需更新显著降低重建成本，间隔越长误差与跟随滞后越大；显示阻尼可以消除离散更新造成的阶跃，但会额外增加响应滞后。默认建议 33.3–50 ms，并在具体场景中结合 `artifacts/frequency.csv` 的误差与 p95 耗时选型。
