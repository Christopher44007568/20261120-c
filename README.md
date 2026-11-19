# 20261120-c

kd-tree 光线求交：逐轴（空间中点）切分 vs SAH 切分对比实验。

## 构建与运行

```sh
g++ -O2 -std=c++17 -Wall -Wextra -o kdtree src/*.cpp
./kdtree
```

输出：每个场景 x 每种策略的构建/遍历统计、逐深度切割面位置表，
并将 `(depth, axis, normPos)` 写入 `splits_<scene>_<strategy>.csv`。

## 代码结构

- `src/geometry.h` — Vec3/Ray/AABB/Triangle，Moller-Trumbore 求交
- `src/kdtree.h/.cpp` — kd-tree 构建（AxisMidpoint / SAH）与 mailbox 遍历
- `src/scenes.h/.cpp` — 均匀、聚集、点云、密集网格、共面测试场景
- `src/main.cpp` — 实验驱动、正确性校验（暴力对照）、共面归属测试

## 关键设计

- 切割面与三角形重叠（含恰好共面）时，三角形按 bbox 重叠规则同时
  归属左右子节点；遍历时用 mailbox（每三角形记录最近射线 id）保证
  同一射线对同一三角形至多求交一次，`duplicatesSkipped` 统计被
  避免的重复测试。
- 叶内三角形按整条射线区间 `[tMin, hit.t]` 测试，节点 t 区间仅用于
  子树剪枝，避免跨越切分面的三角形被漏检。
- SAH 候选取裁剪后三角形 bbox 端点，扫描排序后 O(n log n) 求最优；
  代价不低于不切分时直接成叶，防止聚集场景下无限细分出倾斜深树。
