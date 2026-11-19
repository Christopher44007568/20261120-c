"""Software framebuffer / depth-buffer simulation.

The rasterizer works on axis-aligned colored quads, which is enough to model
fragment coverage, depth testing and per-pixel overdraw without depending on
any GPU API. Every cost is expressed in deterministic model cycles so results
are reproducible; wall-clock timing is layered on top by the benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PIPELINES = ("forward_no_early_z", "forward_early_z", "z_prepass")

# Deterministic per-fragment / per-draw cost model (arbitrary GPU cycles).
C_DEPTH = 3        # depth buffer read + compare + conditional write
C_SHADER = 25      # full fragment shader (lighting, textures, ...)
C_BLEND = 8        # blend read-modify-write used by transparent fragments
C_ALPHA_TEST = 4   # texture lookup + discard check for alpha-tested cuts
C_PREPASS = 1      # cheap depth-only shading work in the prepass
C_DRAW = 50        # fixed draw-call / state-change cost
C_PASS_SETUP = 200  # extra render pass setup (clears, targets, barriers)


@dataclass(frozen=True)
class Quad:
    """One axis-aligned quad rendered as a single draw call."""

    quad_id: int
    x0: int
    y0: int
    x1: int  # exclusive
    y1: int  # exclusive
    z: float
    transparent: bool = False
    alpha_test: bool = False

    @property
    def area(self) -> int:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass
class Metrics:
    pipeline: str
    draw_order: str
    width: int
    height: int
    draws: int = 0
    fragments_visited: int = 0
    depth_tests: int = 0
    depth_rejects: int = 0
    shader_invocations: int = 0
    opaque_shaded: int = 0
    blend_invocations: int = 0
    pass_count: int = 1
    model_cycles: int = 0
    elapsed_ms: float = 0.0
    draw_map: list[int] = field(default_factory=list)
    shade_map: list[int] = field(default_factory=list)

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def covered_pixels(self) -> int:
        return sum(1 for value in self.draw_map if value > 0)

    @property
    def redundant_shaded(self) -> int:
        """Shaded fragments whose result is later replaced (wasted work)."""
        return max(0, self.shader_invocations - self.covered_pixels)

    def avg_draws_per_pixel(self, covered_only: bool = False) -> float:
        if self.fragments_visited == 0:
            return 0.0
        if covered_only:
            covered = self.covered_pixels
            return self.fragments_visited / covered if covered else 0.0
        return self.fragments_visited / self.pixels

    def overdraw_histogram(self) -> dict[int, int]:
        return _histogram(self.draw_map)

    def shading_histogram(self) -> dict[int, int]:
        """Distribution of actual fragment-shader runs per pixel."""
        return _histogram(self.shade_map)


def _histogram(values: list[int]) -> dict[int, int]:
    histogram: dict[int, int] = {}
    for value in values:
        histogram[value] = histogram.get(value, 0) + 1
    return dict(sorted(histogram.items()))


def _pixels(quad: Quad) -> tuple[range, range]:
    return range(quad.y0, quad.y1), range(quad.x0, quad.x1)


def _forward(width: int, height: int, quads: list[Quad], early_z: bool,
             order: str, pipeline: str) -> Metrics:
    depth = [float("inf")] * (width * height)
    draw_map = [0] * (width * height)
    shade_map = [0] * (width * height)
    metrics = Metrics(pipeline=pipeline, draw_order=order,
                      width=width, height=height, draws=len(quads))

    for quad in quads:
        metrics.model_cycles += C_DRAW
        rows, cols = _pixels(quad)
        for y in rows:
            row_base = y * width
            for x in cols:
                index = row_base + x
                metrics.fragments_visited += 1
                draw_map[index] += 1

                # Blended fragments never write depth and must always be
                # shaded: this is the early-Z failure boundary. Alpha-tested
                # cuts discard but surviving fragments still write depth, so
                # they take the normal opaque early-Z path below.
                if quad.transparent and not quad.alpha_test:
                    metrics.depth_tests += 1
                    metrics.shader_invocations += 1
                    metrics.blend_invocations += 1
                    shade_map[index] += 1
                    metrics.model_cycles += C_DEPTH + C_SHADER + C_BLEND
                    continue

                if early_z:
                    metrics.depth_tests += 1
                    metrics.model_cycles += C_DEPTH
                    if quad.z >= depth[index]:
                        metrics.depth_rejects += 1
                        continue

                metrics.shader_invocations += 1
                metrics.opaque_shaded += 1
                shade_map[index] += 1
                metrics.model_cycles += C_SHADER
                if quad.alpha_test:
                    metrics.model_cycles += C_ALPHA_TEST
                if not early_z:
                    metrics.depth_tests += 1
                    metrics.model_cycles += C_DEPTH
                    if quad.z >= depth[index]:
                        metrics.depth_rejects += 1
                        continue
                depth[index] = quad.z

    metrics.draw_map = draw_map
    metrics.shade_map = shade_map
    return metrics


def _z_prepass(width: int, height: int, quads: list[Quad],
               order: str) -> Metrics:
    """Depth prepass followed by a shading pass (depth-first, then color)."""

    nearest = [float("inf")] * (width * height)
    draw_map = [0] * (width * height)
    shade_map = [0] * (width * height)
    metrics = Metrics(pipeline="z_prepass", draw_order=order,
                      width=width, height=height, draws=len(quads),
                      pass_count=2)
    metrics.model_cycles += C_PASS_SETUP

    # Pass 1: depth-only. Transparent objects are excluded because they must
    # not occupy the depth buffer (otherwise objects behind them disappear).
    # Alpha-tested cuts are included: surviving texels legitimately write z.
    for quad in quads:
        if quad.transparent and not quad.alpha_test:
            continue
        metrics.model_cycles += C_DRAW
        rows, cols = _pixels(quad)
        for y in rows:
            row_base = y * width
            for x in cols:
                index = row_base + x
                metrics.depth_tests += 1
                metrics.model_cycles += C_DEPTH + C_PREPASS
                if quad.z < nearest[index]:
                    nearest[index] = quad.z

    # Pass 2: full shading. Opaque fragments equal to the prepass depth win
    # with early-Z; transparent fragments are still shaded and blended.
    for quad in quads:
        metrics.model_cycles += C_DRAW
        rows, cols = _pixels(quad)
        for y in rows:
            row_base = y * width
            for x in cols:
                index = row_base + x
                metrics.fragments_visited += 1
                draw_map[index] += 1
                if quad.transparent and not quad.alpha_test:
                    metrics.depth_tests += 1
                    metrics.shader_invocations += 1
                    metrics.blend_invocations += 1
                    shade_map[index] += 1
                    metrics.model_cycles += C_DEPTH + C_SHADER + C_BLEND
                    continue

                metrics.depth_tests += 1
                metrics.model_cycles += C_DEPTH
                if quad.z != nearest[index]:
                    metrics.depth_rejects += 1
                    continue
                metrics.shader_invocations += 1
                metrics.opaque_shaded += 1
                shade_map[index] += 1
                metrics.model_cycles += C_SHADER
                if quad.alpha_test:
                    metrics.model_cycles += C_ALPHA_TEST

    metrics.draw_map = draw_map
    metrics.shade_map = shade_map
    return metrics


def run_pipeline(pipeline: str, width: int, height: int,
                 quads: list[Quad], draw_order: str) -> Metrics:
    if pipeline == "forward_no_early_z":
        return _forward(width, height, quads, early_z=False,
                        order=draw_order, pipeline=pipeline)
    if pipeline == "forward_early_z":
        return _forward(width, height, quads, early_z=True,
                        order=draw_order, pipeline=pipeline)
    if pipeline == "z_prepass":
        return _z_prepass(width, height, quads, order=draw_order)
    raise ValueError(f"unknown pipeline: {pipeline!r}; expected one of "
                     f"{', '.join(PIPELINES)}")
