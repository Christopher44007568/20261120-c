# MSAA 透明裁剪实验（Vulkan）

针对细叶与镂空金属网的多重采样透明裁剪对照实验：同一套几何与透明度纹理，
对照**固定阈值丢弃（discard）**与 **alpha-to-coverage（A2C）**两条管线，
采样档 1 / 4 / 8，离屏渲染（无窗口依赖，lavapipe/硬件驱动均可运行）。

## 构建与运行

```bash
./build.sh            # 编译着色器 + 主程序（依赖 tools/sysroot 内的 glslang 与 Vulkan 头）
./msaa_cutout_lab artifacts
```

设备不支持的采样档会在报告与终端中明确显示 `NOT SUPPORTED` 并跳过。

## 实验内容

- **共用几何与纹理**：512x512 程序化 RGBA 图集（细叶簇 / 穿孔金属网 / 解析直边 / 纯色块），
  两条管线渲染完全相同的场景。线性过滤让边缘片元获得中间 alpha，A2C 才能转化为部分样本掩码。
- **相机慢速扫描**：96 帧轨道扫过穿孔边缘与近水平叶片轮廓，逐帧输出 ROI 亮度与
  逐像素帧间差（flicker）。
- **逐样本读取**：计算着色器 `texelFetch(sampler2DMS, pixel, sample)` 直接从未解析的
  MSAA 附件读取，显示选定像素每个样本是否被写入（1x 档走图像拷贝路径）。
- **静止帧边缘偏差**：图集内含解析已知直边（alpha 在 v=0.75 处阶跃），投影为近水平线，
  逐像素对比解析覆盖率与解析后亮度，输出 meanAbs / RMS / max。
- **四分之一透明度测试块**：均匀 alpha=0.25 色块，验证 A2C 解析色值约等于
  0.25*前景 + 0.75*背景，discard 下应完全等于背景。
- **遮挡验证**：不透明红色挡板位于测试块前方，逐样本检查被遮样本不透出。

## 输出（artifacts/）

- `report.txt` — 设备与采样档支持、逐样本写入掩码、边缘偏差表、色值/遮挡验证结论
- `luminance_{1,4,8}x.csv` — 逐帧 ROI 亮度与 flicker
- `luminance_plot.png` / `flicker_plot.png` — 波动曲线（图例映射见 report.txt 末尾）
- `frame_{discard,a2c}_Nx_f###.png` — 扫描序列代表帧
- `static_{discard,a2c}_Nx.png` — 静止分析帧

## 参考结果（llvmpipe, Vulkan 1.4）

边缘偏差 meanAbs：discard 0.0533（三档相同，MSAA 无法平滑纹理 alpha 边）；
A2C 0.0747(1x) / 0.0226(4x) / 0.0150(8x)。flicker 随采样数单调下降。
四分之一块与遮挡验证全部 PASS。

## 文件

- `src/main.cpp` — 实验主体（渲染器、场景、分析）
- `src/vk.h` — Vulkan 基础封装；`src/util.h` — 数学/PNG/图集生成
- `src/probe.cpp` — 设备采样能力探针
- `shaders/` — cutout.vert / cutout.frag（两种模式）/ extract.comp（逐样本提取）
