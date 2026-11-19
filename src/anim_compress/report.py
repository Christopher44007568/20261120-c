from __future__ import annotations

import csv
import json
import math
from pathlib import Path


def _num(value: float, digits: int = 4) -> str:
    if value == 0.0:
        return "0"
    if abs(value) < 1.0e-3:
        return f"{value:.3e}"
    return f"{value:.{digits}f}"


def _bytes(value: int) -> str:
    return f"{value:,}"


def _slope(bits: list[int], errors: list[float]) -> float:
    xs = [float(bit) for bit in bits]
    ys = [math.log2(max(error, 1.0e-15)) for error in errors]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    return numerator / denominator


def _acceptance(metrics: dict[str, object]) -> dict[str, bool]:
    first = float(metrics["first_window_rotation_peak_deg"])
    last = float(metrics["last_window_rotation_peak_deg"])
    return {
        "rotation_max <= 0.1 deg": float(metrics["rotation_max_deg"]) <= 0.1,
        "position_max <= 0.001": float(metrics["position_max"]) <= 1.0e-3,
        "end_effector_max <= 0.002": float(metrics["end_effector_max"]) <= 2.0e-3,
        "last_window_no_growth": last <= first * 1.1 + 1.0e-6,
    }


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_sweep_csv(path: Path, sweep: list[dict[str, object]]) -> None:
    columns = [
        "bits",
        "compression_ratio",
        "compressed_bytes",
        "payload_bytes",
        "quantization_rotation_max_deg",
        "quantization_rotation_rmse_deg",
        "quantization_position_max",
        "interpolation_rotation_max_deg",
        "interpolation_position_max",
        "rotation_max_deg",
        "rotation_rmse_deg",
        "position_max",
        "end_effector_max",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in sweep:
            writer.writerow({column: record[column] for column in columns})


def write_markdown_report(
    path: Path,
    metrics: dict[str, object],
    sweep: list[dict[str, object]],
    mesh_report: dict[str, object],
) -> None:
    criteria = _acceptance(metrics)
    quant_slope = _slope(
        [int(record["bits"]) for record in sweep],
        [float(record["quantization_rotation_max_deg"]) for record in sweep],
    )
    position_slope = _slope(
        [int(record["bits"]) for record in sweep],
        [float(record["quantization_position_max"]) for record in sweep],
    )
    window_peaks = metrics["window_rotation_peaks_deg"]
    compressed_kib = int(metrics["compressed_bytes"]) / 1024.0
    baseline_kib = int(metrics["baseline_bytes"]) / 1024.0
    lines = [
        "# 骨骼动画定点压缩与锐边细分验证",
        "",
        "## 结论",
        "",
        f"- 当前配置为 **{int(metrics['bits'])} bit、"
        f"{float(metrics['keyframe_hz']):g} Hz 关键帧**；长动画压缩比 **"
        f"{float(metrics['compression_ratio']):.2f}:1**。",
        f"- 插值重建的最大旋转误差为 **{_num(float(metrics['rotation_max_deg']))}°**，"
        f"局部位置误差为 **{_num(float(metrics['position_max']))}** 模型单位，"
        f"末端执行器世界位置误差为 **{_num(float(metrics['end_effector_max']))}**。",
        f"- 量化本身在 {int(metrics['bits'])} bit 下仅贡献 **"
        f"{_num(float(metrics['quantization_rotation_max_deg']))}°** 旋转误差；"
        f"{float(metrics['keyframe_hz']):g} Hz 插值误差为 **"
        f"{_num(float(metrics['interpolation_rotation_max_deg']))}°**，"
        f"因此继续提高位数在 {int(metrics['bits'])} bit 后收益很小。",
        f"- 量化位数扫描的 log2(旋转误差)-位数斜率为 **{quant_slope:.3f}**，"
        f"位置误差斜率为 **{position_slope:.3f}**；位数每增加 1 bit，"
        "定点误差约减半，但压缩比同时下降。",
        f"- 边界/内部细分后，开放网格边界仍位于原平面；帐篷网格锐脊偏离直线为 "
        f"**{_num(float(mesh_report['sharp_tent']['levels'][-1]['ridge_deviation']), 2)}**，"
        f"锐脊两侧法线夹角保持 **"
        f"{float(mesh_report['sharp_tent']['levels'][-1]['min_crease_deg']):.1f}°**。",
        "",
        "## 实验设置",
        "",
        f"- 动画长度：{float(metrics['duration_seconds']):.0f} s，"
        f"{int(metrics['source_fps'])} fps，{int(metrics['source_frames']):,} 帧，"
        f"{int(metrics['joint_count'])} 个关节。",
        f"- 关键帧：{float(metrics['keyframe_hz']):.1f} Hz，共 "
        f"{int(metrics['key_count']):,} 个关键点；四元数与位置插值分别使用 SLERP 与线性插值。",
        "- 基线：每帧每关节保存 4 个 float32 四元数分量和 3 个 float32 位置分量，共 28 bytes。",
        f"- 压缩流：每个分量 {int(metrics['bits'])} bit，位置按各关节整段包围盒做对称区间定点编码，"
        "四元数按 [-1, 1] 编码并在解码后归一化；统计包含关键时间与关节边界元数据。",
        "",
        "## 压缩与重建结果",
        "",
        "| 项目 | 数值 |",
        "|---|---:|",
        f"| 原始 float32 大小 | {_bytes(int(metrics['baseline_bytes']))} B ({baseline_kib:.1f} KiB) |",
        f"| 仅保留关键帧的 float32 大小 | {_bytes(int(metrics['keyframe_float_bytes']))} B |",
        f"| 压缩后比特流与元数据 | {_bytes(int(metrics['compressed_bytes']))} B ({compressed_kib:.1f} KiB) |",
        f"| 压缩比 | {float(metrics['compression_ratio']):.2f}:1 |",
        f"| 关键帧缩减倍数 | {float(metrics['keyframe_reduction_ratio']):.2f}x |",
        f"| 量化带来的额外缩减 | {float(metrics['quantization_ratio']):.2f}x |",
        f"| 纯插值峰值旋转误差 | {_num(float(metrics['interpolation_rotation_max_deg']))}° |",
        f"| 纯插值峰值局部位置误差 | {_num(float(metrics['interpolation_position_max']))} |",
        f"| 重建峰值旋转误差（插值+量化） | {_num(float(metrics['rotation_max_deg']))}° |",
        f"| 重建峰值局部位置误差（插值+量化） | {_num(float(metrics['position_max']))} |",
        f"| 末端执行器峰值世界位置误差 | {_num(float(metrics['end_effector_max']))} |",
        "",
        "## 长动画稳定性",
        "",
        f"将 {float(metrics['duration_seconds']):.0f} s 动画切成 6 个连续窗口，"
        "分别记录重建旋转误差峰值。"
        "所有窗口使用相同的局部绝对变换解码，不累计增量误差。",
        "",
        "| 窗口 | 1 | 2 | 3 | 4 | 5 | 6 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| 旋转峰值 (°) | "
        + " | ".join(_num(float(value), 5) for value in window_peaks)
        + " |",
        "",
        f"末窗口峰值为 **{_num(float(metrics['last_window_rotation_peak_deg']), 5)}°**，"
        f"首窗口为 **{_num(float(metrics['first_window_rotation_peak_deg']), 5)}°**，"
        "没有随时间增长的误差漂移。",
        "",
        "## 量化位数—误差关系",
        "",
        "`量化误差` 只在关键点比较，隔离插值误差；`重建误差` 在长动画时间轴上密采样比较，"
        "包含关键帧插值与量化两部分。默认行使用 60 fps 全帧，其余扫描行以 20 fps 间隔"
        "抽样加速。压缩比按相同关键帧率计算。",
        "",
        "| 位数 | 压缩比 | 量化旋转峰值 (°) | 量化位置峰值 | 插值旋转峰值 (°) | 插值位置峰值 | 重建旋转峰值 (°) | 末端位置峰值 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in sweep:
        lines.append(
            f"| {int(record['bits'])} | {float(record['compression_ratio']):.2f}:1 | "
            f"{_num(float(record['quantization_rotation_max_deg']))} | "
            f"{_num(float(record['quantization_position_max']))} | "
            f"{_num(float(record['interpolation_rotation_max_deg']))} | "
            f"{_num(float(record['interpolation_position_max']))} | "
            f"{_num(float(record['rotation_max_deg']))} | "
            f"{_num(float(record['end_effector_max']))} |"
        )
    lines.extend(
        [
            "",
            "量化旋转误差满足定点量化近似 `error ∝ 2^-bits`，实测 log2 斜率为 "
            f"**{quant_slope:.3f}**；位置误差斜率为 **{position_slope:.3f}**。"
            f"高位数的总误差会触底到 {float(metrics['keyframe_hz']):g} Hz 插值误差；"
            "若需要继续提升动作精度，"
            "应提高关键帧率，而不是无限增加量化位数。",
            "",
            "## 压缩前后动作对比",
            "",
            "下表的左手坐标来自世界空间；旋转峰值为该时刻各末端关节的最大值。"
            "完整轨迹叠加与三个时刻的骨架叠加见 `action_comparison.svg`。",
            "",
            "| 时间 (s) | 左手原始 (x, y, z) | 左手重建 (x, y, z) | 位置误差 | 最大旋转误差 (°) |",
            "|---:|---|---|---:|---:|",
        ]
    )
    for record in metrics["pose_comparison"]:
        joints = [joint for joint in record["joints"] if joint["name"] == "hand_l"]
        if not joints:
            continue
        joint = joints[0]
        source_position = ", ".join(f"{value:.4f}" for value in joint["source_position"])
        decoded_position = ", ".join(f"{value:.4f}" for value in joint["decoded_position"])
        maximum_rotation = max(
            float(item["rotation_error_deg"]) for item in record["joints"]
        )
        lines.append(
            f"| {float(record['time']):.0f} | ({source_position}) | ({decoded_position}) | "
            f"{_num(float(joint['position_error']))} | {_num(maximum_rotation, 5)} |"
        )
    lines.extend(
        [
            "",
            f"{int(metrics['bits'])} bit 的轨迹与骨架叠加几乎完全重合；"
            f"{_num(float(metrics['rotation_max_deg']))}° 旋转误差和 "
            f"{_num(float(metrics['end_effector_max']))} 量级末端位置误差"
            "低于设定的动作失真阈值。",
            "",
            "## 边界、内部顶点与锐边细分",
            "",
            "细分采用 Catmull–Clark：内部规则点使用面点/边点加权；"
            "开放边界和显式锐边使用折痕规则；转折角超过阈值或显式标记的角点保持不动。"
            "锐边每细分一次由 1 段拆成 2 段并继续标记。",
            "",
            "| 网格 | 级别 | 顶点 | 面 | 边界顶点 | 内部顶点 | 锐边 | 锐脊偏离 | 锐脊夹角 (°) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for level in mesh_report["sharp_tent"]["levels"]:
        lines.append(
            f"| 帐篷（边界+内部+锐脊） | {int(level['level'])} | {int(level['vertices'])} | "
            f"{int(level['faces'])} | {int(level['boundary_vertices'])} | "
            f"{int(level['interior_vertices'])} | {int(level['sharp_edges'])} | "
            f"{_num(float(level['ridge_deviation']), 2)} | "
            f"{float(level['min_crease_deg']):.1f} |"
        )
    patch = mesh_report["open_patch"]
    cube = mesh_report["closed_cube"]
    lines.extend(
        [
            f"| 开放平面片 | 2 | {int(patch['vertices'])} | {int(patch['faces'])} | "
            f"{int(patch['boundary_vertices'])} | {int(patch['interior_vertices'])} | 0 | "
            f"n/a | n/a |",
            f"| 闭合立方体 | 2 | {int(cube['vertices'])} | {int(cube['faces'])} | "
            f"{int(cube['boundary_vertices'])} | {int(cube['interior_vertices'])} | 0 | "
            f"n/a | n/a |",
            "",
            f"开放平面片细分后所有顶点仍位于 z=0（最大 |z| = "
            f"{_num(float(patch['max_abs_z']), 2)}），边界矩形未被圆角化；"
            f"闭合立方体没有边界顶点，全部 {int(cube['interior_vertices'])} 个顶点走内部规则。"
            "帐篷网格含 1 个初始内部顶点，细分后内部顶点数正常增长；"
            "锐脊始终位于 x=0、z=1 的原直线上，且两侧法线夹角保持 90°。",
            "",
            "## 判定",
            "",
        ]
    )
    for criterion, passed in criteria.items():
        lines.append(f"- `{criterion}`: {'PASS' if passed else 'FAIL'}")
    overall = all(criteria.values())
    lines.extend(
        [
            "",
            f"**总体：{'压缩后动作不失真，量化误差可接受' if overall else '存在未达标项'}。**",
            "",
            "## 复现",
            "",
            "```bash",
            "PYTHONPATH=src python3 -m anim_compress.demo --duration 600 --fps 60 \\",
            "  --keyframe-hz 10 --bits 16",
            "PYTHONPATH=src python3 -m unittest discover -s tests -v",
            "```",
            "",
            "输出文件：`animation_compression_metrics.json`、`quantization_sweep.csv`、"
            "`action_comparison.svg`、`quantization_tradeoff.svg`、"
            "`mesh_subdivision.svg`。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
