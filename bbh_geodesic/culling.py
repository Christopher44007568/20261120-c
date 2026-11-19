"""Conservative perspective-frustum culling over the bone BVH."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .bvh import BVHNode, BoneBVH
from .geometry import AABB, Vec3, add, cross, dot, normalize, scale, sub


@dataclass(frozen=True)
class Plane:
    normal: Vec3
    offset: float

    def support(self, box: AABB) -> float:
        return box.support_plane(self.normal, self.offset)


@dataclass(frozen=True)
class Frustum:
    position: Vec3
    target: Vec3
    vertical_fov_deg: float
    aspect: float
    near: float
    far: float
    planes: tuple[Plane, ...]

    @classmethod
    def create(
        cls,
        position: Vec3,
        target: Vec3,
        vertical_fov_deg: float,
        aspect: float = 1.0,
        near: float = 0.05,
        far: float = 20.0,
    ) -> "Frustum":
        forward = normalize(sub(target, position))
        up_hint = (0.0, 1.0, 0.0)
        if abs(dot(forward, up_hint)) > 0.98:
            up_hint = (0.0, 0.0, 1.0)
        right = normalize(cross(forward, up_hint))
        up = normalize(cross(right, forward))
        tan_v = math.tan(math.radians(vertical_fov_deg) * 0.5)
        tan_h = tan_v * aspect

        def plane(normal: Vec3, required: float) -> Plane:
            return Plane(normal, -required)

        planes = (
            plane(forward, dot(forward, position) + near),
            plane(scale(forward, -1.0), -(dot(forward, position) + far)),
            plane(add(right, scale(forward, tan_h)), dot(add(right, scale(forward, tan_h)), position)),
            plane(add(scale(right, -1.0), scale(forward, tan_h)), dot(add(scale(right, -1.0), scale(forward, tan_h)), position)),
            plane(add(up, scale(forward, tan_v)), dot(add(up, scale(forward, tan_v)), position)),
            plane(add(scale(up, -1.0), scale(forward, tan_v)), dot(add(scale(up, -1.0), scale(forward, tan_v)), position)),
        )
        return cls(position, target, vertical_fov_deg, aspect, near, far, planes)

    def outside(self, box: AABB) -> bool:
        return any(plane.support(box) < 0.0 for plane in self.planes)


def _subtree_names(node: BVHNode) -> set[str]:
    names = {node.name}
    for child in node.children:
        names.update(_subtree_names(child))
    return names


def cull(
    root: BVHNode,
    frustum: Frustum,
    depth_limit: int,
) -> set[str]:
    """Return primitive names safely rejected at or above a hierarchy depth."""
    culled: set[str] = set()

    def visit(node: BVHNode) -> None:
        assert node.box is not None and node.own_box is not None
        if frustum.outside(node.box):
            culled.update(_subtree_names(node))
            return
        if frustum.outside(node.own_box):
            culled.add(node.name)
        if node.depth < depth_limit:
            for child in node.children:
                visit(child)

    visit(root)
    return culled


def brute_force(bvh: BoneBVH, frustum: Frustum) -> set[str]:
    outside: set[str] = set()
    for node in bvh.iter_nodes():
        assert node.own_box is not None
        if frustum.outside(node.own_box):
            outside.add(node.name)
    return outside


def make_cameras(bvh: BoneBVH, seed: int = 20261120) -> list[Frustum]:
    rng = random.Random(seed)
    targets: list[Vec3] = []
    for name in ("pelvis", "chest", "head", "hand.L", "hand.R", "foot.L", "foot.R"):
        node = bvh.nodes[name]
        assert node.box is not None
        targets.append(node.box.center)
    cameras: list[Frustum] = []
    for _ in range(18):
        azimuth = rng.uniform(0.0, 2.0 * math.pi)
        elevation = rng.uniform(-0.10, 0.42)
        distance = rng.uniform(2.8, 4.2)
        target = (0.0, 1.00, 0.0)
        position = add(
            target,
            (
                distance * math.cos(elevation) * math.cos(azimuth),
                distance * math.sin(elevation),
                distance * math.cos(elevation) * math.sin(azimuth),
            ),
        )
        cameras.append(Frustum.create(position, target, rng.uniform(17.0, 25.0)))
    for _ in range(18):
        target = rng.choice(targets)
        azimuth = rng.uniform(0.0, 2.0 * math.pi)
        elevation = rng.uniform(-0.25, 0.55)
        distance = rng.uniform(1.15, 2.30)
        position = add(
            target,
            (
                distance * math.cos(elevation) * math.cos(azimuth),
                distance * math.sin(elevation),
                distance * math.cos(elevation) * math.sin(azimuth),
            ),
        )
        cameras.append(Frustum.create(position, target, rng.uniform(20.0, 32.0)))
    return cameras


def benchmark_depths(
    bvh: BoneBVH,
    frames: list[dict[str, tuple[Vec3, ...]]],
    cameras: list[Frustum],
    depths: range = range(0, 7),
) -> tuple[list[dict[str, float | int | bool]], dict[str, float | int | bool]]:
    primitive_count = len(bvh.nodes)
    totals = {depth: 0 for depth in depths}
    queries = 0
    false_culls = 0
    partial_subset_violations = 0
    full_mismatches = 0
    safe_ancestor_violations = 0

    for points in frames:
        bvh.update(points)
        for frustum in cameras:
            brute = brute_force(bvh, frustum)
            hierarchical = cull(bvh.root, frustum, max(depths))
            false_culls += len(hierarchical - brute)
            full_mismatches += int(hierarchical != brute)
            for depth in depths:
                rejected = cull(bvh.root, frustum, depth)
                totals[depth] += len(rejected)
                if not rejected.issubset(brute):
                    partial_subset_violations += 1
                for node in bvh.iter_nodes():
                    if node.name in rejected and node.own_box is not None:
                        if not frustum.outside(node.own_box):
                            safe_ancestor_violations += 1
            queries += 1

    rows: list[dict[str, float | int | bool]] = []
    for depth in depths:
        mean_culled = totals[depth] / queries
        rows.append(
            {
                "depth": depth,
                "mean_culled_primitives": mean_culled,
                "culling_rate": mean_culled / primitive_count,
                "mean_candidate_primitives": primitive_count - mean_culled,
                "queries": queries,
            }
        )
    validation = {
        "queries": queries,
        "false_culls": false_culls,
        "partial_subset_violations": partial_subset_violations,
        "full_mismatches_vs_bruteforce": full_mismatches,
        "outside_ancestor_violations": safe_ancestor_violations,
        "safe": false_culls == 0
        and partial_subset_violations == 0
        and safe_ancestor_violations == 0,
        "exact_at_full_depth": full_mismatches == 0,
    }
    return rows, validation
