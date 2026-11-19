# 路径追踪空间与时域联合去噪

该项目实现一个不依赖第三方库的 C++17 路径追踪器与时空联合去噪器，用于验证：

- 低样本（2 spp）路径追踪噪声的空间/时域联合抑制；
- 基于法线、深度和历史缓冲的双边滤波及边缘保持；
- 相机静止时的收敛、低方差与边缘重影检查；
- 相机运动时的历史重投影、失配降权与鬼影定位；
- 低样本图对比 256 spp 参考图的 MSE；
- 去噪前后的噪点方差、鬼影像素占比和历史失配比例。

## 构建与运行

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/pt_denoise --output artifacts
python3 tools/finalize.py artifacts
```

快速烟雾测试：

```bash
./build/pt_denoise --quick --spp 2 --output artifacts/quick
python3 tools/finalize.py artifacts/quick
```

完整运行约数秒。默认配置为 `160x120`、`2 spp`、`256 spp` 参考、静止
`40` 帧、运动 `16` 帧。可用 `--width`、`--height`、`--static-frames`、
`--moving-frames`、`--spp`、`--ref-spp` 和 `--convergence-mse` 覆盖。

## 去噪流程

1. 路径追踪主射线生成颜色，同时写入世界法线、世界坐标、视深度和物体 ID。
2. 空间双边核使用 3x3 邻域，联合颜色、法线、相对深度和物体 ID 权重，避免跨
   几何边缘平均。
3. 当前像素世界坐标通过上一帧相机反投影；深度、法线、物体 ID 一致时才使用历史。
4. 时域权重为 `confidence * color_gate`。颜色残差使用高斯门控，残差越大历史权重
   越低；几何失配直接丢弃历史。
5. 有效历史与当前空间滤波结果混合；混合权重随历史有效长度增长，但上限为 0.95。
6. 实验另外运行“无几何/颜色保护”的历史累积作为鬼影对照。

## 指标定义

- **时域噪点方差**：静止序列中逐像素亮度对时间求方差，再对全图取平均。
- **收敛帧**：去噪逐帧 MSE 首次不超过最终稳态 MSE 的 115%，并连续 4 帧保持。
- **残差亮度方差**：去噪图与高样本参考图之间的亮度 MSE。
- **鬼影像素**：去噪亮度误差大于 `max(0.055, 局部原始误差 + 0.018)`。
- **历史不匹配**：重投影越界，或物体 ID、法线、相对深度不一致，或几何一致但
  当前/历史颜色差超过颜色门控阈值。
- **快速运动区域**：屏幕位移不小于 0.75 px/帧、存在局部速度突变，或靠近新暴露
  图像边界；随后膨胀 1 像素。

输出：

- `artifacts/metrics.json`：全部原始指标；
- `artifacts/report.md`：自动生成的结论和图像索引；
- `artifacts/static_convergence.csv`：静止逐帧 MSE；
- `artifacts/moving_history.csv`：运动逐帧历史失配；
- `artifacts/moving_ghost_pixels.csv`：鬼影像素坐标、速度及快速运动标记；
- `artifacts/images/*.ppm` 与 `artifacts/png/*.png`：渲染、去噪和掩码图。

## 代码结构

- `src/scene.h`：解析几何、材质、相机投影与反投影；
- `src/renderer.*`：路径追踪、直接光采样和 G-buffer 输出；
- `src/denoiser.*`：空间双边滤波、历史重投影、失配门控与时域累积；
- `src/metrics.*`：MSE、时序方差、边缘/鬼影掩码和收敛检测；
- `src/main.cpp`：静止/运动实验、对照消融、CSV/JSON 输出；
- `tests/unit_tests.cpp`：相机往返、边缘保持、方差下降、失配降权和收敛检测；
- `tools/finalize.py`：PPM 转 PNG 并生成 Markdown 报告。

运动测试使用静态几何和横向平移相机。参考图按最终帧相机渲染；历史失配和快速
运动比例在运动序列上统计。无保护历史仅用于量化鬼影基线，不属于最终去噪结果。

