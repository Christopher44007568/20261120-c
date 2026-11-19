"""Deterministic scene generation and draw-order permutations."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .raster import Quad

ORDERS = ("front_to_back", "back_to_front", "random")


@dataclass(frozen=True)
class Scene:
    name: str
    width: int
    height: int
    quads: tuple[Quad, ...]
    seed: int
    count: int
    overlap: str
    transparent_fraction: float
    alpha_test_fraction: float


def _clamped_rect(rng: random.Random, width: int, height: int,
                  overlap: str) -> tuple[int, int, int, int]:
    if overlap == "heavy":
        wf, hf = rng.uniform(0.65, 0.95), rng.uniform(0.65, 0.95)
        jitter_x, jitter_y = int(width * 0.08), int(height * 0.08)
    elif overlap == "sparse":
        wf, hf = rng.uniform(0.12, 0.28), rng.uniform(0.12, 0.28)
        jitter_x, jitter_y = int(width * 0.9), int(height * 0.9)
    else:
        raise ValueError(f"unknown overlap mode: {overlap!r}")

    quad_w = max(1, int(width * wf))
    quad_h = max(1, int(height * hf))
    cx = width // 2 + rng.randint(-jitter_x, jitter_x)
    cy = height // 2 + rng.randint(-jitter_y, jitter_y)
    x0 = min(max(0, cx - quad_w // 2), width - 1)
    y0 = min(max(0, cy - quad_h // 2), height - 1)
    x1 = min(width, x0 + quad_w)
    y1 = min(height, y0 + quad_h)
    return x0, y0, x1, y1


def make_scene(name: str, *, seed: int, width: int = 256, height: int = 256,
               count: int = 12, overlap: str = "heavy",
               transparent_fraction: float = 0.0,
               alpha_test_fraction: float = 0.0) -> Scene:
    """Build a reproducible scene.

    ``overlap="heavy"`` stacks large quads near the framebuffer center so
    most covered pixels are touched many times; ``"sparse"`` scatters small
    quads to model a low-overlap scene.
    """

    if not 0.0 <= transparent_fraction <= 1.0:
        raise ValueError("transparent_fraction must be within [0, 1]")
    if not 0.0 <= alpha_test_fraction <= 1.0:
        raise ValueError("alpha_test_fraction must be within [0, 1]")
    if transparent_fraction + alpha_test_fraction > 1.0:
        raise ValueError("transparent + alpha_test fractions cannot exceed 1")
    if count <= 0:
        raise ValueError("count must be positive")

    rng = random.Random(seed)
    depths = rng.sample([i / count for i in range(1, count + 1)], count)
    transparent_count = round(count * transparent_fraction)
    alpha_test_count = round(count * alpha_test_fraction)
    special_ids = rng.sample(range(count),
                             transparent_count + alpha_test_count)
    transparent_ids = set(special_ids[:transparent_count])
    alpha_test_ids = set(special_ids[transparent_count:])

    quads: list[Quad] = []
    for index in range(count):
        x0, y0, x1, y1 = _clamped_rect(rng, width, height, overlap)
        quads.append(
            Quad(
                quad_id=index,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                z=depths[index],
                transparent=index in transparent_ids,
                alpha_test=index in alpha_test_ids,
            )
        )

    return Scene(
        name=name,
        width=width,
        height=height,
        quads=tuple(quads),
        seed=seed,
        count=count,
        overlap=overlap,
        transparent_fraction=transparent_fraction,
        alpha_test_fraction=alpha_test_fraction,
    )


def order_quads(scene: Scene, order: str) -> list[Quad]:
    """Return scene quads in the requested submission order."""

    if order == "front_to_back":
        return sorted(scene.quads, key=lambda quad: quad.z)
    if order == "back_to_front":
        return sorted(scene.quads, key=lambda quad: quad.z, reverse=True)
    if order == "random":
        rng = random.Random(scene.seed * 7919 + 17)
        shuffled = list(scene.quads)
        rng.shuffle(shuffled)
        return shuffled
    raise ValueError(f"unknown draw order: {order!r}; expected one of "
                     f"{', '.join(ORDERS)}")
