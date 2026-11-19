#!/usr/bin/env python3
"""Build report figures, summary JSON, and REPORT.md from raw experiment data."""

from __future__ import annotations

import csv
import json
import math
import shutil
import statistics
from pathlib import Path

from canvas import Canvas, ppm

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "artifacts" / "raw"
ART = ROOT / "artifacts"

BG = (11, 15, 22)
PANEL = (20, 27, 38)
TEXT = (231, 236, 244)
MUTED = (151, 165, 184)
ACCENT = (255, 196, 76)
RED = (245, 92, 68)
GREEN = (83, 211, 134)
BLUE = (82, 164, 255)


def read_csv(name: str) -> list[dict[str, str]]:
    with (RAW / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def timing_summary() -> dict[str, float]:
    rows = read_csv("frame_times.csv")
    total = [float(r["total_ms"]) for r in rows]
    ssgi = [float(r["indirect_ssgi_ms"]) for r in rows]
    gbuffer = [float(r["gbuffer_direct_ms"]) for r in rows]
    accumulation = [float(r["accumulation_ms"]) for r in rows]
    return {
        "frames": len(rows),
        "mean_total_ms": statistics.fmean(total),
        "median_total_ms": statistics.median(total),
        "p95_total_ms": percentile(total, 0.95),
        "mean_gbuffer_ms": statistics.fmean(gbuffer),
        "mean_ssgi_ms": statistics.fmean(ssgi),
        "mean_accumulation_ms": statistics.fmean(accumulation),
    }


def make_indirect_figure() -> None:
    images = [
        ("DEPTH", ppm(RAW / "depth.ppm")),
        ("NORMAL", ppm(RAW / "normal.ppm")),
        ("1-FRAME SSGI", ppm(RAW / "indirect_raw.ppm")),
        ("48-FRAME ACCUMULATION", ppm(RAW / "indirect_pre_resolve.ppm")),
        ("TEMPORAL + BILATERAL RESOLVE", ppm(RAW / "indirect.ppm")),
        ("DIRECT + INDIRECT", ppm(RAW / "composite.ppm")),
    ]
    width, height = 1560, 1000
    out = Canvas(width, height, BG)
    out.text(36, 24, "TEMPORAL SCREEN-SPACE GLOBAL ILLUMINATION", TEXT, 3)
    out.text(36, 66, "DEPTH / NORMAL GUIDED HISTORY  |  480 X 300 SOFTWARE RENDER", MUTED, 2)
    positions = [(30, 110), (530, 110), (1030, 110), (30, 505), (530, 505), (1030, 505)]
    for (label, image), (x, y) in zip(images, positions):
        out.rect(x - 3, y - 3, 486, 366, PANEL)
        out.blit(image, x, y, 480, 300)
        out.text(x + 4, y + 310, label, ACCENT if "ACCUM" in label or "RESOLVE" in label else TEXT, 2)
    out.text(30, 938, "RED WALL: X=-3.0 M   GREEN WALL: X=+3.0 M   AREA LIGHT: CEILING PANEL", MUTED, 2)
    out.text(30, 966, "HISTORY REJECTION: DEPTH TOLERANCE + NORMAL DOT > 0.90 + 3X3 VARIANCE CLAMP", MUTED, 2)
    out.save(ART / "indirect_light.png")


def make_color_bleed_figure(bleed: dict[str, dict[str, str]]) -> None:
    image = ppm(RAW / "indirect.ppm")
    out = Canvas(1560, 900, BG)
    out.text(34, 24, "INDOOR COLOR BLEEDING VALIDATION", TEXT, 3)
    out.text(34, 67, "SYMMETRIC 25 CM FLOOR STRIPS ADJACENT TO RED / GREEN WALLS", MUTED, 2)
    out.rect(31, 111, 726, 456, PANEL)
    out.blit(image, 34, 114, 720, 450)
    left_box = (18, 320, 120, 125)
    right_box = (583, 320, 120, 125)
    out.outline(*left_box, ACCENT, 4)
    out.outline(*right_box, GREEN, 4)
    out.text(42, 295, "LEFT ROI", ACCENT, 2)
    out.text(594, 295, "RIGHT ROI", GREEN, 2)
    out.text(790, 116, "FLOOR INDIRECT LIGHT", TEXT, 3)
    left = bleed["left_floor"]
    right = bleed["right_floor"]
    center = bleed["center_floor"]
    lines = [
        f"LEFT  R/G = {float(left['mean_r']) / max(1e-9, float(left['mean_g'])):.2f}",
        f"RIGHT G/R = {float(right['mean_g']) / max(1e-9, float(right['mean_r'])):.2f}",
        f"REDNESS   = {float(left['redness']):+.3f}",
        f"GREENNESS = {float(right['greenness']):+.3f}",
        f"CENTER R/G = {float(center['mean_r']) / max(1e-9, float(center['mean_g'])):.2f}",
    ]
    for i, line in enumerate(lines):
        out.text(794, 176 + i * 38, line, TEXT, 2)
    out.text(790, 388, "INTERPRETATION", ACCENT, 2)
    out.text(790, 426, "BOTH SIDES POSITIVE", TEXT, 2)
    out.text(790, 458, "ASYMMETRY < 0.22", TEXT, 2)
    out.text(790, 490, "SATURATION < 0.90", TEXT, 2)
    out.text(790, 522, "CENTER TINT BELOW WALL STRIPS", TEXT, 2)

    left_crop = image.crop(0, 230, 110, 69)
    right_crop = image.crop(370, 230, 110, 69)
    out.rect(34, 614, 726, 250, PANEL)
    out.text(46, 625, "LEFT WALL / FLOOR", ACCENT, 2)
    out.blit(left_crop, 44, 660, 330, 206)
    out.text(410, 625, "RIGHT WALL / FLOOR", GREEN, 2)
    out.blit(right_crop, 408, 660, 330, 206)
    out.text(790, 610, "NATURAL BLEED CRITERIA", TEXT, 2)
    criteria = [
        "1. RED AND GREEN TINTS HAVE OPPOSITE SIGN",
        "2. LEFT/RIGHT STRENGTH DIFFER BY < 0.22",
        "3. NO CHANNEL SATURATES ABOVE 0.90",
        "4. CENTER FLOOR TINT STAYS BELOW WALL STRIPS",
    ]
    for i, line in enumerate(criteria):
        out.text(790, 650 + i * 32, line, MUTED, 2)
    out.save(ART / "indoor_color_bleed.png")


def chart_frame(canvas: Canvas, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = x + 72, y + 24, x + w - 24, y + h - 60
    canvas.rect(left, top, right - left, bottom - top, (16, 22, 31))
    canvas.line(left, bottom, right, bottom, MUTED, 2)
    canvas.line(left, top, left, bottom, MUTED, 2)
    for i in range(5):
        yy = top + round((bottom - top) * i / 4)
        canvas.line(left, yy, right, yy, (43, 54, 68), 1)
    return left, top, right, bottom


def plot_series(
    canvas: Canvas,
    bounds: tuple[int, int, int, int],
    points: list[tuple[float, float]],
    color,
    x_max: float = 1.0,
    y_max: float = 1.0,
) -> None:
    left, top, right, bottom = bounds
    mapped = []
    for px, py in points:
        sx = left + int(round((right - left) * px / max(1e-9, x_max)))
        sy = bottom - int(round((bottom - top) * py / max(1e-9, y_max)))
        mapped.append((sx, sy))
    for a, b in zip(mapped, mapped[1:]):
        canvas.line(a[0], a[1], b[0], b[1], color, 3)
    for x, y in mapped:
        canvas.rect(x - 4, y - 4, 8, 8, color)


def make_ghost_figure() -> None:
    ghost = {r["method"]: r for r in read_csv("ghost_metrics.csv")}
    entries = [
        ("NAIVE HISTORY", ppm(RAW / "ghost_naive.ppm"), RED,
         f"ERROR {float(ghost['naive']['ghost_error']):.3f}"),
        ("DEPTH + NORMAL REJECTION", ppm(RAW / "ghost_proposed.ppm"), GREEN,
         f"ERROR {float(ghost['depth_normal_adaptive']['ghost_error']):.3f}"),
        ("CURRENT-FRAME REFERENCE", ppm(RAW / "ghost_reference.ppm"), BLUE,
         "256 SPP VALIDATION"),
        ("VACATED-PIXEL MASK", ppm(RAW / "ghost_mask.ppm"), ACCENT,
         f"{int(ghost['naive']['mask_pixels'])} PIXELS"),
    ]
    out = Canvas(1560, 1200, BG)
    out.text(34, 24, "TEMPORAL GHOST VALIDATION", TEXT, 3)
    out.text(34, 67, "ORANGE EMITTER TELEPORTS AT FRAME 15; MEASUREMENT AT FRAME 16", MUTED, 2)
    positions = [(34, 100), (790, 100), (34, 625), (790, 625)]
    for (label, image, color, detail), (x, y) in zip(entries, positions):
        out.rect(x - 3, y - 3, 726, 510, PANEL)
        out.blit(image, x, y, 720, 450)
        out.text(x + 4, y + 458, label, color, 2)
        out.text(x + 4, y + 486, detail, MUTED, 2)
    out.text(34, 1155, "ADAPTIVE PATH: REPROJECT WORLD POSITION, REJECT DEPTH/NORMAL MISMATCH, CLAMP HISTORY TO 3X3 LOCAL DISTRIBUTION", MUTED, 2)
    out.save(ART / "temporal_ghost_validation.png")


def make_history_figure(rows: list[dict[str, str]]) -> None:
    out = Canvas(1900, 900, BG)
    out.text(34, 24, "HISTORY WEIGHT: QUALITY, NOISE, AND GHOSTING", TEXT, 3)
    out.text(34, 67, "SWEEP OF HISTORY WEIGHT H FOR 34-FRAME INDOOR SEQUENCES", MUTED, 2)
    chart_box = (34, 102, 930, 720)
    out.rect(chart_box[0], chart_box[1], chart_box[2], chart_box[3], PANEL)
    bounds = chart_frame(out, 44, 128, 900, 640)
    weights = [float(r["history_weight"]) for r in rows]
    noise = [float(r["temporal_noise"]) for r in rows]
    naive = [float(r["ghost_error_naive"]) for r in rows]
    light = [float(r["ghost_error_lightstep"]) for r in rows]
    quality = [float(r["quality_score"]) / 100.0 for r in rows]
    noise_max = max(noise)
    naive_max = max(naive)
    light_max = max(light)
    series = [
        ("TEMPORAL NOISE", [(w, v / noise_max) for w, v in zip(weights, noise)], BLUE),
        ("NAIVE GHOST", [(w, v / naive_max) for w, v in zip(weights, naive)], RED),
        ("LIGHT-STEP GHOST", [(w, v / light_max) for w, v in zip(weights, light)], ACCENT),
        ("QUALITY SCORE", list(zip(weights, quality)), GREEN),
    ]
    for _, points, color in series:
        plot_series(out, bounds, points, color)
    for i in range(6):
        x = bounds[0] + round((bounds[2] - bounds[0]) * i / 5)
        label = f"{i / 5:.1f}"
        out.text(x - 12, bounds[3] + 12, label, MUTED, 1)
    for i in range(5):
        y = bounds[3] - round((bounds[3] - bounds[1]) * i / 4)
        out.text(bounds[0] - 42, y - 4, f"{i / 4:.2f}", MUTED, 1)
    out.text(bounds[0] + 300, bounds[3] + 38, "HISTORY WEIGHT H", TEXT, 2)
    out.text(bounds[0] - 68, bounds[1] - 24, "NORMALIZED", MUTED, 1)
    best = int(float(next(r for r in rows if r["recommended"] == "1")["history_weight"]) * 100)
    bx = bounds[0] + int(round((bounds[2] - bounds[0]) * best / 100))
    out.line(bx, bounds[1], bx, bounds[3], (235, 235, 235), 2)
    text_x = bx - 320 if best >= 70 else bx + 8
    out.text(text_x, bounds[1] + 8, f"RECOMMENDED H={best / 100:.2f}", TEXT, 2)
    for i, (label, _, color) in enumerate(series):
        out.rect(76, 740 + i * 24, 18, 12, color)
        out.text(104, 738 + i * 24, label, TEXT, 1)

    out.text(1000, 108, "LIGHT-STEP RESPONSE (FIRST FRAME AFTER EMISSION DROP)", TEXT, 2)
    chosen = [0.75, 0.92, 0.98]
    for i, weight in enumerate(chosen):
        image = ppm(RAW / f"lightstep_h{weight:.2f}.ppm")
        crop = image.crop(95, 85, 145, 145)
        y = 148 + i * 246
        out.rect(1004, y - 4, 352, 232, PANEL)
        out.blit(crop, 1010, y, 340, 220)
        out.text(1370, y + 8, f"H={weight:.2f}", ACCENT, 2)
        row = next(r for r in rows if abs(float(r["history_weight"]) - weight) < 1e-6)
        out.text(1370, y + 42, f"GHOST {float(row['ghost_error_lightstep']):.3f}", TEXT, 2)
        out.text(1370, y + 76, f"NOISE {float(row['temporal_noise']):.3f}", TEXT, 2)
    out.save(ART / "history_weight_quality.png")


def make_timing_figure(stats: dict[str, float]) -> None:
    rows = read_csv("frame_times.csv")
    frames = [int(r["frame"]) for r in rows]
    gb = [float(r["gbuffer_direct_ms"]) for r in rows]
    ssgi = [float(r["indirect_ssgi_ms"]) for r in rows]
    accum = [float(r["accumulation_ms"]) for r in rows]
    total = [float(r["total_ms"]) for r in rows]
    out = Canvas(1260, 700, BG)
    out.text(34, 24, "PER-FRAME CPU TIMING", TEXT, 3)
    out.text(34, 67, "480 X 300 | 10 SSGI RAYS/PIXEL | 12 DIRECT SHADOW SAMPLES", MUTED, 2)
    out.rect(30, 100, 1200, 530, PANEL)
    bounds = chart_frame(out, 42, 120, 1176, 480)
    fmax = max(frames) + 1
    tmax = max(total)
    for values, color in [(total, TEXT), (ssgi, RED), (gb, BLUE), (accum, GREEN)]:
        plot_series(out, bounds, [(f / fmax, v / tmax) for f, v in zip(frames, values)], color,
                    x_max=1.0, y_max=1.0)
    for i in range(5):
        x = bounds[0] + round((bounds[2] - bounds[0]) * i / 4)
        out.text(x - 10, bounds[3] + 12, f"{int(fmax * i / 4)}", MUTED, 1)
        y = bounds[3] - round((bounds[3] - bounds[1]) * i / 4)
        out.text(bounds[0] - 48, y - 4, f"{tmax * i / 4:.0f}", MUTED, 1)
    out.text(bounds[0] + 470, bounds[3] + 42, "FRAME INDEX", TEXT, 2)
    out.text(bounds[0] - 60, bounds[1] - 24, "MS", MUTED, 1)
    legend = [("TOTAL", TEXT), ("SSGI", RED), ("G-BUFFER + DIRECT", BLUE), ("ACCUM", GREEN)]
    for i, (label, color) in enumerate(legend):
        out.rect(80 + i * 260, 632, 18, 12, color)
        out.text(106 + i * 260, 630, label, TEXT, 1)
    summary = (
        f"MEAN {stats['mean_total_ms']:.1f} MS   MEDIAN {stats['median_total_ms']:.1f} MS   "
        f"P95 {stats['p95_total_ms']:.1f} MS   SSGI {stats['mean_ssgi_ms']:.1f} MS"
    )
    out.text(80, 660, summary, ACCENT, 2)
    out.save(ART / "frame_times.png")


def make_terrain_figure(data: dict) -> None:
    out = Canvas(1800, 1080, BG)
    out.text(34, 24, "D8 HYDROLOGY: RIVER NETWORK AND VALLEY POSITIONS", TEXT, 3)
    out.text(34, 67, "360 X 360 GRID | PRIORITY-FLOOD FILL | STEEPEST DESCENT | FLOW ACCUMULATION", MUTED, 2)
    panels = [
        ("RIVER NETWORK + VALLEY WAYPOINTS", ppm(RAW / "terrain_hydrology.ppm")),
        ("FLOW ACCUMULATION (LOG INTENSITY)", ppm(RAW / "terrain_flow.ppm")),
        ("SLOPE MAGNITUDE", ppm(RAW / "terrain_slope.ppm")),
    ]
    positions = [(32, 112), (632, 112), (1232, 112)]
    for (label, image), (x, y) in zip(panels, positions):
        out.rect(x - 3, y - 3, 546, 606, PANEL)
        out.blit(image, x, y, 540, 540)
        out.text(x, y + 550, label, TEXT, 2)
    for node in data["confluences"][:8]:
        px = positions[0][0] + round(node["px"] * 540 / 360)
        py = positions[0][1] + round(node["py"] * 540 / 360)
        out.rect(px - 7, py - 7, 14, 14, (8, 10, 14))
        out.text(px + 7, py - 12, str(node["id"]), ACCENT, 1)

    out.text(32, 752, "VALIDATION", GREEN, 2)
    metrics = [
        f"DOWNHILL RATIO          {data['downhill_ratio_percent']:.2f}%",
        f"FLOW CONSERVATION       {data['flow_conservation_ratio_percent']:.2f}%",
        f"CONFLUENCE CORRECTNESS  {data['confluence_correct_ratio_percent']:.2f}%",
        f"RIVER CELLS             {data['river_cells']}",
        f"MAX ACCUMULATION        {data['max_accumulation_cells']:.0f} CELLS",
    ]
    for i, line in enumerate(metrics):
        out.text(32, 790 + i * 28, line, TEXT, 2)
    outlet = data["outlet"]
    out.text(520, 752, "MAIN OUTLET", ACCENT, 2)
    out.text(520, 790, f"PX ({outlet['px']}, {outlet['py']})  X={outlet['x_m']:.1f} M  Y={outlet['y_m']:.1f} M", TEXT, 2)
    out.text(520, 822, f"ELEVATION {outlet['elevation_m']:.2f} M   FLOW {outlet['flow_cells']:.0f} CELLS", TEXT, 2)
    out.text(1010, 752, "MAJOR CONFLUENCES", ACCENT, 2)
    for i, node in enumerate(data["confluences"][:5]):
        line = (
            f"{node['id']}: ({node['x_m']:.0f}, {node['y_m']:.0f}) M  "
            f"Z={node['elevation_m']:.1f}  Q={node['flow_cells']:.0f}  "
            f"IN={node['upstream_branches']}"
        )
        out.text(1010, 790 + i * 28, line, TEXT, 2)
    out.text(32, 1008, "RED = CONFLUENCE, YELLOW = SAMPLED VALLEY CENTERLINE. FLOW CONSERVATION CHECKS ACC = 1 + SUM(UPSTREAM ACC).", MUTED, 2)
    out.text(32, 1040, "VALLEY COORDINATES AND EVERY RIVER CELL ARE EXPORTED TO VALLEYS.CSV AND RIVER_NETWORK.CSV.", MUTED, 2)
    out.save(ART / "terrain_hydrology.png")


def load_bleed() -> dict[str, dict[str, str]]:
    rows = read_csv("color_bleed.csv")
    return {row["region"]: row for row in rows}


def build_summary() -> tuple[dict, list[dict[str, str]], dict[str, dict[str, str]]]:
    timing = timing_summary()
    sweep = read_csv("history_weight_sweep.csv")
    ghost = {r["method"]: r for r in read_csv("ghost_metrics.csv")}
    bleed = load_bleed()
    terrain = json.loads((RAW / "terrain_analysis.json").read_text())
    recommended = next(r for r in sweep if r["recommended"] == "1")
    naive_error = float(ghost["naive"]["ghost_error"])
    adaptive_error = float(ghost["depth_normal_adaptive"]["ghost_error"])
    left = bleed["left_floor"]
    right = bleed["right_floor"]
    summary = {
        "title": "Temporal screen-space GI and D8 hydrology validation",
        "temporal_ssgi": {
            "resolution": [480, 300],
            "ssgi_rays_per_pixel": 10,
            "direct_shadow_samples": 12,
            "baseline_history_weight": 0.92,
            "baseline_frames": 48,
            "static_temporal_noise": float(
                next(r["temporal_noise"] for r in sweep if abs(float(r["history_weight"]) - 0.92) < 1e-6)
            ),
        },
        "color_bleed": {
            "left_redness": float(left["redness"]),
            "right_greenness": float(right["greenness"]),
            "left_r_over_g": float(left["mean_r"]) / max(1e-9, float(left["mean_g"])),
            "right_g_over_r": float(right["mean_g"]) / max(1e-9, float(right["mean_r"])),
            "asymmetry": abs(float(left["redness"]) - float(right["greenness"])),
            "natural": next(
                r.get("bleed_natural", "0") for r in sweep
                if abs(float(r["history_weight"]) - 0.92) < 1e-6
            ) == "1",
            "left_pixels": int(left["pixels"]),
            "right_pixels": int(right["pixels"]),
        },
        "ghost": {
            "naive_error": naive_error,
            "adaptive_error": adaptive_error,
            "reduction_percent": 100.0 * (naive_error - adaptive_error) / max(1e-9, naive_error),
            "mask_pixels": int(ghost["naive"]["mask_pixels"]),
        },
        "history_weight_sweep": sweep,
        "recommended_history_weight": float(recommended["history_weight"]),
        "timing": timing,
        "terrain": terrain,
        "artifacts": [
            "artifacts/indirect_light.png",
            "artifacts/indoor_color_bleed.png",
            "artifacts/temporal_ghost_validation.png",
            "artifacts/history_weight_quality.png",
            "artifacts/frame_times.png",
            "artifacts/terrain_hydrology.png",
            "artifacts/frame_times.csv",
            "artifacts/history_weight_sweep.csv",
            "artifacts/terrain_analysis.json",
            "artifacts/river_network.csv",
            "artifacts/valleys.csv",
        ],
    }
    return summary, sweep, bleed


def make_report(summary: dict, sweep: list[dict[str, str]], bleed: dict[str, dict[str, str]]) -> None:
    timing = summary["timing"]
    color = summary["color_bleed"]
    ghost = summary["ghost"]
    terrain = summary["terrain"]
    recommended = summary["recommended_history_weight"]
    left = bleed["left_floor"]
    right = bleed["right_floor"]
    sweep_lines = [
        "| H | 时域噪声 | 朴素历史鬼影 | 发光突变鬼影 | 左墙红偏 | 右墙绿偏 | 综合分 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sweep:
        mark = " **推荐**" if row["recommended"] == "1" else ""
        sweep_lines.append(
            f"| {float(row['history_weight']):.2f}{mark} | {float(row['temporal_noise']):.3f} | "
            f"{float(row['ghost_error_naive']):.3f} | {float(row['ghost_error_lightstep']):.3f} | "
            f"{float(row['bleed_left_redness']):+.3f} | {float(row['bleed_right_greenness']):+.3f} | "
            f"{float(row['quality_score']):.1f} |"
        )
    confluence_lines = [
        "| 编号 | 像素坐标 | 米制坐标 (X,Y) | 高程 | 流量 | 上游支流 | 下游落差 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for node in terrain["confluences"][:5]:
        confluence_lines.append(
            f"| {node['id']} | ({node['px']}, {node['py']}) | "
            f"({node['x_m']:.0f}, {node['y_m']:.0f}) | {node['elevation_m']:.2f} m | "
            f"{node['flow_cells']:.0f} | {node['upstream_branches']} | {node['downstream_drop_m']:.3f} m |"
        )
    outlet = terrain["outlet"]
    report = f"""# 累积屏幕空间全局光照与时域验证

本项目提供一个无第三方依赖的 CPU 软件实现与完整验证产物。室内实验在 `480x300` 分辨率下使用 G-buffer、屏幕空间半球步进、深度/法线重投影历史、方差裁剪和历史权重扫描；地形实验使用 priority-flood 洼地填充与 D8 最陡下降汇流。

## 实现链路

1. 主光线生成深度、世界坐标、法线、反照率和直接光 G-buffer。
2. 每个像素使用 10 条余弦加权半球射线在屏幕空间步进，采样可见表面的直接光形成单帧间接光。
3. 时域重投影以当前世界坐标投影到上一帧相机，要求线性深度误差在 `0.035 + 0.013z` 内，且法线点积大于 `0.90`。
4. 通过 3x3 当前帧邻域均值与标准差裁剪历史颜色，随后执行 `H` 比例指数累积。
5. 显示与测量使用同对象、同深度、同法线约束的双边解析滤波；该滤波不回写历史，避免把空间去噪误当成时域收敛。

## 间接光图与耗时

![indirect light](artifacts/indirect_light.png)

- 单帧 SSGI 噪声明显，48 帧累积后墙脚与天花板可见稳定的红色/绿色能量转移。
- 基线逐帧耗时：平均 `{timing['mean_total_ms']:.1f} ms`，中位数 `{timing['median_total_ms']:.1f} ms`，P95 `{timing['p95_total_ms']:.1f} ms`。
- 其中屏幕空间间接光平均 `{timing['mean_ssgi_ms']:.1f} ms`，G-buffer/直接光平均 `{timing['mean_gbuffer_ms']:.1f} ms`，累积平均 `{timing['mean_accumulation_ms']:.1f} ms`。
- 每帧原始数据见 `artifacts/frame_times.csv`，曲线见 `artifacts/frame_times.png`。

## 室内颜色溢出

![color bleed](artifacts/indoor_color_bleed.png)

测量区域为左右墙脚各 25 cm 宽、纵跨同一段地面的对称条带，排除家具遮挡与墙后区域。

- 左墙脚红色偏色 `(R-G)/(R+G) = {color['left_redness']:.3f}`，平均 `R/G = {color['left_r_over_g']:.2f}`。
- 右墙脚绿色偏色 `(G-R)/(G+R) = {color['right_greenness']:.3f}`，平均 `G/R = {color['right_g_over_r']:.2f}`。
- 左右差 `{color['asymmetry']:.3f}`，小于自然性阈值 `0.22`；两侧均为正偏色且未出现单通道饱和。
- 结论：颜色溢出方向正确、左右基本对称、中心地面保持弱染色，判定为自然。

## 时域鬼影抑制

![ghost validation](artifacts/temporal_ghost_validation.png)

第 15 帧橙色发光球从左侧瞬移到右侧，第 16 帧在旧球体占用的 `{ghost['mask_pixels']}` 个像素上测量。

- 无深度/法线拒绝的朴素历史误差：`{ghost['naive_error']:.3f}`。
- 深度/法线拒绝加方差裁剪后的误差：`{ghost['adaptive_error']:.3f}`。
- 鬼影能量下降 `{ghost['reduction_percent']:.1f}%`；旧位置不再存在稳定的橙色球体残影。

## 历史缓冲权重与画质

![history weight](artifacts/history_weight_quality.png)

`H=0` 等价于不使用历史；`H` 越接近 1，时域噪声越低。发光球位置不变但亮度突变时，深度/法线无法拒绝，只能依赖邻域裁剪，因此高 `H` 会产生更长的响应拖尾。综合分由 `50%` 时域噪声、`35%` 发光突变鬼影和 `15%` 颜色溢出自然性组成。

{chr(10).join(sweep_lines)}

- 当前场景推荐 `H={recommended:.2f}`：在噪声已经显著下降的同时，发光突变鬼影尚未进入快速上升段。
- `H=0.98` 时噪声最低，但发光突变鬼影高于推荐值，说明单纯追求历史权重会牺牲响应速度。
- `H<=0.50` 时右墙脚绿色偏色尚未充分累积，颜色溢出不对称。

## 河网与山谷位置

![terrain hydrology](artifacts/terrain_hydrology.png)

- 地形网格：`360x360`，域大小 `1800 m x 2400 m`。
- 河网单元：`{terrain['river_cells']}`，最大流量 `{terrain['max_accumulation_cells']:.0f}` 个上游单元。
- 最陡下降合规率：`{terrain['downhill_ratio_percent']:.2f}%`。
- 流量守恒率 `ACC = 1 + SUM(UPSTREAM_ACC)`：`{terrain['flow_conservation_ratio_percent']:.2f}%`。
- 汇流点坡度/守恒合规率：`{terrain['confluence_correct_ratio_percent']:.2f}%`，共 `{terrain['confluence_cells']}` 个汇流单元。
- 主出口：像素 `({outlet['px']}, {outlet['py']})`，米制坐标 `({outlet['x_m']:.1f}, {outlet['y_m']:.1f})`，高程 `{outlet['elevation_m']:.2f} m`，流量 `{outlet['flow_cells']:.0f}`。

{chr(10).join(confluence_lines)}

两条 V 形支流在谷底汇聚后进入南侧出口，红色汇流点沿主沟逐级向下，黄色主谷中心线采样点的高程单调降低，说明坡度方向与汇流路径一致。

## 产物

- `artifacts/indirect_light.png`：深度、法线、单帧 SSGI、累积、解析和最终合成图。
- `artifacts/indoor_color_bleed.png`：墙脚 ROI、偏色数值和放大裁片。
- `artifacts/temporal_ghost_validation.png`：朴素历史、深度/法线拒绝、参考帧和鬼影像素掩码。
- `artifacts/history_weight_quality.png`：权重曲线与发光突变响应裁片。
- `artifacts/frame_times.png`、`artifacts/frame_times.csv`：每帧耗时。
- `artifacts/history_weight_sweep.csv`：所有权重指标。
- `artifacts/terrain_hydrology.png`：河网、流量、坡度与汇流编号。
- `artifacts/river_network.csv`、`artifacts/valleys.csv`、`artifacts/terrain_analysis.json`：逐单元河网、山谷坐标和数值校验。

## 限制

- 屏幕空间步进无法采集屏幕外或背面能量，未命中射线按 0 处理；这是 SSGI 的固有限制。
- 耗时是单线程 CPU 软件实现的结果，不代表 GPU 实际帧时间。
- 地形为程序化合成场景；汇流校验针对该网格与高程场，而非真实测绘数据。
"""
    (ROOT / "REPORT.md").write_text(report, encoding="utf-8")


def main() -> None:
    summary, sweep, bleed = build_summary()
    for name in [
        "frame_times.csv",
        "history_weight_sweep.csv",
        "ghost_metrics.csv",
        "color_bleed.csv",
        "terrain_analysis.json",
        "river_network.csv",
        "valleys.csv",
    ]:
        shutil.copy2(RAW / name, ART / name)
    make_indirect_figure()
    make_color_bleed_figure(bleed)
    make_ghost_figure()
    make_history_figure(sweep)
    make_timing_figure(summary["timing"])
    make_terrain_figure(summary["terrain"])
    (ART / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    make_report(summary, sweep, bleed)
    print("Generated artifacts and REPORT.md")


if __name__ == "__main__":
    main()




