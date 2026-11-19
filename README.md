# LTC 面光源连续性实验台

一个无构建依赖的浏览器实验台，用标准 GGX-LTC 拟合表渲染**矩形**与**圆盘**面光源，并对解析积分、面积蒙特卡洛采样、粗糙度连续性、采样方向分布和输入网格拓扑做可复现验收。

## 快速开始

```bash
npm start
# 打开 http://127.0.0.1:8080
```

重新生成回归数据、PNG 快照、矩阵 CSV、方向 CSV 与连续性 SVG：

```bash
npm test
npm run validate
```

> 页面通过 `fetch` 读取 `src/ltc-data.bin`，因此请使用本地 HTTP 服务，不要直接双击 `index.html`。

## 页面内容

- **矩形的 LTC / MC 对照**：左侧为无噪声解析积分，右侧为有限样本面积采样。
- **圆盘的 LTC / MC 对照**：同一面积、同一中心的 128 边圆盘，面积误差约 0.04%。
- **粗糙度渐变条**：`α = 0.045 → 0.82` 的分段线性渐变，用于检查高光是否平滑伸缩。
- **矩阵曲线**：固定 `N·V = 0.7` 时 `M⁻¹` 的 `a/b/c/d` 随粗糙度连续变化。
- **采样方向分布**：四档粗糙度的切平面投影，显示 LTC 采样瓣由窄到宽。
- **亮度误差曲线**：1–1024 spp 下解析解与采样估计的相对误差。
- **输入验收**：合法闭合盒体与缺失顶面的非水密网格并排对照。

控制栏可调固定粗糙度、spp（4/12/32/128）和随机种子；报告与矩阵可直接从浏览器导出。

## 方法

标准 LTC 表按 `(roughness, sqrt(1-N·V))` 双线性采样。单个矩阵按 GLSL 列主序存储为：

```text
M⁻¹ = [ a  0  c ]
      [ 0  1  0 ]
      [ b  0  d ]
```

矩形使用标准多边形线积分；圆盘用 128 边内接多边形，边缘向量形式因子逐边求和并做地平线裁剪。`ltcEvaluatePolygon` 的返回值就是该 LTC 瓣在面光源上的积分能量。

采样侧使用分层面积蒙特卡洛。对均匀面积采样点 `q`：

```text
pdf_area = 1 / A
pdf_ω    = pdf_area · r² / cosθ_L
E_MC     = 1/N · Σ D_LTC(ω_i) / pdf_ω
```

其中 `D_LTC(ω)` 由 `M⁻¹`、矩阵行列式和逆变换后的余弦瓣密度得到。解析与采样使用**同一个拟合 LTC 瓣**，因此误差图主要暴露解析积分近似和有限样本噪声，而不是两种不同 BRDF 的模型差异。

粗糙度轴上的解析矩阵不做最近邻查表，而是对整张 64×64 表做连续双线性插值。页面同时保留最近邻量化作为反例。

## 实测结果

`npm run validate` 在 360×220、32 spp、固定 `α = 0.12` 下生成以下结果：

| 项目 | 矩形 | 圆盘 |
| --- | ---: | ---: |
| 高光形状 IoU | 0.815 | 0.857 |
| 整图相对亮度偏差 | 2.08% | 4.44% |
| 1024 spp 探针亮度误差 | 0.093% | 0.101% |

粗糙度连续性：

| 指标 | 数值 |
| --- | ---: |
| 断点 `α = 0.14 / 0.32 / 0.58` 的连续最大跳变 | 0.0783% |
| 最近邻 8 级量化反例最大跳变 | 44.00% |
| 257 点矩阵扫描最大相邻差 | 约 0.0054 |

输入验收：

| 样例 | 顶点 | 三角面 | 边界边 | Euler χ | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| `fixtures/valid-scene.json` | 8 | 12 | 0 | 2 | PASS |
| `fixtures/nonwatertight-scene.json` | 8 | 10 | 4 | 1 | REJECT |

## 生成产物

```text
artifacts/validation-report.json     完整数值报告与逐项检查
artifacts/ltc-matrix-sweep.csv       1001 行 LTC 矩阵连续扫描
artifacts/sampling-directions.csv    4 档粗糙度 × 512 个方向
artifacts/ltc-continuity.svg         矩阵连续曲线与断点标记
artifacts/rect-ltc.png               矩形解析高光
artifacts/rect-mc-32spp.png          矩形采样高光
artifacts/disk-ltc.png               圆盘解析高光
artifacts/disk-mc-32spp.png          圆盘采样高光
artifacts/roughness-gradient-ltc.png 粗糙度渐变解析图
artifacts/roughness-gradient-mc-32spp.png
artifacts/acceptance.txt             命令行验收摘要
```

## 逐步验收

1. **启动与初始状态**：`npm start`，打开 `http://127.0.0.1:8080`。顶部应为绿色“输入合法”，网格状态为 `0 boundary edges · χ 2`。
2. **矩形形状**：保持 `α = 0.12`，矩形解析图高光为圆角方形；切换 4→128 spp，MC 图颗粒减少、相对亮度偏差收敛。
3. **圆盘形状**：同一行右侧解析图高光为圆形；与矩形使用相同面积与中心，便于直接比较轮廓。
4. **粗糙度渐变**：观察渐变条。高光随 `α` 增大平滑变宽；状态胶囊应显示“边界零跳变”，连续跳变小于 1%。
5. **矩阵曲线**：`a/b/c/d` 四条线穿过 `α = 0.14/0.32/0.58` 虚线时无台阶；红色最近邻量化条明显高出一个数量级以上。
6. **方向分布**：四个圆盘中的点云随 `α` 由集中变宽；外圈是切线/地平线，点的透明度对应 `cosθ`。
7. **误差收敛**：误差图横轴为 spp 对数。1024 spp 的矩形/圆盘探针误差均小于 0.2%。
8. **网格门禁**：点击“非水密”样例，状态条变红并报告 4 条边界边、`χ = 1`；再点击“合法输入”恢复 PASS。
9. **命令行复核**：
   ```bash
   npm test && npm run validate
   ```
   预期最后为 `status: PASS (8/8)`，并生成上表中的全部产物。

## 文件结构

```text
index.html / styles.css        实验台界面
src/ltc.js                     LTC 表、矩阵、多边形积分、采样密度
src/render.js                  表面遍历、渐变场、像素比较、连续性探针
src/analysis.js                方向分布与误差收敛统计
src/mesh.js                    水密性、非流形、绕序、Euler 特征校验
src/charts.js                  矩阵/误差/方向/网格画布
src/app.js                     交互、渲染调度与导出
src/ltc-data.bin               three.js r170 的 64×64×2 拟合表
fixtures/                      合法与非水密输入样例
tools/build-ltc-data.mjs       从固定上游版本重建矩阵二进制
tools/validate.mjs             无浏览器端验收并生成 artifacts
test/core.test.mjs             数学、连续性、形状、误差与网格回归
```

## 说明与边界

- `src/ltc-data.bin` 来自 three.js `r170` 的 `RectAreaLightTexturesLib.js`，原始拟合与算法见 Heitz et al., *Real-Time Polygonal-Light Shading with Linearly Transformed Cosines*, ACM TOG 35(4), 2016。许可与来源见 `THIRD_PARTY_NOTICES.md`。
- 圆盘采用 128 边多边形，截图已与连续面积采样的圆盘对照；面积误差约 `4.0 × 10⁻⁴`（0.04%）。
- 页面展示的是同一 LTC 瓣的解析积分与抽样积分，目标是隔离“解析 vs 采样”的噪声和亮度误差；不是对完整路径追踪场景的 GGX 真值复现。
- 所有计算均在 CPU/JavaScript 中完成，不依赖 WebGL 或第三方运行时。
