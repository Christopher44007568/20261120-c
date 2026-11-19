# 20261120-c — 程序化云层 + 早 Z 边界验证

纯 C（C11，仅 libm）实现，无第三方依赖。`make` 生成 `clouds` 与 `earlyz`。

## 云层（`./clouds`）

- **密度场**：`density = remap(FBM(x,y,2z), coverage)` 经 Worley 侵蚀后乘
  **高度衰减** `falloff(h)`（`src/cloud.c`）。积云：低处快速 ramp、顶部圆化；
  层云：平顶、上下软边。
- **体积光照**（`src/render.c`）：沿视线 raymarch，每步
  `T *= exp(-σ·d·Δs)`（Beer-Lambert），并向太阳方向次级步进累计光学厚度
  `τ_l`，光照 = `环境项 + 太阳·HG相函数(g=0.55)·exp(-τ_l)`。
  `exp(-τ_l)` 即云的自阴影/云影来源；`out/*_shadow.png` 为地面云影图。
- **输出**：`out/{cumulus,stratus}_sky.png`（天空渲染）、
  `out/{cumulus,stratus}_shadow.png`（地面云影），stdout 打印覆盖率、
  厚度、高度剖面与渲染耗时。

## 早 Z / overdraw（`./earlyz`）

逐片元模拟深度管线，统计着色调用次数并与解析值对拍（7 组用例全 PASS）。
早 Z 失效边界：透明物体不写深度（pass 内互相无法剔除）、绘制顺序
back-to-front、alpha-test/discard 强制 late-Z、shader 写深度强制 late-Z。
