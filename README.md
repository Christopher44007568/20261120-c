# 基于亮度的重要性采样 IBL

零第三方依赖的 C++17 实验：在合成 HDR 等距柱状环境图上，按环境亮度 CDF 生成采样方向，
为 GGX IBL 查询选择 mip，并比较均匀半球采样与重要性采样的噪点。

完整结果、图表与验证结论见 [`outputs/REPORT.md`](outputs/REPORT.md)。

## 构建与运行

```bash
make run
make test
```

`make run` 会构建 C++ 程序、生成实验数据，并用 Python 标准库输出 PNG/SVG 图表和报告。
编译需要 C++17 编译器与 CMake；报告生成仅需 Python 3，不需要 NumPy/Matplotlib。

也可以单独运行：

```bash
./build/ibl_demo --output outputs
python3 tools/report.py --input outputs --output outputs
```

参数示例：

```bash
./build/ibl_demo --help
./build/ibl_demo --output outputs --spp 32 --frames 16 --roughness 0.25
```

## 方法

- 合成含 3 个高动态范围光源（最高约 `1.5e4`）的 HDR 环境图，并构建 5 级 mip。
- 每个 mip 建立 `luminance × solid-angle` 二维 CDF：行边缘 CDF + 行内列 CDF。
- 采样时选择 mip 后从该 mip 的 CDF 抽方向，使采样 PDF 与查询亮度一致。
- 渲染 GGX 金属球；均匀基线在法线半球均匀采样，重要性方法按环境亮度采样。
- 使用 12 个独立帧统计逐像素方差；以 mip0 纹素积分作为参考计算 RMSE。

## 主要输出

- `outputs/REPORT.md`：中文实验报告与结论。
- `outputs/direction_histogram.csv`：96×48 采样方向计数、密度与相对密度。
- `outputs/samples_per_pixel.csv`：逐像素尝试次数、有效 spp、mip LOD。
- `outputs/noise_by_pixel.csv`：逐像素方差与标准差。
- `outputs/mip_policy_variance.csv`：mip0 / roughness / lobe_footprint 的方差。
- `outputs/metrics.json`：全部机器可读指标和过采样判定。
- `outputs/env_map_linear.f32`：`int32 width, int32 height, float32 RGB...` 线性 HDR 数据。

默认实验的关键结果：高光邻域只占约 `1.29%` 球面立体角，却获得约 `82.56%` 重要性样本，
方向密度为均匀采样的约 `63.26×`；相同 192 次/像素尝试下，平均像素标准差从约 `23.07`
下降到 `6.20`（`3.72×`）。

## 目录

- `src/`：环境图、CDF 采样、mip、GGX 渲染、统计与输出。
- `tests/test_ibl.cpp`：PDF 归一化、方向集中度、mip 选择与确定性测试。
- `tools/report.py`：无依赖 PNG/SVG/Markdown 报告生成器。
- `outputs/`：复现生成的图像、CSV、JSON 与报告。
