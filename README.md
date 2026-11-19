# 20261120-c — 体积路径追踪 (Volume Path Tracing)

NumPy 实现的波前式体积路径追踪器，支持均质/异质参与介质，比较均匀步进与
指数（delta / ratio tracking）步进的透射率、噪点方差、步进成本与光照一致性。

## 运行

```bash
pip install numpy matplotlib
python3 -m src.run_all
```

约 25 秒完成，固定随机种子可复现。也可单独运行：

- `python3 -m src.experiments.exp1_transmittance` — 透射率-深度曲线
- `python3 -m src.experiments.exp2_noise` — 六估计器噪点/方差/效率
- `python3 -m src.experiments.exp3_render` — 烟柱与云雾渲染 + 每像素步数
- `python3 -m src.experiments.exp4_surface` — 体积/表面路径光照一致性

## 产物

- `artifacts/data/*.csv` — 透射率曲线、噪点方差、渲染统计、表面一致性指标。
- `artifacts/figures/fig1..fig5*.png` — 七张分析图。
- `REPORT.md` — 方法、数据与结论。
