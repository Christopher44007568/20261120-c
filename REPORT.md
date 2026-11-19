# Ashikhmin 天鹅绒/布料 BRDF 实现与验证报告

纯 Python 标准库实现（无第三方依赖）。运行 `python3 run_all.py` 重新生成全部结果到 `out/`。

## 模型

- `src/brdf.py:36` `velvet_isotropic` — Ashikhmin & Premoze (2007) 天鹅绒模型：
  `fr = (28/23π) ρ (1−Rs) p(h) / (4(cosθi + cosθo − cosθi cosθo))`，`p(h) = 1/(π(1+a θh²))`。
- `src/brdf.py:81` `velvet_aniso` — 各向异性纤维版本：纤维沿切向 `t`，微法线集中在垂直于纤维的平面内，
  半向量分布 `p(h) = K / (1 + a·tan²γ)`，`tan²γ = (h·t)²/(1−(h·t)²)`，`K` 数值归一化使 `p` 在上半球积分为 1；
  保留 Ashikhmin 逆反射分母以保证能量守恒。
- `src/brdf.py:110` `ggx_aniso` — 各向异性 GGX（Walter et al.，Smith G + Schlick Fresnel），用于对比。
- `src/brdf.py:135` `sample_velvet_aniso` — 对 `p_aniso(h)` 拒绝采样半向量并反射得到出射方向，PDF 为 `p(h)/(4 wi·h)`。

## 验证结果（`python3 src/validate.py`，全部 PASS）

**1. 能量守恒**（`out/energy.csv`）：半球反射率全部 ≤ 1

| θi | velvet_iso | velvet_aniso | ggx_aniso |
|----|-----------|--------------|-----------|
| 0° | 0.043 | 0.056 | 0.245 |
| 60° | 0.033 | 0.040 | 0.273 |
| 80° | 0.028 | 0.036 | 0.441 |

**2. 旋转纤维 → 高光跟随**（`out/rotation.csv`）：高光方位角随纤维角单调旋转（0°→180°、45°→−127°、
90°→0°、135°→127°，跨度 324°），确认各向异性方向与切向（纤维方向）一致。
渲染图 `out/rotate_velvet_{000,045,090,135}.png`：光泽带随纤维角从竖直→对角→水平→反对角旋转。

**3. 采样方向分布**（`out/sampled_directions.csv`，`out/sampling_distribution.png`）：
8 万余采样方向，分布沿垂直纤维方向拉长（纤维沿 x 时亮带在 y 方向展开），并偏向光源方位（逆反射特性）。

**4. 掠射角亮度对比**（`out/grazing_comparison.csv`，`out/grazing_comparison.png`，黄=velvet，蓝=GGX）：
GGX 因 Fresnel 在掠射角急剧增亮（85° 时反射率 0.51），Ashikhmin 天鹅绒保持低而平缓（85° 时 0.036），
比值从正入射的 0.23 降至 85° 的 0.071。渲染对比 `out/grazing_{velvet,ggx}_{000,090}.png`：
掠射光下 GGX 出现明亮锐利的新月形高光，天鹅绒为柔和宽泛的光泽，且两者高光都随纤维旋转 90° 而改变形态。

## 文件

- `src/brdf.py` — BRDF 模型与采样
- `src/validate.py` — 数值验证（能量/旋转/采样/掠射角）
- `src/render.py` — 球体渲染器
- `src/pngutil.py` — PNG 输出
- `run_all.py` — 一键运行
