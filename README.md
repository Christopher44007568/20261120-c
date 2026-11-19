# Curl Noise 粒子流场

这是一个无第三方依赖的 C11 实现：用谱域 curl noise 驱动周期域中的粒子，
输出流场、粒子轨迹和统计验证，并通过 Python `ctypes` 检查 C ABI、结构体
和数组布局是否一致。

## 快速开始

```bash
make
./build/curl_noise --out artifacts
python3 tools/render.py artifacts
make check
```

`make check` 会重新生成默认实验、SVG、C/Python 两套 ABI 布局描述，并执行
数值散度、粒子分布、频率弯曲度和独立 ctypes 推演检查。

常用参数：

```bash
./build/curl_noise \
  --out artifacts \
  --particles 16384 \
  --steps 720 \
  --dt 0.005 \
  --frequency 2 \
  --seed 20261120 \
  --trace-count 96 \
  --trace-every 3
```

`--layout-json PATH` 只导出 C 端 ABI 描述并退出。

## 数值方法

二维不可压缩场由流函数 `psi` 的旋度构造：

```text
psi(x) = -sum_j A_j / |k_j| * sin(k_j . x + phi_j)
v(x)   = ( d psi / d y, -d psi / d x )
       = sum_j A_j * (-k_j.y, k_j.x) / |k_j| * cos(k_j . x + phi_j)
div(v) = d vx / dx + d vy / dy = 0
```

每个模态的速度垂直于波矢，因此散度在解析上恒为零。波矢分量取
`2*pi*n/L` 的整数倍，保证 `[0,L)^2` 周期箱内无缝衔接。默认使用 4 个
倍频、每倍频 5 个随机相位模态，共 20 个模态；高频倍频幅度按 `gain`
衰减，速度整体缩放到给定 RMS 速度。

粒子使用四阶 Runge-Kutta 在周期环面上积分。小步长下 RK4 的体积误差很小，
因此初始均匀分布不会因流场压缩而聚集。

## 验证口径

- 数值散度：在 96x96 网格上以中心差分 `h=1e-5` 计算，报告
  `max |div(v)|` 与 RMS。
- 密度：将周期域划分为 20x20 个箱。`clustering_index = CV * sqrt(N/箱数)`
  对有限粒子数归一化，约等于 1 时接近独立均匀采样；约化卡方同理。
- 聚集判定：同时检查归一化聚集指数、最大箱占比、约化卡方和分布均匀度。
- 轨迹曲率：由相邻采样速度方向角变化除以弧长估计，
  单位为 `1/length`。频率扫描时保持 RMS 速度一致，以隔离频率本身的影响。
- 频率扫描：`0.75, 1, 1.5, 2, 3, 4, 6, 8` 周期/箱，使用 96 条探针轨迹。

## 输出产物

运行后 `artifacts/` 包含：

- `flow_field.csv`：96x96 网格上的 `x,y,vx,vy,potential,divergence,speed`。
- `particles_initial.csv`、`particles_final.csv`：粒子初始/最终状态。
- `trajectories.csv`：96 条轨迹，每条 241 个采样点。
- `frequency_sweep.csv`：频率、平均/P95 曲率、路程和净位移。
- `metrics.json`：配置、散度、密度统计、轨迹统计和结论标志。
- `summary.txt`：便于阅读的验证摘要。
- `flow_field.svg`、`trajectories.svg`：无外部依赖的矢量化视图。
- `layout_c.json`、`layout_python.json`：C 与 ctypes 的布局描述。

默认运行结果：

| 指标 | 结果 |
|---|---:|
| 20 模态场 `max abs(div)` | `5.19e-7` |
| 初始/最终密度 CV | `0.0473 / 0.1249` |
| 最终归一化聚集指数 | `0.799` |
| 最终约化卡方 | `0.640` |
| 最终分布均匀度 | `0.950` |
| 是否判定聚集 | 否 |
| 轨迹平均曲率 | `16.60` |
| 频率-曲率 Pearson r | `0.991` |

粒子数有限时，流场混合会让分箱计数从低差异初始格点退化为更接近普通
均匀采样，因此原始 CV 会上升；归一化聚集指数仍小于 1，约化卡方也小于 1，
没有出现密度峰。可视化时轨迹中的断线表示周期边界回绕，并非粒子跳跃。

## 频率与轨迹弯曲度

频率以每个周期箱内的噪声周期数计。速度保持同一 RMS 缩放，所以曲率变化
主要来自空间噪声尺度：

| 频率 | 平均曲率 | P95 曲率 |
|---:|---:|---:|
| 0.75 | 10.73 | 38.59 |
| 1.0 | 10.13 | 33.46 |
| 1.5 | 17.88 | 64.30 |
| 2.0 | 20.47 | 67.21 |
| 3.0 | 32.55 | 104.93 |
| 4.0 | 39.59 | 132.75 |
| 6.0 | 62.11 | 222.90 |
| 8.0 | 69.46 | 221.45 |

总体趋势是频率越高，单位路程上的转向越频繁、轨迹弯曲度越大，相关系数为
`0.991`。低频场给出长而舒展的弧线；高频场产生细小、密集的涡旋。频率很高
时曲率增长的边际变化变小，主要受采样步长和模态幅度衰减限制。

## ABI、结构体与数组布局

公共头文件为 `include/curl_noise.h`，共享库为 `build/libcurlnoise.so`。
当前 x86_64 布局：

| 类型 | size | align |
|---|---:|---:|
| `CNVec2` | 8 | 4 |
| `CNFlowParams` | 36 | 4 |
| `CNExperimentConfig` | 52 | 4 |
| `CNParticle` | 28 | 4 |
| `CNFieldSample` | 28 | 4 |
| `CNTrajectorySample` | 36 | 4 |

数组均为一维/展平的 C-contiguous 布局：

- 粒子数组：`i * 28` 字节，元素 `CNParticle`。
- 流场数组：`(row * cols + col) * 28`，元素 `CNFieldSample`。
- 轨迹数组：`(trace * samples_per_trace + sample) * 36`，元素
  `CNTrajectorySample`。

`src/layout.c` 用 `_Static_assert` 固定这些尺寸，并导出字段偏移 JSON；
`bindings/curl_noise.py` 用 `ctypes` 独立声明同一组结构体。检查命令：

```bash
./build/curl_noise --layout-json artifacts/layout_c.json
python3 bindings/curl_noise.py --layout-json artifacts/layout_python.json
python3 bindings/curl_noise.py --verify-c artifacts/layout_c.json
```

三处描述（C 编译结果、C JSON、ctypes）在测试中逐字段一致。
