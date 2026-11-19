# 四边重网格化与可见性缓冲实验报告

## 结论摘要

- 两个有机模型都完成了纯四边形重网格化，没有三角形 fallback，也没有非流形边或退化面。
- `organic_ring` 从 3,456 个三角形得到 1,728 个四边形；`organic_leaf` 从 2,688 个三角形得到 1,344 个四边形。
- 四边形边长方差和变异系数都低于三角剖分；角度集中到 90 度附近，角度落在 `90° ± 15°` 的比例分别为 100% 和 99.93%。
- 两个模型的特征边精确保留率、长度加权保留率和几何覆盖率均为 100%，最大几何偏差为 0。
- 粗、中、细三档网格均通过均匀性、流形、质量和特征边门限，可进入后续细分流程。
- Visibility buffer 的帧缓冲显存稳定低于 deferred G-buffer：1x MSAA 低 37.5%，4x MSAA 低 46.2%。
- 总带宽优势不是无条件的：1080p、1x MSAA、零材质缓存惩罚时只低 7.1%；4x MSAA 时低 31.2%。若 1x MSAA 下材质随机访问惩罚超过 `G-buffer 字节数 - visibility 字节数`，deferred 反而更省带宽。
- 预算模型连续 5 次运行哈希一致；真实网格 CPU 光栅化连续 3 次结果一致，并复现了 7.14% / 19.89% / 30.91% 的 1x/2x/4x 带宽节省趋势。

## 复现方式

```bash
python3 run_experiment.py
python3 -m unittest discover -s tests -v
```

实验只使用 Python 标准库，不需要 NumPy、SciPy、Blender、GPU 或图形驱动。完整流程约 2 秒，会重新生成 `artifacts/` 下的全部网格、CSV、JSON 和 SVG。

## 网格实验

### 模型与算法

`organic_ring` 是封闭的管状有机体，`organic_leaf` 是带自由边界的叶片状有机曲面。二者先按纯四边形拓扑生成，再沿较短对角线三角化，并作为重网格器的唯一输入。重网格器只接收顶点、三角形和特征边标签，不读取参考四边形。

重网格流程如下：

1. 对每条非特征内部边构造候选四边形，检查凸性、内角、边长比、两侧法线一致性和对角线长度。
2. 在三角形对偶图上求最大基数匹配；局部贪心冲突用带奇环收缩的 Edmonds blossom 增广路径解决。
3. 用局部配对交换提高四边形质量；特征边禁止作为合并对角线。
4. 只有匹配失败时才启用 conforming 1-to-3 四边形细分 fallback；本次两个模型和六个变体都未触发。

指标定义：

- 边长方差：唯一网格边长的总体方差。
- 边长变异系数 CV：边长标准差除以边长均值，便于跨尺度比较。
- 四边形质量：四个内角中 `min(min(angle, 180-angle) / 90)`，正方形为 1。
- 特征边精确保留率：原特征边以相同顶点对出现在输出中的比例。
- 特征边长度加权保留率：被精确保留的原特征边长度占原特征边总长度的比例。
- 特征边几何覆盖率：原特征边采样点到输出特征边网络的距离不超过包围盒对角线 0.2% 的长度比例。

### 主结果

| 模型 | 三角形 -> 四边形 | 原特征边 | 边长方差（三角 -> 四边） | 边长 CV（三角 -> 四边） | 角度在 90°±15° | 质量均值 / P05 | 参考四边形恢复 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `organic_ring` | 3,456 -> 1,728 | 888 | 0.000907 -> 0.000272 | 0.187 -> 0.115 | 100.00% | 0.943 / 0.882 | 1,728 / 1,728 |
| `organic_leaf` | 2,688 -> 1,344 | 302 | 0.000452 -> 0.000145 | 0.207 -> 0.133 | 99.93% | 0.987 / 0.957 | 1,344 / 1,344 |

绝对方差会受平均边长影响，所以同时报告 CV。两个模型的 CV 都下降，说明分布均匀性改善不是尺度变化造成的。

角度分布从三角形约 60° 的均值转为接近 90°：

| 模型 | 输出角 P05 | 输出角 P50 | 输出角 P95 | 质量 >= 0.7 | 质量 >= 0.85 |
|---|---:|---:|---:|---:|---:|
| `organic_ring` | 82.03° | 89.98° | 97.92° | 100% | 100% |
| `organic_leaf` | 87.82° | 90.00° | 92.12° | 100% | 99.70% |

![organic ring quality histogram](artifacts/charts/organic_ring_quality_histogram.svg)

![organic ring angle distribution](artifacts/charts/organic_ring_angle_distribution.svg)

![organic leaf quality histogram](artifacts/charts/organic_leaf_quality_histogram.svg)

![organic leaf angle distribution](artifacts/charts/organic_leaf_angle_distribution.svg)

完整直方图计数在 `artifacts/data/histograms.csv`，线框对照在：

- `artifacts/charts/organic_ring_wireframe.svg`
- `artifacts/charts/organic_leaf_wireframe.svg`

### 三档分辨率验证

| 模型 | 档位 | 四边形数 | 边长 CV | 质量均值 | 质量 P05 | 特征边精确率 | 可细分 |
|---|---|---:|---:|---:|---:|---:|---|
| `organic_ring` | coarse 84x16 | 1,344 | 0.112 | 0.938 | 0.880 | 100% | 是 |
| `organic_ring` | nominal 96x18 | 1,728 | 0.115 | 0.943 | 0.882 | 100% | 是 |
| `organic_ring` | fine 108x20 | 2,160 | 0.112 | 0.942 | 0.884 | 100% | 是 |
| `organic_leaf` | coarse 40x24 | 960 | 0.122 | 0.987 | 0.955 | 100% | 是 |
| `organic_leaf` | nominal 48x28 | 1,344 | 0.133 | 0.987 | 0.957 | 100% | 是 |
| `organic_leaf` | fine 56x32 | 1,792 | 0.145 | 0.988 | 0.959 | 100% | 是 |

三档结果的边长 CV、质量和特征边保留率没有随分辨率发生退化，支持“分布均匀”和“满足后续细分”的判断。

### 特征边保留率

| 模型 | 原特征边 | 精确保留 | 长度加权保留 | 几何覆盖 | 最大偏差 |
|---|---:|---:|---:|---:|---:|
| `organic_ring` | 888 | 100% | 100% | 100% | 0 |
| `organic_leaf` | 302 | 100% | 100% | 100% | 0 |

![feature edge retention](artifacts/charts/feature_edge_retention.svg)

保留率高的原因是匹配器拒绝跨特征边配对，因此每条输入特征边在输出中仍是同一条四边形边界边；没有细分或更换端点。输出同时通过纯四边形、无三角形 fallback、无非流形边、无退化面检查，因此可以继续做 Catmull-Clark 或其他四边细分。

## 可见性缓冲与延迟渲染

### 预算口径

这是可复现的架构预算实验，不是 GPU 厂商计数器实验；当前机器没有可用 GPU profiler。两条路径都使用相同的场景、覆盖率和材质输入，以下公共成本被排除：

- 深度测试本身的读/写、顶点抓取、纹理采样和三角形光栅化；
- 两条路径共有的场景几何与材质存储；
- 渲染目标压缩、缓存命中和硬件早期深度优化。

显式字节布局：

| 资源 | Deferred | Visibility |
|---|---:|---:|
| 颜色属性 | 20 B/sample | 8 B/sample（几何/实例 ID） |
| 深度 | 4 B/sample | 4 B/sample |
| HDR 输出 | 8 B/pixel | 8 B/pixel |
| 材质数据 | 已写入 G-buffer | resolve 时从场景缓冲读取 20 B/pixel |

令 `P` 为像素数，`C` 为覆盖率，`S` 为 MSAA 样本数，`M=20` 为 G-buffer 字节，`V=8` 为 visibility ID 字节，`D=4` 为深度字节，`H=8` 为 HDR 字节，`R` 为 visibility resolve 的每像素材质缓存惩罚：

```text
Deferred 显存 = P * (S * (M + D) + H)
Visibility 显存 = P * (S * (V + D) + H)

Deferred 带宽 = C * P * (S * (M + D) + (M + D) + H)
Visibility 带宽 = C * P * (S * (V + D) + (V + D) + M + R + H)
```

### 1080p / 4K 结果

| 配置 | Deferred 显存 | Visibility 显存 | 显存节省 | Deferred 带宽 | Visibility 带宽 | 带宽节省 |
|---|---:|---:|---:|---:|---:|---:|
| 1080p, 1x | 63.3 MiB | 39.6 MiB | 37.5% | 72.0 MiB/frame | 66.8 MiB/frame | 7.1% |
| 1080p, 4x | 205.7 MiB | 110.7 MiB | 46.2% | 164.5 MiB/frame | 113.1 MiB/frame | 31.2% |
| 4K, 1x | 253.1 MiB | 158.2 MiB | 37.5% | 287.9 MiB/frame | 267.4 MiB/frame | 7.1% |
| 4K, 4x | 822.7 MiB | 443.0 MiB | 46.2% | 658.1 MiB/frame | 452.5 MiB/frame | 31.2% |

![framebuffer memory](artifacts/charts/rendering_framebuffer_memory.svg)

![frame bandwidth](artifacts/charts/rendering_frame_bandwidth.svg)

### 结论成立条件

显存结论是稳健的：visibility buffer 在 1x 到 4x MSAA 下都更低，因为每样本只保存 12 B，而 deferred 每样本保存 24 B；HDR 输出两边相同。

带宽结论依赖缓存行为。由于 visibility 路径要写两次、读两次紧凑缓冲，再读取一次材质数据，而 deferred 路径写一次、读一次 G-buffer，1x MSAA 下的差额为：

```text
Deferred - Visibility = S*M - (S + 1)*V - R
                     = 20 - 16 - R
                     = 4 - R  (字节/覆盖像素)
```

因此 1x MSAA 时只有材质随机访问惩罚 `R < 4 B/pixel`，visibility buffer 才省带宽；`R = 4` 持平，`R = 8` 或更高则 deferred 更省。4x MSAA 时条件放宽为 `R < 4*20 - 5*8 = 40 B/pixel`，visibility buffer 仍明显占优。

这解释了为什么不能把“visibility buffer 总是带宽更低”作为结论。它的优势来自用更窄的逐样本 ID 取代逐样本 G-buffer，而不是消除材质读取。

敏感度扫描覆盖 `M = 16/20/24 B`、`S = 1/2/4`、`R = 0/4/8/16 B`，完整数据见 `artifacts/data/rendering_sensitivity.csv`。

### 独立光栅交叉校验与复现

用重网格得到的 `organic_ring` 三角网格在 240x135 分辨率做 CPU 参考光栅化，实际写入逐样本深度和三角形 ID，再按同一字节口径计数。三次重复得到相同摘要哈希。

| MSAA | 覆盖像素 | 覆盖样本 | 可见三角形 | 实测带宽节省 | 固定 65% 覆盖率模型 |
|---:|---:|---:|---:|---:|---:|
| 1x | 7,634 | 7,634 | 1,457 | 7.14% | 7.14% |
| 2x | 7,682 | 15,270 | 1,497 | 19.89% | 20.00% |
| 4x | 7,832 | 30,591 | 1,556 | 30.91% | 31.25% |

实测与解析模型的差异来自真实样本覆盖率不等于像素覆盖率，而不是结论方向变化。预算模型连续 5 次运行只产生一个 SHA-256 哈希：

```text
743f75bb8826a6daa5ef0db52e71f051ee67500cc11f62dc92ea96d79fc46b50
```

## 最终确认

1. 四边形分布：两个有机模型和三档分辨率均满足边长 CV <= 0.20、质量均值 >= 0.90、质量 P05 >= 0.75、95% 以上角度位于 `90° ± 15°`。
2. 特征边保留：两个主模型和六个变体的精确、长度加权、几何覆盖率均为 100%，最大偏差为 0。
3. 后续细分：所有输出均为纯四边形、无 fallback、无非流形边、无退化面，且特征边完整，可进入细分流程。
4. 渲染显存：visibility buffer 在测试配置下稳定节省 37.5%-46.2% 帧缓冲显存。
5. 渲染带宽：1080p/1x MSAA 零缓存惩罚时节省 7.1%，4x MSAA 时节省 31.2%；无 MSAA 且材质随机访问惩罚较高时 deferred 可反超。
6. 可复现性：解析预算 5/5 次哈希一致，CPU 光栅化 3/3 次摘要一致，单元测试 12/12 通过。

若要把上述架构结论升级为具体 GPU 的实测结论，下一步应在目标硬件上用 Nsight Graphics、RGP 或厂商性能计数器测 `R`、材质缓存命中率和实际 external-memory traffic；本仓库的模型和脚本可直接作为对照基线。
