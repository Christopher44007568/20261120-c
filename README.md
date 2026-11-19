# 各向异性球面高斯光照积分实验

本仓库实现一个可复现实验：用非负的各向异性球面高斯（ASG）混合拟合强方向性环境图，
用论文 _Anisotropic Spherical Gaussians_ 的闭式积分/乘积算子解析计算亮度，
并与实球谐（SH）和独立均匀球面 Monte Carlo 参考比较。

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 run_experiment.py
python3 -m unittest discover -s tests -v
```

快速验证可减少采样和拟合迭代：

```bash
python3 run_experiment.py --quick --counts 1,2,4,8 --output /tmp/asg_quick
```

## 实验定义

- 环境真值由 6 个 ASG 和一个常数 `0.10` 组成，最强峰值约 `14.1`。
- ASG：
  `G(w)=c*max(w.z,0)*exp(-lambda_u*(w.x)^2-lambda_v*(w.y)^2)`。
- 环境拟合：贪心初始化 + 有界非线性最小二乘，输出 `6N+1` 个参数。
- 光照核：各向异性 ASG，`sigma_u=0.14`、`sigma_v=0.24`。
- 亮度：`B(n)=integral L(w) K_n(w) dw`。
- ASG 路径：乘积折叠为单个 ASG，再调用 ASG 闭式积分。
- SH 路径：环境与光照核分别投影到实球谐，使用系数内积计算亮度。
- MC 参考：`2^20` 个均匀球面样本，输出分块标准误。

详细公式、误差表和逐高斯参数由实验自动写入 `artifacts/report.md`。

## 关键结果

默认数量扫描为 `1, 2, 3, 4, 6, 8, 12, 16`：

- 环境拟合 NRMSE 从 N=1 的 `52.3%` 降到 N=6 的近零，说明 6 个高斯足以覆盖
  真值环境的 6 个方向模态。
- N=1/2/4/6 的亮度 rel-L1 误差分别约为 `45.1% / 40.2% / 28.6% / 2.56%`。
- N=6 只用 37 个参数达到 `2.56%` 亮度误差；SH 需 12 阶、169 个系数达到
  `2.26%`，ASG 在相近质量下自由度数约少 4.6 倍。
- 8 阶 SH 的亮度 rel-L1 为 `11.3%`，且环境重建约 `12.7%` 的样本为负值；
  ASG 混合保持非负，没有负值振铃。
- 数量不足时表现为高光合并、能量扩散和质心方向偏差，而不是负值/振荡型方向性伪影。
- 拟合时间随数量快速增加：N=6 约 `90 ms`，N=16 约十余秒；逐法线解析积分从
  `0.46 ms` 增加到 `1.27 ms`。

## 输出

运行后 `artifacts/` 包含：

- `report.md`：中文实验报告、误差表、高斯参数和结论。
- `scan.csv`：数量、拟合耗时、积分耗时、环境误差、亮度误差与方向性指标。
- `gaussians_N*.csv`：每个数量下各高斯的中心、方位/仰角、宽度、各向异性、
  带宽、旋转、幅值与积分。
- `brightness_by_count.csv`：每个数量、每个测试法线的 ASG 与 MC 亮度。
- `brightness_N16.csv`：选定数量的逐法线亮度、MC 标准误和 SH8 对照。
- `sh_comparison.csv`：SH 4/6/8/10/12 阶误差。
- `error_vs_gaussians.png/svg`：重建误差随高斯数量下降曲线。
- `time_vs_gaussians.png/svg`：拟合与解析积分耗时随数量变化。
- `environment_reconstruction.png/svg`：环境真值及 N=1/4/8/16 重建。
- `brightness_reconstruction.png/svg`：亮度积分及绝对误差图。
- `brightness_profiles.png/svg`：固定仰角的亮度角向剖面。
- `results.json`：机器可读汇总。

## 实现说明

- `asg_experiment/model.py`：ASG 定义、球面采样与方向基。
- `asg_experiment/integration.py`：ASG 闭式积分/乘积、实 SH、MC 参考。
- `asg_experiment/fitting.py`：非负 ASG 混合拟合。
- `asg_experiment/metrics.py`：相对误差、能量偏差、峰值/质心方向误差。
- `asg_experiment/experiment.py`：完整实验编排与报告生成。
- `asg_experiment/plotting.py`：曲线和重建图。

ASG 乘积与积分是论文给出的近似闭式算子；最终亮度仍以独立 MC 参考校验。
