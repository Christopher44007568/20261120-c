#!/usr/bin/env python3
"""Render dependency-free SVG views of the exported flow and trajectories."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

WIDTH = 960
HEIGHT = 960
BG = "#07101d"
PANEL = "#0c1b2e"
INK = "#dce9f8"
MUTED = "#7f98b5"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def speed_color(value: float, low: float, high: float) -> str:
    if high <= low:
        t = 0.5
    else:
        t = max(0.0, min(1.0, (value - low) / (high - low)))
    stops = [
        (0.0, (48, 104, 224)),
        (0.35, (37, 196, 220)),
        (0.7, (244, 206, 77)),
        (1.0, (242, 88, 74)),
    ]
    for index in range(len(stops) - 1):
        t0, c0 = stops[index]
        t1, c1 = stops[index + 1]
        if t <= t1:
            local = (t - t0) / max(1e-12, t1 - t0)
            rgb = tuple(round(a + (b - a) * local) for a, b in zip(c0, c1))
            return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
    return "rgb(242,88,74)"


def svg_start(title: str, subtitle: str) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        "<defs>",
        f'<radialGradient id="bg" cx="50%" cy="42%" r="72%">'
        f'<stop offset="0%" stop-color="{PANEL}"/>'
        f'<stop offset="100%" stop-color="{BG}"/></radialGradient>',
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>',
        f'<text x="56" y="54" fill="{INK}" font-family="monospace" '
        f'font-size="25" font-weight="700">{title}</text>',
        f'<text x="56" y="82" fill="{MUTED}" font-family="monospace" '
        f'font-size="13">{subtitle}</text>',
    ]


def render_flow(source: Path, destination: Path) -> None:
    rows = read_csv(source)
    if not rows:
        raise ValueError(f"empty flow field: {source}")
    columns = len({row["x"] for row in rows})
    count = len(rows)
    row_count = count // columns
    speeds = [float(row["speed"]) for row in rows]
    low, high = min(speeds), max(speeds)
    arrow_step = max(1, columns // 32)
    left, top, size = 56.0, 118.0, 848.0
    cell_x = size / columns
    cell_y = size / row_count
    lines = svg_start(
        "Divergence-free curl-noise field",
        f"{columns}x{row_count} samples | arrows normalized | color = speed "
        f"({low:.3f}..{high:.3f})",
    )
    lines.append(
        f'<rect x="{left}" y="{top}" width="{size}" height="{size}" '
        f'fill="#06101b" stroke="#22364f" stroke-width="1"/>'
    )
    for row_index in range(0, row_count, arrow_step):
        for column_index in range(0, columns, arrow_step):
            row = rows[row_index * columns + column_index]
            vx = float(row["vx"])
            vy = float(row["vy"])
            speed = float(row["speed"])
            norm = math.hypot(vx, vy)
            if norm < 1e-9:
                continue
            x = left + (column_index + 0.5) * cell_x
            y = top + size - (row_index + 0.5) * cell_y
            length = 0.34 * min(cell_x, cell_y) * arrow_step
            dx = vx / norm * length
            dy = -vy / norm * length
            color = speed_color(speed, low, high)
            lines.append(
                f'<line x1="{x - dx * 0.5:.2f}" y1="{y - dy * 0.5:.2f}" '
                f'x2="{x + dx * 0.5:.2f}" y2="{y + dy * 0.5:.2f}" '
                f'stroke="{color}" stroke-width="1.25" stroke-opacity="0.78"/>'
            )
            lines.append(
                f'<circle cx="{x + dx * 0.5:.2f}" cy="{y + dy * 0.5:.2f}" '
                f'r="0.9" fill="{color}" fill-opacity="0.9"/>'
            )
    lines.append(
        f'<text x="{left}" y="{top + size + 28}" fill="{MUTED}" '
        f'font-family="monospace" font-size="12">'
        f"periodic box [0,1]^2 | spectral modes with analytical div(v)=0</text>"
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def path_segments(points: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in points:
        if current and (
            abs(point[0] - current[-1][0]) > 0.5
            or abs(point[1] - current[-1][1]) > 0.5
        ):
            if len(current) > 1:
                segments.append(current)
            current = []
        current.append(point)
    if len(current) > 1:
        segments.append(current)
    return segments


def render_trajectories(
    source: Path, particles_final: Path, destination: Path
) -> None:
    rows = read_csv(source)
    grouped: dict[int, list[tuple[float, float]]] = {}
    for row in rows:
        particle_id = int(row["particle_id"])
        grouped.setdefault(particle_id, []).append((float(row["x"]), float(row["y"])))
    left, top, size = 56.0, 118.0, 848.0
    lines = svg_start(
        "Particles advected by curl noise",
        f"{len(grouped)} trajectories | RK4 | periodic torus | colored by id",
    )
    lines.append(
        f'<rect x="{left}" y="{top}" width="{size}" height="{size}" '
        f'fill="#06101b" stroke="#22364f" stroke-width="1"/>'
    )
    for index, (particle_id, points) in enumerate(sorted(grouped.items())):
        hue = (index * 137.508) % 360.0
        sampled = points[::2]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        for segment in path_segments(sampled):
            commands = []
            for point_index, (x, y) in enumerate(segment):
                sx = left + x * size
                sy = top + size - y * size
                commands.append(("M" if point_index == 0 else "L") + f"{sx:.2f},{sy:.2f}")
            lines.append(
                f'<path d="{" ".join(commands)}" fill="none" '
                f'stroke="hsl({hue:.1f},88%,68%)" stroke-width="1.25" '
                f'stroke-opacity="0.72" stroke-linejoin="round"/>'
            )
        final_x, final_y = points[-1]
        lines.append(
            f'<circle cx="{left + final_x * size:.2f}" '
            f'cy="{top + size - final_y * size:.2f}" r="1.9" '
            f'fill="hsl({hue:.1f},92%,74%)"/>'
        )
    for row in read_csv(particles_final)[::97]:
        x = left + float(row["x"]) * size
        y = top + size - float(row["y"]) * size
        lines.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="0.65" '
            f'fill="#bcd2ea" fill-opacity="0.30"/>'
        )
    lines.append(
        f'<text x="{left}" y="{top + size + 28}" fill="{MUTED}" '
        f'font-family="monospace" font-size="12">'
        f"line breaks suppress torus wrap segments | dots = final particles</text>"
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_frequency_curvature(source: Path, destination: Path) -> None:
    rows = read_csv(source)
    if not rows:
        raise ValueError(f"empty frequency sweep: {source}")
    frequencies = [float(row["frequency"]) for row in rows]
    means = [float(row["mean_curvature"]) for row in rows]
    p95s = [float(row["p95_curvature"]) for row in rows]
    width, height = 960, 620
    left, top, right, bottom = 112.0, 126.0, 54.0, 88.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_y = max(p95s) * 1.08
    min_x, max_x = min(frequencies), max(frequencies)

    def point(frequency: float, curvature: float) -> tuple[float, float]:
        x = left + (frequency - min_x) / (max_x - min_x) * plot_width
        y = top + plot_height - curvature / max_y * plot_height
        return x, y

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="56" y="54" fill="{INK}" font-family="monospace" '
        f'font-size="25" font-weight="700">Noise frequency vs curvature</text>',
        f'<text x="56" y="82" fill="{MUTED}" font-family="monospace" '
        f'font-size="13">RMS speed fixed | solid = mean | dashed = p95</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
        f'fill="#07131f" stroke="#22364f"/>',
    ]
    for tick in range(6):
        value = max_y * tick / 5.0
        y = top + plot_height - value / max_y * plot_height
        lines.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" '
            f'y2="{y:.2f}" stroke="#183048" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{left - 14}" y="{y + 4:.2f}" text-anchor="end" '
            f'fill="{MUTED}" font-family="monospace" font-size="12">{value:.0f}</text>'
        )
    for frequency in frequencies:
        x, _ = point(frequency, 0.0)
        lines.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
            f'y2="{top + plot_height}" stroke="#12263b" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{x:.2f}" y="{top + plot_height + 25}" text-anchor="middle" '
            f'fill="{MUTED}" font-family="monospace" font-size="12">'
            f"{frequency:g}</text>"
        )
    for values, color, dash, width_px in (
        (means, "#39d7c9", "", 2.0),
        (p95s, "#f4c44d", ' stroke-dasharray="7 5"', 1.5),
    ):
        commands = []
        for frequency, value in zip(frequencies, values):
            x, y = point(frequency, value)
            commands.append(("M" if not commands else "L") + f"{x:.2f},{y:.2f}")
        lines.append(
            f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" '
            f'stroke-width="{width_px}"{dash}/>'
        )
        for frequency, value in zip(frequencies, values):
            x, y = point(frequency, value)
            lines.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{color}"/>'
            )
    lines.append(
        f'<text x="{left + plot_width / 2:.2f}" y="{height - 28}" '
        f'text-anchor="middle" fill="{MUTED}" font-family="monospace" '
        f'font-size="13">noise frequency (cycles per box)</text>'
    )
    lines.append(
        f'<text x="30" y="{top + plot_height / 2:.2f}" fill="{MUTED}" '
        f'font-family="monospace" font-size="13" '
        f'transform="rotate(-90 30 {top + plot_height / 2:.2f})" '
        f'text-anchor="middle">curvature (1 / length)</text>'
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", default="artifacts")
    args = parser.parse_args()
    root = Path(args.output_dir)
    render_flow(root / "flow_field.csv", root / "flow_field.svg")
    render_trajectories(
        root / "trajectories.csv",
        root / "particles_final.csv",
        root / "trajectories.svg",
    )
    render_frequency_curvature(
        root / "frequency_sweep.csv", root / "frequency_curvature.svg"
    )
    print(
        f"rendered SVG: {root / 'flow_field.svg'} {root / 'trajectories.svg'} "
        f"{root / 'frequency_curvature.svg'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
