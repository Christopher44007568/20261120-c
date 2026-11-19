from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Iterable

from .builders import BVH, Node, STRATEGIES, build_bvh
from .geometry import AABB, Vec3
from .mesh import Triangle


@dataclass(slots=True)
class LocalRebuildStats:
    frame: int
    updated_primitive_count: int
    rebuilt_primitive_count: int
    rebuilt_subtree_root: int
    rebuilt_node_count: int
    allocated_node_count: int
    reachable_node_count: int
    old_bounds_volume: float
    new_bounds_volume: float
    overlap_volume: float
    overlap_ratio_of_old: float
    local_rebuild: bool
    rebuild_ms: float

    def as_dict(self) -> dict[str, int | float | bool]:
        return {
            "frame": self.frame,
            "updated_primitive_count": self.updated_primitive_count,
            "rebuilt_primitive_count": self.rebuilt_primitive_count,
            "rebuilt_subtree_root": self.rebuilt_subtree_root,
            "rebuilt_node_count": self.rebuilt_node_count,
            "allocated_node_count": self.allocated_node_count,
            "reachable_node_count": self.reachable_node_count,
            "old_bounds_volume": self.old_bounds_volume,
            "new_bounds_volume": self.new_bounds_volume,
            "overlap_volume": self.overlap_volume,
            "overlap_ratio_of_old": self.overlap_ratio_of_old,
            "local_rebuild": self.local_rebuild,
            "rebuild_ms": self.rebuild_ms,
        }


class DynamicBVH:
    def __init__(
        self,
        triangles: list[Triangle],
        strategy: str = "sah",
        max_leaf_size: int = 8,
        sah_bins: int = 16,
    ) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        self.triangles = triangles
        self.strategy = strategy
        self.max_leaf_size = max_leaf_size
        self.sah_bins = sah_bins
        self.bvh = build_bvh(
            triangles,
            strategy=strategy,
            max_leaf_size=max_leaf_size,
            sah_bins=sah_bins,
        )
        self.root_index = self.bvh.root_index
        self.frame = 0

    def translate_primitives(
        self, primitive_indices: Iterable[int], delta: Vec3
    ) -> LocalRebuildStats:
        def transform(triangle: Triangle) -> Triangle:
            return triangle.translated(delta)

        return self.update_primitives(primitive_indices, transform)

    def update_primitives(
        self,
        primitive_indices: Iterable[int],
        transform: Callable[[Triangle], Triangle],
    ) -> LocalRebuildStats:
        start_time = time.perf_counter()
        updated = sorted(set(primitive_indices))
        if not updated:
            raise ValueError("at least one primitive must be updated")
        if updated[0] < 0 or updated[-1] >= len(self.triangles):
            raise IndexError("updated primitive index is out of range")
        leaves = {self.bvh.primitive_to_leaf[primitive] for primitive in updated}
        subtree_root = self._lowest_common_ancestor(leaves)
        subtree_node = self.bvh.nodes[subtree_root]
        rebuild_start = subtree_node.start
        rebuild_count = subtree_node.count
        primitive_ids = self.bvh.order[
            rebuild_start : rebuild_start + rebuild_count
        ]
        old_bounds = subtree_node.bounds

        for primitive in updated:
            replacement = transform(self.triangles[primitive])
            triangle = self.triangles[primitive]
            triangle.set_vertices(replacement.v0, replacement.v1, replacement.v2)

        local_triangles = [self.triangles[primitive] for primitive in primitive_ids]
        local_bvh = build_bvh(
            local_triangles,
            strategy=self.strategy,
            max_leaf_size=self.max_leaf_size,
            sah_bins=self.sah_bins,
        )
        self._splice_subtree(
            subtree_root,
            rebuild_start,
            primitive_ids,
            local_bvh,
        )
        new_bounds = self.bvh.nodes[subtree_root].bounds
        overlap = old_bounds.intersection(new_bounds)
        overlap_volume = overlap.volume if overlap is not None else 0.0
        old_volume = old_bounds.volume
        self.frame += 1
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return LocalRebuildStats(
            frame=self.frame,
            updated_primitive_count=len(updated),
            rebuilt_primitive_count=rebuild_count,
            rebuilt_subtree_root=subtree_root,
            rebuilt_node_count=len(local_bvh.nodes),
            allocated_node_count=len(self.bvh.nodes),
            reachable_node_count=len(self.bvh.reachable_nodes()),
            old_bounds_volume=old_volume,
            new_bounds_volume=new_bounds.volume,
            overlap_volume=overlap_volume,
            overlap_ratio_of_old=(
                overlap_volume / old_volume if old_volume > 0.0 else 0.0
            ),
            local_rebuild=subtree_root != self.root_index,
            rebuild_ms=elapsed_ms,
        )

    def _lowest_common_ancestor(self, node_indices: set[int]) -> int:
        if not node_indices:
            raise ValueError("node set must not be empty")
        first = next(iter(node_indices))
        path: list[int] = []
        current = first
        while current >= 0:
            path.append(current)
            current = self.bvh.nodes[current].parent
        for node_index in node_indices:
            ancestors: set[int] = set()
            current = node_index
            while current >= 0:
                ancestors.add(current)
                current = self.bvh.nodes[current].parent
            path = [candidate for candidate in path if candidate in ancestors]
        return path[0]

    def _splice_subtree(
        self,
        subtree_root: int,
        rebuild_start: int,
        primitive_ids: list[int],
        local_bvh: BVH,
    ) -> None:
        global_nodes = self.bvh.nodes
        old_parent = global_nodes[subtree_root].parent
        offset = len(global_nodes)

        def global_index(local_index: int) -> int:
            if local_index < 0:
                return -1
            if local_index == 0:
                return subtree_root
            return offset + local_index - 1

        for local_index in range(1, len(local_bvh.nodes)):
            local_node = local_bvh.nodes[local_index]
            global_nodes.append(
                Node(
                    bounds=local_node.bounds,
                    left=global_index(local_node.left),
                    right=global_index(local_node.right),
                    start=rebuild_start + local_node.start,
                    count=local_node.count,
                    parent=(
                        global_index(local_node.parent)
                        if local_node.parent >= 0
                        else -1
                    ),
                )
            )

        local_root = local_bvh.nodes[local_bvh.root]
        global_nodes[subtree_root] = Node(
            bounds=local_root.bounds,
            left=global_index(local_root.left),
            right=global_index(local_root.right),
            start=rebuild_start + local_root.start,
            count=local_root.count,
            parent=old_parent,
        )
        mapped_order = [primitive_ids[index] for index in local_bvh.order]
        self.bvh.order[
            rebuild_start : rebuild_start + len(mapped_order)
        ] = mapped_order

        for local_index, local_bound in enumerate(local_bvh.triangle_bounds):
            self.bvh.triangle_bounds[primitive_ids[local_index]] = local_bound

        for local_index, local_node in enumerate(local_bvh.nodes):
            if not local_node.is_leaf:
                continue
            global_leaf = global_index(local_index)
            for order_index in range(
                local_node.start, local_node.start + local_node.count
            ):
                primitive = primitive_ids[local_bvh.order[order_index]]
                self.bvh.primitive_to_leaf[primitive] = global_leaf

        parent_index = old_parent
        while parent_index >= 0:
            parent = global_nodes[parent_index]
            left = global_nodes[parent.left]
            right = global_nodes[parent.right]
            parent.bounds = left.bounds.merged(right.bounds)
            parent_index = parent.parent

    def full_rebuild(self) -> float:
        start_time = time.perf_counter()
        self.bvh = build_bvh(
            self.triangles,
            strategy=self.strategy,
            max_leaf_size=self.max_leaf_size,
            sah_bins=self.sah_bins,
        )
        self.root_index = self.bvh.root_index
        return (time.perf_counter() - start_time) * 1000.0
