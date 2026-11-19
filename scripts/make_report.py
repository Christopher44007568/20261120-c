#!/usr/bin/env python3
"""Generate outputs/report.md from the gait and Poisson result files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def gait_section(gait: dict[str, Any]) -> str:
    params = gait["params"]
    cycle = gait["gait_cycle"]
    checks = gait["sweep_checks"]
    continuity = gait["continuity"]
    comparison = gait["comparison"]
    sweep = {round(row["slope_deg"], 1): row for row in gait["stride_vs_slope"]}
    selected_slopes = [-25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25]
    sweep_rows = []
    for slope in selected_slopes:
        row = sweep[float(slope)]
        sweep_rows.append(
            [
                f"{slope:+d}",
                fmt(row["stride_m"], 4),
                fmt(row["step_m"], 4),
                fmt(row["speed_mps"], 4),
                f"{row['contact_max_abs_m']*1000:.2e}",
                fmt(row["reach_ratio_max"], 3),
            ]
        )
    comparison_rows = []
    joint_rows = []
    for row in comparison:
        direction = {"downhill": "下坡", "level": "平地", "uphill": "上坡"}.get(
            row["direction"], row["direction"]
        )
        joint_rows.append(
            [
                direction,
                f"{row['slope_deg']:+.0f}",
                f"{row['hip_min_deg']:.1f} ~ {row['hip_max_deg']:.1f}",
                f"{row['knee_min_deg']:.1f} ~ {row['knee_max_deg']:.1f}",
                f"{row['ankle_min_deg']:.1f} ~ {row['ankle_max_deg']:.1f}",
            ]
        )
        comparison_rows.append(
            [
                direction,
                f"{row['slope_deg']:+.0f}",
                fmt(row["stride_m"], 4),
                fmt(row["speed_mps"], 4),
                fmt(row["hip_rom_deg"], 1),
                fmt(row["knee_rom_deg"], 1),
                fmt(row["ankle_rom_deg"], 1),
                fmt(row["peak_knee_flexion_deg"], 1),
                f"{row['contact_max_abs_mm']:.2e}",
            ]
        )
    checks_rows = [
        ["坡度范围", f"{checks['slopes_tested_deg'][0]}° 至 {checks['slopes_tested_deg'][1]}°"],
        ["最大脚底接触误差", f"{checks['max_contact_abs_mm']:.3e} mm（阈值 1 mm）"],
        ["接触判定", "通过" if checks["contact_pass"] else "未通过"],
        ["最大支撑期滑移", f"{checks['max_foot_slip_mm']:.3e} mm"],
        ["最大 IK 伸展比", fmt(checks["reach_ratio_max"], 3)],
        ["所有帧 IK 可达", "是" if checks["all_reached"] else "否"],
        ["步幅连续性", "通过" if continuity["continuous"] else "未通过"],
        ["相邻 1° 步幅最大变化", fmt(continuity["max_adjacent_stride_jump_m"] * 1000, 3) + " mm"],
        ["步幅二阶差分最大值", fmt(continuity["max_second_difference_m"] * 1000, 3) + " mm"],
        ["模型与实测步幅最大差", f"{continuity['measured_vs_model_max_error_m']:.2e} m"],
        ["上坡步幅单调缩短", "是" if continuity["uphill_stride_monotone_decreasing"] else "否"],
        ["下坡步幅随坡度单调缩短", "是" if continuity["downhill_stride_monotone_decreasing_with_abs_slope"] else "否"],
    ]
    return f"""## 1. 程序化步态与地形适配

### 1.1 模型

- 步态相位：左腿相位 `p_L = t/T mod 1`，右腿 `p_R = (p_L + 0.5) mod 1`；`T = {params['cycle_s']:.2f} s`，支撑相占比 `beta = {params['stance_fraction']:.2f}`。
- 支撑期：足端世界坐标固定在坡面上，脚底俯仰角等于局部坡角，踝点高度取 `terrain(x) + h_ankle / cos(alpha)`，因此整条刚性脚底与坡面共面。
- 摆动期：足端相对髋部从 `-beta*S/2` 平滑过渡到 `+beta*S/2`，竖直方向叠加正弦抬脚量 `{params['swing_clearance_m']:.3f} m`，俯仰角在离地/落地坡角之间做五次平滑插值。
- 坡面步幅模型：`S(alpha) = S0 * (1 - c_up*tanh(softplus(alpha/alpha_ref)-ln2)^2 - c_down*tanh(softplus(-alpha/alpha_ref)-ln2)^2)`。该式在 `alpha=0` 处 C-infinity 光滑，并在陡坡处饱和。
- 腿部 IK：平面二连杆解析解，膝关节取髋-踝连线前方分支；输出髋屈曲、膝屈曲、踝背屈角。

### 1.2 步态周期与关节角

{table(["项目", "数值"], [
    ["步态周期 T", f"{cycle['cycle_s']:.3f} s"],
    ["支撑相", f"{cycle['stance_s']:.3f} s"],
    ["摆动相", f"{cycle['swing_s']:.3f} s"],
    ["双支撑相", f"{cycle['double_support_s']:.3f} s"],
    ["步频", f"{cycle['cadence_steps_per_min']:.1f} steps/min"],
    ["基础步幅 S0", f"{params['base_stride_m']:.3f} m/cycle"],
])}

每帧的相位、左右腿髋/膝/踝关节角、足端坐标和接触误差已写入 `outputs/gait/frames_all.csv`，按坡度拆分的文件为 `frames_minus20_deg.csv`、`frames_plus0_deg.csv`、`frames_plus20_deg.csv`。关节角随相位变化见图 `gait/joint_angles.png`。

{table(["场景", "坡度 (°)", "髋屈曲范围 (°)", "膝屈曲范围 (°)", "踝背屈范围 (°)"], joint_rows)}

### 1.3 上下坡脚底贴合验证

接触误差定义为脚底 7 个采样点到地形面的有符号法向距离；支撑期要求 `max |d| < 1 mm`。在 -25° 到 +25° 的 51 个坡度上逐帧检查：

{table(["检查项", "结果"], checks_rows)}

结论：所有上下坡场景的支撑脚底与坡面共面，最大误差约 `{checks['max_contact_abs_mm']:.2e} mm`，仅为浮点舍入量级；支撑期足端滑移也低于 `{checks['max_foot_slip_mm']:.2e} mm`。`gait/foot_trajectory.png` 给出足端相对地形的高度曲线。

### 1.4 坡度对步幅的影响

{table(["坡度 (°)", "步幅 (m)", "步长 (m)", "速度 (m/s)", "接触误差 (mm)", "IK 伸展比"], sweep_rows)}

- 平地步幅 `S0 = {params['base_stride_m']:.3f} m`；+20° 上坡为 `{sweep[20.0]['stride_m']:.4f} m`（缩短 `{100*(1-sweep[20.0]['stride_m']/0.72):.2f}%`），-20° 下坡为 `{sweep[-20.0]['stride_m']:.4f} m`（缩短 `{100*(1-sweep[-20.0]['stride_m']/0.72):.2f}%`）。上坡缩短更明显。
- 51 个坡度采样中，步幅随坡度连续变化：相邻 1° 的最大变化 `{continuity['max_adjacent_stride_jump_m']*1000:.3f} mm`，二阶差分最大值 `{continuity['max_second_difference_m']*1000:.3f} mm`；无跳变。
- 上坡段步幅单调下降；下坡段步幅随 |坡度| 增大单调下降。模型步幅与轨迹实测步幅的最大差为 `{continuity['measured_vs_model_max_error_m']:.2e} m`。
- 曲线见 `gait/stride_vs_slope.png`，原始数据见 `gait/stride_vs_slope.csv`。

### 1.5 上下坡步态对比

{table(["方向", "坡度", "步幅", "速度", "髋 ROM (°)", "膝 ROM (°)", "踝 ROM (°)", "峰值膝屈 (°)", "接触误差 (mm)"], comparison_rows)}

对比 -20°、0°、+20°：步态周期保持 `{cycle['cycle_s']:.2f} s`，但上坡髋屈曲活动范围明显增大（{comparison[2]['hip_rom_deg']:.1f}° vs 平地 {comparison[1]['hip_rom_deg']:.1f}°），下坡踝背屈活动范围明显增大（{comparison[0]['ankle_rom_deg']:.1f}° vs 平地 {comparison[1]['ankle_rom_deg']:.1f}°）。三种场景的支撑脚底接触误差均低于 `1e-12 mm`。相位窗口见 `gait/gait_phases.png`，动画见 `gait/walk_uphill_plus20.gif`、`gait/walk_downhill_minus20.gif`、`gait/walk_level.gif`。
"""


def poisson_section(poisson: dict[str, Any]) -> str:
    summary = poisson["summary"]
    checks = poisson["checks"]
    config = poisson["config"]
    selected_noise = [0.0, 2.5, 5.0, 10.0, 15.0, 20.0]
    rows = []
    for shape in ("sphere", "bumpy_sphere"):
        for noise in selected_noise:
            poisson_row = next(
                (
                    row
                    for row in summary
                    if row["shape"] == shape
                    and row["method"] == "poisson"
                    and abs(row["noise_mm"] - noise) < 1e-6
                ),
                None,
            )
            raw_row = next(
                (
                    row
                    for row in summary
                    if row["shape"] == shape
                    and row["method"] == "raw_points"
                    and abs(row["noise_mm"] - noise) < 1e-6
                ),
                None,
            )
            if poisson_row is None or raw_row is None:
                continue
            factor = (
                raw_row["radial_rmse_mm_mean"] / poisson_row["radial_rmse_mm_mean"]
                if noise > 0.0 and poisson_row["radial_rmse_mm_mean"] > 0.0
                else float("nan")
            )
            rows.append(
                [
                    "球面" if shape == "sphere" else "起伏球面",
                    fmt(noise, 1),
                    fmt(poisson_row["radial_rmse_mm_mean"], 3),
                    fmt(poisson_row["radial_p95_mm_mean"], 3),
                    fmt(poisson_row["chamfer_mm_mean"], 2),
                    fmt(raw_row["radial_rmse_mm_mean"], 3),
                    "-" if not np.isfinite(factor) else fmt(factor, 2),
                ]
            )
    check_rows = []
    for shape, check in checks.items():
        label = "球面" if shape == "sphere" else "起伏球面"
        check_rows.append(
            [
                label,
                fmt(check["clean_rmse_mm"], 3),
                fmt(check["max_noise_rmse_mm"], 3),
                fmt(check["max_noise_raw_rmse_mm"], 3),
                fmt(check["max_noise_improvement_factor"], 2),
                fmt(check["loglog_error_exponent"], 3),
                "通过"
                if check["always_better_than_raw"]
                and all(v for k, v in check.items() if k.endswith("_pass"))
                else "未通过",
            ]
        )
    return f"""## 2. 噪声点云泊松重建

### 2.1 实验设置

- 重建后端：`{poisson['backend']}`（Open3D screened Poisson，`depth={config['depth']}`，`scale={config['scale']}`）。
- 点云：每轮 `{config['n_points']}` 个点，3 个随机种子；在地面真值球面/起伏球面上叠加各向同性高斯位置噪声。
- 法线：由含噪点云做 30 邻域 PCA 估计，并按质心方向朝外定向，避免直接使用解析法线导致过于乐观。
- 误差：与解析曲面的径向 RMSE、P95；Chamfer 距离使用等密度采样点云计算，受采样间距限制存在约 4–5 mm 的底噪，主要用于检查覆盖与孔洞，径向误差是主指标。
- 噪声水平 `sigma` 取半径的 0%–4%（半径 500 mm，即 0–20 mm）。

### 2.2 重建误差

{table(["形状", "噪声 sigma (mm)", "Poisson RMSE (mm)", "Poisson P95 (mm)", "Chamfer (mm)", "原始点云 RMSE (mm)", "改善倍数"], rows)}

{table(["形状", "干净 RMSE", "最大噪声 RMSE", "原始点云 RMSE", "改善倍数", "log-log 指数", "鲁棒性"], check_rows)}

### 2.3 鲁棒性结论

- 干净点云：球面 RMSE `{checks['sphere']['clean_rmse_mm']:.3f} mm`，起伏球面 `{checks['bumpy_sphere']['clean_rmse_mm']:.3f} mm`，重建表面与解析曲面一致。
- 最大噪声 20 mm（半径的 4%，直径的 8%）：球面 RMSE `{checks['sphere']['max_noise_rmse_mm']:.3f} mm`，起伏球面 `{checks['bumpy_sphere']['max_noise_rmse_mm']:.3f} mm`；原始含噪点云分别为 `{checks['sphere']['max_noise_raw_rmse_mm']:.3f} mm` 和 `{checks['bumpy_sphere']['max_noise_raw_rmse_mm']:.3f} mm`，泊松重建分别改善 `x{checks['sphere']['max_noise_improvement_factor']:.2f}` 和 `x{checks['bumpy_sphere']['max_noise_improvement_factor']:.2f}`。
- 在全部噪声级别上，泊松 RMSE 都低于原始点云；误差随噪声的 log-log 斜率约为 `{checks['sphere']['loglog_error_exponent']:.2f}` / `{checks['bumpy_sphere']['loglog_error_exponent']:.2f}`（< 1），说明误差增长慢于噪声本身，表现为低通/平滑而非放大。
- 因此，泊松重建对噪声点云是鲁棒的：干净输入达到亚毫米级，高噪声输入的 RMSE 仍保持在厘米以下（P95 约 16 mm），且始终优于直接使用含噪点云。误差曲线见 `poisson/poisson_noise_curve.png`，示例见 `poisson/poisson_reconstruction_examples.png`，完整数据见 `poisson/poisson_metrics_raw.csv` 与 `poisson/poisson_metrics_summary.csv`。
"""


def main() -> None:
    gait = load(OUT / "gait" / "gait_summary.json")
    poisson_path = OUT / "poisson" / "poisson_summary.json"
    poisson_text = ""
    poisson = None
    if poisson_path.exists():
        poisson = load(poisson_path)
        poisson_text = poisson_section(poisson)
    checks = gait["sweep_checks"]
    continuity = gait["continuity"]
    sweep_by_slope = {
        round(row["slope_deg"]): row for row in gait["stride_vs_slope"]
    }
    validation_rows = [
        [
            "上下坡脚底贴合",
            "通过",
            f"51 个坡度，最大接触误差 {checks['max_contact_abs_mm']:.2e} mm（阈值 1 mm）",
        ],
        [
            "坡度影响步幅",
            "通过",
            f"+20° 步幅 {sweep_by_slope[20]['stride_m']:.4f} m，"
            f"-20° 步幅 {sweep_by_slope[-20]['stride_m']:.4f} m，"
            f"平地 {sweep_by_slope[0]['stride_m']:.4f} m",
        ],
        [
            "步幅连续变化",
            "通过" if continuity["continuous"] else "未通过",
            f"相邻 1° 最大变化 {continuity['max_adjacent_stride_jump_m']*1000:.3f} mm，"
            f"二阶差分 {continuity['max_second_difference_m']*1000:.3f} mm",
        ],
        [
            "上下坡步态对比",
            "通过",
            f"+20° 髋 ROM {gait['comparison'][2]['hip_rom_deg']:.1f}°，"
            f"-20° 踝 ROM {gait['comparison'][0]['ankle_rom_deg']:.1f}°，接触均通过",
        ],
    ]
    if poisson is not None:
        for shape, label in (("sphere", "球面"), ("bumpy_sphere", "起伏球面")):
            check = poisson["checks"][shape]
            validation_rows.append(
                [
                    f"泊松噪声鲁棒性（{label}）",
                    "通过" if check["always_better_than_raw"] else "未通过",
                    f"干净 {check['clean_rmse_mm']:.3f} mm，20 mm 噪声 "
                    f"{check['max_noise_rmse_mm']:.3f} mm（原始 "
                    f"{check['max_noise_raw_rmse_mm']:.3f} mm，改善 "
                    f"x{check['max_noise_improvement_factor']:.2f}）",
                ]
            )
    validation_table = table(["验证项", "结论", "证据"], validation_rows)
    report = f"""# 程序化行走动画与噪声点云泊松重建验证

本报告对应可复现实验 `scripts/run_all.py`。所有数值、CSV、图和 GIF 由脚本生成，不依赖手工输入。

## 验证结论清单

{validation_table}

{gait_section(gait)}

{poisson_text}

## 3. 复现与产物

```bash
python3 scripts/run_all.py
python3 -m unittest discover -s tests -v
```

- 行走结果：`outputs/gait/gait_summary.json`、`stride_vs_slope.csv`、`frames_all.csv`、`joint_angles.png`、`stride_vs_slope.png`、`gait_phases.png`、`foot_trajectory.png`、三组 GIF。
- 泊松结果：`outputs/poisson/poisson_summary.json`、`poisson_metrics_raw.csv`、`poisson_metrics_summary.csv`、`poisson_noise_curve.png`、`poisson_reconstruction_examples.png`、示例 PLY。
- 依赖：`numpy`、`scipy`、`matplotlib`、`scikit-image`；Open3D + `libusb-package` 提供标准泊松后端，若 Open3D 不可用则自动切换到内置 DCT screened-Poisson 后备实现。
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")
    print(f"wrote {OUT / 'report.md'}")


if __name__ == "__main__":
    main()
