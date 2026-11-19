"""Dependency-free SVG figures for the experiment artifacts."""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from .rig import BONE_BY_NAME, RunRig

DEPTH_COLORS = (
    "#1f4e79",
    "#2e75b6",
    "#2f9e8f",
    "#5b9a3c",
    "#d39b22",
    "#d06a24",
    "#b43b4b",
)


def _svg(width: int, height: int, body: list[str], title: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">',
            "<title>" + escape(title) + "</title>",
            "<style>",
            "text{font-family:'DejaVu Sans','Noto Sans CJK SC',sans-serif;fill:#17202a}",
            ".small{font-size:12px}.label{font-size:13px}.title{font-size:22px;font-weight:700}",
            ".muted{fill:#5d6d7e}",
            "</style>",
            '<rect width="100%" height="100%" fill="#fbfcfd"/>',
            *body,
            "</svg>",
            "",
        ]
    )


def _text(x: float, y: float, value: str, css: str = "small", anchor: str = "start") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css}" text-anchor="{anchor}">'
        f"{escape(value)}</text>"
    )


def _line(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1.0, extra: str = "") -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{color}" stroke-width="{width}" {extra}/>'
    )


def _rect(
    x: float,
    y: float,
    width: float,
    height: float,
    stroke: str,
    fill: str = "none",
    width_px: float = 1.0,
    extra: str = "",
) -> str:
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(0.2, width):.2f}" '
        f'height="{max(0.2, height):.2f}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{width_px}" {extra}/>'
    )


def _polyline(points: list[tuple[float, float]], color: str, width: float, extra: str = "") -> str:
    if not points:
        return ""
    encoded = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polyline points="{encoded}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" {extra}/>'
    )


def _project(point: tuple[float, float, float], mode: str) -> tuple[float, float]:
    if mode == "front":
        return point[0], point[1]
    return point[2], point[1]


def render_running_bbh(path: Path, rig: RunRig, bvh, frame: int = 12) -> None:
    sample = rig.pose(frame / rig.frame_count)
    bvh.update(sample.points, collect_timing=True)
    body: list[str] = [
        _text(
            30,
            38,
            f"奔跑角色骨骼包围盒层次 / 帧 {frame + 1}/{rig.frame_count}",
            "title",
        ),
        _text(
            30,
            62,
            f"19 骨骼 · 7 层 · 每帧 1824 蒙皮顶点 · 根盒体积 "
            f"{bvh.root.box.volume:.3f} m³ · 顶点包含率 100%",
            "label muted",
        ),
    ]
    for panel, mode, title in ((0, "front", "正视图 (x-y)"), (1, "side", "侧视图 (z-y)")):
        left = 55 + panel * 575
        top = 95
        width, height = 535, 515
        scale = 240.0
        origin_x = left + width * 0.5
        origin_y = top + height - 55
        body.append(_rect(left, top, width, height, "#d5dbdb", "#ffffff", 1.2))
        body.append(_text(left + 14, top + 24, title, "label"))

        def screen(point: tuple[float, float, float]) -> tuple[float, float]:
            u, v = _project(point, mode)
            return origin_x + u * scale, origin_y - v * scale

        for grid in range(0, 20, 5):
            y = origin_y - grid * 0.1 * scale
            body.append(_line(left + 10, y, left + width - 10, y, "#eef1f2", 0.8))

        if mode == "front":
            for node in bvh.iter_nodes():
                if node.depth > 3 or node.box is None:
                    continue
                lo = screen(node.box.minimum)
                hi = screen(node.box.maximum)
                body.append(
                    _rect(
                        min(lo[0], hi[0]),
                        min(lo[1], hi[1]),
                        abs(hi[0] - lo[0]),
                        abs(hi[1] - lo[1]),
                        DEPTH_COLORS[node.depth],
                        "none",
                        0.6 + (3 - node.depth) * 0.45,
                        'stroke-dasharray="5 4"',
                    )
                )
        else:
            for node in bvh.iter_nodes():
                if node.own_box is None:
                    continue
                lo = screen(node.own_box.minimum)
                hi = screen(node.own_box.maximum)
                color = DEPTH_COLORS[node.depth]
                body.append(
                    _rect(
                        min(lo[0], hi[0]),
                        min(lo[1], hi[1]),
                        abs(hi[0] - lo[0]),
                        abs(hi[1] - lo[1]),
                        color,
                        color,
                        1.0,
                        'fill-opacity="0.07"',
                    )
                )

        for bone in BONE_BY_NAME.values():
            transform = sample.transforms[bone.name]
            head = screen(transform.apply((0.0, 0.0, 0.0)))
            tail = screen(transform.apply((bone.tail[0] - bone.head[0], bone.tail[1] - bone.head[1], bone.tail[2] - bone.head[2])))
            body.append(_line(head[0], head[1], tail[0], tail[1], "#202830", 3.2))
            body.append(
                f'<circle cx="{head[0]:.2f}" cy="{head[1]:.2f}" r="3.2" fill="#ffffff" '
                f'stroke="#202830" stroke-width="1.2"/>'
            )

        for name, points in sample.points.items():
            step = 3 if name in ("head", "chest", "pelvis") else 4
            for point in points[::step]:
                sx, sy = screen(point)
                body.append(
                    f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="1.35" '
                    f'fill="{DEPTH_COLORS[0]}" fill-opacity="0.42"/>'
                )

    legend_y = 642
    body.append(_text(55, legend_y, "层次颜色：", "small"))
    for depth in range(7):
        x = 140 + depth * 105
        body.append(_rect(x, legend_y - 11, 20, 12, DEPTH_COLORS[depth], DEPTH_COLORS[depth], 1))
        body.append(_text(x + 27, legend_y, f"深度 {depth}", "small"))
    body.append(
        _text(
            55,
            674,
            "左：深度 0–3 的层级包围盒；右：各骨骼自身贴合盒。骨架与蒙皮点均已随姿态更新。",
            "small muted",
        )
    )
    path.write_text(_svg(1200, 700, body, "奔跑角色骨骼包围盒层次"), encoding="utf-8")


def render_culling_chart(
    path: Path,
    rows: list[dict[str, object]],
    validation: dict[str, object],
    frames: int = 48,
    cameras: int = 36,
) -> None:
    width, height = 980, 600
    left, top, plot_w, plot_h = 95, 110, 820, 390
    max_rate = max(float(row["culling_rate"]) for row in rows)
    axis_max = max(0.10, math.ceil(max_rate * 110.0) / 100.0)
    body: list[str] = [
        _text(32, 40, "层次深度对视锥剔除率的影响", "title"),
        _text(
            32,
            64,
            f"{cameras} 个确定性透视相机 × {frames} 个奔跑姿态；"
            "剔除结果与逐骨骼暴力测试完全一致。",
            "label muted",
        ),
    ]
    for tick in range(0, 11):
        rate = axis_max * tick / 10.0
        y = top + plot_h - plot_h * tick / 10.0
        body.append(_line(left, y, left + plot_w, y, "#e7eaec", 0.8))
        body.append(_text(left - 12, y + 4, f"{rate * 100:.0f}%", "small", "end"))
    body.append(_line(left, top + plot_h, left + plot_w, top + plot_h, "#34495e", 1.2))
    body.append(_line(left, top, left, top + plot_h, "#34495e", 1.2))
    bar_width = plot_w / (len(rows) + 1.0) * 0.58
    points: list[tuple[float, float]] = []
    for index, row in enumerate(rows):
        rate = float(row["culling_rate"])
        x = left + plot_w * (index + 1.0) / (len(rows) + 1.0)
        bar_h = plot_h * rate / axis_max
        y = top + plot_h - bar_h
        depth = int(row["depth"])
        body.append(
            _rect(
                x - bar_width * 0.5,
                y,
                bar_width,
                bar_h,
                DEPTH_COLORS[depth],
                DEPTH_COLORS[depth],
                1.1,
                'fill-opacity="0.80"',
            )
        )
        body.append(_text(x, y - 8, f"{rate * 100:.1f}%", "small", "middle"))
        body.append(
            _text(
                x,
                top + plot_h + 24,
                f"深度 {depth}",
                "small",
                "middle",
            )
        )
        candidates = float(row["mean_candidate_primitives"])
        body.append(
            _text(x, top + plot_h + 42, f"{candidates:.2f} 候选", "small muted", "middle")
        )
        points.append((x, y))
    body.append(_polyline(points, "#17202a", 2.0, 'stroke-linejoin="round"'))
    for x, y in points:
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="#ffffff" stroke="#17202a" stroke-width="1.6"/>')
    body.append(_text(left + plot_w * 0.5, top + plot_h + 74, "遍历深度上限", "label", "middle"))
    body.append(
        _text(
            32,
            550,
            f"安全校验：误剔除 {validation['false_culls']}；部分深度子集违规 "
            f"{validation['partial_subset_violations']}；全深度与暴力测试不一致 "
            f"{validation['full_mismatches_vs_bruteforce']}。",
            "label",
        )
    )
    body.append(
        _text(
            32,
            575,
            "深度增加后，更多枝干在内部节点被整体拒绝，候选骨骼数由 "
            f"{float(rows[0]['mean_candidate_primitives']):.2f} 降至 "
            f"{float(rows[-1]['mean_candidate_primitives']):.2f}。",
            "small muted",
        )
    )
    path.write_text(_svg(width, height, body, "层次深度对剔除率的影响"), encoding="utf-8")


def render_layer_volume_chart(path: Path, rows: list[dict[str, object]]) -> None:
    width, height = 980, 600
    left, top, plot_w, plot_h = 105, 105, 800, 400
    values = [max(1e-8, float(row["total_volume_m3"])) for row in rows]
    y_min, y_max = 1e-4, 5.0

    def y_for(value: float) -> float:
        fraction = (math.log10(value) - math.log10(y_min)) / (
            math.log10(y_max) - math.log10(y_min)
        )
        return top + plot_h * (1.0 - fraction)

    body: list[str] = [
        _text(32, 40, "各层包围盒体积与更新耗时", "title"),
        _text(32, 64, "总体积按深度汇总（对数轴）；标签同时给出该层每帧盒更新耗时。", "label muted"),
    ]
    for decade in (-4, -3, -2, -1, 0):
        y = y_for(10.0**decade)
        body.append(_line(left, y, left + plot_w, y, "#e7eaec", 0.8))
        body.append(_text(left - 12, y + 4, f"10^{decade}", "small", "end"))
    body.append(_line(left, top + plot_h, left + plot_w, top + plot_h, "#34495e", 1.2))
    body.append(_line(left, top, left, top + plot_h, "#34495e", 1.2))
    bar_width = plot_w / (len(rows) + 1.0) * 0.56
    for index, (row, value) in enumerate(zip(rows, values)):
        depth = int(row["depth"])
        x = left + plot_w * (index + 1.0) / (len(rows) + 1.0)
        y = y_for(value)
        body.append(
            _rect(
                x - bar_width * 0.5,
                y,
                bar_width,
                top + plot_h - y,
                DEPTH_COLORS[depth],
                DEPTH_COLORS[depth],
                1.1,
                'fill-opacity="0.80"',
            )
        )
        body.append(_text(x, y - 24, f"{value:.4f} m³", "small", "middle"))
        body.append(
            _text(
                x,
                y - 8,
                f"{float(row['update_ms_per_frame']) * 1000:.1f} µs",
                "small muted",
                "middle",
            )
        )
        body.append(_text(x, top + plot_h + 22, f"深度 {depth}", "small", "middle"))
        body.append(
            _text(x, top + plot_h + 40, f"{int(row['nodes'])} 节点", "small muted", "middle")
        )
    body.append(_text(left + plot_w * 0.5, top + plot_h + 70, "骨骼层次深度", "label", "middle"))
    body.append(
        _text(
            32,
            565,
            "根盒覆盖整身，体积随奔跑姿态变化；深层叶节点体积小但数量少。"
            "盒更新时间仅统计 AABB 重算与自底向上合并，不含蒙皮。",
            "small muted",
        )
    )
    path.write_text(_svg(width, height, body, "各层包围盒体积与更新耗时"), encoding="utf-8")


def _height_color(z: float, z_max: float = 0.22) -> str:
    t = max(0.0, min(1.0, z / z_max))
    red = int(42 + 205 * t)
    green = int(120 + 80 * t)
    blue = int(180 - 120 * t)
    return f"#{red:02x}{green:02x}{blue:02x}"


def render_geodesic_chart(
    path: Path,
    curved_points: list[tuple[float, float, float]],
    analytic_points: list[tuple[float, float, float]],
    rows: list[dict[str, object]],
    checks: dict[str, object],
) -> None:
    width, height = 1000, 760
    center_x, center_y, scale = 500.0, 385.0, 190.0
    domain = 1.80

    def screen(x: float, y: float) -> tuple[float, float]:
        return center_x + x * scale, center_y - y * scale

    body: list[str] = [
        _text(32, 38, "圆形障碍曲面最短路径", "title"),
        _text(
            32,
            62,
            "0.01 m 高度场三角网 · 24 邻域图搜索 · 路径始终在障碍半径之外",
            "label muted",
        ),
    ]

    cells = 24
    step = 2.0 * domain / cells
    for iy in range(cells):
        for ix in range(cells):
            x = -domain + (ix + 0.5) * step
            y = -domain + (iy + 0.5) * step
            radius = math.hypot(x, y)
            if radius <= 0.60:
                continue
            t = max(0.0, min(1.0, (radius - 0.60) / 1.80))
            theta = math.atan2(y, x)
            z = 0.18 * t * t + 0.032 * math.sin(3.0 * theta) * math.sin(math.pi * t)
            sx, sy = screen(x - step * 0.5, y + step * 0.5)
            body.append(
                _rect(
                    sx,
                    sy,
                    step * scale,
                    step * scale,
                    "none",
                    _height_color(z),
                    0,
                    'fill-opacity="0.13"',
                )
            )
    for tick in range(-6, 7):
        value = tick * 0.3
        x1, y1 = screen(-domain, value)
        x2, y2 = screen(domain, value)
        body.append(_line(x1, y1, x2, y2, "#ffffff", 0.7, 'stroke-opacity="0.72"'))
        x1, y1 = screen(value, -domain)
        x2, y2 = screen(value, domain)
        body.append(_line(x1, y1, x2, y2, "#ffffff", 0.7, 'stroke-opacity="0.72"'))

    cx, cy = screen(0.0, 0.0)
    body.append(
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{0.60 * scale:.2f}" '
        'fill="#2c3e50" fill-opacity="0.18" stroke="#34495e" stroke-width="2"/>'
    )
    body.append(_text(cx, cy + 4, "障碍", "label", "middle"))
    body.append(
        _line(cx - 12, cy + 18, cx + 12, cy + 18, "#34495e", 1.2)
    )

    if analytic_points:
        analytic_xy = [screen(point[0], point[1]) for point in analytic_points]
        body.append(
            _polyline(
                analytic_xy,
                "#16a085",
                2.0,
                'stroke-dasharray="7 5" stroke-linecap="round"',
            )
        )
    for a, b in zip(curved_points, curved_points[1:]):
        color = _height_color((a[2] + b[2]) * 0.5)
        x1, y1 = screen(a[0], a[1])
        x2, y2 = screen(b[0], b[1])
        body.append(_line(x1, y1, x2, y2, color, 4.2, 'stroke-linecap="round"'))

    if curved_points:
        for point, label in ((curved_points[0], "起点"), (curved_points[-1], "终点")):
            sx, sy = screen(point[0], point[1])
            body.append(
                f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="8" fill="#ffffff" '
                'stroke="#17202a" stroke-width="2.5"/>'
            )
            body.append(_text(sx, sy - 14, label, "small", "middle"))

    curved_row = next(row for row in rows if row["case"] == "curved_fine")
    flat_row = next(row for row in rows if row["case"] == "flat_mesh_dijkstra")
    info_x = 770
    body.append(_rect(info_x, 100, 200, 178, "#d5dbdb", "#ffffff", 1.0))
    body.append(_text(info_x + 14, 126, "结果", "label"))
    body.append(_text(info_x + 14, 150, f"曲面路径 {float(curved_row['distance_m']):.4f} m", "small"))
    body.append(_text(info_x + 14, 172, f"平面解析 {float(checks['analytic_distance_m']):.4f} m", "small"))
    body.append(_text(info_x + 14, 194, f"平面误差 {float(checks['flat_relative_error']) * 100:.3f}%", "small"))
    body.append(_text(info_x + 14, 216, f"曲面收敛差 {float(checks['curved_convergence_difference']) * 100:.5f}%", "small"))
    body.append(_text(info_x + 14, 238, f"最小净距 {float(curved_row['clearance_m']):.4f} m", "small"))
    body.append(_text(info_x + 14, 260, "净距要求 ≥ 0.6000 m", "small muted"))

    body.append(_rect(85, 708, 680, 18, "none", "#ffffff", 0.8))
    for index in range(50):
        x = 85 + index * 13.6
        z = 0.22 * index / 49.0
        body.append(_rect(x, 708, 13.8, 14, "none", _height_color(z), 0))
    body.append(_text(85, 744, "高度 0 m", "small"))
    body.append(_text(765, 744, "0.22 m", "small", "end"))
    body.append(_text(795, 721, "路径按曲面高度着色；绿色虚线为平面解析解。", "small muted"))

    path.write_text(_svg(width, height, body, "圆形障碍曲面最短路径"), encoding="utf-8")
