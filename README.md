# ATMOS — 大气散射天空实验室

一个无运行时依赖的 WebGL 2 大气光学实验台。它使用瑞利散射、米氏散射和
Beer–Lambert 透射计算太阳光颜色、天顶颜色和地平线颜色，并用太阳方向
光线步进绘制带自阴影的体积云与海面云影。

## 功能

- 瑞利相位函数与米氏 HG 相位函数
- 球面大气分层积分与太阳方向单位向量
- 太阳透射色温、直射透射率和水平面照度
- 0.25° 太阳高度角连续扫描（−6° 至 90°）
- 天顶色、地平线色与天空—地平线连续渐变
- 体积云密度场、太阳方向云内采样和海面投影云影
- 云量、云厚、光学厚度与云影遮蔽的实时输出
- 响应式观测面板、连续色带与系数—日照曲线

## 运行

```bash
npm run serve
```

打开 `http://127.0.0.1:4173`。

```bash
npm test
npm run validate
npm run capture
```

- `npm test` 验证颜色单调性、连续性与云影关系。
- `npm run validate` 生成 `artifacts/validation.md`、JSON、CSV 和 SVG 报告。
- `npm run capture` 生成默认、正午、日落和晴空截图。

## 模型

瑞利系数为 `βR = (0.0058, 0.0135, 0.0331) km⁻¹`，米氏系数为
`βM = 0.021 km⁻¹`，标高分别为 `8 km` 与 `1.2 km`。直射透射采用：

```text
T = exp[−(βR · HR · mR + βM · HM · mM)]
E = E0 · sin(h) · T
```

天空颜色通过沿视线对大气密度、相位函数和太阳透射率积分得到；GPU 渲染使用
相同参数，并在每个云样本沿太阳方向继续采样。云光学厚度与云影遮蔽为：

```text
τ = thickness · (0.16 + 3.15 · coverage)
shadow = 1 − exp(−τ)
```

## 验证结果

当前报告显示：

- 0.25° 相邻最大 sRGB ΔRGB：`0.067`（−1.25°）
- 天空到地平线 0.5° 最大相邻 ΔRGB：`0.024`
- 正午天顶蓝色占优，低太阳高度角地平线更暖
- 瑞利系数增大时直射日照单调下降、漫射天空上升
- 云量和厚度增大时光学厚度与云影遮蔽单调增强

详细数据见 `artifacts/validation.md` 和 `artifacts/atmosphere-validation.json`。

## 文件

- `src/atmosphere.js`：CPU 物理模型、颜色、日照与验证采样
- `src/sky-shader.js`：GPU 大气、太阳、海洋和体积云着色
- `src/renderer.js`：WebGL 2 渲染器
- `src/main.js`：交互、数据绑定和连续色带
- `scripts/validate.mjs`：报告生成
- `tests/atmosphere.test.js`：自动化断言
