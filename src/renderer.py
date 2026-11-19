"""CPU rasteriser: nebula volume sprites, star sprites and additive batching."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from camera import project
from noise import fbm3


@dataclass
class RenderStats:
    star_count: int
    visible_stars: int
    nebula_points: int
    draw_batches: int
    draw_calls: int


def _additive_blend(base: np.ndarray, layer: np.ndarray) -> np.ndarray:
    return np.clip(base + layer, 0, 255).astype(np.uint8)


def _radial_sprite(size: int, color: tuple[float, float, float],
                   intensity: float) -> np.ndarray:
    r = np.arange(size) - (size - 1) / 2.0
    xx, yy = np.meshgrid(r, r)
    dist = np.sqrt(xx * xx + yy * yy) / ((size - 1) / 2.0)
    alpha = np.clip(1.0 - dist, 0.0, 1.0) ** 2 * intensity
    sprite = np.zeros((size, size, 3))
    sprite[..., 0] = alpha * color[0]
    sprite[..., 1] = alpha * color[1]
    sprite[..., 2] = alpha * color[2]
    return np.clip(sprite * 255, 0, 255).astype(np.uint8)


def generate_nebula(galaxy: dict, n_points: int = 2600, seed: int = 77) -> dict:
    """Nebula sprites sampled near the star disc, coloured by 3D fBm fields."""
    rng = np.random.default_rng(seed)
    pos = galaxy["positions"]
    idx = rng.integers(0, pos.shape[0], n_points)
    jitter = rng.normal(0, 0.55, (n_points, 3))
    jitter[:, 2] *= 0.4
    points = pos[idx] + jitter

    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    red_field = fbm3(x * 0.31 + 5, y * 0.31, z * 0.31, octaves=4, seed=101)
    teal_field = fbm3(x * 0.43, y * 0.43 + 9, z * 0.43, octaves=4, seed=202)
    violet_field = fbm3(x * 0.57 + 3, y * 0.57, z * 0.57 + 4, octaves=3, seed=303)
    colors = np.stack([
        0.85 * red_field + 0.25 * violet_field,
        0.55 * teal_field + 0.3 * red_field,
        0.9 * violet_field + 0.4 * teal_field,
    ], axis=1)
    colors = np.clip(colors, 0, 1)
    radius_mag = np.linalg.norm(points[:, :2], axis=1)
    intensity = np.clip(0.5 * np.exp(-radius_mag / 8.0) + 0.35 * teal_field, 0.1, 1.0)
    sprite_size = rng.integers(14, 34, n_points)
    return {"points": points, "colors": colors, "intensity": intensity,
            "sprite_sizes": sprite_size}


def render_scene(galaxy: dict, nebula: dict, view: np.ndarray, proj: np.ndarray,
                 width: int = 720, height: int = 720) -> tuple[Image.Image, RenderStats]:
    frame = np.zeros((height, width, 3), dtype=np.float64)
    draw_calls = 0

    # Batch 1: nebula sprites, far-to-near for stable additive overlap.
    nxy, nvis = project(nebula["points"], view, proj, width, height)
    order = np.argsort(-nxy[:, 2])
    cache: dict[tuple, np.ndarray] = {}
    for i in order:
        if not nvis[i]:
            continue
        size = int(nebula["sprite_sizes"][i])
        key = (size, int(nebula["intensity"][i] * 10))
        color = tuple(float(c) for c in nebula["colors"][i])
        sprite = _radial_sprite(size, color, nebula["intensity"][i] * 0.32)
        cache[key] = sprite
        x0 = int(nxy[i, 0] - size / 2)
        y0 = int(nxy[i, 1] - size / 2)
        x1, y1 = x0 + size, y0 + size
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(width, x1), min(height, y1)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        crop = sprite[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        frame[sy0:sy1, sx0:sx1] += crop.astype(np.float64)
        draw_calls += 1

    # Batch 2: star points splatted as soft radial sprites in one numpy pass.
    sxy, svis = project(galaxy["positions"], view, proj, width, height)
    visible = int(svis.sum())
    cols = np.clip(galaxy["colors"] * 255, 0, 255).astype(np.uint8)
    kernel = np.array([[0.0, 0.25, 0.0],
                       [0.25, 1.0, 0.25],
                       [0.0, 0.25, 0.0]])
    for i in np.where(svis)[0]:
        px, py = int(round(sxy[i, 0])), int(round(sxy[i, 1]))
        scale = float(galaxy["sizes"][i])
        x0, y0 = px - 1, py - 1
        x1, y1 = px + 2, py + 2
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(width, x1), min(height, y1)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        kx0, ky0 = sx0 - x0, sy0 - y0
        kx1, ky1 = kx0 + (sx1 - sx0), ky0 + (sy1 - sy0)
        glow = kernel[ky0:ky1, kx0:kx1, None] * scale
        frame[sy0:sy1, sx0:sx1] += glow * cols[i].astype(np.float64)
        draw_calls += 1
    img = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8), "RGB")

    stats = RenderStats(
        star_count=galaxy["positions"].shape[0],
        visible_stars=visible,
        nebula_points=nebula["points"].shape[0],
        draw_batches=2,
        draw_calls=draw_calls,
    )
    return img, stats
