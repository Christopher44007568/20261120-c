# 着色器排列裁剪与首帧编译基准

本仓库实现了一套无外部依赖的着色器排列裁剪流程：

- 以 10 个材质关键字和 4 条光照路径建立 4096 个基线组合。
- 通过依赖闭包、互斥规则和光照路径能力裁剪无效组合。
- 将可被其他关键字激活的关键字从缓存键中删除，得到最小关键字集合。
- 用 LRU 编译缓存统计请求命中率、全量编译耗时和首帧耗时。
- 输出 JSON 报告、无效组合审计、DOT/Mermaid 依赖图与 Markdown 摘要。

> 编译耗时来自仓库内置的小型着色器栈编译器，是本机 CPU 上的可复现实测值，
> 不等同于具体 GPU 驱动的离线编译器或驱动缓存耗时。裁剪与缓存口径保持一致，
> 用于比较相同工作负载下的相对变化。

## 快速运行

```bash
python3 -m shader_permutations --runs 3
python3 -m unittest discover -v
```

也可以安装命令行入口：

```bash
python3 -m pip install -e .
shader-permute --runs 3
```

## 当前结果

默认配置为 7 种材质、每排列 4 轮场景请求、LRU 容量 96。以下数值取 3 轮中位数：

| 指标 | 裁剪前 | 裁剪后 |
| --- | ---: | ---: |
| 排列数量 | 4096 | 68 |
| 全量编译耗时 | 183.259 ms | 2.470 ms |
| 首帧耗时 | 208.283 ms | 1.951 ms |
| 缓存命中率 | 75.00%（204/272） | 100.00%（272/272） |

- 排列数量下降 98.34%，首帧耗时下降 99.06%。
- 3040 个无效组合被删除，最终排列与无效集合交集为 0。
- 626 个重复的有效组合被最小关键字集合合并，362 个场景未使用的有效组合被移除。
- 依赖图环检测为无环，最终验收全部通过。

完整结果见 `artifacts/report.json` 和 `artifacts/summary.md`。

## 裁剪规则

基线是 `2^10 × 4 = 4096` 个关键字与光照路径的笛卡尔积。材质配置位于
`shader_permutations/model.py`，每个材质声明必需关键字、可选关键字和可用光照路径。

依赖闭包示例：

- `ANISOTROPY -> NORMAL_MAP -> PBR`
- `TRANSMISSION -> PBR`
- `CLEARCOAT -> PBR`
- `SUBSURFACE -> PBR`

因此 `ANISOTROPY` 的最小缓存键不需要显式包含 `NORMAL_MAP` 和 `PBR`。编译前会由
依赖闭包补齐，缓存键则使用最小集合。

无效组合示例：

- `TRANSMISSION` 不能与 `ALPHA_MASK` 同时使用。
- `SUBSURFACE` 只能用于 `FORWARD`，且不能与透射或各向异性同时使用。
- `TRANSMISSION` 不支持 `DEFERRED` 和 `RAYTRACE`。
- `ALPHA_MASK` 不支持 `DEFERRED`。
- `CLEARCOAT`、`ANISOTROPY`、`SHADOW_CASCADE` 不支持 `RAYTRACE`。

## 首帧与缓存口径

首帧流程：

1. 管线预热：裁剪前编译全部 4096 个候选，裁剪后只编译 68 个最小排列。
2. 场景发出 68 个排列 × 4 轮共 272 次缓存请求。
3. 首帧耗时等于预热编译耗时加请求缺失编译耗时。

裁剪前 4096 个候选中只有 1552 个唯一闭包键，超过 96 条缓存容量，预热后场景请求
产生 68 次缺失；裁剪后 68 个键可全部驻留，因此请求命中率为 100%。

## 产物

- `artifacts/report.json`：数量、编译耗时、首帧、缓存和全部验收布尔值。
- `artifacts/summary.md`：可直接阅读的裁剪报告。
- `artifacts/invalid-combinations.json`：无效组合数量、原因计数和样例。
- `artifacts/dependency-graph.dot`：Graphviz 依赖图。
- `artifacts/dependency-graph.mmd`：Mermaid 依赖图。

## 代码结构

- `shader_permutations/model.py`：关键字域、材质特性、依赖闭包、最小化与校验。
- `shader_permutations/compiler.py`：生成并编译着色器栈程序。
- `shader_permutations/cache.py`：有界 LRU 缓存。
- `shader_permutations/dependency.py`：依赖图、环检测和拓扑排序。
- `shader_permutations/benchmark.py`：编译与首帧基准。
- `shader_permutations/report.py`：报告与依赖图产物。
- `tests/`：数量、最小性、无效集合、编译、缓存、依赖图和产物验收。
