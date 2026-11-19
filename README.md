# Mesh UV Island Segmentation Study

可复现实验：比较“法线 + 测地距离”聚类与谱聚类的 UV 岛分割质量，用纹理拉伸验证分割收益，并给出软阴影固定步长光线步进的成本/半影精度权衡。

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.run_experiment
```

若系统的 Python 缺少 `ensurepip`（本工作区初始环境即如此），可先执行：

```bash
curl -sS -L https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
python3 -m venv --without-pip .venv
.venv/bin/python /tmp/get-pip.py
```

实验输出在 `artifacts/`，完整中文结果见 [REPORT.md](REPORT.md)。

## Outputs

- `artifacts/metrics.csv` / `metrics.json`：岛数、内部切割长度、总岛边界、接缝法线跃变、纹理拉伸。
- `artifacts/segmentation_*.png`：两种模型的着色岛与接缝。
- `artifacts/uv_islands_*.png`：打包后的 UV 岛。
- `artifacts/stretch_*.png`：平面投影与两种分割的纹理拉伸热图。
- `artifacts/soft_shadow_tradeoff.png` / `soft_shadow.json`：步长、步进次数、半影宽度与可见性误差。

## Scope

所有数值来自仓库内的合成高度场实验。纹理拉伸使用面积加权的 L2 奇异值指标，1.0 表示局部等距；两种分割使用相同的逐岛平面 UV 展开器，以隔离分割本身的影响。
