# Bidirectional Path Tracing + MIS

这是一个无外部依赖的 CPU 路径追踪实验工程，用于比较：

- 单向路径追踪（PT）：相机子路径 + 光源采样 NEE + BSDF 采样 MIS。
- 双向路径追踪（BDPT）：相机子路径 + 光源子路径，枚举全部 `(s,t)` 连接并使用平衡启发式 MIS。

核心实现：

- `src/bdpt.h`：子路径生成、路径空间 MIS、连接可见性、光源到相机的双线性 splat。
- `src/integrators.h`：PT 基线与参考误差度量所需的直接光照采样。
- `src/scenes.h`：间接光、室内、强焦散三个场景。
- `src/renderer.h`：多线程渲染、固定样本和固定墙钟时间两种模式。
- `scripts/run_experiments.py`：可复现实验、CSV 汇总和 SVG 图表生成。

## 构建与运行

```bash
make -j4
./rpt render --scene caustic --integrator bdpt --spp 64 \
  --width 160 --height 120 --threads 12 --out caustic_bdpt
```

输出 `caustic_bdpt.ppm`、`caustic_bdpt.pfm`。CLI 还支持：

```bash
# 固定墙钟预算
./rpt render --scene caustic --integrator bdpt --time 1.0 \
  --width 160 --height 120 --threads 12 --out caustic_1s

# PFM 对比
./rpt compare --reference results/reference_caustic.pfm \
  --image results/previews/equal_caustic_bdpt.pfm

# 多张独立结果图的逐像素方差
./rpt stats a.pfm b.pfm c.pfm
```

完整实验：

```bash
python3 scripts/run_experiments.py --threads 12
make test
```

## 算法要点

对连接策略 `(s,t)`，其中 `s` 为光源子路径顶点数，`t` 为相机子路径顶点数，路径贡献写作

```text
F_s = throughput_light * f(qs) * f(pt) * throughput_eye * G(qs, pt)
```

平衡启发式权重为

```text
w_s = p_s / sum_j p_j
```

`bdptMisWeight()` 通过沿两条子路径的 `pdfRev / pdfFwd` 链逐项重建所有候选策略的路径密度；Dirac BSDF 对应的零密度按 1 处理，和标准 BDPT 一致。像素级 `t=1` 策略使用双线性 film splat，以降低光子式焦散估计的方差。

PT 基线在每个漫反射顶点做 NEE，并对光源采样与 BSDF 采样使用相同的平衡启发式；玻璃和镜面作为 delta 分支完整传输。

## 实验结果

详见 [RESULTS.md](RESULTS.md)。主要图表与数据：

- `results/error_curves.svg`：三个场景的 MSE-spp 曲线。
- `results/equal_time_error.svg`：1 秒等时预算下的 MSE 对比。
- `results/convergence.csv`：按 spp 的 MSE、方差和焦散关注区误差。
- `results/equal_time.csv`：相同墙钟时间下的 spp 与参考误差。
- `results/variance_summary.csv`：固定 32 spp 的逐像素方差。
- `results/reference_*.png`：高样本参考图。
- `results/previews/`：PT/BDPT 等时和 64 spp 预览图。

实验配置为 160x120、最大深度 8、12 个渲染线程；参考图使用 BDPT 4096 spp（焦散场景 8192 spp）。
