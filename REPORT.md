# 体积路径追踪实验报告

本项目用 NumPy 实现了一个波前式（wavefront）体积路径追踪器，支持均质与异质
参与介质，并系统比较了均匀步进（uniform stepping）与指数步进（exponential /
Woodcock delta tracking、ratio tracking）两类采样策略。

## 代码结构

- `src/medium.py`：介质盒、三线性网格密度采样、均质介质的解析 Beer-Lambert。
- `src/fields.py`：过程化密度场——湍流烟柱 `smoke_plume` 与分层云雾 `cloud_fog`。
- `src/sampling.py`：四种透射率估计器
  （均匀 ratio、指数 ratio、指数 delta+RR、均匀 delta+RR）。
- `src/phase.py`：各向同性与 Henyey-Greenstein 相函数。
- `src/tracer.py`：体积路径追踪主循环，含 NEE 直接照明、表面路径、
  每像素步进统计；`render_surface_only` 提供无介质表面参考。
- `src/experiments/`：四个实验脚本，输出 CSV。
- `src/figures.py`、`src/run_all.py`：绘图与一键复现入口。

运行：`python3 -m src.run_all`（约 25 秒，固定随机种子，结果可复现）。

## 实验1：透射率随深度的曲线

均质 slab（sigma_t=1.2）中，沿光线在 20 个深度上各投 4 万条射线
（`artifacts/data/transmittance_curves.csv`）。

- 指数 ratio tracking 的均值与解析 Beer-Lambert `exp(-sigma_t d)` 完全吻合，
  无偏；均匀步进存在 O(dt^2) 的系统性偏低（dt=0.08）。
- 均匀 ratio 估计器的逐样本方差接近 0（确定性求积），
  但二进制 RR 估计器与指数法一样具有 `T(1-T)` 量级的方差。
- 图：`artifacts/figures/fig1_transmittance_depth.png`。

## 实验2：噪点方差与效率

在烟柱与均质 slab 上对 6 种估计器各投 16 万条射线、分 40 批
（`artifacts/data/noise_variance.csv`），统计偏差、批均值方差、MSE、
平均步数、墙钟时间与效率 `1/(MSE*time)`。

- 指数 ratio 在烟柱上效率最高（约为最佳均匀配置的 2.8 倍），且无偏差。
- 均质 slab 下指数 delta RR 效率达 2.5e7，远超所有均匀配置（约 5e5–1e6）。
- 均匀 ratio 靠缩小 dt 换偏差，步数与时间线性增长，效率停滞。
- 图：`artifacts/figures/fig2_noise_variance.png`。

## 实验3：烟柱与云雾的亮度分布与步进成本

对两个异质密度场分别用指数/均匀模式渲染（每像素 48 样本，
`artifacts/data/render_stats.csv`）。

- 两种步进模式给出一致的平均亮度（相对差 < 0.1%），验证实现自洽。
- 指数步进每像素平均约 2–3 次介质求值，均匀步进约 9–47 次；
  热力图（`fig3`/`fig4` 下半部）显示指数法步数随局部密度自适应，
  均匀法在整个盒内恒定。
- 亮度剖面（`fig3b`/`fig4b`）恢复出烟柱柱体与云雾团块结构。

## 实验4：体积路径与表面路径的光照一致性

相机与朗伯地面之间放置吸收型或散射型均质 slab
（`artifacts/data/surface_consistency.csv`）。

- 吸收介质下 `L_vol/L_surf = 0.3028`，与 Beer-Lambert `T=0.3012`
  的相对误差仅 0.5%。
- 纯散射（albedo=1）下内向散射能量比 `0.6988 = 1-T`。
- 吸收 + 散射能量和 `1.0016 ≈ 1`，满足能量守恒，
  说明体积散射路径与表面路径的光照在数学上一致。
- 图：`artifacts/figures/fig5_surface_consistency.png`。

## 结论

指数步进（delta/ratio tracking）无偏、步数随光学厚度自适应，
在等噪点预算下显著快于均匀步进；均匀步进实现简单、逐样本方差低，
但偏差与固定步长成本使其综合效率落后。两种方法在收敛后给出一致的
体积光照，且与 Beer-Lambert 解析解、表面路径能量守恒严格吻合。
