"""A small deterministic rasterizer used to cross-check traffic accounting."""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace

from .geometry import Mesh, Vec3, cross, dot, normalize, vsub
from .render_compare import FrameConfig, estimate_frame


SAMPLE_POSITIONS = {
    1: ((0.5, 0.5),),
    2: ((0.25, 0.5), (0.75, 0.5)),
    4: ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)),
}


def _project(mesh: Mesh, width: int, height: int) -> list[tuple[float, float, float] | None]:
    eye: Vec3 = (0.0, -6.8, 2.7)
    target: Vec3 = (0.0, 0.0, 0.0)
    forward = normalize(vsub(target, eye))
    right = normalize(cross(forward, (0.0, 0.0, 1.0)))
    up = cross(right, forward)
    focal = 1.55 * height
    projected: list[tuple[float, float, float] | None] = []
    for vertex in mesh.vertices:
        relative = vsub(vertex, eye)
        view_x = dot(relative, right)
        view_y = dot(relative, up)
        view_z = dot(relative, forward)
        if view_z <= 0.05:
            projected.append(None)
            continue
        projected.append(
            (
                width * 0.5 + focal * view_x / view_z,
                height * 0.5 - focal * view_y / view_z,
                view_z,
            )
        )
    return projected


def _edge(a: tuple[float, float], b: tuple[float, float], px: float, py: float) -> float:
    return (px - a[0]) * (b[1] - a[1]) - (py - a[1]) * (b[0] - a[0])


def rasterize(mesh: Mesh, config: FrameConfig) -> dict[str, float | int | str]:
    width, height = config.width, config.height
    samples = config.samples
    if samples not in SAMPLE_POSITIONS:
        raise ValueError("raster validation supports 1, 2, or 4 samples")
    projected = _project(mesh, width, height)
    sample_count = width * height * samples
    depth = [float("inf")] * sample_count
    triangle_ids = [-1] * sample_count
    sample_offsets = SAMPLE_POSITIONS[samples]

    for face_index, face in enumerate(mesh.faces):
        points = [projected[index] for index in face]
        if any(point is None for point in points):
            continue
        a, b, c = points  # type: ignore[misc]
        area = _edge((a[0], a[1]), (b[0], b[1]), c[0], c[1])
        if abs(area) < 1e-12:
            continue
        min_x = max(0, int(math.floor(min(a[0], b[0], c[0]))))
        max_x = min(width - 1, int(math.ceil(max(a[0], b[0], c[0]))))
        min_y = max(0, int(math.floor(min(a[1], b[1], c[1]))))
        max_y = min(height - 1, int(math.ceil(max(a[1], b[1], c[1]))))
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                for sample_index, (offset_x, offset_y) in enumerate(sample_offsets):
                    px = x + offset_x
                    py = y + offset_y
                    w0 = _edge((b[0], b[1]), (c[0], c[1]), px, py) / area
                    w1 = _edge((c[0], c[1]), (a[0], a[1]), px, py) / area
                    w2 = 1.0 - w0 - w1
                    if w0 < 0.0 or w1 < 0.0 or w2 < 0.0:
                        continue
                    inverse_z = w0 / a[2] + w1 / b[2] + w2 / c[2]
                    if inverse_z <= 0.0:
                        continue
                    z_value = 1.0 / inverse_z
                    sample_id = (y * width + x) * samples + sample_index
                    if z_value < depth[sample_id]:
                        depth[sample_id] = z_value
                        triangle_ids[sample_id] = face_index

    covered_samples = sum(1 for value in triangle_ids if value >= 0)
    covered_pixels = sum(
        1 for pixel in range(width * height) if any(
            triangle_ids[pixel * samples + sample] >= 0 for sample in range(samples)
        )
    )
    visible_ids = {value for value in triangle_ids if value >= 0}
    frame = estimate_frame(replace(config, coverage=covered_pixels / (width * height)))
    gbuffer = config.gbuffer_bytes
    visibility = config.visibility_bytes
    depth_bytes = config.depth_bytes
    hdr = config.hdr_bytes
    deferred_traffic = (
        covered_samples * (gbuffer + depth_bytes)
        + covered_pixels * (gbuffer + depth_bytes + hdr)
    )
    visibility_traffic = (
        covered_samples * (visibility + depth_bytes)
        + covered_pixels * (
            visibility + depth_bytes + gbuffer + config.material_cache_penalty + hdr
        )
    )
    digest = hashlib.sha256(
        f"{width}x{height}:{samples}:{covered_samples}:{covered_pixels}:{len(visible_ids)}".encode()
    ).hexdigest()
    return {
        "width": width,
        "height": height,
        "samples": samples,
        "covered_pixels": covered_pixels,
        "covered_samples": covered_samples,
        "coverage": covered_pixels / (width * height),
        "visible_triangles": len(visible_ids),
        "deferred_traffic_bytes": deferred_traffic,
        "visibility_traffic_bytes": visibility_traffic,
        "traffic_saving_percent": 100.0 * (deferred_traffic - visibility_traffic) / deferred_traffic,
        "estimated_frame_deferred_traffic_bytes": frame["deferred_traffic_bytes"],
        "digest": digest,
    }


def validate(mesh: Mesh, width: int = 240, height: int = 135, repeats: int = 3) -> dict[str, object]:
    rows = []
    for samples in (1, 2, 4):
        config = FrameConfig(width=width, height=height, samples=samples)
        first = rasterize(mesh, config)
        repeats_digest = []
        for _ in range(repeats):
            repeats_digest.append(rasterize(mesh, config)["digest"])
        first["repeatable"] = len(set(repeats_digest)) == 1
        rows.append(first)
    return {
        "resolution": f"{width}x{height}",
        "repeats": repeats,
        "all_repeatable": all(row["repeatable"] for row in rows),
        "rows": rows,
    }
