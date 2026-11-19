"""Bone-topology bounding-box hierarchy with per-pose updates."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from .geometry import AABB, Vec3
from .rig import BONE_BY_NAME, BONE_DEPTH, BONES, RunRig


@dataclass
class BVHNode:
    name: str
    depth: int
    parent: "BVHNode | None" = None
    children: list["BVHNode"] = field(default_factory=list)
    own_box: AABB | None = None
    box: AABB | None = None
    primitive_count: int = 1
    update_ns: int = 0

    @property
    def capsule_volume(self) -> float:
        bone = BONE_BY_NAME[self.name]
        segment = math.dist(bone.head, bone.tail)
        return math.pi * bone.radius**2 * segment + 4.0 / 3.0 * math.pi * bone.radius**3


class BoneBVH:
    def __init__(self, rig: RunRig | None = None) -> None:
        self.rig = rig or RunRig()
        self.nodes: dict[str, BVHNode] = {}
        for bone in BONES:
            self.nodes[bone.name] = BVHNode(bone.name, BONE_DEPTH[bone.name])
        for bone in BONES:
            node = self.nodes[bone.name]
            if bone.parent is not None:
                parent = self.nodes[bone.parent]
                node.parent = parent
                parent.children.append(node)
        self.root = self.nodes[self.rig.root_name]
        for node in reversed(BONES):
            bvh_node = self.nodes[node.name]
            bvh_node.primitive_count = 1 + sum(
                child.primitive_count for child in bvh_node.children
            )
        self.last_timing: dict[str, int] = {}
        self.update_count = 0

    def _update_node(
        self,
        node: BVHNode,
        points: dict[str, tuple[Vec3, ...]],
        collect_timing: bool,
    ) -> AABB:
        started = time.perf_counter_ns() if collect_timing else 0
        node.own_box = AABB.from_points(points[node.name])
        own_elapsed = time.perf_counter_ns() - started if collect_timing else 0
        boxes = [node.own_box]
        for child in node.children:
            boxes.append(self._update_node(child, points, collect_timing))
        merge_started = time.perf_counter_ns() if collect_timing else 0
        node.box = AABB.from_boxes(boxes)
        if collect_timing:
            node.update_ns = own_elapsed + time.perf_counter_ns() - merge_started
            self.last_timing[node.name] = node.update_ns
        return node.box

    def update(
        self,
        points: dict[str, tuple[Vec3, ...]],
        collect_timing: bool = False,
    ) -> AABB:
        if collect_timing:
            self.last_timing = {}
        root_box = self._update_node(self.root, points, collect_timing)
        self.update_count += 1
        return root_box

    def update_pose(self, phase: float, collect_timing: bool = False) -> AABB:
        sample = self.rig.pose(phase)
        return self.update(sample.points, collect_timing)

    def iter_nodes(self) -> list[BVHNode]:
        result: list[BVHNode] = []

        def visit(node: BVHNode) -> None:
            result.append(node)
            for child in node.children:
                visit(child)

        visit(self.root)
        return result

    def layer_nodes(self) -> dict[int, list[BVHNode]]:
        layers: dict[int, list[BVHNode]] = {}
        for node in self.iter_nodes():
            layers.setdefault(node.depth, []).append(node)
        return dict(sorted(layers.items()))

    def validate_fit(
        self,
        points: dict[str, tuple[Vec3, ...]],
        tolerance: float = 1e-9,
    ) -> dict[str, float | int | bool]:
        nodes = self.iter_nodes()
        total_points = sum(len(points[node.name]) for node in nodes)
        contained = 0
        max_outside = 0.0
        hierarchy_ok = True
        subtree_contained = 0
        subtree_total = 0
        supported_faces = 0
        total_faces = 0
        fill_ratios: list[float] = []

        def subtree_points(node: BVHNode) -> list[Vec3]:
            result = list(points[node.name])
            for child in node.children:
                result.extend(subtree_points(child))
            return result

        for node in nodes:
            assert node.box is not None and node.own_box is not None
            own_points = points[node.name]
            for point in own_points:
                if node.box.contains(point, tolerance):
                    contained += 1
                else:
                    max_outside = max(
                        max_outside,
                        max(
                            node.box.minimum[a] - point[a]
                            if point[a] < node.box.minimum[a]
                            else point[a] - node.box.maximum[a]
                            if point[a] > node.box.maximum[a]
                            else 0.0
                            for a in range(3)
                        ),
                    )
            for point in subtree_points(node):
                subtree_total += 1
                if node.box.contains(point, tolerance):
                    subtree_contained += 1
            for child in node.children:
                if child.box is None or not node.box.contains_box(child.box, tolerance):
                    hierarchy_ok = False
            for axis in range(3):
                total_faces += 2
                lo = node.own_box.minimum[axis]
                hi = node.own_box.maximum[axis]
                if any(abs(p[axis] - lo) <= tolerance for p in own_points):
                    supported_faces += 1
                if any(abs(p[axis] - hi) <= tolerance for p in own_points):
                    supported_faces += 1
            if node.own_box.volume > 0.0:
                fill_ratios.append(node.capsule_volume / node.own_box.volume)

        count = sum(1 for _ in nodes)
        return {
            "vertices": total_points,
            "contained_vertices": contained,
            "containment_ratio": contained / total_points,
            "max_outside_distance": max_outside,
            "subtree_contained_ratio": subtree_contained / subtree_total,
            "hierarchy_contains_children": hierarchy_ok,
            "supported_box_faces_ratio": supported_faces / total_faces,
            "mean_capsule_fill_ratio": sum(fill_ratios) / len(fill_ratios),
            "root_volume": self.root.box.volume if self.root.box else 0.0,
            "node_count": count,
        }

    def layer_metrics(self, timing: dict[str, int] | None = None) -> list[dict[str, float | int]]:
        timing = timing or {}
        rows: list[dict[str, float | int]] = []
        for depth, nodes in self.layer_nodes().items():
            volumes = [node.box.volume for node in nodes if node.box is not None]
            rows.append(
                {
                    "depth": depth,
                    "nodes": len(nodes),
                    "total_volume_m3": sum(volumes),
                    "mean_volume_m3": sum(volumes) / len(volumes),
                    "max_volume_m3": max(volumes),
                    "min_volume_m3": min(volumes),
                    "update_ms_per_frame": sum(
                        timing.get(node.name, node.update_ns) for node in nodes
                    )
                    / 1_000_000.0,
                }
            )
        return rows

    def node_rows(self) -> list[dict[str, float | str | int]]:
        rows: list[dict[str, float | str | int]] = []
        for node in self.iter_nodes():
            assert node.box is not None and node.own_box is not None
            rows.append(
                {
                    "bone": node.name,
                    "depth": node.depth,
                    "subtree_primitives": node.primitive_count,
                    "own_volume_m3": node.own_box.volume,
                    "hierarchy_volume_m3": node.box.volume,
                    "capsule_fill_ratio": node.capsule_volume / node.own_box.volume,
                    "update_ms": node.update_ns / 1_000_000.0,
                }
            )
        return rows
