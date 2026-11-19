# 解析面光源：胶囊体、圆盘与矩形

本项目计算三类朗伯面光源在带挡板场景中的解析辐照度，并用固定种子的
Monte Carlo 面积采样独立校验逐像素照度、5%–95% 半影宽度和总通量。

## 运行

```bash
make verify
```

`make verify` 会编译 C++ 计算核心，使用相同参数独立运行两次，比较全部
CSV/PNG 的 SHA-256、误差指标与通量指标，并把结果发布到 `artifacts/`。

可覆盖默认样本数：

```bash
make verify PIXEL_SAMPLES=32768 FLUX_SAMPLES=1000000 \
  PENUMBRA_SAMPLES=65536
```

只运行一次并生成到临时目录：

```bash
mkdir -p build
make build/area_lights
./build/area_lights --out build/run \
  --pixel-samples 32768 --flux-samples 1000000 \
  --penumbra-samples 65536
python3 scripts/finalize.py build/run
```

## 主要文件

- `src/area_lights.cpp`：解析积分、PCG32 Monte Carlo、场景与 CSV 生成。
- `scripts/finalize.py`：PNG 编码和中文报告生成。
- `scripts/verify.py`：双运行可复现性检查与产物发布。
- `artifacts/report.md`：结论、参数表、误差表和图像。
- `artifacts/data/pixel_validation.csv`：每像素照度、可见比例与半影宽度。

解析模型、阈值、参数和全部验证结果见 `artifacts/report.md`。
