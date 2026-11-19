"""Render L-system trees as 2D projected line segments."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from camera import look_at, project, perspective


def render_tree(tree: dict, elevation_deg: float = 12.0, azimuth_deg: float = 35.0,
                size: int = 640) -> tuple[Image.Image, dict]:
    segments = tree["segments"]
    pts = np.array([s[0] for s in segments] + [s[1] for s in segments])
    center = (pts.max(axis=0) + pts.min(axis=0)) / 2
    extent = np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))
    distance = extent * 1.55
    el, az = np.radians(elevation_deg), np.radians(azimuth_deg)
    eye = center + distance * np.array([
        np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)
    ])
    view = look_at(eye, center, np.array([0.0, 0.0, 1.0]))
    proj = perspective(45.0, 1.0, 0.1, distance * 10.0)

    all_ends = np.array([s[1] for s in segments])
    proj_pts, _ = project(np.vstack([pts, all_ends]), view, proj, size, size)
    n = pts.shape[0]
    starts = proj_pts[:n // 2]
    ends = proj_pts[n:]

    img = Image.new("RGB", (size, size), (8, 10, 18))
    draw = ImageDraw.Draw(img)
    depths = []
    for (p0, p1, w), a, b in zip(segments, starts, ends):
        line_w = max(1, int(round(w * 2.2)))
        shade = int(np.clip(120 + 90 * min(w, 1.0), 0, 230))
        draw.line((a[0], a[1], b[0], b[1]), fill=(shade // 2, shade // 2 + 20, shade),
                  width=line_w)
        depths.append((p0[2] + p1[2]) / 2)

    if tree["leaves"].shape[0]:
        leaf_xy, leaf_vis = project(tree["leaves"], view, proj, size, size)
        rng = np.random.default_rng(9)
        for i in np.where(leaf_vis)[0]:
            r = rng.uniform(2.0, 4.5) / (1.0 + 0.22 * tree["depth"])
            x, y = leaf_xy[i, 0], leaf_xy[i, 1]
            draw.ellipse((x - r, y - r, x + r, y + r),
                         fill=(40, int(rng.uniform(110, 170)), 55))

    metrics = {
        "branch_segments": len(segments),
        "leaf_tips": int(tree["leaves"].shape[0]),
        "sentence_length": tree["sentence_len"],
        "depth": tree["depth"],
    }
    return img, metrics
