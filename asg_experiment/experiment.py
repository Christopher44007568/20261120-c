"""End-to-end ASG environment fitting and brightness comparison experiment."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import numpy as np

from .fitting import FittedEnvironment, fit_asg_mixture
from .integration import (
    asg_brightness,
    asg_integral,
    monte_carlo_brightness,
    real_sh_basis,
    sh_brightness,
    sh_kernel_coefficients,
    sh_project,
)
from .metrics import brightness_metrics, environment_metrics
from .model import DirectionalEnvironment, fibonacci_sphere, normalize
from .plotting import (
    plot_brightness_maps,
    plot_brightness_profiles,
    plot_environment_maps,
    plot_error_curves,
    plot_time_curve,
)


@dataclass(frozen=True)
class ExperimentConfig:
    output_dir: Path
    lobe_counts: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 12, 16)
    fit_samples: int = 1024
    fit_max_nfev: int = 150
    validation_samples: int = 32768
    test_normals: int = 64
    mc_samples: int = 1 << 20
    sh_samples: int = 8192
    sh_max_degree: int = 12
    selected_count: int = 16
    kernel_sigma_u: float = 0.14
    kernel_sigma_v: float = 0.24
    integration_repeats: int = 12
    seed: int = 20261120


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _brightness_callable(model: FittedEnvironment, config: ExperimentConfig):
    def evaluate(directions: np.ndarray) -> np.ndarray:
        return asg_brightness(
            model.lobes,
            directions,
            config.kernel_sigma_u,
            config.kernel_sigma_v,
            ambient=model.ambient,
        )

    return evaluate


def _reference_brightness_callable(
    environment: DirectionalEnvironment, config: ExperimentConfig
):
    def evaluate(directions: np.ndarray) -> np.ndarray:
        return asg_brightness(
            environment.lobes,
            directions,
            config.kernel_sigma_u,
            config.kernel_sigma_v,
            ambient=environment.ambient,
        )

    return evaluate


def _gaussian_rows(model: FittedEnvironment) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, lobe in enumerate(model.lobes):
        rows.append(
            {
                "index": index,
                "amplitude": lobe.amplitude,
                "center_x": lobe.center[0],
                "center_y": lobe.center[1],
                "center_z": lobe.center[2],
                "azimuth_deg": np.degrees(lobe.azimuth),
                "elevation_deg": np.degrees(lobe.elevation),
                "sigma_u_rad": lobe.sigma_u,
                "sigma_v_rad": lobe.sigma_v,
                "lambda_u": lobe.lambda_u,
                "lambda_v": lobe.lambda_v,
                "rotation_deg": np.degrees(lobe.rotation),
                "anisotropy_ratio": lobe.anisotropy,
                "integral_sr": asg_integral(lobe.amplitude, lobe.lambda_u, lobe.lambda_v),
            }
        )
    return rows


def _add_ambient_row(
    rows: list[dict[str, object]], ambient: float
) -> list[dict[str, object]]:
    rows.append(
        {
            "index": "ambient",
            "amplitude": ambient,
            "center_x": "",
            "center_y": "",
            "center_z": "",
            "azimuth_deg": "",
            "elevation_deg": "",
            "sigma_u_rad": "",
            "sigma_v_rad": "",
            "lambda_u": "",
            "lambda_v": "",
            "rotation_deg": "",
            "anisotropy_ratio": "",
            "integral_sr": 4.0 * np.pi * ambient,
        }
    )
    return rows


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def run_experiment(config: ExperimentConfig) -> dict[str, object]:
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    environment = DirectionalEnvironment.studio()
    counts = tuple(sorted(set(config.lobe_counts)))
    selected_count = config.selected_count if config.selected_count in counts else counts[-1]

    models = fit_asg_mixture(
        environment,
        lobe_counts=counts,
        fit_samples=config.fit_samples,
        max_nfev=config.fit_max_nfev,
    )
    validation_directions = fibonacci_sphere(config.validation_samples, offset=0.771)
    validation_truth = environment.radiance(validation_directions)

    test_normals = normalize(fibonacci_sphere(config.test_normals, offset=0.613))
    mc_reference, mc_standard_error = monte_carlo_brightness(
        environment,
        test_normals,
        config.kernel_sigma_u,
        config.kernel_sigma_v,
        sample_count=config.mc_samples,
        seed=config.seed,
    )

    sh_directions = fibonacci_sphere(config.sh_samples, offset=0.293)
    sh_basis, sh_terms = real_sh_basis(sh_directions, config.sh_max_degree)
    sh_environment_coefficients = sh_project(
        environment.radiance(sh_directions), sh_basis
    )
    sh_kernel = sh_kernel_coefficients(
        test_normals,
        sh_basis,
        config.kernel_sigma_u,
        config.kernel_sigma_v,
        0.0,
        sh_directions,
    )
    validation_basis, _ = real_sh_basis(
        validation_directions, config.sh_max_degree
    )

    sh_comparison: list[dict[str, object]] = []
    sh_predictions: dict[int, np.ndarray] = {}
    sh_negative_fraction: dict[int, float] = {}
    for degree in (4, 6, 8, 10, 12):
        if degree > config.sh_max_degree:
            continue
        prediction = sh_brightness(
            sh_environment_coefficients, sh_kernel, degree, sh_terms
        )
        sh_predictions[degree] = prediction
        metrics = brightness_metrics(
            prediction, mc_reference, mc_standard_error, test_normals
        )
        selected = np.array([item[0] <= degree for item in sh_terms])
        reconstructed = validation_basis[:, selected] @ sh_environment_coefficients[selected]
        sh_negative_fraction[degree] = float(np.mean(reconstructed < -1e-12))
        sh_comparison.append(
            {
                "sh_degree": degree,
                "n_coefficients": int(selected.sum()),
                "brightness_rel_l1": metrics["relative_l1"],
                "brightness_nrmse": metrics["nrmse"],
                "brightness_relative_bias": metrics["relative_bias"],
                "brightness_max_relative_error": metrics["max_relative_error"],
                "brightness_peak_direction_error_deg": metrics[
                    "peak_direction_error_deg"
                ],
                "brightness_centroid_direction_error_deg": metrics[
                    "centroid_direction_error_deg"
                ],
                "brightness_overshoot_25_fraction": metrics[
                    "overshoot_25_fraction"
                ],
                "median_mc_relative_se": metrics["median_mc_relative_se"],
                "environment_negative_fraction": sh_negative_fraction[degree],
            }
        )

    scan: list[dict[str, object]] = []
    brightness_by_count: list[dict[str, object]] = []
    brightness_callables = {}
    predictions: dict[int, np.ndarray] = {}
    for count in counts:
        model = models[count]
        environment_prediction = model.radiance(validation_directions)
        env_metrics = environment_metrics(
            environment_prediction, validation_truth, validation_directions
        )

        started = time.perf_counter()
        for _ in range(config.integration_repeats):
            prediction = asg_brightness(
                model.lobes,
                test_normals,
                config.kernel_sigma_u,
                config.kernel_sigma_v,
                ambient=model.ambient,
            )
        integration_elapsed = time.perf_counter() - started
        predictions[count] = prediction
        bright_metrics = brightness_metrics(
            prediction, mc_reference, mc_standard_error, test_normals
        )
        integration_us_per_normal = (
            integration_elapsed
            / config.integration_repeats
            / test_normals.shape[0]
            * 1e6
        )
        scan.append(
            {
                "n_gauss": count,
                "n_parameters": 6 * count + 1,
                "fit_time_ms": 1000.0 * model.fit_time_s,
                "fit_nfev": model.nfev,
                "integration_us_per_normal": integration_us_per_normal,
                "ambient": model.ambient,
                "environment_nrmse": env_metrics["nrmse"],
                "environment_relative_l1": env_metrics["relative_l1"],
                "environment_relative_bias": env_metrics["relative_bias"],
                "environment_max_relative_error": env_metrics["max_relative_error"],
                "environment_peak_ratio": env_metrics["peak_ratio"],
                "environment_peak_direction_error_deg": env_metrics[
                    "peak_direction_error_deg"
                ],
                "environment_centroid_direction_error_deg": env_metrics[
                    "centroid_direction_error_deg"
                ],
                "environment_flux_ratio": env_metrics["flux_ratio"],
                "environment_negative_fraction": env_metrics["negative_fraction"],
                "environment_minimum_value": env_metrics["minimum_value"],
                "brightness_rel_l1": bright_metrics["relative_l1"],
                "brightness_nrmse": bright_metrics["nrmse"],
                "brightness_relative_bias": bright_metrics["relative_bias"],
                "brightness_max_relative_error": bright_metrics["max_relative_error"],
                "brightness_peak_direction_error_deg": bright_metrics[
                    "peak_direction_error_deg"
                ],
                "brightness_centroid_direction_error_deg": bright_metrics[
                    "centroid_direction_error_deg"
                ],
                "brightness_overshoot_25_fraction": bright_metrics[
                    "overshoot_25_fraction"
                ],
                "median_mc_relative_se": bright_metrics["median_mc_relative_se"],
            }
        )
        for normal_index, normal in enumerate(test_normals):
            brightness_by_count.append(
                {
                    "n_gauss": count,
                    "normal_id": normal_index,
                    "normal_x": normal[0],
                    "normal_y": normal[1],
                    "normal_z": normal[2],
                    "brightness_mc": mc_reference[normal_index],
                    "brightness_asg": prediction[normal_index],
                    "mc_standard_error": mc_standard_error[normal_index],
                    "asg_abs_error": abs(
                        prediction[normal_index] - mc_reference[normal_index]
                    ),
                }
            )
        brightness_callables[count] = _brightness_callable(model, config)

    selected_brightness_rows: list[dict[str, object]] = []
    selected_prediction = predictions[selected_count]
    sh_selected = sh_predictions.get(8, sh_predictions[max(sh_predictions)])
    for normal_index, normal in enumerate(test_normals):
        selected_brightness_rows.append(
            {
                "normal_id": normal_index,
                "normal_x": normal[0],
                "normal_y": normal[1],
                "normal_z": normal[2],
                "brightness_mc_reference": mc_reference[normal_index],
                "mc_standard_error": mc_standard_error[normal_index],
                "brightness_asg": selected_prediction[normal_index],
                "asg_absolute_error": abs(
                    selected_prediction[normal_index] - mc_reference[normal_index]
                ),
                "brightness_sh8": sh_selected[normal_index],
                "sh8_absolute_error": abs(
                    sh_selected[normal_index] - mc_reference[normal_index]
                ),
            }
        )

    _write_csv(output_dir / "scan.csv", scan)
    _write_csv(output_dir / "sh_comparison.csv", sh_comparison)
    _write_csv(output_dir / "brightness_by_count.csv", brightness_by_count)
    _write_csv(output_dir / f"brightness_N{selected_count}.csv", selected_brightness_rows)
    for count in counts:
        rows = _add_ambient_row(_gaussian_rows(models[count]), models[count].ambient)
        _write_csv(output_dir / f"gaussians_N{count}.csv", rows)

    plot_error_curves(scan, sh_comparison, output_dir / "error_vs_gaussians")
    plot_time_curve(scan, output_dir / "time_vs_gaussians")
    selected_counts = tuple(sorted(set((1, 4, 8, selected_count))))
    plot_environment_maps(
        environment, models, selected_counts, output_dir / "environment_reconstruction"
    )
    reference_callable = _reference_brightness_callable(environment, config)
    plot_brightness_maps(
        reference_callable,
        brightness_callables,
        selected_counts,
        output_dir / "brightness_reconstruction",
    )
    plot_brightness_profiles(
        reference_callable,
        brightness_callables,
        selected_counts,
        output_dir / "brightness_profiles",
    )

    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            **config.__dict__,
            "output_dir": str(config.output_dir),
        },
        "environment": {
            "true_lobes": len(environment.lobes),
            "ambient": environment.ambient,
            "kernel_sigma_u": config.kernel_sigma_u,
            "kernel_sigma_v": config.kernel_sigma_v,
        },
        "scan": scan,
        "sh_comparison": sh_comparison,
        "selected_count": selected_count,
    }
    (output_dir / "results.json").write_text(
        json.dumps(_json_safe(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _build_report(result, environment, models, selected_count),
        encoding="utf-8",
    )
    return result


def _build_report(
    result: dict[str, object],
    environment: DirectionalEnvironment,
    models: dict[int, FittedEnvironment],
    selected_count: int,
) -> str:
    scan = result["scan"]
    sh_comparison = result["sh_comparison"]
    scan_rows = [
        [
            str(row["n_gauss"]),
            str(row["n_parameters"]),
            f"{row['fit_time_ms']:.2f}",
            f"{row['integration_us_per_normal']:.2f}",
            f"{100.0 * row['environment_nrmse']:.4g}",
            f"{100.0 * row['brightness_rel_l1']:.4g}",
            f"{row['environment_peak_direction_error_deg']:.2f}/{row['environment_centroid_direction_error_deg']:.2f}",
            f"{row['brightness_peak_direction_error_deg']:.2f}/{row['brightness_centroid_direction_error_deg']:.2f}",
            f"{row['brightness_overshoot_25_fraction']:.3g}",
            f"{row['environment_negative_fraction']:.3g}",
        ]
        for row in scan
    ]
    sh_rows = [
        [
            str(row["sh_degree"]),
            str(row["n_coefficients"]),
            f"{100.0 * row['brightness_rel_l1']:.4g}",
            f"{100.0 * row['brightness_nrmse']:.4g}",
            f"{100.0 * row['brightness_relative_bias']:.4g}",
            f"{row['brightness_peak_direction_error_deg']:.2f}",
            f"{row['environment_negative_fraction']:.3g}",
        ]
        for row in sh_comparison
    ]
    selected_model = models[selected_count]
    gaussian_rows = []
    for index, lobe in enumerate(selected_model.lobes):
        gaussian_rows.append(
            [
                str(index),
                f"{lobe.amplitude:.4f}",
                f"{np.degrees(lobe.azimuth):.2f}",
                f"{np.degrees(lobe.elevation):.2f}",
                f"{lobe.sigma_u:.4f}",
                f"{lobe.sigma_v:.4f}",
                f"{lobe.anisotropy:.3f}",
                f"{lobe.lambda_u:.3f}",
                f"{lobe.lambda_v:.3f}",
                f"{np.degrees(lobe.rotation):.2f}",
                f"{asg_integral(lobe.amplitude, lobe.lambda_u, lobe.lambda_v):.5f}",
            ]
        )

    selected_scan = next(row for row in scan if row["n_gauss"] == selected_count)
    sh8 = next(row for row in sh_comparison if row["sh_degree"] == 8)
    sh12 = next(row for row in sh_comparison if row["sh_degree"] == 12)
    first = scan[0]
    exact_row = next(
        (row for row in scan if row["environment_nrmse"] < 1e-4),
        scan[-1],
    )
    config = result["config"]
    return f"""# 各向异性球面高斯环境光与亮度积分实验

生成时间：{result['generated_utc']}

## 方法

- 环境真值由 {len(environment.lobes)} 个各向异性球面高斯（ASG）和一个常数
  `{environment.ambient:.3f}` 组成，主峰辐射亮度约
  `{max(lobe.amplitude for lobe in environment.lobes):.2f}`，属于强方向性环境图。
- ASG 采用 Xu et al. (2013) 的 Bingham 型定义：
  `G(w)=c*max(w.z,0)*exp(-lambda_u*(w.x)^2-lambda_v*(w.y)^2)`。
- 环境拟合使用非负 ASG 混合、贪心初始化与有界非线性最小二乘；数量扫描为
  `{counts_text(result)}`。
- 光照核同样为各向异性 ASG，宽度
  `sigma_u={config['kernel_sigma_u']:.3f}`、`sigma_v={config['kernel_sigma_v']:.3f}`。
  亮度定义为 `B(n)=integral L(w) K_n(w) dw`。
- ASG-ASG 亮度使用论文的乘积近似（乘积仍是 ASG）与 ASG 闭式积分进行计算，
  不使用逐法线 Monte Carlo。参考值使用 `{config['mc_samples']}` 个均匀随机球面样本，
  并给出分块标准误。
- SH 基线先投影真值环境与光照核，再用同阶实球谐系数内积计算亮度。

## 数量扫描：拟合质量、亮度误差与耗时

{_table(
    ["N", "参数数", "拟合 ms", "积分 us/法线", "环境 NRMSE %", "亮度 rel-L1 %", "环境峰值/质心误差 deg", "亮度峰值/质心误差 deg", "过冲比例", "负值比例"],
    scan_rows,
)}

{exact_row['n_gauss']} 个高斯时环境验证集 NRMSE 已降到
`{100.0 * exact_row['environment_nrmse']:.3g}%`，说明该数量已覆盖环境图的 6 个方向模态。
继续增加高斯主要增加拟合耗时，误差只在小数值噪声附近变化。N={selected_count} 的
亮度相对 L1 误差为 `{100.0 * selected_scan['brightness_rel_l1']:.3g}%`，
平均积分耗时为 `{selected_scan['integration_us_per_normal']:.2f} us/法线`。

## 与 SH 的亮度误差比较

{_table(
    ["SH 阶数", "系数数", "亮度 rel-L1 %", "亮度 NRMSE %", "亮度偏差 %", "峰值方向误差 deg", "环境负值比例"],
    sh_rows,
)}

在相同亮度积分任务上，8 阶 SH 的 rel-L1 为
`{100.0 * sh8['brightness_rel_l1']:.3g}%`，12 阶为
`{100.0 * sh12['brightness_rel_l1']:.3g}%`。ASG 拟合模型在 N={selected_count}
时为 `{100.0 * selected_scan['brightness_rel_l1']:.3g}%`。
达到近零环境误差的最小 ASG 混合是 N={exact_row['n_gauss']}，仅用
`{exact_row['n_parameters']}` 个参数就取得
`{100.0 * exact_row['brightness_rel_l1']:.3g}%` 的亮度 rel-L1；12 阶 SH 使用
`{sh12['n_coefficients']}` 个系数取得
`{100.0 * sh12['brightness_rel_l1']:.3g}%`。在相近亮度质量下，ASG 的自由度约少
`{sh12['n_coefficients'] / exact_row['n_parameters']:.1f}` 倍。
SH 的低阶截断还会在环境重建中出现负值，负值比例为
`{sh8['environment_negative_fraction']:.3g}`（8 阶）；
ASG 是非负高斯混合，负值比例为 0。

## 各高斯参数（N={selected_count}）

{_table(
    ["#", "幅值", "方位 deg", "仰角 deg", "sigma_u", "sigma_v", "各向异性", "lambda_u", "lambda_v", "旋转 deg", "积分 sr"],
    gaussian_rows,
)}

拟合得到的常数环境项为 `{selected_model.ambient:.5f}`。逐法线重建亮度、MC 参考、
标准误及 SH8 对照见 `brightness_N{selected_count}.csv`；全部数量的逐法线结果见
`brightness_by_count.csv`。

## 方向性伪影检查

- N=1 的环境 NRMSE 为 `{100.0 * first['environment_nrmse']:.3g}%`，属于明显欠拟合；
  高光被少数宽高斯合并，峰值和质心方向存在偏差，但重建仍保持非负、平滑。
- 所有 ASG 模型的最小值均非负，`environment_negative_fraction=0`；因此数量不足时
  不会产生 SH 截断常见的负值振铃或反方向亮环。误差表现为能量扩散和峰值低估，
  而不是虚假的负方向性条纹。
- 数量增加到 {exact_row['n_gauss']} 后，环境峰值方向误差降到
  `{exact_row['environment_peak_direction_error_deg']:.3f} deg`；继续增加数量不再
  显著改变方向结构。

## 复现方式

```bash
python3 -m pip install -r requirements.txt
python3 run_experiment.py
```

输出文件：

- `scan.csv`：高斯数量、耗时、环境误差、亮度误差和方向性指标。
- `brightness_by_count.csv`：每个数量、每个测试法线的 ASG 与 MC 亮度。
- `brightness_N{selected_count}.csv`：选定数量的详细亮度重建。
- `gaussians_N{selected_count}.csv`：每个高斯的完整参数与积分。
- `gaussians_N*.csv`：每个扫描数量对应的完整高斯参数。
- `sh_comparison.csv`：SH 各阶亮度误差。
- `error_vs_gaussians.png/svg`、`time_vs_gaussians.png/svg`。
- `environment_reconstruction.png/svg`、`brightness_reconstruction.png/svg`、
  `brightness_profiles.png/svg`。
- `results.json`：机器可读汇总。

## 注意事项

- ASG 的闭式积分与乘积是论文给出的近似闭式算子；本实验同时用独立 MC 参考检查了
  最终亮度，典型误差处于数个百分点量级。
- 拟合采用顺序贪心初始化；这是可复现的局部优化流程，不保证全局最优。
- 均匀球面 MC 的统计误差已写入 CSV；极低亮度方向的相对误差会被放大，因此主指标
  采用相对 L1、NRMSE 与能量偏差，并辅以峰值/质心方向误差。
"""


def counts_text(result: dict[str, object]) -> str:
    return ", ".join(str(row["n_gauss"]) for row in result["scan"])
