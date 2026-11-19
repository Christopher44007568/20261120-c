from __future__ import annotations

from math import log10
from pathlib import Path

from .animation import ProceduralAnimation
from .compression import CompressedAnimation
from .math3d import vec_length, vec_sub


def _map(value: float, low: float, high: float, start: float, end: float) -> float:
    if high == low:
        return (start + end) * 0.5
    return start + (value - low) / (high - low) * (end - start)


def _points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f5ef"/>',
        '<style>text{font-family:ui-monospace,Menlo,Consolas,monospace;fill:#263238}'
        '.axis{stroke:#90a4ae;stroke-width:1}.grid{stroke:#dde3e3;stroke-width:1}'
        '.panel{fill:#fffdf8;stroke:#cfd8dc;stroke-width:1.5;rx:10}</style>',
        f'<text x="36" y="42" font-size="24" font-weight="700">{title}</text>',
    ]


def _legend(lines: list[str], x: float, y: float) -> None:
    lines.extend(
        [
            f'<line x1="{x}" y1="{y}" x2="{x + 28}" y2="{y}" stroke="#263238" stroke-width="3"/>',
            f'<text x="{x + 36}" y="{y + 5}" font-size="13">source</text>',
            f'<line x1="{x + 120}" y1="{y}" x2="{x + 148}" y2="{y}" '
            f'stroke="#ff6f00" stroke-width="2" stroke-dasharray="5 4"/>',
            f'<text x="{x + 156}" y="{y + 5}" font-size="13">decoded</text>',
        ]
    )


def _world_trace(
    animation: ProceduralAnimation | CompressedAnimation,
    joint_name: str,
    duration: float,
) -> list[tuple[float, float, float]]:
    names = [joint.name for joint in animation.joints]
    index = names.index(joint_name)
    step = max(0.1, duration / 700.0)
    trace = []
    time_seconds = 0.0
    while time_seconds < duration:
        trace.append(animation.world_poses_at(time_seconds)[index].position)
        time_seconds += step
    trace.append(animation.world_poses_at(duration)[index].position)
    return trace


def render_action_comparison_svg(
    path: Path,
    source: ProceduralAnimation,
    decoded: CompressedAnimation,
    metrics: dict[str, object],
) -> None:
    width, height = 1200, 780
    duration_label = f"{source.duration_seconds:.0f} s"
    lines = _header(width, height, "Skeletal action: source vs fixed-point reconstruction")
    lines.extend(
        [
            '<rect class="panel" x="36" y="64" width="552" height="300"/>',
            '<rect class="panel" x="612" y="64" width="552" height="300"/>',
            '<rect class="panel" x="36" y="386" width="1128" height="358"/>',
            '<text x="58" y="92" font-size="16" font-weight="700">End-effector trajectory (x/z)</text>',
            f'<text x="634" y="92" font-size="16" font-weight="700">'
            f'Rotation error over {duration_label} (log scale)</text>',
            '<text x="58" y="414" font-size="16" font-weight="700">Pose overlay at three times</text>',
        ]
    )
    _legend(lines, 84, 116)

    source_trace = _world_trace(source, "hand_l", source.duration_seconds)
    decoded_trace = _world_trace(decoded, "hand_l", source.duration_seconds)
    xs = [point[0] for point in source_trace + decoded_trace]
    zs = [point[2] for point in source_trace + decoded_trace]
    x_low, x_high = min(xs), max(xs)
    z_low, z_high = min(zs), max(zs)
    x_pad = max(0.05, (x_high - x_low) * 0.08)
    z_pad = max(0.05, (z_high - z_low) * 0.08)
    map_x = lambda value: _map(value, x_low - x_pad, x_high + x_pad, 72, 560)
    map_z = lambda value: _map(value, z_low - z_pad, z_high + z_pad, 338, 142)
    for fraction in range(1, 4):
        y = 142 + fraction * 49
        lines.append(f'<line class="grid" x1="72" y1="{y}" x2="560" y2="{y}"/>')
    source_points = [(map_x(p[0]), map_z(p[2])) for p in source_trace]
    decoded_points = [(map_x(p[0]), map_z(p[2])) for p in decoded_trace]
    lines.append(
        f'<polyline fill="none" stroke="#263238" stroke-width="2.4" points="{_points(source_points)}"/>'
    )
    lines.append(
        f'<polyline fill="none" stroke="#ff6f00" stroke-width="1.4" '
        f'stroke-dasharray="4 3" points="{_points(decoded_points)}"/>'
    )

    series = metrics["series"]
    times = series["time"]
    errors = series["rotation_max_deg"]
    maximum_error = max(max(errors), 0.1)
    log_low, log_high = -5.0, log10(maximum_error) + 0.15
    map_time = lambda value: _map(value, 0.0, source.duration_seconds, 640, 1132)
    map_error = lambda value: _map(
        log10(max(value, 10.0 ** log_low)), log_low, log_high, 338, 142
    )
    for exponent in range(-5, int(log_high) + 1):
        y = map_error(10.0 ** exponent)
        lines.append(f'<line class="grid" x1="640" y1="{y:.2f}" x2="1132" y2="{y:.2f}"/>')
        lines.append(
            f'<text x="598" y="{y + 4:.2f}" font-size="11" text-anchor="end">1e{exponent}</text>'
        )
    error_points = [(map_time(t), map_error(e)) for t, e in zip(times, errors)]
    lines.append(
        f'<polyline fill="none" stroke="#d84315" stroke-width="1.8" points="{_points(error_points)}"/>'
    )
    threshold_y = map_error(0.1)
    lines.append(
        f'<line x1="640" y1="{threshold_y:.2f}" x2="1132" y2="{threshold_y:.2f}" '
        f'stroke="#2e7d32" stroke-width="1.5" stroke-dasharray="7 4"/>'
    )
    lines.append(
        f'<text x="1126" y="{threshold_y - 7:.2f}" font-size="12" text-anchor="end">'
        f'limit 0.1 deg</text>'
    )
    lines.append(f'<text x="640" y="366" font-size="12">0 s</text>')
    lines.append(
        f'<text x="1132" y="366" font-size="12" text-anchor="end">{duration_label}</text>'
    )
    lines.append(
        f'<text x="640" y="122" font-size="12">peak {float(metrics["rotation_max_deg"]):.4f} deg</text>'
    )

    pose_times = [
        source.duration_seconds * fraction for fraction in (0.2, 0.5, 0.8)
    ]
    panel_width = 352
    for panel_index, time_seconds in enumerate(pose_times):
        source_world = source.world_poses_at(time_seconds)
        decoded_world = decoded.world_poses_at(time_seconds)
        center_x = 208 + panel_index * panel_width
        all_points = [pose.position for pose in source_world + decoded_world]
        local_x = [point[0] for point in all_points]
        local_z = [point[2] for point in all_points]
        scale = min(
            105 / max(0.5, max(local_x) - min(local_x)),
            225 / max(0.5, max(local_z) - min(local_z)),
        )
        origin_x = center_x - (min(local_x) + max(local_x)) * scale * 0.5
        origin_z = 610 + (min(local_z) + max(local_z)) * scale * 0.5
        project = lambda point: (
            origin_x + point[0] * scale,
            origin_z - point[2] * scale,
        )
        index_by_name = {joint.name: i for i, joint in enumerate(source.joints)}
        for world, color, line_width, dash in (
            (source_world, "#b0bec5", 7.0, ""),
            (decoded_world, "#ff6f00", 2.0, ' stroke-dasharray="5 4"'),
        ):
            for joint_index, joint in enumerate(source.joints):
                if joint.parent is None:
                    continue
                a = project(world[index_by_name[joint.parent]].position)
                b = project(world[joint_index].position)
                lines.append(
                    f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" '
                    f'y2="{b[1]:.2f}" stroke="{color}" stroke-width="{line_width}"'
                    f'{dash} stroke-linecap="round"/>'
                )
        lines.append(
            f'<text x="{center_x}" y="704" font-size="13" text-anchor="middle">'
            f't = {time_seconds:.0f} s</text>'
        )

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_quantization_svg(path: Path, sweep: list[dict[str, object]]) -> None:
    width, height = 1200, 700
    lines = _header(width, height, "Fixed-point bits: reconstruction error and compression")
    lines.extend(
        [
            '<rect class="panel" x="44" y="68" width="1112" height="288"/>',
            '<rect class="panel" x="44" y="386" width="1112" height="256"/>',
            '<text x="66" y="96" font-size="16" font-weight="700">Rotation error (degrees, log scale)</text>',
            '<text x="66" y="414" font-size="16" font-weight="700">Compression ratio at 10 Hz keyframes</text>',
        ]
    )
    bits = [int(record["bits"]) for record in sweep]
    quant_errors = [float(record["quantization_rotation_max_deg"]) for record in sweep]
    total_errors = [float(record["rotation_max_deg"]) for record in sweep]
    ratios = [float(record["compression_ratio"]) for record in sweep]
    minimum = max(1.0e-5, min(quant_errors) * 0.6)
    maximum = max(total_errors) * 1.4
    map_x = lambda bit: _map(bit, min(bits) - 0.4, max(bits) + 0.4, 94, 1118)
    map_y = lambda value: _map(log10(max(value, minimum)), log10(minimum), log10(maximum), 326, 126)
    for record in sweep:
        x = map_x(int(record["bits"]))
        lines.append(f'<line class="grid" x1="{x:.2f}" y1="126" x2="{x:.2f}" y2="326"/>')
        lines.append(
            f'<text x="{x:.2f}" y="350" font-size="12" text-anchor="middle">'
            f'{int(record["bits"])} bit</text>'
        )
    for exponent in range(int(log10(minimum)) - 1, int(log10(maximum)) + 2):
        value = 10.0 ** exponent
        if value < minimum or value > maximum:
            continue
        y = map_y(value)
        lines.append(f'<line class="grid" x1="94" y1="{y:.2f}" x2="1118" y2="{y:.2f}"/>')
        lines.append(
            f'<text x="84" y="{y + 4:.2f}" font-size="11" text-anchor="end">1e{exponent}</text>'
        )
    quant_points = [(map_x(bit), map_y(error)) for bit, error in zip(bits, quant_errors)]
    total_points = [(map_x(bit), map_y(error)) for bit, error in zip(bits, total_errors)]
    lines.append(
        f'<polyline fill="none" stroke="#1565c0" stroke-width="2.5" points="{_points(quant_points)}"/>'
    )
    lines.append(
        f'<polyline fill="none" stroke="#d84315" stroke-width="2.5" points="{_points(total_points)}"/>'
    )
    for x, y in quant_points:
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#1565c0"/>')
    for x, y in total_points:
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#d84315"/>')
    lines.extend(
        [
            '<line x1="94" y1="112" x2="122" y2="112" stroke="#1565c0" stroke-width="3"/>',
            '<text x="130" y="117" font-size="13">quantization-only max</text>',
            '<line x1="340" y1="112" x2="368" y2="112" stroke="#d84315" stroke-width="3"/>',
            '<text x="376" y="117" font-size="13">interpolated reconstruction max</text>',
        ]
    )
    floor = float(sweep[0]["interpolation_rotation_max_deg"])
    floor_y = map_y(floor)
    lines.append(
        f'<line x1="94" y1="{floor_y:.2f}" x2="1118" y2="{floor_y:.2f}" '
        f'stroke="#2e7d32" stroke-width="1.5" stroke-dasharray="7 4"/>'
    )
    lines.append(
        f'<text x="1112" y="{floor_y - 7:.2f}" font-size="12" text-anchor="end" fill="#2e7d32">'
        f'interpolation floor {floor:.4f} deg</text>'
    )

    ratio_max = max(ratios) * 1.12
    map_ratio = lambda value: _map(value, 0.0, ratio_max, 620, 444)
    ratio_points = [(map_x(bit), map_ratio(ratio)) for bit, ratio in zip(bits, ratios)]
    lines.append(
        f'<polyline fill="none" stroke="#6a1b9a" stroke-width="2.5" points="{_points(ratio_points)}"/>'
    )
    for record, point in zip(sweep, ratio_points):
        lines.append(f'<circle cx="{point[0]:.2f}" cy="{point[1]:.2f}" r="4" fill="#6a1b9a"/>')
        lines.append(
            f'<text x="{point[0]:.2f}" y="{point[1] - 9:.2f}" font-size="11" '
            f'text-anchor="middle">{float(record["compression_ratio"]):.1f}x</text>'
        )
    for ratio in (0, ratio_max / 2.0, ratio_max):
        y = map_ratio(ratio)
        lines.append(f'<line class="grid" x1="94" y1="{y:.2f}" x2="1118" y2="{y:.2f}"/>')
        lines.append(
            f'<text x="84" y="{y + 4:.2f}" font-size="11" text-anchor="end">{ratio:.1f}x</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_mesh_svg(path: Path, records: list[dict[str, object]]) -> None:
    from .subdivision import boundary_edges

    width, height = 1200, 520
    lines = _header(width, height, "Catmull-Clark subdivision: boundary and sharp ridge")
    panel_width = 360
    projected_sets = []
    for record in records:
        mesh = record["mesh"]
        projected = [((v[0] - v[1]) * 0.82, (v[0] + v[1]) * 0.34 - v[2]) for v in mesh.vertices]
        projected_sets.append(projected)
    all_points = [point for points in projected_sets for point in points]
    low_x = min(point[0] for point in all_points)
    high_x = max(point[0] for point in all_points)
    low_y = min(point[1] for point in all_points)
    high_y = max(point[1] for point in all_points)
    for panel_index, (record, projected) in enumerate(zip(records, projected_sets)):
        mesh = record["mesh"]
        left = 24 + panel_index * 388
        lines.append(f'<rect class="panel" x="{left}" y="76" width="{panel_width}" height="392"/>')
        lines.append(
            f'<text x="{left + 18}" y="104" font-size="16" font-weight="700">{record["label"]}</text>'
        )
        scale = min(300 / max(0.1, high_x - low_x), 275 / max(0.1, high_y - low_y))
        center_x = left + panel_width * 0.5
        center_y = 285
        project = lambda point: (
            center_x + (point[0] - (low_x + high_x) * 0.5) * scale,
            center_y + (point[1] - (low_y + high_y) * 0.5) * scale,
        )
        edge_faces: dict[tuple[int, int], int] = {}
        for face in mesh.faces:
            for offset, a in enumerate(face):
                b = face[(offset + 1) % len(face)]
                edge = (a, b) if a < b else (b, a)
                edge_faces[edge] = edge_faces.get(edge, 0) + 1
        boundary = set(boundary_edges(mesh))
        for edge, count in edge_faces.items():
            is_sharp = edge in mesh.sharp_edges
            is_boundary = count == 1
            color = "#d32f2f" if is_sharp else "#1565c0" if is_boundary else "#90a4ae"
            line_width = 3.0 if is_sharp else 1.6 if is_boundary else 0.7
            a = project(projected[edge[0]])
            b = project(projected[edge[1]])
            lines.append(
                f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" '
                f'stroke="{color}" stroke-width="{line_width}" stroke-linecap="round"/>'
            )
        lines.append(
            f'<text x="{left + 18}" y="440" font-size="12">'
            f'V {len(mesh.vertices)}  F {len(mesh.faces)}  '
            f'boundary {record["boundary_vertices"]}  interior {record["interior_vertices"]}'
            f'</text>'
        )
        lines.append(
            f'<text x="{left + 18}" y="458" font-size="12">'
            f'sharp edges {len(mesh.sharp_edges)}  '
            f'ridge deviation {float(record["ridge_deviation"]):.1e}  '
            f'crease {float(record["min_crease_deg"]):.1f} deg</text>'
        )
    lines.extend(
        [
            '<line x1="472" y1="490" x2="500" y2="490" stroke="#d32f2f" stroke-width="3"/>',
            '<text x="508" y="495" font-size="12">sharp ridge</text>',
            '<line x1="620" y1="490" x2="648" y2="490" stroke="#1565c0" stroke-width="2"/>',
            '<text x="656" y="495" font-size="12">boundary</text>',
            '<line x1="760" y1="490" x2="788" y2="490" stroke="#90a4ae" stroke-width="1"/>',
            '<text x="796" y="495" font-size="12">interior</text>',
        ]
    )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")
