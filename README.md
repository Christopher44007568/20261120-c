# 程序化行走动画与噪声点云泊松重建

一个可复现的运动学实验：用步态相位和平面二连杆 IK 生成脚步轨迹，令脚底俯仰角适配地形坡度，验证上下坡脚底贴合，并分析坡度对步幅的影响；随后用带噪声的合成点云评估 screened Poisson 重建的鲁棒性。

## 快速开始

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run_all.py          # 行走分析 + 泊松基准 + outputs/report.md
python3 -m unittest discover -s tests -v
```

快速冒烟运行：

```bash
python3 scripts/run_all.py --quick
```

完整泊松扫噪约需 2 分钟；行走分析、绘图和 3 组 GIF 约需 15 秒。

## 目录

- `walker/`：地形、二连杆 IK、步态相位、足端轨迹、接触/步幅指标、绘图与动画。
- `poisson_recon/`：点云采样、PCA 法线、Open3D Poisson 后端、DCT screened-Poisson 后备、噪声基准。
- `scripts/`：`run_walking.py`、`run_poisson.py`、`run_all.py`、`make_report.py`。
- `tests/`：接触、连续性、IK 可达性、泊松降噪的单元测试。
- `outputs/`：生成的 JSON/CSV/PNG/GIF/PLY 和中文报告 `report.md`。

## 模型要点

- 步态周期 `T=1.0 s`，支撑相 `beta=0.62`，左右腿相位差 `0.5`。
- 支撑足固定于坡面，脚底俯仰角等于局部坡角，踝高取 `h_ankle/cos(alpha)`；因此刚性脚底与平面坡共面。
- 摆动足采用五次平滑横向插值和正弦抬脚，离地/落地俯仰角与坡面连续衔接。
- 步幅模型 `S(alpha)` 在零坡度处光滑，上坡缩短强于下坡，并在陡坡处饱和。
- IK 输出髋屈曲、膝屈曲、踝背屈角；支撑期同时检查脚底 7 点有符号接触误差和足端滑移。
- 泊松基准：18k 点、3 个随机种子、0–20 mm 位置噪声；法线由含噪点云 PCA 估计并朝外定向；以解析曲面径向 RMSE/P95 为主指标，Chamfer 为覆盖检查。

## 验证口径

- 脚底贴合：支撑期 `max |signed distance| < 1 mm`。
- 步幅连续：相邻 1° 坡度步幅变化 `< 10 mm`，二阶差分 `< 1 mm`。
- 泊松鲁棒：干净输入 RMSE 亚毫米；高噪声下误差低于原始点云且 log-log 指数 `< 1.25`。

依赖 `numpy`、`scipy`、`matplotlib`、`scikit-image`；`open3d` 提供标准 Poisson 后端，Linux 下由 `libusb-package` 预加载 `libusb`；Open3D 不可用时自动退回内置 DCT screened-Poisson。
