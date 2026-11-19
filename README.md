# 20261120-c

程序化室内房间布局：按墙体/门/窗约束放置家具，栅格 BFS 保证走道连通，
并对排列搜索做约束传播裁剪。纯 Python 标准库实现。

```bash
python3 -m unittest discover -s tests
python3 scripts/run_layouts.py
python3 scripts/run_culling_benchmark.py
```

完整算法、参数影响与基准结论见 [REPORT.md](REPORT.md)，
机器可读结果在 `artifacts/`（布局 JSON、基准 JSON、SVG/ASCII 平面图）。
