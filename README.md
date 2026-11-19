# 骨骼动画定点压缩与锐边细分

纯 Python 标准库实现的骨骼动画压缩/重建演示，以及对开放边界、内部顶点和锐边友好的
Catmull–Clark 细分。

## 功能

- 按目标频率抽取关节关键帧，位置使用逐关节包围盒定点量化，四元数使用 `[-1, 1]`
  定点量化并在解码后归一化。
- 位置线性插值、旋转 SLERP 插值；重建误差拆分为纯插值误差、关键点量化误差和
  最终密采样误差。
- 600 s、60 fps、15 关节长动画验证，按 6 个时间窗口检查误差是否漂移。
- 输出压缩比、局部/世界位置误差、旋转角误差、末端轨迹对比和量化位数扫描。
- Catmull–Clark 细分支持开放边界、内部规则点、显式锐边和角点保留。

## 快速运行

```bash
PYTHONPATH=src python3 -m anim_compress.demo \
  --duration 600 --fps 60 --keyframe-hz 10 --bits 16

PYTHONPATH=src python3 -m unittest discover -s tests -v
```

默认运行会写入 `artifacts/`：

- `animation_compression_report.md`：中文结果报告与判定
- `animation_compression_metrics.json`：完整指标、误差时序和姿态对比
- `quantization_sweep.csv`：8–20 bit 扫描数据
- `action_comparison.svg`：原动画/重建动画轨迹与骨架叠加、误差时序
- `quantization_tradeoff.svg`：量化位数、重建误差和压缩比
- `mesh_subdivision.svg`：边界、内部顶点及锐脊细分前后对比
- `mesh_subdivision_metrics.json`：细分几何指标

## 默认结果

16 bit、10 Hz 关键帧、600 s 动画：

| 指标 | 结果 |
|---|---:|
| 压缩比 | 11.77:1 |
| 最大旋转重建误差 | 0.02545° |
| 最大局部位置误差 | 1.809e-05 |
| 最大末端世界位置误差 | 5.981e-04 |
| 6 个时间窗口旋转峰值 | 0.02248°–0.02545° |

量化误差随位数增加约按 `2^-bits` 下降，实测 log2 斜率为 `-1.000`。16 bit 时
量化误差约 `0.0031°`，已经低于 10 Hz 插值造成的 `0.0250°` 误差地板；因此继续增加
位数收益有限，应改用更高关键帧率。8 bit 的旋转/末端位置峰值为
`0.8029°` / `0.0482`，说明低位数量化会明显损失动作精度。

细分验证中，开放平面片细分后全部顶点仍在 `z=0`，边界矩形保持；帐篷网格的锐脊
细分两级后偏离原直线为 `0`，两侧法线夹角保持 `90°`。

完整数值、对比表和判定见 [artifacts/animation_compression_report.md](artifacts/animation_compression_report.md)。

## 目录

```text
src/anim_compress/
  animation.py      关节层级与程序化长动画
  compression.py    定点量化、关键帧压缩与 SLERP 解码
  metrics.py        插值/量化/重建误差及窗口稳定性
  subdivision.py    边界、内部点与锐边 Catmull–Clark
  demo.py           完整演示 CLI
  report.py         Markdown/JSON/CSV 报告
  svg_report.py     SVG 可视化
tests/              标准库 unittest
artifacts/          已生成的报告与图表
```

运行环境：Python 3.10+，无第三方依赖。
