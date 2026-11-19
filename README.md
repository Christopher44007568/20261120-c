# 骨骼包围盒层次与障碍曲面测地路径

纯 Python 标准库实现的可复现实验：

- 19 骨骼人体按父子拓扑构建 AABB 层次，随 48 帧奔跑姿态逐帧更新；
- 校验每帧蒙皮点、子树、父子盒包含关系，并统计各层体积与更新耗时；
- 用固定透视相机比较深度上限 0–6 的剔除率，并与逐骨骼暴力测试交叉验证；
- 在带圆形障碍的高度场曲面上用 Dijkstra 求最短路，与平面圆障碍解析解及粗细网格收敛结果对照。

## 运行

```bash
python3 run_all.py
python3 -m unittest discover -s tests -v
```

`python3 run_all.py --quick` 使用 12 帧与较少计时重复，便于快速检查。完整运行只需
Python 3.10+，不依赖 NumPy、Matplotlib 或第三方网格库。

## 主要产物

| 文件 | 内容 |
|---|---|
| `REPORT.md` / `artifacts/report.md` | 中文实验报告、结论与限制 |
| `artifacts/figure_running_bbh.svg` | 奔跑姿态骨架、胶囊点与层级/自身包围盒 |
| `artifacts/figure_layer_volumes.svg` | 各层包围盒体积及更新耗时 |
| `artifacts/figure_culling_depth.svg` | 深度上限对剔除率的影响 |
| `artifacts/figure_geodesic_path.svg` | 障碍曲面、最短路径与解析对照 |
| `artifacts/layer_bbox_metrics.csv` | 每层节点数、体积、更新耗时 |
| `artifacts/node_bbox_metrics.csv` | 每个骨骼节点盒体积、填充率与耗时 |
| `artifacts/pose_fit.csv` | 每帧包含率、根盒体积、中心和更新时间 |
| `artifacts/culling_depth.csv` | 各深度剔除骨骼数、剔除率、候选数 |
| `artifacts/geodesic_validation.csv` | 测地距离与解析/收敛参照 |
| `artifacts/geodesic_path_curved.csv` | 曲面最短路径坐标、分段长、累计弧长 |
| `artifacts/metrics.json` | 全部关键指标汇总 |

## 验证口径

- `own_box` 仅包住该骨骼采样点；层次 `box` 为自身盒与子节点盒的并集。
- “贴合”要求所有帧的全部顶点位于自身盒，所有子树顶点位于祖先盒，父盒包含所有子盒，
  并且每帧盒体随姿态发生位移/体积变化。
- 剔除只有当 AABB 完全位于某个视锥平面外侧时才拒绝；全深度输出必须与逐骨骼暴力测试相同。
- 平面障碍使用两条切线段加圆弧的解析最短距离；曲面用粗细网格收敛差和 0.60 m 最小净距共同校验。

具体数值、局限性及复验结果均由 `run_all.py` 写入 `REPORT.md`。
