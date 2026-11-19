# 累积屏幕空间全局光照与时域验证

无第三方依赖的 CPU 图形实验，包含两部分：

- 室内 `480x300` 屏幕空间全局光照：深度/法线重投影、历史方差裁剪、鬼影对照、历史权重扫描。
- `360x360` 地形 D8 汇流：priority-flood 洼地填充、最陡下降、流量累积、河网/山谷坐标。

## 运行

```bash
make run
```

产物写入 `artifacts/`，总报告为 `REPORT.md`。完整流程为单线程 CPU 实现，约需数分钟；单帧耗时统计写入 `artifacts/frame_times.csv`。

## 主要产物

- `artifacts/indirect_light.png`：深度、法线、单帧/累积间接光与最终合成。
- `artifacts/indoor_color_bleed.png`：墙脚颜色溢出 ROI 与偏色数值。
- `artifacts/temporal_ghost_validation.png`：朴素历史与深度/法线拒绝的鬼影对照。
- `artifacts/history_weight_quality.png`：历史权重、噪声、鬼影和画质关系。
- `artifacts/frame_times.png` / `frame_times.csv`：逐帧耗时。
- `artifacts/terrain_hydrology.png`：河网、汇流点、山谷中心线和坡度图。
- `artifacts/river_network.csv`、`valleys.csv`、`terrain_analysis.json`：逐单元汇流结果与校验。

## 说明

这是可复现的算法验证实现，不是 GPU 生产渲染器。屏幕空间未命中射线按零能量处理，CPU 帧时间不能直接代表 GPU 性能。
