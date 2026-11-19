"""L-system plant generation.

A bracketed stochastic-free deterministic L-system is rewritten iteratively
and interpreted by a 2D turtle.  Every produced segment keeps its recursion
depth (branch hierarchy level), leaves are emitted at terminal ``L`` symbols,
and a bounding box is accumulated while walking the string.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LSystemParams:
    """Rule and geometry parameters of one L-system plant."""

    name: str
    axiom: str
    rules: dict[str, str]
    angle_deg: float
    step: float
    leaf_length: float = 0.35

    @property
    def angle_rad(self) -> float:
        return math.radians(self.angle_deg)


@dataclass
class Segment:
    start: tuple[float, float]
    end: tuple[float, float]
    level: int
    width: float


@dataclass
class Leaf:
    base: tuple[float, float]
    tip: tuple[float, float]
    level: int


@dataclass
class Tree:
    params: LSystemParams
    depth: int
    string: str
    segments: list[Segment] = field(default_factory=list)
    leaves: list[Leaf] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    elapsed_ms: float = 0.0

    @property
    def level_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for seg in self.segments:
            counts[seg.level] = counts.get(seg.level, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def bbox_size(self) -> tuple[float, float]:
        xmin, ymin, xmax, ymax = self.bbox
        return (xmax - xmin, ymax - ymin)

    def summary(self) -> dict[str, object]:
        xmin, ymin, xmax, ymax = self.bbox
        return {
            "name": self.params.name,
            "depth": self.depth,
            "string_len": len(self.string),
            "segment_instances": len(self.segments),
            "leaf_instances": len(self.leaves),
            "total_instances": len(self.segments) + len(self.leaves),
            "levels": self.level_counts,
            "max_level": max(self.level_counts, default=0),
            "bbox": {
                "xmin": round(xmin, 4),
                "ymin": round(ymin, 4),
                "xmax": round(xmax, 4),
                "ymax": round(ymax, 4),
                "width": round(self.bbox_size[0], 4),
                "height": round(self.bbox_size[1], 4),
            },
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


def rewrite(params: LSystemParams, depth: int) -> str:
    """Apply production rules ``depth`` times starting from the axiom."""
    current = params.axiom
    rules = params.rules
    for _ in range(depth):
        current = "".join(rules.get(ch, ch) for ch in current)
    return current


@dataclass
class _Turtle:
    x: float
    y: float
    heading: float
    level: int


def _interpret(params: LSystemParams, depth: int, string: str) -> Tree:
    angle = params.angle_rad
    step = params.step
    tree = Tree(params=params, depth=depth, string=string)
    turtle = _Turtle(0.0, 0.0, math.pi / 2.0, 0)
    stack: list[_Turtle] = []
    xmin = ymin = xmax = ymax = 0.0

    def extend_box(x: float, y: float) -> None:
        nonlocal xmin, ymin, xmax, ymax
        if x < xmin:
            xmin = x
        if x > xmax:
            xmax = x
        if y < ymin:
            ymin = y
        if y > ymax:
            ymax = y

    for symbol in string:
        if symbol in "FA":
            nx = turtle.x + step * math.cos(turtle.heading)
            ny = turtle.y + step * math.sin(turtle.heading)
            width = max(0.5, 4.0 * 0.72**turtle.level)
            tree.segments.append(
                Segment((turtle.x, turtle.y), (nx, ny), turtle.level, width)
            )
            turtle.x, turtle.y = nx, ny
            extend_box(nx, ny)
        elif symbol == "L":
            tx = turtle.x + params.leaf_length * math.cos(turtle.heading)
            ty = turtle.y + params.leaf_length * math.sin(turtle.heading)
            tree.leaves.append(Leaf((turtle.x, turtle.y), (tx, ty), turtle.level))
            extend_box(tx, ty)
        elif symbol == "+":
            turtle.heading += angle
        elif symbol == "-":
            turtle.heading -= angle
        elif symbol == "[":
            stack.append(
                _Turtle(turtle.x, turtle.y, turtle.heading, turtle.level)
            )
            turtle.level += 1
        elif symbol == "]":
            if stack:
                turtle = stack.pop()

    tree.bbox = (xmin, ymin, xmax, ymax)
    return tree


def generate(params: LSystemParams, depth: int) -> Tree:
    """Rewrite to ``depth`` and interpret the result, timing the whole run."""
    start = time.perf_counter()
    string = rewrite(params, depth)
    tree = _interpret(params, depth, string)
    tree.elapsed_ms = (time.perf_counter() - start) * 1000.0
    return tree

