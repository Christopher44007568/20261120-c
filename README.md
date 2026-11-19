# BVH 构建策略、求交统计与动态局部重建

本项目用纯 Python 标准库实现了三种 BVH 构建策略，并在同一随机三角形网格和同一组光线上统计构建耗时、节点访问数、三角形求交次数、命中数和逐层结构。动态基准只重建受更新影响的局部子树，并输出新旧重建区域 AABB 的重叠体积。

## 快速运行

要求 Python 3.10+，无第三方依赖。

```bash
python3 -m bvh generate --output-dir data
python3 -m bvh benchmark --mesh data/random_mesh.json --out artifacts/benchmark.json
python3 -m unittest discover -s tests -v
```

`data/` 中已经附带生成好的两个网格样例，因此通常只需运行第二条和第三条命令。基准的完整结果写入 `artifacts/benchmark.json`。

## 三种构建策略

- `sah`：16-bin 分箱 SAH。三个轴分别构造前缀/后缀包围盒，代价为 `1 + (面积左 * 左数量 + 面积右 * 右数量) / 父面积`，选择代价最小的分箱位置。分箱无法产生非空划分时回退到中位切分。
- `median`：沿质心包围盒最长轴排序，按对象数量中位切分。
- `lbvh`：把质心量化到每轴 10 bit，生成 30-bit Morton 码，按最高不同 bit 递归划分。若整个区间 Morton 码相同，则用最长轴中位切分保证叶子上限。

三种策略共享 `max_leaf_size=4` 和同一套 `Node`/`BVH` 数据结构。每个节点保存世界空间 AABB、左右子节点、叶子三角形区间和父节点，因此可以直接做局部子树替换。

## 统计口径

- `node_visits`：光线访问并接受 AABB 相交测试的 BVH 节点数。
- `triangle_tests`：实际执行的 ray-triangle 测试次数，即“总求交次数”的主要指标。
- `hit_count`：最近命中非空的射线数。
- `elapsed_ms`：重复运行后的中位遍历耗时。
- `build_time_ms`：重复构建后的中位构建耗时。
- `levels`：每层节点数、叶子数、叶子三角形数和该层平均叶子三角形数。
- `average_leaf_triangles`：整棵 BVH 的平均叶子三角形数。

遍历使用 Möller–Trumbore 最近命中测试，并按子节点入口距离优先访问近节点。

## 动态局部重建

`DynamicBVH` 对一组移动三角形执行以下流程：

1. 从旧树找到这些三角形所在叶子的最近公共祖先（LCA）。
2. 只收集该子树内的三角形，用相同策略重建局部 BVH。
3. 将局部树接回原树，替换 LCA 节点；其余子树保持不变。
4. 只沿 LCA 到根节点更新包围盒和父链接。

每帧输出的 `overlap_volume` 定义为“重建区域旧 AABB”和“重建区域新 AABB”的交集体积，单位为世界坐标体积。`overlap_ratio_of_old` 是该交集体积除以旧 AABB 体积。基准中的 `actual_full_rebuilds=0`；所有帧完成后才在最终状态上单独执行 3 次全量构建作为耗时参考，参考结果不参与任何场景更新。

局部重建刻意选择初始 SAH 树中体积最小的、包含 16 到 32 个三角形的内部子树，保证更新集中且可重复。任意分散到全场景的更新仍会自然退化到根节点重建。

## 可复现测试场景

随机网格参数：

```json
{
  "seed": 20261120,
  "triangle_count": 1536,
  "dense_triangle_count": 768,
  "dense_region": [[1.5, -1.5, -1.5], [3.5, 0.5, 0.5]],
  "sparse_region": [[-10.0, -10.0, -10.0], [10.0, 10.0, 10.0]],
  "dense_triangle_scale": 0.07,
  "sparse_triangle_scale": 0.55
}
```

前 768 个三角形散布在高密度区域，其余 768 个散布在稀疏区域。每个三角形由随机质心附近三个随机点构成，退化时使用固定备用三角形。

光线参数：

```json
{
  "seed": 424242,
  "ray_count": 1200,
  "focus_ray_percent": 70,
  "focus_ray_count": 840,
  "camera_radius_factor": 0.52,
  "direction_model": "uniform sphere shell toward a random scene/focus point"
}
```

相机原点在场景中心外接球壳上；索引满足 `index % 100 < 70` 的射线对准高密度区域内的随机点，其余射线对准整个场景内的随机点。当前样例场景中心约为 `[0.00749, -0.02934, -0.00131]`，相机半径 `18.78455`，`t_max=75.13821`。

构建与动态参数：

```json
{
  "max_leaf_size": 4,
  "sah_bins": 16,
  "build_repeats": 3,
  "traversal_repeats": 5,
  "dynamic_frames": 8,
  "dynamic_step": [0.025, 0.015, 0.01],
  "full_rebuild_reference_repeats": 3,
  "dynamic_selection": "smallest-volume internal SAH subtree with 16 to 32 triangles"
}
```

## 当前基准结果

以下计数由固定网格和固定光线确定，换机器应保持不变；毫秒数会随机器负载变化。

| 策略 | 构建 ms | 节点数 | 平均叶子三角形 | 总节点访问 | 总求交次数 | 聚焦节点访问 | 聚焦求交次数 | 聚焦遍历 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SAH | 33.450 | 1031 | 2.977 | 55067 | 20853 | 45399 | 17264 | 48.294 |
| 中位切分 | 6.163 | 1023 | 3.000 | 64079 | 27564 | 52150 | 23136 | 57.357 |
| LBVH | 4.351 | 1153 | 2.662 | 302305 | 228188 | 253669 | 188229 | 278.525 |

在高密度区域的 840 条射线上：

- SAH 比中位切分少 `12.95%` 节点访问和 `25.38%` 三角形求交次数。
- SAH 比 LBVH 少 `82.10%` 节点访问和 `90.83%` 三角形求交次数。
- 本次实测 SAH 聚焦遍历约 `48.3 ms`，中位切分约 `57.4 ms`；验收判定同时要求节点访问数和三角形测试数都更低，不依赖易抖动的墙钟时间。
- SAH 构建更慢，体现了“构建换查询”的取舍。

动态基准中 8 帧全部为局部重建：局部重建合计约 `1.442 ms`。最终状态单次全量重建参考中位数为 `34.334 ms`，按 8 帧外推约 `274.669 ms`，局部/全量时间比约 `0.00525`；8 帧重叠体积合计 `0.790768`，平均重叠比例为 `89.71%`。

逐层数据完整保存在：

```bash
jq '.strategies.sah.levels' artifacts/benchmark.json
jq '.strategies.median.levels' artifacts/benchmark.json
jq '.strategies.lbvh.levels' artifacts/benchmark.json
```

## JSON 网格样例

随机网格：`data/random_mesh.json`

- `vertices`：4608 个顶点，每个为 `[x, y, z]`。
- `indices`：1536 个三角形，每个为三个顶点索引。
- `metadata.parameters`：完整生成参数。
- `metadata.focus_region`：高密度区域。
- 文件中保存的是已经固定的顶点坐标和索引；读取时不再调用随机数生成器。
- 当前样例的规范化网格 SHA-256 为 `df4c21c565b56e0a6f91177347baab0a86a928f66f1cfc93d74c91a4317957fb`。

固定顶点索引网格：`data/fixed_mesh.json`

- 8 个共享顶点构成一个立方体。
- 12 个固定三角形索引，可直接与文件中的顶点数组对应。
- 用于验证三种策略在完全相同输入上的构建和最近命中结果。

在 `max_leaf_size=4` 下，固定网格的确定性结果为：SAH 为 9 节点/5 叶子，中位切分为 7 节点/4 叶子，LBVH 为 9 节点/5 叶子。射线 `origin=[0,0,-5]`、`direction=[0,0,1]` 在三种树上都命中三角形 `0`，`t=4.0`。该射线的节点访问/三角形测试数分别为 SAH `5/4`、中位切分 `7/12`、LBVH `6/6`。

两个文件使用相同 schema：

```json
{
  "schema": "bvh-mesh-v1",
  "vertices": [[0.0, 0.0, 0.0]],
  "indices": [[0, 1, 2]],
  "metadata": {}
}
```

`generate_random_mesh()` 先使用固定种子生成随机数据，`save_mesh()` 再固定为 9 位小数写入 JSON。测试会比较重新生成的文件与仓库内样例的字节内容。

## 验收命令

```bash
python3 -m unittest discover -s tests -v
python3 -m bvh benchmark \
  --mesh data/random_mesh.json \
  --rays 1200 \
  --focus-percent 70 \
  --ray-seed 424242 \
  --max-leaf 4 \
  --sah-bins 16 \
  --dynamic-frames 8 \
  --out artifacts/benchmark.json
```

验收测试会检查：三种 BVH 结构合法；最近命中与暴力求交一致；固定网格已知交点 `t=4.0`；重复构建产生相同节点和三角形顺序；动态局部重建后 BVH 仍合法；聚焦射线上 SAH 的节点访问和三角形测试均低于中位切分与 LBVH；JSON 样例可逐字节复现。
