#!/usr/bin/env python3
"""Render PNGs and a Chinese report from one area_lights run."""

from __future__ import annotations

import argparse
import csv
import math
import struct
import zlib
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_config(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["key"]: row["value"] for row in csv.DictReader(handle)}


def png_bytes(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    stride = width * 3
    scanlines = b"".join(
        b"\x00" + pixels[row * stride : (row + 1) * stride]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines, 9))
        + chunk(b"IEND", b"")
    )


def write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(png_bytes(width, height, pixels))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


_COLOR_STOPS = (
    (0.00, (5, 6, 28)),
    (0.12, (28, 24, 92)),
    (0.28, (24, 92, 142)),
    (0.44, (38, 166, 126)),
    (0.60, (210, 194, 62)),
    (0.78, (247, 118, 44)),
    (0.92, (255, 206, 118)),
    (1.00, (255, 250, 226)),
)


def color_map(value: float) -> tuple[int, int, int]:
    value = clamp01(value)
    for index in range(1, len(_COLOR_STOPS)):
        right_position, right_color = _COLOR_STOPS[index]
        if value <= right_position:
            left_position, left_color = _COLOR_STOPS[index - 1]
            amount = (value - left_position) / (
                right_position - left_position
            )
            return tuple(
                round(left + amount * (right - left))
                for left, right in zip(left_color, right_color)
            )
    return _COLOR_STOPS[-1][1]


def source_grid(rows: list[dict[str, str]], field: str) -> list[list[float]]:
    width = max(int(row["ix"]) for row in rows) + 1
    height = max(int(row["iy"]) for row in rows) + 1
    grid = [[0.0 for _ in range(width)] for _ in range(height)]
    for row in rows:
        grid[int(row["iy"])][int(row["ix"])] = float(row[field])
    return grid


def render_grid(
    grid: list[list[float]], scale: int, maximum: float | None = None
) -> tuple[int, int, bytes]:
    source_height = len(grid)
    source_width = len(grid[0])
    width = source_width * scale
    height = source_height * scale
    if maximum is None:
        maximum = max(max(row) for row in grid)
    maximum = max(maximum, 1e-15)
    pixels = bytearray(width * height * 3)
    for out_y in range(height):
        source_y = source_height - 1 - out_y // scale
        for out_x in range(width):
            value = grid[source_y][out_x // scale] / maximum
            red, green, blue = color_map(math.sqrt(clamp01(value)))
            offset = 3 * (out_y * width + out_x)
            pixels[offset : offset + 3] = bytes((red, green, blue))
    return width, height, bytes(pixels)


def stack_images(
    images: list[tuple[int, int, bytes]], gap: int = 5
) -> tuple[int, int, bytes]:
    width = sum(image[0] for image in images) + gap * (len(images) - 1)
    height = max(image[1] for image in images)
    pixels = bytearray(width * height * 3)
    offset_x = 0
    for image_width, image_height, image_pixels in images:
        for y in range(image_height):
            start = 3 * (y * width + offset_x)
            end = start + 3 * image_width
            source = 3 * y * image_width
            pixels[start:end] = image_pixels[source : source + 3 * image_width]
        offset_x += image_width + gap
    return width, height, bytes(pixels)


def render_images(run_dir: Path) -> None:
    image_dir = run_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    shape_rows = read_rows(run_dir / "data" / "parameters.csv")
    shapes = [row["shape"] for row in shape_rows]
    analytic: dict[str, list[list[float]]] = {}
    monte_carlo: dict[str, list[list[float]]] = {}
    visibility: dict[str, list[list[float]]] = {}
    for shape in shapes:
        rows = read_rows(run_dir / "data" / f"{shape}_pixels.csv")
        analytic[shape] = source_grid(rows, "E_analytic_W_m2")
        monte_carlo[shape] = source_grid(rows, "E_monte_carlo_W_m2")
        visibility[shape] = source_grid(rows, "visible_fraction")

    common_maximum = max(
        max(max(row) for row in analytic[shape]) for shape in shapes
    )
    analytic_images = []
    mc_images = []
    shadow_images = []
    for shape in shapes:
        rendered = render_grid(analytic[shape], 2, common_maximum)
        analytic_images.append(rendered)
        write_png(
            image_dir / f"{shape}_irradiance.png",
            rendered[0],
            rendered[1],
            rendered[2],
        )
        mc_images.append(render_grid(monte_carlo[shape], 1, common_maximum))
        shadow_images.append(render_grid(visibility[shape], 2, 1.0))

    width, height, pixels = stack_images(analytic_images)
    write_png(image_dir / "comparison.png", width, height, pixels)
    width, height, pixels = stack_images(shadow_images)
    write_png(image_dir / "shadow_visibility.png", width, height, pixels)
    width, height, pixels = stack_images(mc_images)
    write_png(image_dir / "comparison_mc.png", width, height, pixels)


def combine_tables(run_dir: Path) -> None:
    data_dir = run_dir / "data"
    parameters = read_rows(data_dir / "parameters.csv")
    for suffix, destination in (
        ("_pixels.csv", "pixel_validation.csv"),
        ("_directions.csv", "directions.csv"),
    ):
        combined: list[dict[str, str]] = []
        fieldnames: list[str] = []
        for parameter in parameters:
            rows = read_rows(
                data_dir / f"{parameter['shape']}{suffix}"
            )
            if rows and not fieldnames:
                fieldnames = list(rows[0].keys())
            combined.extend(rows)
        if destination == "directions.csv":
            fieldnames = list(
                read_rows(
                    data_dir / f"{parameters[0]['shape']}{suffix}"
                )[0].keys()
            )
        with (data_dir / destination).open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(combined)


def pct(value: float, digits: int = 3) -> str:
    return f"{100.0 * value:.{digits}f}%"


def write_report(run_dir: Path) -> None:
    data_dir = run_dir / "data"
    config = read_config(data_dir / "run_config.csv")
    parameters = read_rows(data_dir / "parameters.csv")
    summaries = read_rows(data_dir / "pixel_summary.csv")
    penumbras = read_rows(data_dir / "penumbra.csv")
    fluxes = read_rows(data_dir / "flux_validation.csv")
    directions = []
    for parameter in parameters:
        shape = parameter["shape"]
        rows = read_rows(data_dir / f"{shape}_directions.csv")
        directions.extend(
            row
            for row in rows
            if row["probe"] in {"beam_center", "penumbra_50pct"}
        )
    reproducibility_path = data_dir / "reproducibility.csv"
    reproducibility = (
        read_rows(reproducibility_path)
        if reproducibility_path.exists()
        else []
    )
    all_pass = (
        all(row["pass"] == "true" for row in summaries)
        and all(row["pass"] == "true" for row in penumbras)
        and all(row["pass"] == "true" for row in fluxes)
        and (
            not reproducibility
            or all(row["pass"] == "true" for row in reproducibility)
        )
    )

    lines = [
        "# 胶囊体、圆盘与矩形解析面光源验证",
        "",
        "## 结论",
        "",
        (
            "全部给定阈值通过。"
            if all_pass
            else "存在未通过阈值的检查，详见下表。"
        ),
        "",
        (
            f"- 三类光源面积均为 `{float(parameters[0]['area_m2']):.3f} m²`，"
            f"总功率均为 `{float(parameters[0]['power_W']):.3f} W`，"
            "因此具有相同的总能量。"
        ),
        (
            f"- 每像素比较使用 `{config['pixel_width']}×{config['pixel_height']}` "
            f"网格、每像素 `{int(config['pixel_samples'])}` 个固定种子样本。"
        ),
        (
            f"- 总通量蒙特卡洛使用 `{int(config['flux_samples'])}` 个均匀半球方向样本；"
            "解析总通量为 `P = πLA`。"
        ),
        (
            "- 场景以米为单位；接收面为 `z=0`，光源面为 "
            f"`z={float(parameters[0]['source_height_m']):.3f} m`，"
            f"挡板位于 `x={float(parameters[0]['wall_x_m']):.3f} m`、"
            f"顶边 `z={float(parameters[0]['wall_top_z_m']):.3f} m`。"
        ),
        "",
        "## 数值阈值",
        "",
        "| 检查 | 阈值 |",
        "|---|---:|",
        f"| 每像素平均相对误差 | ≤ {pct(float(config['mean_relative_threshold']))} |",
        f"| 每像素 P99 相对误差 | ≤ {pct(float(config['p99_relative_threshold']))} |",
        f"| 每像素归一化 RMSE | ≤ {pct(float(config['normalized_rmse_threshold']))} |",
        f"| 总通量相对误差 | ≤ {pct(float(config['flux_relative_threshold']))} |",
        (
            "| 5%–95% 半影宽度误差 | ≤ "
            f"{float(config['penumbra_width_threshold_m']):.3f} m |"
        ),
        "",
        "## 面光源参数",
        "",
        "| 形状 | 面积 (m²) | 辐亮度 (W·m⁻²·sr⁻¹) | 功率 (W) | x 范围 (m) | y 半宽 (m) |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for row in parameters:
        lines.append(
            f"| {row['shape']} | {float(row['area_m2']):.6f} | "
            f"{float(row['radiance_W_m2_sr']):.6f} | "
            f"{float(row['power_W']):.3f} | "
            f"[{float(row['x_min_m']):.6f}, {float(row['x_max_m']):.6f}] | "
            f"{float(row['y_max_m']):.6f} |"
        )
    capsule = next(row for row in parameters if row["shape"] == "capsule")
    disk = next(row for row in parameters if row["shape"] == "disk")
    rectangle = next(row for row in parameters if row["shape"] == "rectangle")
    lines.extend(
        [
            "",
            (
                "几何尺寸：圆盘半径 "
                f"`{float(disk['radius_m']):.6f} m`；矩形 "
                f"`{float(rectangle['width_x_m']):.3f}×"
                f"{float(rectangle['width_y_m']):.3f} m`；胶囊体半径 "
                f"`{float(capsule['radius_m']):.3f} m`、芯段长度 "
                f"`{float(capsule['core_length_m']):.6f} m`。"
            ),
            "",
            "完整参数表见 [`data/parameters.csv`](data/parameters.csv)。",
            "",
            "## 解析模型",
            "",
            "接收点 `p=(x,y,0)` 到源点 `q=(u,v,H)` 的辐照度为",
            "",
            "```text",
            "E(p) = L H² ∫_A vis(p,u) / (H² + (u-x)² + (v-y)²)² dA",
            "```",
            "",
            (
                "其中 `vis` 是挡板可见性，`L=P/(πA)` 是单侧朗伯辐射亮度。"
                "对固定 `u`，`v` 方向使用闭式原函数；`u` 方向使用 64 点 "
                "Gauss–Legendre 求积，并在阴影边界处切分积分区间。圆盘和"
                "胶囊体圆角使用角度参数化，避免平方根端点误差。Monte Carlo "
                "参考独立地对源面积均匀采样，使用固定种子 PCG32，估计式为 "
                "`E ≈ P/(πN) Σ vis·H²/r⁴`。"
            ),
            "",
        ]
    )

    lines.extend(
        [
            "## 相同能量下的亮度分布",
            "",
            (
                "三种光源使用相同的公共线性色标；面积、辐射亮度和总功率"
                "均相同。色标上限取三类解析图像的最大值。"
            ),
            "",
            "![三类面光源照度图](images/comparison.png)",
            "",
            (
                "单图：[`capsule`](images/capsule_irradiance.png)、"
                "[`disk`](images/disk_irradiance.png)、"
                "[`rectangle`](images/rectangle_irradiance.png)。"
            ),
            "",
            (
                "由于线性照度图的动态范围较大，阴影过渡另以可见比例显示；"
                "深色为全遮挡，亮色为完全可见。"
            ),
            "",
            "![三类面光源可见比例图](images/shadow_visibility.png)",
            "",
            (
                "![每像素 Monte Carlo 参考图]"
                "(images/comparison_mc.png)"
            ),
            "",
            "## 每像素解析解与 Monte Carlo 参考",
            "",
            "| 形状 | 解析峰值 (W/m²) | 平均相对误差 | P99 相对误差 | 归一化 RMSE | 最大归一化误差 | 结果 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    peak_by_shape = {}
    for row in summaries:
        shape = row["shape"]
        peaks = [
            float(pixel["E_analytic_W_m2"])
            for pixel in read_rows(data_dir / f"{shape}_pixels.csv")
        ]
        peak = max(peaks)
        peak_by_shape[shape] = peak
        lines.append(
            f"| {shape} | {peak:.6f} | "
            f"{pct(float(row['mean_relative_error']))} | "
            f"{pct(float(row['p99_relative_error']))} | "
            f"{pct(float(row['normalized_rmse']))} | "
            f"{pct(float(row['max_normalized_error']))} | "
            f"{'通过' if row['pass'] == 'true' else '失败'} |"
        )
    lines.extend(
        [
            "",
            (
                "误差统计排除了低于峰值 1% 的像素，以避免暗区相对误差放大；"
                "归一化 RMSE 使用全图并按解析峰值归一化。"
            ),
            "",
            (
                "逐像素照度、误差、可见比例和半影宽度见 "
                "[`data/pixel_validation.csv`](data/pixel_validation.csv)。"
            ),
            "",
            "## 阴影边缘与半影",
            "",
            "| 形状 | 全阴影结束 x (m) | 半影结束 x (m) | 几何半影宽 (m) | 5–95% 解析宽 (m) | 5–95% MC 宽 (m) | 宽度误差 | 结果 |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in penumbras:
        lines.append(
            f"| {row['shape']} | {float(row['umbra_end_x_m']):.6f} | "
            f"{float(row['penumbra_end_x_m']):.6f} | "
            f"{float(row['geometric_penumbra_width_m']):.6f} | "
            f"{float(row['penumbra_5_95_analytic_m']):.6f} | "
            f"{float(row['penumbra_5_95_mc_m']):.6f} | "
            f"{float(row['width_error_m']):.3e} m | "
            f"{'通过' if row['pass'] == 'true' else '失败'} |"
        )
    lines.extend(
        [
            "",
            (
                "半影宽度由 `y=0` 中心线上核加权可见比例的 5% 与 95% "
                "交点定义；Monte Carlo 侧使用相同固定种子独立求根。"
            ),
            "",
            (
                "完整边缘表见 [`data/penumbra.csv`](data/penumbra.csv)。"
            ),
            "",
            "## 相同能量下的总通量",
            "",
            "| 形状 | 解析功率 (W) | MC 功率 (W) | 相对误差 | 阈值 | 结果 |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in fluxes:
        lines.append(
            f"| {row['shape']} | {float(row['power_analytic_W']):.6f} | "
            f"{float(row['power_monte_carlo_W']):.6f} | "
            f"{pct(float(row['relative_error']))} | "
            f"{pct(float(row['threshold']))} | "
            f"{'通过' if row['pass'] == 'true' else '失败'} |"
        )
    lines.extend(
        [
            "",
            (
                "三类光源均以 `P=100 W` 为统一能量。近场峰值可以不同，但"
                "半球总通量相同；因此逐像素照度和半影宽度是在可比较的"
                "总能量基准下给出的。总通量明细见 "
                "[`data/flux_validation.csv`](data/flux_validation.csv)。"
            ),
            "",
            "## 光照方向与距离衰减样例",
            "",
            (
                "方向为接收点指向光源的单位向量；`centroid` 使用几何中心，"
                "`mean` 是核加权平均源位置对应的方向。"
                "`attenuation=(H/d_c)²`，`d_c` 为到光源几何中心的距离。"
            ),
            "",
            "| 形状 | 探针 | 位置 x (m) | 中心方向 | 加权方向 | 距离 (m) | 衰减 | E (W/m²) |",
            "|---|---|---:|---|---|---:|---:|---:|",
        ]
    )
    for row in directions:
        centroid = (
            f"({float(row['to_light_centroid_x']):.4f}, "
            f"{float(row['to_light_centroid_y']):.4f}, "
            f"{float(row['to_light_centroid_z']):.4f})"
        )
        mean = (
            f"({float(row['mean_to_light_x']):.4f}, "
            f"{float(row['mean_to_light_y']):.4f}, "
            f"{float(row['mean_to_light_z']):.4f})"
        )
        lines.append(
            f"| {row['shape']} | {row['probe']} | "
            f"{float(row['x_m']):.4f} | {centroid} | {mean} | "
            f"{float(row['distance_m']):.4f} | "
            f"{float(row['distance_attenuation']):.5f} | "
            f"{float(row['E_analytic_W_m2']):.5f} |"
        )
    lines.extend(
        [
            "",
            (
                "完整五探针表见 [`data/directions.csv`]"
                "(data/directions.csv)。"
            ),
            "",
        ]
    )

    lines.extend(["## 可复现性", ""])
    if reproducibility:
        lines.extend(
            [
                (
                    "同一可执行文件、同一参数与固定种子独立运行两次；"
                    "下表比较样本估计值和全部数据/图像文件哈希。"
                ),
                "",
                "| 检查 | 第一次 | 第二次 | 绝对差 | 结果 |",
                "|---|---|---|---:|---|",
            ]
        )
        for row in reproducibility:
            lines.append(
                f"| {row['check']} | `{row['run1']}` | "
                f"`{row['run2']}` | {row['absolute_difference']} | "
                f"{'通过' if row['pass'] == 'true' else '失败'} |"
            )
        lines.extend(
            [
                "",
                (
                    "机器可读记录见 "
                    "[`data/reproducibility.csv`]"
                    "(data/reproducibility.csv)。"
                ),
            ]
        )
    else:
        lines.extend(
            [
                (
                    "运行 `make verify` 会独立生成两次并比较全部数据与"
                    "图像哈希，同时写入 `data/reproducibility.csv`。"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            "- [`data/parameters.csv`](data/parameters.csv)：三类面光源参数数值表。",
            (
                "- [`data/pixel_validation.csv`](data/pixel_validation.csv)："
                "每像素解析/MC 照度、误差、可见比例与半影宽度。"
            ),
            "- [`data/penumbra.csv`](data/penumbra.csv)：阴影和半影边缘。",
            "- [`data/flux_validation.csv`](data/flux_validation.csv)：解析与 MC 总通量。",
            "- [`data/directions.csv`](data/directions.csv)：方向、距离与衰减。",
            "- [`images/comparison.png`](images/comparison.png)：公共色标亮度对比。",
            (
                "- [`images/shadow_visibility.png`]"
                "(images/shadow_visibility.png)：阴影边缘与半影可见比例。"
            ),
            "",
        ]
    )
    (run_dir / "report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    combine_tables(args.run_dir)
    render_images(args.run_dir)
    write_report(args.run_dir)


if __name__ == "__main__":
    main()
