"""Early-Z / Z-Prepass overdraw simulator.

A tiny software rasterizer that models three GPU pipelines and counts
per-fragment depth tests, shader invocations, rejections and blending work,
so the overdraw impact of draw order and depth prepass can be measured.
"""

from .raster import (
    C_DRAW,
    C_PASS_SETUP,
    C_PREPASS,
    C_SHADER,
    C_DEPTH,
    Metrics,
    Quad,
    run_pipeline,
)
from .scenarios import Scene, make_scene, order_quads

__all__ = [
    "C_DRAW",
    "C_PASS_SETUP",
    "C_PREPASS",
    "C_SHADER",
    "C_DEPTH",
    "Metrics",
    "Quad",
    "run_pipeline",
    "Scene",
    "make_scene",
    "order_quads",
]
