# 可见性缓冲 vs 延迟渲染基准

这是一个无第三方依赖的 C++17 基准，包含真实软件光栅化的两条管线：

- 可见性缓冲：第一遍只写 `triangleId(4B) + depth(4B)`，第二遍按 16x16
  tile 去重 ID、读取三角形属性和材质并着色。
- 延迟渲染：第一遍写 `32B/px` G-buffer 和深度，第二遍读取 G-buffer 着色。

两条管线使用同一套深度测试、三角覆盖规则和像素着色函数，最终 8 位图像
checksum 必须一致。基准以确定性的等效渲染目标流量统计带宽，时间取多次
运行的中位数。

## 构建与运行

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/visbuf_bench --runs 3 --output-dir results
ctest --test-dir build --output-on-failure
```

输出：

- `results/benchmark.csv`：每个场景、每条管线的完整带宽与耗时数据。
- `results/report.md`：中文分析、带宽拆分、多材质比较与结论。

## 统计口径

带宽包含深度测试读、深度写、G-buffer 或可见性缓冲写、第二阶段缓冲读、
三角形属性读和最终颜色写。三角形属性按 tile 内可见 ID 去重，记录大小为
`sizeof(Triangle) = 100B`。顶点索引、剔除和命令提交是两条管线共有的开销，
不计入比较。

时间是 CPU 软件光栅化的相对测量，不是 GPU 硬件计数器。带宽是解析式
缓冲区访问模型，因此结果可复现，但真实 GPU 还会受压缩、cache 命中率、
residency 和三角属性格式影响。报告明确给出这些限制。

## 默认场景

- `small_triangles_8mat`：115,200 个约 8 像素三角形，1 层，8 材质。
- `dense_small_8mat`：691,200 个约 8 像素三角形，6 层覆盖，8 材质。
- `dense_small_64mat`：与上组几何相同，64 材质。
- `tiny_dense_64mat`：1,843,200 个约 2 像素三角形，4 层覆盖，64 材质。

`1280x720` 下可见性缓冲固定为 `7.03 MiB`，延迟 G-buffer 加深度为
`31.64 MiB`。最新实测结果和百分比见 `results/report.md`。
