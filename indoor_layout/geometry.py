"""二维矩形几何：碰撞、膨胀、网格栅格化等基础工具。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """轴对齐矩形，坐标单位为米。"""

    x: float
    y: float
    w: float
    h: float

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def rotated(self) -> "Rect":
        """旋转 90 度（围绕自身中心），保持中心不变。"""
        return Rect(self.cx - self.h / 2.0, self.cy - self.w / 2.0, self.h, self.w)

    def inflated(self, margin: float) -> "Rect":
        return Rect(self.x - margin, self.y - margin, self.w + 2 * margin, self.h + 2 * margin)

    def contains(self, other: "Rect") -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and other.x1 <= self.x1
            and other.y1 <= self.y1
        )

    def intersects(self, other: "Rect") -> bool:
        return self.x < other.x1 and other.x < self.x1 and self.y < other.y1 and other.y < self.y1

    def intersection_area(self, other: "Rect") -> float:
        ox = max(0.0, min(self.x1, other.x1) - max(self.x, other.x))
        oy = max(0.0, min(self.y1, other.y1) - max(self.y, other.y))
        return ox * oy

    def snapped(self, step: float) -> "Rect":
        return Rect(
            round(self.x / step) * step,
            round(self.y / step) * step,
            round(self.w / step) * step,
            round(self.h / step) * step,
        )


def count_pairwise_collisions(rects: list[Rect]) -> int:
    """统计矩形对之间的重叠数量（触碰不算碰撞）。"""
    collisions = 0
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects[i].intersects(rects[j]):
                collisions += 1
    return collisions


def total_overlap_area(rects: list[Rect]) -> float:
    total = 0.0
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            total += rects[i].intersection_area(rects[j])
    return total
