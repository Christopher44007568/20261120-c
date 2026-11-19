#!/usr/bin/env python3
"""Convert result images to PNG and build a human-readable metrics report."""

from __future__ import annotations

import json
import pathlib
import sys

from ppm_to_png import read_ppm, write_png


def percentage(value: float) -> str:
    return f"{value * 100.0:.4f}%"


def number(value: float) -> str:
    return f"{value:.8g}"


def convert_images(root: pathlib.Path) -> pathlib.Path:
    source = root / "images"
    destination = root / "png"
    destination.mkdir(parents=True, exist_ok=True)
    for ppm_path in sorted(source.glob("*.ppm")):
        width, height, pixels = read_ppm(ppm_path)
        write_png(destination / f"{ppm_path.stem}.png", width, height, pixels)
    return destination


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} RESULT_DIRECTORY", file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    with (root / "metrics.json").open(encoding="utf-8") as handle:
        metrics = json.load(handle)
    convert_images(root)
    static = metrics["static"]
    moving = metrics["moving"]
    config = metrics["config"]

    static_mse_reduction = 1.0 - static["mse_after"] / static["mse_before"]
    static_variance_reduction = (
        1.0 - static["noise_variance_after"] / static["noise_variance_before"]
    )
    moving_ghost_reduction = (
        0.0
        if moving["ghost_ratio_before_guard"] == 0.0
        else 1.0
        - moving["ghost_ratio_after_guard"] / moving["ghost_ratio_before_guard"]
    )
    static_pass = (
        static["frames_to_convergence"] > 0
        and static["edge_ghost_ratio"] == 0.0
        and static["mse_after"] < static["mse_before"]
        and static["noise_variance_after"] < static["noise_variance_before"]
    )
    moving_pass = (
        moving["naive_ghost_pixels_outside_fast_motion"] == 0
        and moving["guarded_ghost_pixels_outside_fast_motion"] == 0
        and moving["ghost_ratio_after_guard"]
        < moving["ghost_ratio_before_guard"]
    )

    lines = [
        "# 路径追踪时空联合去噪验证报告",
        "",
        "## 结论",
        "",
        f"- 静止相机在 **{static['frames_to_convergence']} 帧**内达到收敛阈值 "
        f"`{number(static['convergence_target_mse'])}` MSE；之后保持稳定。",
        f"- 静止序列时域噪点方差从 `{number(static['noise_variance_before'])}` "
        f"降至 `{number(static['noise_variance_after'])}`，降幅 "
        f"**{static_variance_reduction * 100.0:.2f}%**。",
        f"- 静止场景边缘鬼影像素占比为 **{percentage(static['edge_ghost_ratio'])}**，"
        "时域累积未在几何/颜色边缘产生重影。",
        f"- 运动相机历史不匹配均值为 **{percentage(moving['history_mismatch_ratio_mean'])}**；"
        f"最终帧为 **{percentage(moving['history_mismatch_ratio_final'])}**。",
        f"- 运动场景鬼影像素占比在启用几何/颜色历史门控前为 "
        f"**{percentage(moving['ghost_ratio_before_guard'])}**，启用后为 "
        f"**{percentage(moving['ghost_ratio_after_guard'])}**，降幅 "
        f"**{moving_ghost_reduction * 100.0:.2f}%**。",
        f"- 鬼影像素数从 **{moving['ghost_pixel_count_before_guard']}** 降至 "
        f"**{moving['ghost_pixel_count_after_guard']}**。",
        f"- 未保护历史的鬼影有 **{moving['naive_ghost_pixels_outside_fast_motion']}** "
        "个像素落在快速运动/运动突变区域之外；联合去噪后为 "
        f"**{moving['guarded_ghost_pixels_outside_fast_motion']}**。",
        "",
        "## 定量结果",
        "",
        "| 指标 | 去噪前 | 去噪后 |",
        "|---|---:|---:|",
        f"| 静止图 MSE（对比 256 spp 参考） | {number(static['mse_before'])} | "
        f"{number(static['mse_after'])} |",
        f"| 静止时序噪点方差 | {number(static['noise_variance_before'])} | "
        f"{number(static['noise_variance_after'])} |",
        f"| 静止残差亮度方差 | {number(static['residual_luma_variance_before'])} | "
        f"{number(static['residual_luma_variance_after'])} |",
        f"| 运动图 MSE（对比参考） | {number(moving['mse_before'])} | "
        f"{number(moving['mse_after'])} |",
        f"| 运动鬼影像素占比 | {percentage(moving['ghost_ratio_before_guard'])} | "
        f"{percentage(moving['ghost_ratio_after_guard'])} |",
        "",
        f"- 静止 MSE 降幅：**{static_mse_reduction * 100.0:.2f}%**。",
        f"- 运动相机快速运动区域占比：**{percentage(moving['fast_motion_pixel_ratio'])}**"
        "（屏幕速度不低于 0.75 px/帧、局部运动突变或新暴露边界）。",
        f"- 历史不匹配像素中位于快速运动区域的比例："
        f"**{percentage(moving['history_mismatch_fraction_in_fast_motion'])}**。",
        f"- 未保护鬼影位于快速运动区域的比例："
        f"**{percentage(moving['naive_ghost_fraction_in_fast_motion'])}**。",
        f"- 屏幕运动速度 p50 / p75 / p90："
        f"`{number(moving['screen_motion_p50_pixels'])}` / "
        f"`{number(moving['screen_motion_p75_pixels'])}` / "
        f"`{number(moving['screen_motion_p90_pixels'])}` px/帧。",
        "",
        "## 验证判定",
        "",
        f"- 静止收敛、降噪、无边缘鬼影：**{'通过' if static_pass else '未通过'}**。",
        f"- 运动历史失配被抑制、鬼影仅位于快速运动区域："
        f"**{'通过' if moving_pass else '未通过'}**。",
        "",
        "## 图像",
        "",
        "静止场景（参考 / 2 spp 原始 / 去噪）：",
        "",
        "![static reference](png/static_reference.png)",
        "![static raw](png/static_raw.png)",
        "![static denoised](png/static_denoised.png)",
        "",
        "运动场景（参考 / 2 spp 原始 / 未保护历史 / 联合去噪）：",
        "",
        "![moving reference](png/moving_reference.png)",
        "![moving raw](png/moving_raw.png)",
        "![moving naive temporal](png/moving_naive_temporal.png)",
        "![moving denoised](png/moving_denoised.png)",
        "",
        "运动场景掩码（历史不匹配 / 快速运动 / 去噪前鬼影 / 去噪后鬼影）：",
        "",
        "![mismatch](png/moving_mismatch_mask.png)",
        "![fast motion](png/moving_fast_motion_mask.png)",
        "![ghost before](png/moving_ghost_mask_before.png)",
        "![ghost after](png/moving_ghost_mask_after.png)",
        "",
        "## 指标定义",
        "",
        "- **时域噪点方差**：静止序列每个像素亮度对时间求方差，再对全图取平均。",
        "- **收敛帧**：去噪后逐帧 MSE 首次进入最终稳态 MSE 的 115% 以内，并连续"
        " 4 帧保持；帧号从 1 开始。",
        "- **鬼影像素**：去噪亮度误差同时超过 `0.055` 和当前低样本局部误差加 `0.018` "
        "的像素；该判定用高样本参考图作为真值。",
        "- **历史不匹配**：重投影越界、物体 ID/法线/深度不一致，或通过几何检查后"
        " 当前空间滤波颜色与历史颜色差异超过门限。",
        "- **快速运动区域**：屏幕位移不小于 0.75 px/帧，或 3x3 邻域速度突变，或距离"
        " 图像新暴露边界不超过 3 像素；再膨胀 1 像素。",
        "",
        "## 运行配置",
        "",
        f"- 分辨率 `{config['width']}x{config['height']}`，低样本 `{config['low_spp']} spp`，"
        f"参考 `{config['reference_spp']} spp`。",
        f"- 静止序列 `{config['static_frames']}` 帧，运动序列 `{config['moving_frames']}` 帧。",
        f"- 总运行时间 `{metrics['runtime_seconds']:.2f}` 秒。",
        "",
    ]
    report_path = root / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

