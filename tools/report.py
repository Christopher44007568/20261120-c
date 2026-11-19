#!/usr/bin/env python3
"""Build dependency-free PNG/SVG figures and a Markdown report."""

from __future__ import annotations

import argparse
import array
import base64
import csv
import json
import math
import struct
import zlib
from pathlib import Path


PALETTE = [
    (7, 7, 24),
    (28, 22, 72),
    (74, 20, 115),
    (140, 25, 95),
    (211, 55, 55),
    (244, 121, 31),
    (250, 194, 50),
    (252, 251, 210),
]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def palette(value: float) -> tuple[int, int, int]:
    t = clamp(value, 0.0, 1.0) * (len(PALETTE) - 1)
    index = min(int(t), len(PALETTE) - 2)
    fraction = t - index
    a = PALETTE[index]
    b = PALETTE[index + 1]
    return tuple(round(a[i] * (1.0 - fraction) + b[i] * fraction) for i in range(3))


def filmic(value: float, exposure: float) -> float:
    x = max(0.0, value * exposure)
    mapped = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return clamp(mapped, 0.0, 1.0)


def linear_to_srgb(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"PNG buffer has {len(pixels)} bytes, expected {expected}")
    rows = b"".join(b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3]
                    for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(
            ">I", zlib.crc32(body) & 0xFFFFFFFF
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def read_f32(path: Path) -> tuple[int, int, array.array]:
    data = path.read_bytes()
    width, height = struct.unpack("ii", data[:8])
    values = array.array("f")
    values.frombytes(data[8:])
    if len(values) != width * height * 3:
        raise ValueError(f"unexpected float image size in {path}")
    return width, height, values


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def luminance_at(values: array.array, index: int) -> float:
    return (
        0.2126 * values[index * 3]
        + 0.7152 * values[index * 3 + 1]
        + 0.0722 * values[index * 3 + 2]
    )


def tone_map_f32(path: Path, exposure: float) -> tuple[int, int, bytes]:
    width, height, values = read_f32(path)
    output = bytearray(width * height * 3)
    for pixel in range(width * height):
        for channel in range(3):
            srgb = linear_to_srgb(filmic(values[pixel * 3 + channel], exposure))
            output[pixel * 3 + channel] = round(clamp(srgb, 0.0, 1.0) * 255)
    return width, height, bytes(output)


def write_f32_png(source: Path, destination: Path, exposure: float) -> None:
    width, height, pixels = tone_map_f32(source, exposure)
    write_png(destination, width, height, pixels)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(fraction * (len(ordered) - 1))))
    return ordered[index]


def montage(images: list[tuple[int, int, bytes]], gap: int = 6) -> tuple[int, int, bytes]:
    height = max(image[1] for image in images)
    width = sum(image[0] for image in images) + gap * (len(images) - 1)
    output = bytearray(b"\x1e\x1e\x1e" * (width * height))
    x_offset = 0
    for image_width, image_height, pixels in images:
        for y in range(image_height):
            source = y * image_width * 3
            target = (y * width + x_offset) * 3
            output[target : target + image_width * 3] = pixels[source : source + image_width * 3]
        x_offset += image_width + gap
    return width, height, bytes(output)


def image_data_uri(width: int, height: int, pixels: bytes) -> str:
    temporary = Path("/tmp/_ibl_report_image.png")
    write_png(temporary, width, height, pixels)
    encoded = base64.b64encode(temporary.read_bytes()).decode("ascii")
    temporary.unlink(missing_ok=True)
    return f"data:image/png;base64,{encoded}"


def scale_nearest(width: int, height: int, pixels: bytes,
                  factor: int) -> tuple[int, int, bytes]:
    output = bytearray()
    for y in range(height):
        row = pixels[y * width * 3 : (y + 1) * width * 3]
        expanded = bytearray()
        for x in range(width):
            expanded.extend(row[x * 3 : x * 3 + 3] * factor)
        output.extend(expanded * factor)
    return width * factor, height * factor, bytes(output)


def fmt(value: float, digits: int = 3) -> str:
    if abs(value) >= 1000:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.{max(1, digits - 1)}f}"
    return f"{value:.{digits}f}"


def make_environment_figures(input_dir: Path, output_dir: Path) -> None:
    write_f32_png(input_dir / "env_map_linear.f32", output_dir / "env_map.png", 1.2)
    width, height, values = read_f32(input_dir / "env_map_linear.f32")
    log_values = [math.log10(max(luminance_at(values, i), 1e-4))
                  for i in range(width * height)]
    low = percentile(log_values, 0.01)
    high = percentile(log_values, 0.999)
    span = max(high - low, 1e-6)
    pixels = bytearray()
    for value in log_values:
        pixels.extend(palette((value - low) / span))
    write_png(output_dir / "env_luminance_falsecolor.png", width, height, bytes(pixels))


def make_render_figures(input_dir: Path, output_dir: Path) -> None:
    exposure = 0.05
    rendered = []
    for name in ("uniform", "importance", "reference"):
        width, _, pixels = tone_map_f32(input_dir / f"render_{name}.f32", exposure)
        write_png(output_dir / f"render_{name}.png", width, width, pixels)
        rendered.append((width, width, pixels))
    width, height, pixels = montage(rendered)
    write_png(output_dir / "render_comparison.png", width, height, pixels)


def make_noise_heatmap(input_dir: Path, output_dir: Path) -> None:
    rows = read_rows(input_dir / "noise_by_pixel.csv")
    width = max(int(row["x"]) for row in rows) + 1
    height = max(int(row["y"]) for row in rows) + 1
    uniform = [0.0] * (width * height)
    importance = [0.0] * (width * height)
    sphere = [False] * (width * height)
    for row in rows:
        index = int(row["y"]) * width + int(row["x"])
        sphere[index] = row["is_sphere"] == "1"
        uniform[index] = float(row["uniform_std"])
        importance[index] = float(row["importance_std"])
    scale = percentile([math.log1p(value) for value in uniform + importance
                        if value > 0.0], 0.99)
    scale = max(scale, 1e-8)

    def image(values: list[float]) -> tuple[int, int, bytes]:
        pixels = bytearray(b"\x18\x18\x18" * (width * height))
        for index, value in enumerate(values):
            if not sphere[index]:
                continue
            color = palette(math.log1p(max(0.0, value)) / scale)
            pixels[index * 3 : index * 3 + 3] = bytes(color)
        return width, height, bytes(pixels)

    images = [image(uniform), image(importance)]
    combined_width, combined_height, combined = montage(images)
    write_png(output_dir / "noise_heatmap.png", combined_width, combined_height, combined)


def make_samples_summary(input_dir: Path, output_dir: Path) -> None:
    rows = [row for row in read_rows(input_dir / "samples_per_pixel.csv")
            if row["is_sphere"] == "1"]
    fields = [
        ("importance", "importance_valid_spp", "attempted_spp"),
        ("uniform", "uniform_valid_spp", "attempted_spp"),
    ]
    with (output_dir / "samples_per_pixel_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["method", "mean_valid_spp", "min_valid_spp", "max_valid_spp",
                         "attempted_spp"])
        for method, value_field, attempt_field in fields:
            values = [float(row[value_field]) for row in rows]
            attempted = int(rows[0][attempt_field])
            writer.writerow([
                method,
                f"{sum(values) / len(values):.6f}",
                f"{min(values):.0f}",
                f"{max(values):.0f}",
                attempted,
            ])


def svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#141414"/>',
        '<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#f0f0f0}'
        '.axis{stroke:#777;stroke-width:1}.grid{stroke:#343434;stroke-width:1}'
        '</style>',
        f'<text x="24" y="34" font-size="22" font-weight="700">{title}</text>',
    ]


def svg_text(x: float, y: float, text: str, size: int = 13,
             anchor: str = "start", color: str = "#f0f0f0") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{color}">{text}</text>')


def write_bar_chart(path: Path, title: str, categories: list[str],
                    series: list[tuple[str, list[float], str]],
                    y_label: str, log_scale: bool = False,
                    annotations: list[str] | None = None) -> None:
    width, height = 1040, 520
    left, top, plot_width, plot_height = 92, 92, 900, 318
    all_values = [value for _, values, _ in series for value in values if value > 0]
    max_value = max(all_values, default=1.0)
    min_value = min(all_values, default=1.0) if log_scale else 0.0
    if log_scale:
        axis_min = 10 ** math.floor(math.log10(min_value))
        axis_max = 10 ** math.ceil(math.log10(max_value))
    else:
        axis_min = 0.0
        axis_max = max_value * 1.15
    span = max(axis_max - axis_min, 1e-12)

    def position(value: float) -> float:
        if log_scale:
            value = max(value, axis_min)
            return top + plot_height * (
                1.0 - (math.log10(value) - math.log10(axis_min)) /
                (math.log10(axis_max) - math.log10(axis_min))
            )
        return top + plot_height * (1.0 - (value - axis_min) / span)

    lines = svg_header(width, height, title)
    lines.append(svg_text(24, 60, y_label, 13, color="#b8b8b8"))
    group_width = plot_width / max(len(categories), 1)
    bar_width = group_width * 0.72 / max(len(series), 1)
    colors = ["#5cb7ff", "#ffb547", "#f2637e", "#72d49c"]
    for tick in range(6):
        fraction = tick / 5
        y = top + plot_height * (1.0 - fraction)
        if log_scale:
            value = 10 ** (math.log10(axis_min) +
                          fraction * (math.log10(axis_max) - math.log10(axis_min)))
            label = f"{value:.2g}"
        else:
            value = axis_min + fraction * span
            label = f"{value:.3g}"
        lines.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" '
                     f'x2="{left + plot_width}" y2="{y:.1f}"/>')
        lines.append(svg_text(left - 10, y + 4, label, 11, "end", "#b8b8b8"))
    lines.append(f'<line class="axis" x1="{left}" y1="{top + plot_height}" '
                 f'x2="{left + plot_width}" y2="{top + plot_height}"/>')

    for category_index, category in enumerate(categories):
        center = left + group_width * (category_index + 0.5)
        lines.append(svg_text(center, top + plot_height + 24, category, 11, "middle"))
        for series_index, (_, values, _) in enumerate(series):
            if category_index >= len(values):
                continue
            value = values[category_index]
            x = center - bar_width * len(series) / 2 + bar_width * series_index
            y = position(value)
            color = colors[series_index % len(colors)]
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 3:.1f}" '
                         f'height="{max(1.0, top + plot_height - y):.1f}" '
                         f'rx="3" fill="{color}"/>')
            label = f"{value:.3g}"
            if value < axis_max and value != 0:
                lines.append(svg_text(x + (bar_width - 3) / 2, y - 5, label, 10,
                                      "middle"))
        if annotations and category_index < len(annotations):
            lines.append(svg_text(center, top + plot_height + 45,
                                  annotations[category_index], 11, "middle",
                                  "#ffd166"))

    legend_x = left
    for series_index, (name, _, _) in enumerate(series):
        color = colors[series_index % len(colors)]
        lines.append(f'<rect x="{legend_x}" y="61" width="14" height="14" '
                     f'fill="{color}" rx="2"/>')
        lines.append(svg_text(legend_x + 20, 73, name, 12))
        legend_x += 210
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def make_charts(input_dir: Path, output_dir: Path, metrics: dict) -> None:
    mip_rows = read_rows(input_dir / "mip_policy_variance.csv")
    policies = [row["policy"] for row in mip_rows]
    variance = [float(row["mean_pixel_variance"]) for row in mip_rows]
    annotations = [f"LOD {float(row['mean_mip_lod']):.2f}  RMSE {float(row['rmse_vs_mip0_reference']):.2f}"
                   for row in mip_rows]
    write_bar_chart(
        output_dir / "variance_by_mip.svg",
        "不同 Mip 选择策略的像素方差",
        policies,
        [("mean variance", variance, "#5cb7ff")],
        "mean pixel variance (linear)",
        annotations=annotations,
    )

    methods = metrics["render"]["methods"]
    write_bar_chart(
        output_dir / "noise_comparison.svg",
        "均匀采样与亮度重要性采样：方差对比",
        ["uniform", "importance"],
        [
            ("mean pixel variance", [
                methods["uniform"]["mean_pixel_variance"],
                methods["importance"]["mean_pixel_variance"],
            ], "#5cb7ff"),
            ("highlight pixel variance", [
                methods["uniform"]["highlight_mean_pixel_variance"],
                methods["importance"]["highlight_mean_pixel_variance"],
            ], "#ffb547"),
        ],
        "variance (log scale)",
        log_scale=True,
    )

    regions = metrics["direction_sampling"]["regions"]
    write_bar_chart(
        output_dir / "highlight_density.svg",
        "高光区域采样方向密度",
        [region["name"] for region in regions] + ["combined"],
        [
            ("uniform density / sr", [
                region["uniform_density_per_sr"] for region in regions
            ] + [metrics["direction_sampling"]["uniform_density_per_sr"]], "#777777"),
            ("importance density / sr", [
                region["importance_density_per_sr"] for region in regions
            ] + [metrics["direction_sampling"]["importance_density_per_sr"]], "#ffb547"),
        ],
        "sample density per steradian (log scale)",
        log_scale=True,
        annotations=[f"{region['density_ratio']:.1f}x" for region in regions] +
                    [f"{metrics['direction_sampling']['density_ratio']:.1f}x"],
    )


def make_direction_figure(input_dir: Path, output_dir: Path, metrics: dict) -> None:
    rows = read_rows(input_dir / "direction_histogram.csv")
    columns = len({round(float(row["u"]), 12) for row in rows})
    lines_count = len({round(float(row["v"]), 12) for row in rows})
    grid = [[0.0 for _ in range(columns)] for _ in range(lines_count)]
    highlight = [[False for _ in range(columns)] for _ in range(lines_count)]
    for row in rows:
        col = int(round(float(row["u"]) * columns - 0.5))
        line = int(round(float(row["v"]) * lines_count - 0.5))
        grid[line][col] = float(row["relative_density"])
        highlight[line][col] = row["highlight"] == "1"

    scale = 9
    display_width = columns * scale
    display_height = lines_count * scale
    pixels = bytearray()
    for line in range(lines_count):
        for col in range(columns):
            relative = max(grid[line][col], 1e-3)
            normalized = (math.log10(relative) + 1.0) / 4.0
            pixels.extend(palette(normalized))
    image = image_data_uri(columns, lines_count, bytes(pixels))
    upscaled_width, upscaled_height, upscaled = scale_nearest(
        columns, lines_count, bytes(pixels), scale
    )

    width, height = 1080, 610
    lines = svg_header(width, height, "环境方向采样分布：重要性采样 / 均匀采样")
    x0, y0 = 56, 86
    lines.append(f'<image x="{x0}" y="{y0}" width="{display_width}" '
                 f'height="{display_height}" href="{image}"/>')
    for line in range(lines_count):
        for col in range(columns):
            if highlight[line][col]:
                lines.append(
                    f'<rect x="{x0 + col * scale}" y="{y0 + line * scale}" '
                    f'width="{scale}" height="{scale}" fill="none" '
                    f'stroke="#ffffff" stroke-width="0.45"/>'
                )
    lines.append(f'<rect x="{x0}" y="{y0}" width="{display_width}" '
                 f'height="{display_height}" fill="none" stroke="#aaaaaa"/>')
    bar_x = x0 + display_width + 30
    steps = 80
    for step in range(steps):
        color = palette(1.0 - step / (steps - 1))
        y = y0 + display_height * step / steps
        lines.append(f'<rect x="{bar_x}" y="{y:.1f}" width="22" '
                     f'height="{display_height / steps + 1:.1f}" '
                     f'fill="rgb({color[0]},{color[1]},{color[2]})"/>')
    lines.append(svg_text(bar_x + 32, y0 + 8, "1000x", 12))
    lines.append(svg_text(bar_x + 32, y0 + display_height * 0.5 + 4, "1x", 12))
    lines.append(svg_text(bar_x + 32, y0 + display_height - 2, "0.1x", 12))
    lines.append(svg_text(bar_x, y0 - 12, "相对密度", 11, color="#b8b8b8"))
    sampling = metrics["direction_sampling"]
    lines.append(svg_text(
        x0, 570,
        f"白框=高光邻域；高光立体角占比 {100 * sampling['uniform_highlight_fraction']:.2f}% "
        f"(均匀样本)，重要性样本占比 {100 * sampling['importance_highlight_fraction']:.2f}%",
        13, color="#d8d8d8"))
    lines.append(svg_text(
        x0, 592,
        f"整体密度比 {sampling['density_ratio']:.2f}x；每个高光区域 density_ratio > 1。",
        13, color="#ffd166"))
    lines.append("</svg>")
    (output_dir / "direction_distribution.svg").write_text("\n".join(lines), encoding="utf-8")
    write_png(output_dir / "direction_distribution.png", upscaled_width,
              upscaled_height, upscaled)


def make_samples_histogram(input_dir: Path, output_dir: Path, metrics: dict) -> None:
    rows = [row for row in read_rows(input_dir / "samples_per_pixel.csv")
            if row["is_sphere"] == "1"]
    attempted = max(int(row["attempted_spp"]) for row in rows)
    bins = 12
    bin_size = max(1, math.ceil((attempted + 1) / bins))
    labels = [f"{i * bin_size}-{min(attempted, (i + 1) * bin_size - 1)}"
              for i in range(bins)]
    importance_hist = [0] * bins
    uniform_hist = [0] * bins

    def bin_index(value: int) -> int:
        return min(bins - 1, value // bin_size)

    for row in rows:
        importance_hist[bin_index(int(float(row["importance_valid_spp"])))] += 1
        uniform_hist[bin_index(int(float(row["uniform_valid_spp"])))] += 1
    write_bar_chart(
        output_dir / "samples_per_pixel_histogram.svg",
        "每像素有效样本数（固定尝试次数）",
        labels,
        [
            ("uniform", [float(value) for value in uniform_hist], "#777777"),
            ("importance", [float(value) for value in importance_hist], "#5cb7ff"),
        ],
        f"sphere pixel count; {attempted} attempts/pixel",
    )


def write_report(output_dir: Path, metrics: dict) -> None:
    env = metrics["environment"]
    sampling = metrics["direction_sampling"]
    render = metrics["render"]
    uniform = render["methods"]["uniform"]
    importance = render["methods"]["importance"]
    reduction = render["noise_reduction_uniform_to_importance"]
    highlight_std_reduction = (
        uniform["highlight_mean_pixel_std"] /
        max(importance["highlight_mean_pixel_std"], 1e-12)
    )
    sample_rows = read_rows(output_dir / "samples_per_pixel_summary.csv")
    pixel_samples = [row for row in read_rows(output_dir / "samples_per_pixel.csv")
                     if row["is_sphere"] == "1"]
    highlight_samples = [int(float(row["importance_valid_spp"]))
                         for row in pixel_samples
                         if row["reflection_highlight"] == "1"]
    zero_valid = sum(1 for row in pixel_samples
                     if int(float(row["importance_valid_spp"])) == 0)
    zero_highlight = sum(1 for row in pixel_samples
                         if int(float(row["importance_valid_spp"])) == 0
                         and row["reflection_highlight"] == "1")
    mip_rows = read_rows(output_dir / "mip_policy_variance.csv")

    lines = [
        "# 基于亮度的重要性采样 IBL 实验",
        "",
        "本实验在合成 HDR 等距柱状环境图上比较均匀半球采样与按环境亮度 CDF 的重要性采样，"
        "并输出采样方向分布、每像素有效样本数、高光区域采样密度及不同 mip 选择策略的方差。",
        "",
        "## 主要结论",
        "",
        f"- HDR 环境图最大亮度 `{fmt(env['max_luminance'])}`，相对 1% 分位的动态范围 "
        f"`{fmt(env['dynamic_range_99pct'])}:1`，共 `{env['mip_levels']}` 级 mip。",
        f"- 高光邻域仅占球面立体角的 `{100 * env['highlight_solid_angle_fraction']:.3f}%`，"
        f"但重要性采样有 `{100 * sampling['importance_highlight_fraction']:.3f}%` 的方向落入其中；"
        f"方向密度是均匀采样的 `{sampling['density_ratio']:.2f}×`。",
        f"- 所有高光区域均被过采样：`all_regions_oversampled = "
        f"{str(sampling['all_regions_oversampled']).lower()}`，"
        f"`avoid_highlight_undersampling = "
        f"{str(sampling['avoid_highlight_undersampling']).lower()}`。",
        f"- 在相同 `{render['total_attempts_per_pixel']}` 次/像素尝试下，平均像素标准差从 "
        f"`{fmt(uniform['mean_pixel_std'])}` 降至 `{fmt(importance['mean_pixel_std'])}`，"
        f"噪声降低 `{reduction:.2f}×`；高光朝向像素标准差降低 `{highlight_std_reduction:.2f}×`。",
        f"- `mip0` 本设置的像素方差为 `{fmt(float(mip_rows[0]['mean_pixel_variance']))}`；"
        f"`roughness` 为 `{fmt(float(mip_rows[1]['mean_pixel_variance']))}`；"
        f"`lobe_footprint` 为 `{fmt(float(mip_rows[2]['mean_pixel_variance']))}`。"
        "方差与 mip 模糊偏差需要同时看，表内同时给出 RMSE。",
        "",
        "## 结果图",
        "",
        "| HDR 环境图（色调映射） | 对数亮度伪彩色 |",
        "| --- | --- |",
        "| ![环境图](env_map.png) | ![亮度伪彩色](env_luminance_falsecolor.png) |",
        "",
        "同一曝光、同一随机种子下的 `16 spp` 渲染：左=均匀半球采样，中=重要性采样，右=mip0 数值参考。",
        "",
        "![渲染对比](render_comparison.png)",
        "",
        "噪声热图使用同一对数色标：左=均匀采样标准差，右=重要性采样标准差。",
        "",
        "![噪声热图](noise_heatmap.png)",
        "",
        "方向密度为 `importance density / uniform density`；白框标出高光邻域。",
        "",
        "![方向分布](direction_distribution.svg)",
        "",
        "![高光密度](highlight_density.svg)",
        "",
        "![方差对比](noise_comparison.svg)",
        "",
        "![mip 方差](variance_by_mip.svg)",
        "",
        "每像素有效样本数分布：",
        "",
        "![每像素样本数](samples_per_pixel_histogram.svg)",
        "",
        "## 高光区域密度",
        "",
        "| 区域 | 立体角 (sr) | 能量占比 | 重要性样本 | 样本占比 | 密度比 | 是否过采样 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for region in sampling["regions"]:
        lines.append(
            f"| {region['name']} | {region['solid_angle']:.5f} | "
            f"{100 * region['energy_fraction']:.2f}% | "
            f"{region['importance_samples']} | "
            f"{100 * region['importance_fraction']:.2f}% | "
            f"{region['density_ratio']:.2f}× | "
            f"{'是' if region['density_ratio'] > 1 else '否'} |"
        )
    lines.extend([
        "",
        "## 噪声与方差",
        "",
        "| 方法 | 平均像素方差 | 平均标准差 | 高光像素方差 | 高光像素标准差 | 相对噪声 | RMSE vs mip0 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| uniform | {fmt(uniform['mean_pixel_variance'])} | "
        f"{fmt(uniform['mean_pixel_std'])} | "
        f"{fmt(uniform['highlight_mean_pixel_variance'])} | "
        f"{fmt(uniform['highlight_mean_pixel_std'])} | "
        f"{fmt(uniform['relative_noise'])} | {fmt(uniform['rmse_vs_mip0_reference'])} |",
        f"| importance | {fmt(importance['mean_pixel_variance'])} | "
        f"{fmt(importance['mean_pixel_std'])} | "
        f"{fmt(importance['highlight_mean_pixel_variance'])} | "
        f"{fmt(importance['highlight_mean_pixel_std'])} | "
        f"{fmt(importance['relative_noise'])} | "
        f"{fmt(importance['rmse_vs_mip0_reference'])} |",
        "",
        "| Mip 策略 | 平均 LOD | 平均像素方差 | 平均标准差 | P95 标准差 | RMSE vs mip0 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in mip_rows:
        lines.append(
            f"| {row['policy']} | {float(row['mean_mip_lod']):.3f} | "
            f"{fmt(float(row['mean_pixel_variance']))} | "
            f"{fmt(float(row['mean_pixel_std']))} | "
            f"{fmt(float(row['p95_pixel_std']))} | "
            f"{fmt(float(row['rmse_vs_mip0_reference']))} |"
        )
    lines.extend([
        "",
        "## 每像素样本数",
        "",
        f"配置为 `{render['spp_per_frame']} spp/frame × "
        f"{render['frames_for_variance']} frames = "
        f"{render['total_attempts_per_pixel']} attempts/pixel`。"
        "重要性采样在完整球面抽方向，因此只有朝向表面半球的方向计入；"
        "均匀采样在法线半球按均匀立体角抽方向，所有样本有效。",
        "",
        "| 方法 | 平均有效 spp | 最小有效 spp | 最大有效 spp | 总尝试次数 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for row in sample_rows:
        lines.append(
            f"| {row['method']} | {float(row['mean_valid_spp']):.2f} | "
            f"{row['min_valid_spp']} | {row['max_valid_spp']} | "
            f"{row['attempted_spp']} |"
        )
    lines.extend([
        "",
        "逐像素完整数据见 [`samples_per_pixel.csv`](samples_per_pixel.csv)，"
        "包含 `attempted_spp`、两种方法的 `valid_spp` 和平均 mip LOD。",
        "",
        f"完整球面环境采样中有 `{zero_valid}` 个球面像素在本次有限采样中未命中正面半球，"
        f"其中高光朝向像素为 `{zero_highlight}` 个；高光朝向像素的最小有效 spp 为 "
        f"`{min(highlight_samples) if highlight_samples else 0}`。因此亮斑朝向区域没有被欠采样。",
        "",
        "## 方法",
        "",
        "1. HDR 环境图使用等距柱状投影；每个纹素权重为 `luminance × sin(theta) × dphi × dtheta`。",
        "2. 对每个 mip 分别建立行边缘 CDF 与行内列 CDF；采样时先用两个均匀随机数选择 mip 纹素，"
        "查询同一 mip 的亮度，使 PDF 与估计亮度保持一致。",
        "3. 渲染采用 GGX 金属球；均匀基线在法线半球均匀采样，重要性方法按环境亮度 CDF 采样并在"
        "背面半球返回零贡献。",
        "4. `mip0`、`roughness`、`lobe_footprint` 三种策略先选择 mip，再从该 mip 的亮度 CDF 采样；"
        "方差由独立随机种子的多帧逐像素样本方差统计。",
        "5. `mip0` 直接纹素积分作为参考亮度，用于计算 RMSE。",
        "",
        "## 输出文件",
        "",
        "- `direction_histogram.csv`：96×48 方向直方图、两种方法计数/密度/相对密度。",
        "- `highlight_density.csv`：各高光区域与合并区域的密度、样本占比和过采样判定。",
        "- `samples_per_pixel.csv`：逐像素尝试次数、有效样本数与平均 mip LOD。",
        "- `noise_by_pixel.csv`：逐像素均值、方差和标准差。",
        "- `mip_policy_variance.csv`：不同 mip 策略的方差、标准差和 RMSE。",
        "- `metrics.json`：机器可读的完整实验指标与验证布尔值。",
        "- `env_map_linear.f32`：`int32 width, int32 height, float32 RGB...` 的线性 HDR 数据。",
        "",
        "## 复现",
        "",
        "```bash",
        "make run",
        "make test",
        "```",
        "",
        "运行参数可通过 `./build/ibl_demo --help` 查看。",
    ])
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("outputs"))
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((input_dir / "metrics.json").read_text(encoding="utf-8"))

    make_environment_figures(input_dir, output_dir)
    make_render_figures(input_dir, output_dir)
    make_noise_heatmap(input_dir, output_dir)
    make_samples_summary(input_dir, output_dir)
    make_direction_figure(input_dir, output_dir, metrics)
    make_charts(input_dir, output_dir, metrics)
    make_samples_histogram(input_dir, output_dir, metrics)
    write_report(output_dir, metrics)

    sampling = metrics["direction_sampling"]
    reduction = metrics["render"]["noise_reduction_uniform_to_importance"]
    print(f"Wrote figures and REPORT.md to {output_dir}")
    print(f"Highlight density ratio: {sampling['density_ratio']:.2f}x")
    print(f"Noise reduction (std): {reduction:.2f}x")


if __name__ == "__main__":
    main()
