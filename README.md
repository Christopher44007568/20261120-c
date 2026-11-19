# 20261120-c — 基于 Tile 的分层光栅化实验

仿真一个 1920×1080 软件光栅化器，对比逐三角形 immediate 绘制与两级
分层 tile 管线（宏块粗剔除 + 细 tile 边函数精确测试 + 分批提交），
测量剔除率、外部存储带宽、绘制批次与模型耗时。

## 构建与运行

```bash
make                       # 构建 build/tile_rast (C++17)
./scripts/run_benchmarks.sh   # 全部实验，产物写入 results/
```

## 子命令

```bash
build/tile_rast compare  --scene clustered --tris 100000 --tile 32
build/tile_rast sweep    --tris 100000 --scene uniform results/sweep.csv
build/tile_rast matrix   --tris 100000 results/matrix.csv
build/tile_rast scaling  --tile 32 results/scaling.csv
build/tile_rast tiles    --tile 32 results/tiles.csv
build/tile_rast tilehist --tile 128
```

场景：`clustered`（稀疏热点）、`uniform`、`large`（超大三角形）、
`offscreen`（视口外压力）。完整方法学、带宽模型与结论见 [REPORT.md](REPORT.md)。
