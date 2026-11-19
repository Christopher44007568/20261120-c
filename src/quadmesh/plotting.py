"""Dependency-free SVG charts for the experiment artifacts."""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from .geometry import Mesh


PALETTE = ("#d1495b", "#00798c", "#edae49", "#30638e", "#6a994e")


def grouped_bars(
    path: Path,
    title: str,
    labels: list[str],
    series: list[tuple[str, list[float]]],
    y_label: str,
    suffix: str = "%",
) -> None:
    width, height = 980, 540
    left, right, top, bottom = 88, 28, 72, 122
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum = max(max(values, default=0.0) for _, values in series)
    maximum = max(maximum, 1.0)
    y_max = maximum * 1.12

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700">{escape(title)}</text>',
        f'<text x="24" y="{top + plot_height / 2}" text-anchor="middle" transform="rotate(-90 24 {top + plot_height / 2})" font-family="sans-serif" font-size="13">{escape(y_label)}</text>',
    ]
    for tick in range(6):
        value = y_max * tick / 5
        y = top + plot_height - plot_height * tick / 5
        elements.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#d9dee3" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#495057">{value:.1f}{suffix}</text>'
        )
    group_width = plot_width / max(len(labels), 1)
    bar_width = group_width * 0.72 / max(len(series), 1)
    for group_idx, label in enumerate(labels):
        x0 = left + group_idx * group_width + group_width * 0.14
        for series_idx, (_, values) in enumerate(series):
            value = values[group_idx] if group_idx < len(values) else 0.0
            bar_height = max(0.0, value / y_max * plot_height)
            x = x0 + series_idx * bar_width
            y = top + plot_height - bar_height
            elements.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width - 2:.2f}" height="{bar_height:.2f}" fill="{PALETTE[series_idx % len(PALETTE)]}"/>'
            )
        if len(labels) <= 14 or group_idx % max(1, math.ceil(len(labels) / 10)) == 0:
            center = left + group_idx * group_width + group_width / 2
            elements.append(
                f'<text x="{center:.2f}" y="{top + plot_height + 18}" text-anchor="end" transform="rotate(-40 {center:.2f} {top + plot_height + 18})" font-family="sans-serif" font-size="10" fill="#343a40">{escape(label)}</text>'
            )
    legend_x = left
    for index, (name, _) in enumerate(series):
        x = legend_x + index * 190
        elements.append(
            f'<rect x="{x}" y="{height - 34}" width="14" height="14" fill="{PALETTE[index % len(PALETTE)]}"/>'
        )
        elements.append(
            f'<text x="{x + 20}" y="{height - 22}" font-family="sans-serif" font-size="12" fill="#212529">{escape(name)}</text>'
        )
    elements.append("</svg>")
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")


def _panel_edges(mesh: Mesh, x_offset: float, panel_width: float, panel_height: float) -> list[str]:
    min_x = min(vertex[0] for vertex in mesh.vertices)
    max_x = max(vertex[0] for vertex in mesh.vertices)
    min_y = min(vertex[1] for vertex in mesh.vertices)
    max_y = max(vertex[1] for vertex in mesh.vertices)
    scale = min((panel_width - 32) / max(max_x - min_x, 1e-9), (panel_height - 32) / max(max_y - min_y, 1e-9))
    lines = []
    for item in mesh.edges():
        a, b = mesh.vertices[item[0]], mesh.vertices[item[1]]
        x1 = x_offset + panel_width / 2 + (a[0] - (min_x + max_x) / 2) * scale
        y1 = 72 + panel_height / 2 - (a[1] - (min_y + max_y) / 2) * scale
        x2 = x_offset + panel_width / 2 + (b[0] - (min_x + max_x) / 2) * scale
        y2 = 72 + panel_height / 2 - (b[1] - (min_y + max_y) / 2) * scale
        lines.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
    return lines


def mesh_comparison(path: Path, title: str, before: Mesh, after: Mesh) -> None:
    width, height = 1100, 610
    panel_width, panel_height = 500, 460
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700">{escape(title)}</text>',
        '<text x="300" y="58" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#d1495b">triangle source</text>',
        '<text x="800" y="58" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#00798c">quad remesh</text>',
        '<g stroke="#d1495b" stroke-width="0.35" stroke-opacity="0.55" fill="none">',
        *_panel_edges(before, 50, panel_width, panel_height),
        "</g>",
        '<g stroke="#00798c" stroke-width="0.55" stroke-opacity="0.55" fill="none">',
        *_panel_edges(after, 550, panel_width, panel_height),
        "</g>",
        "</svg>",
    ]
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")
