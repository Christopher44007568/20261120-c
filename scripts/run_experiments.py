#!/usr/bin/env python3
"""Reproducible PT/BDPT convergence and equal-time benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path


SCENES = ("indirect", "interior", "caustic")
METHODS = ("pt", "bdpt")
DEFAULT_SPP = (1, 2, 4, 8, 16, 32, 64, 128, 256)
REFERENCE_SPP = {"indirect": 4096, "interior": 4096, "caustic": 8192}
CAUSTIC_ROI = (0.35, 0.65, 0.60, 0.85)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--height", type=int, default=120)
    parser.add_argument("--threads", type=int,
                        default=min(12, os.cpu_count() or 1))
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--time-budget", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--reuse-reference", action="store_true")
    return parser.parse_args()


def run_render(binary: Path, scene: str, method: str, width: int, height: int,
               threads: int, max_depth: int, out_base: Path, seed: int,
               spp: int = 0, time_limit: float = 0.0) -> dict[str, str]:
    cmd = [
        str(binary), "render", "--scene", scene, "--integrator", method,
        "--width", str(width), "--height", str(height), "--threads", str(threads),
        "--max-depth", str(max_depth), "--out", str(out_base), "--seed", str(seed),
    ]
    if time_limit > 0.0:
        cmd.extend(["--time", f"{time_limit:.6f}"])
    else:
        cmd.extend(["--spp", str(spp)])
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    fields = {}
    for item in proc.stdout.strip().split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            fields[key] = value
    return fields


def read_pfm(path: Path) -> tuple[int, int, list[tuple[float, float, float]]]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"PF":
            raise ValueError(f"Not a PFM file: {path}")
        width, height = map(int, handle.readline().split())
        scale = float(handle.readline())
        raw = handle.read()
    values = struct.unpack("<%df" % (width * height * 3), raw)
    pixels = list(zip(values[0::3], values[1::3], values[2::3]))
    if scale > 0.0:
        pixels = [(r / scale, g / scale, b / scale) for r, g, b in pixels]
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    rows.reverse()
    return width, height, [p for row in rows for p in row]


def luminance(pixel: tuple[float, float, float]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def region_indices(width: int, height: int,
                   roi: tuple[float, float, float, float] | None) -> list[int]:
    if roi is None:
        return list(range(width * height))
    x0, y0, x1, y1 = roi
    left = max(0, int(x0 * width))
    right = min(width, int(math.ceil(x1 * width)))
    top = max(0, int(y0 * height))
    bottom = min(height, int(math.ceil(y1 * height)))
    return [y * width + x for y in range(top, bottom) for x in range(left, right)]


def image_metrics(image: list[tuple[float, float, float]],
                  reference: list[tuple[float, float, float]],
                  indices: list[int]) -> dict[str, float]:
    mse = 0.0
    lum_mse = 0.0
    ref_energy = 0.0
    abs_lum = 0.0
    for i in indices:
        a, b = image[i], reference[i]
        mse += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 +
                (a[2] - b[2]) ** 2) / 3.0
        ref_lum = luminance(b)
        lum_mse += (luminance(a) - ref_lum) ** 2
        ref_energy += ref_lum * ref_lum
        abs_lum += abs(luminance(a) - ref_lum)
    count = float(len(indices))
    mse /= count
    lum_mse /= count
    ref_energy /= count
    return {
        "mse": mse,
        "rmse": math.sqrt(mse),
        "relative_rmse": math.sqrt(lum_mse / ref_energy) if ref_energy > 0 else 0.0,
        "mean_abs_lum": abs_lum / count,
    }


def population_variance(images: list[list[tuple[float, float, float]]],
                        indices: list[int]) -> tuple[float, float]:
    if len(images) < 2:
        return 0.0, 0.0
    variance_sum = 0.0
    mean_sum = 0.0
    for i in indices:
        values = [luminance(img[i]) for img in images]
        mean = sum(values) / len(values)
        variance_sum += sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        mean_sum += mean
    count = float(len(indices))
    return variance_sum / count, mean_sum / count


def read_ppm(path: Path) -> tuple[int, int, bytes]:
    with path.open("rb") as handle:
        if handle.readline().strip() != b"P6":
            raise ValueError(f"Not a PPM file: {path}")
        width, height = map(int, handle.readline().split())
        if handle.readline().strip() != b"255":
            raise ValueError("Only 8-bit PPM files are supported")
        return width, height, handle.read()


def write_png_from_ppm(ppm_path: Path, png_path: Path) -> None:
    width, height, data = read_ppm(ppm_path)
    rows = b"".join(b"\x00" + data[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
           chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
    png_path.write_bytes(png)


def svg_error_curves(path: Path, data: dict[str, dict[str, list[dict]]]) -> None:
    panel_w, panel_h = 480, 360
    margin_l, margin_r, margin_t, margin_b = 58, 18, 40, 48
    width = panel_w * 3
    height = panel_h + 52
    colors = {"pt": "#d95f02", "bdpt": "#1b6ca8"}
    names = {"pt": "Unidirectional PT", "bdpt": "BDPT + MIS"}
    all_values = [row["mse_mean"] for scene in SCENES for method in METHODS
                  for row in data[scene][method] if row["mse_mean"] > 0]
    y_min = 10 ** math.floor(math.log10(min(all_values)))
    y_max = 10 ** math.ceil(math.log10(max(all_values)))
    spp_values = sorted({row["spp"] for scene in SCENES for method in METHODS
                         for row in data[scene][method]})
    x_min, x_max = min(spp_values), max(spp_values)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<style>text{font-family:Inter,Arial,sans-serif;fill:#222}'
        '.title{font-size:16px;font-weight:600}.axis{font-size:11px}'
        '.label{font-size:12px}</style>',
        f'<text x="18" y="24" class="title">Error vs high-sample BDPT reference</text>',
    ]
    for panel, scene in enumerate(SCENES):
        ox = panel * panel_w
        plot_x0 = ox + margin_l
        plot_y0 = margin_t
        plot_w = panel_w - margin_l - margin_r
        plot_h = panel_h - margin_t - margin_b

        def xmap(spp: float) -> float:
            return plot_x0 + ((math.log10(spp) - math.log10(x_min)) /
                              (math.log10(x_max) - math.log10(x_min))) * plot_w

        def ymap(value: float) -> float:
            return (plot_y0 + plot_h -
                    ((math.log10(max(value, y_min)) - math.log10(y_min)) /
                     (math.log10(y_max) - math.log10(y_min))) * plot_h)

        parts.append(f'<text x="{plot_x0}" y="32" class="title">{scene}</text>')
        for decade in range(int(math.log10(y_min)), int(math.log10(y_max)) + 1):
            value = 10 ** decade
            y = ymap(value)
            parts.append(f'<line x1="{plot_x0}" y1="{y:.2f}" x2="{plot_x0+plot_w}" '
                         f'y2="{y:.2f}" stroke="#dedbd3" stroke-width="1"/>')
            parts.append(f'<text x="{plot_x0-8}" y="{y+4:.2f}" text-anchor="end" '
                         f'class="axis">{value:g}</text>')
        for spp in spp_values:
            x = xmap(spp)
            parts.append(f'<line x1="{x:.2f}" y1="{plot_y0}" x2="{x:.2f}" '
                         f'y2="{plot_y0+plot_h}" stroke="#ece9e2" stroke-width="1"/>')
            parts.append(f'<text x="{x:.2f}" y="{plot_y0+plot_h+18}" '
                         f'text-anchor="middle" class="axis">{spp}</text>')
        parts.append(f'<line x1="{plot_x0}" y1="{plot_y0+plot_h}" '
                     f'x2="{plot_x0+plot_w}" y2="{plot_y0+plot_h}" '
                     f'stroke="#777" stroke-width="1.2"/>')
        parts.append(f'<line x1="{plot_x0}" y1="{plot_y0}" x2="{plot_x0}" '
                     f'y2="{plot_y0+plot_h}" stroke="#777" stroke-width="1.2"/>')

        for method in METHODS:
            rows = data[scene][method]
            points = " ".join(f"{xmap(row['spp']):.2f},{ymap(row['mse_mean']):.2f}"
                              for row in rows)
            parts.append(f'<polyline points="{points}" fill="none" '
                         f'stroke="{colors[method]}" stroke-width="2.2"/>')
            for row in rows:
                parts.append(f'<circle cx="{xmap(row["spp"]):.2f}" '
                             f'cy="{ymap(row["mse_mean"]):.2f}" r="2.8" '
                             f'fill="{colors[method]}"/>')
        parts.append(f'<text x="{plot_x0+plot_w/2}" y="{panel_h-8}" '
                     f'text-anchor="middle" class="label">samples per pixel</text>')
        if panel == 0:
            parts.append(f'<text x="14" y="{plot_y0+plot_h/2}" class="label" '
                         f'transform="rotate(-90 14 {plot_y0+plot_h/2})" '
                         f'text-anchor="middle">MSE (log scale)</text>')

    legend_y = height - 12
    for i, method in enumerate(METHODS):
        x = 80 + i * 190
        parts.append(f'<line x1="{x}" y1="{legend_y}" x2="{x+24}" y2="{legend_y}" '
                     f'stroke="{colors[method]}" stroke-width="2.2"/>')
        parts.append(f'<text x="{x+30}" y="{legend_y+4}" class="label">'
                     f'{names[method]}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_equal_time(path: Path, rows: list[dict], budget: float) -> None:
    width, height = 900, 460
    left, right, top, bottom = 76, 28, 54, 82
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = {"pt": "#d95f02", "bdpt": "#1b6ca8"}
    names = {"pt": "Unidirectional PT", "bdpt": "BDPT + MIS"}
    values = [row["mse_mean"] for row in rows if row["mse_mean"] > 0]
    y_min = 10 ** math.floor(math.log10(min(values)))
    y_max = 10 ** math.ceil(math.log10(max(values)))

    def ymap(value: float) -> float:
        return (top + plot_h -
                ((math.log10(max(value, y_min)) - math.log10(y_min)) /
                 (math.log10(y_max) - math.log10(y_min))) * plot_h)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<style>text{font-family:Inter,Arial,sans-serif;fill:#222}'
        '.title{font-size:17px;font-weight:600}.axis{font-size:11px}'
        '.label{font-size:12px}.value{font-size:10px;font-weight:600}</style>',
        f'<text x="20" y="26" class="title">Equal wall-clock error '
        f'({budget:.1f} s budget)</text>',
    ]
    for decade in range(int(math.log10(y_min)), int(math.log10(y_max)) + 1):
        value = 10 ** decade
        y = ymap(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left+plot_w}" '
                     f'y2="{y:.2f}" stroke="#dedbd3"/>')
        parts.append(f'<text x="{left-9}" y="{y+4:.2f}" text-anchor="end" '
                     f'class="axis">{value:g}</text>')
    parts.append(f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" '
                 f'y2="{top+plot_h}" stroke="#777" stroke-width="1.2"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" '
                 f'stroke="#777" stroke-width="1.2"/>')
    parts.append(f'<text x="16" y="{top+plot_h/2}" class="label" '
                 f'transform="rotate(-90 16 {top+plot_h/2})" '
                 f'text-anchor="middle">MSE (log scale)</text>')

    group_w = plot_w / len(SCENES)
    bar_w = group_w * 0.26
    for scene_index, scene in enumerate(SCENES):
        center = left + group_w * (scene_index + 0.5)
        parts.append(f'<text x="{center:.2f}" y="{top+plot_h+24}" '
                     f'text-anchor="middle" class="label">{scene}</text>')
        for method_index, method in enumerate(METHODS):
            row = next(r for r in rows if r["scene"] == scene and r["method"] == method)
            x = center + (method_index - 0.5) * bar_w * 1.18 - bar_w / 2
            y = ymap(row["mse_mean"])
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" '
                         f'height="{top+plot_h-y:.2f}" fill="{colors[method]}" '
                         f'rx="2"/>')
            parts.append(f'<text x="{x+bar_w/2:.2f}" y="{y-6:.2f}" '
                         f'text-anchor="middle" class="value">'
                         f'{row["mse_mean"]:.4g}</text>')
            parts.append(f'<text x="{x+bar_w/2:.2f}" y="{top+plot_h+40:.2f}" '
                         f'text-anchor="middle" class="axis">'
                         f'{row["spp_mean"]:.0f} spp</text>')
    for i, method in enumerate(METHODS):
        x = width - 300 + i * 145
        parts.append(f'<rect x="{x}" y="{height-28}" width="14" height="10" '
                     f'fill="{colors[method]}"/>')
        parts.append(f'<text x="{x+20}" y="{height-19}" class="label">'
                     f'{names[method]}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def mean_and_std(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    binary = root / "rpt"
    out_dir = (args.out or root / "results").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "previews").mkdir(exist_ok=True)
    subprocess.run(["make", "-j4"], cwd=root, check=True, stdout=subprocess.DEVNULL)

    spp_values = DEFAULT_SPP
    repeats = args.repeats
    ref_spp = dict(REFERENCE_SPP)
    width, height = args.width, args.height
    time_budget = args.time_budget
    if args.quick:
        width, height = 96, 72
        spp_values = (1, 2, 4, 8, 16, 32)
        repeats = min(repeats, 2)
        ref_spp = {scene: 512 for scene in SCENES}
        time_budget = 0.2

    started = time.time()
    convergence_rows: list[dict] = []
    equal_rows: list[dict] = []
    curve_data = {scene: {method: [] for method in METHODS} for scene in SCENES}
    references: dict[str, tuple[list[tuple[float, float, float]], list[int], list[int]]] = {}

    with tempfile.TemporaryDirectory(prefix="rpt_bench_") as temp_name:
        temp = Path(temp_name)
        for scene_index, scene in enumerate(SCENES):
            ref_pfm = out_dir / f"reference_{scene}.pfm"
            ref_ppm = out_dir / f"reference_{scene}.ppm"
            reused = (args.reuse_reference and ref_pfm.exists() and ref_ppm.exists())
            if not reused:
                base = temp / f"reference_{scene}"
                info = run_render(binary, scene, "bdpt", width, height,
                                  args.threads, args.max_depth, base,
                                  args.seed + 900 + scene_index,
                                  spp=ref_spp[scene])
                shutil.copy2(base.with_suffix(".pfm"), ref_pfm)
                shutil.copy2(base.with_suffix(".ppm"), ref_ppm)
                print(f"reference {scene}: {info['spp']} spp, "
                      f"{info['seconds']} s", flush=True)
            rw, rh, pixels = read_pfm(ref_pfm)
            if (rw, rh) != (width, height):
                raise RuntimeError(f"Reference size mismatch for {scene}")
            full_indices = region_indices(width, height, None)
            roi_indices = (region_indices(width, height, CAUSTIC_ROI)
                           if scene == "caustic" else full_indices)
            references[scene] = (pixels, full_indices, roi_indices)
            write_png_from_ppm(ref_ppm, out_dir / f"reference_{scene}.png")
            if not reused:
                ref_ppm.unlink()

        for curve_scene_index, scene in enumerate(SCENES):
            reference, full_indices, _ = references[scene]
            for spp in spp_values:
                for method in METHODS:
                    images = []
                    metrics_runs = []
                    times = []
                    last_base: Path | None = None
                    for repeat in range(repeats):
                        base = temp / f"{scene}_{method}_{spp}_{repeat}"
                        info = run_render(
                            binary, scene, method, width, height, args.threads,
                            args.max_depth, base,
                            args.seed + curve_scene_index * 10000 + spp * 17 + repeat,
                            spp=spp)
                        _, _, image = read_pfm(base.with_suffix(".pfm"))
                        images.append(image)
                        metrics_runs.append(image_metrics(image, reference, full_indices))
                        times.append(float(info["seconds"]))
                        last_base = base
                    mse_mean, mse_std = mean_and_std([m["mse"] for m in metrics_runs])
                    rmse_mean, _ = mean_and_std([m["rmse"] for m in metrics_runs])
                    rel_mean, _ = mean_and_std(
                        [m["relative_rmse"] for m in metrics_runs])
                    variance, mean_lum = population_variance(images, full_indices)
                    row = {
                        "scene": scene,
                        "method": method,
                        "spp": spp,
                        "repeats": repeats,
                        "seconds_mean": sum(times) / len(times),
                        "mse_mean": mse_mean,
                        "mse_std": mse_std,
                        "rmse_mean": rmse_mean,
                        "relative_rmse_mean": rel_mean,
                        "pixel_variance": variance,
                        "relative_variance": variance / (mean_lum * mean_lum)
                        if mean_lum > 0 else 0.0,
                    }
                    if scene == "caustic":
                        roi_runs = [
                            image_metrics(image, reference,
                                          references[scene][2])["mse"]
                            for image in images
                        ]
                        row["caustic_roi_mse_mean"] = sum(roi_runs) / len(roi_runs)
                    convergence_rows.append(row)
                    curve_data[scene][method].append(row)
                    if spp == 64 and last_base is not None:
                        preview = out_dir / "previews" / f"{scene}_{method}_{spp}spp"
                        shutil.copy2(last_base.with_suffix(".ppm"),
                                     preview.with_suffix(".ppm"))
                        shutil.copy2(last_base.with_suffix(".pfm"),
                                     preview.with_suffix(".pfm"))
                        write_png_from_ppm(preview.with_suffix(".ppm"),
                                           preview.with_suffix(".png"))
                print(f"curve {scene} spp={spp}: done", flush=True)

        for equal_scene_index, scene in enumerate(SCENES):
            reference, full_indices, roi_indices = references[scene]
            for method in METHODS:
                mses = []
                roi_mses = []
                seconds = []
                samples = []
                last_base = None
                for repeat in range(repeats):
                    base = temp / f"equal_{scene}_{method}_{repeat}"
                    info = run_render(
                        binary, scene, method, width, height, args.threads,
                        args.max_depth, base,
                        args.seed + 50000 + equal_scene_index * 1000 + repeat,
                        time_limit=time_budget)
                    _, _, image = read_pfm(base.with_suffix(".pfm"))
                    mses.append(image_metrics(image, reference, full_indices)["mse"])
                    roi_mses.append(image_metrics(image, reference, roi_indices)["mse"])
                    seconds.append(float(info["seconds"]))
                    samples.append(int(info["spp"]))
                    last_base = base
                mse_mean, mse_std = mean_and_std(mses)
                roi_mean, roi_std = mean_and_std(roi_mses)
                sec_mean, _ = mean_and_std(seconds)
                spp_mean, _ = mean_and_std([float(v) for v in samples])
                equal_rows.append({
                    "scene": scene,
                    "method": method,
                    "time_budget_s": time_budget,
                    "seconds_mean": sec_mean,
                    "spp_mean": spp_mean,
                    "mse_mean": mse_mean,
                    "mse_std": mse_std,
                    "caustic_roi_mse_mean": roi_mean,
                    "caustic_roi_mse_std": roi_std,
                })
                if last_base is not None:
                    preview = out_dir / "previews" / f"equal_{scene}_{method}"
                    shutil.copy2(last_base.with_suffix(".ppm"),
                                 preview.with_suffix(".ppm"))
                    shutil.copy2(last_base.with_suffix(".pfm"),
                                 preview.with_suffix(".pfm"))
                    write_png_from_ppm(preview.with_suffix(".ppm"),
                                       preview.with_suffix(".png"))
            print(f"equal-time {scene}: done", flush=True)

    convergence_fields = [
        "scene", "method", "spp", "repeats", "seconds_mean", "mse_mean",
        "mse_std", "rmse_mean", "relative_rmse_mean", "pixel_variance",
        "relative_variance", "caustic_roi_mse_mean",
    ]
    write_csv(out_dir / "convergence.csv", convergence_rows, convergence_fields)
    equal_fields = [
        "scene", "method", "time_budget_s", "seconds_mean", "spp_mean",
        "mse_mean", "mse_std", "caustic_roi_mse_mean", "caustic_roi_mse_std",
    ]
    write_csv(out_dir / "equal_time.csv", equal_rows, equal_fields)

    variance_rows = [
        {key: row[key] for key in (
            "scene", "method", "spp", "pixel_variance", "relative_variance")}
        for row in convergence_rows
        if row["spp"] == 32 or (32 not in spp_values and row["spp"] == spp_values[-1])
    ]
    write_csv(
        out_dir / "variance_summary.csv",
        variance_rows,
        ["scene", "method", "spp", "pixel_variance", "relative_variance"],
    )
    svg_error_curves(out_dir / "error_curves.svg", curve_data)
    svg_equal_time(out_dir / "equal_time_error.svg", equal_rows, time_budget)

    summary = {
        "width": width,
        "height": height,
        "max_depth": args.max_depth,
        "threads": args.threads,
        "spp_values": list(spp_values),
        "repeats": repeats,
        "reference_spp": ref_spp,
        "time_budget_seconds": time_budget,
        "caustic_roi_normalized": CAUSTIC_ROI,
        "elapsed_seconds": time.time() - started,
        "convergence_csv": "convergence.csv",
        "equal_time_csv": "equal_time.csv",
        "variance_csv": "variance_summary.csv",
        "error_curve_svg": "error_curves.svg",
        "equal_time_svg": "equal_time_error.svg",
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
