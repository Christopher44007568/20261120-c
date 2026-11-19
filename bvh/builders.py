from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterator

from .geometry import AABB, EPSILON, union_bounds
from .mesh import Triangle


STRATEGIES = ("sah", "median", "lbvh")


@dataclass(slots=True)
class Node:
    bounds: AABB
    left: int = -1
    right: int = -1
    start: int = 0
    count: int = 0
    parent: int = -1

    @property
    def is_leaf(self) -> bool:
        return self.left < 0 and self.right < 0

    @property
    def volume(self) -> float:
        return self.bounds.volume


@dataclass(slots=True)
class BVH:
    nodes: list[Node]
    order: list[int]
    primitive_to_leaf: list[int]
    triangle_bounds: list[AABB]
    root_index: int
    strategy: str
    max_leaf_size: int
    build_time_ms: float
    sah_bins: int

    @property
    def root(self) -> int:
        return self.root_index

    @property
    def primitive_count(self) -> int:
        return len(self.primitive_to_leaf)

    def leaves(self) -> Iterator[int]:
        stack = [self.root]
        while stack:
            node_index = stack.pop()
            node = self.nodes[node_index]
            if node.is_leaf:
                yield node_index
            else:
                stack.append(node.left)
                stack.append(node.right)

    def reachable_nodes(self) -> list[int]:
        result: list[int] = []
        stack = [self.root]
        while stack:
            node_index = stack.pop()
            node = self.nodes[node_index]
            result.append(node_index)
            if not node.is_leaf:
                stack.append(node.left)
                stack.append(node.right)
        return result

    def subtree_primitives(self, node_index: int) -> list[int]:
        node = self.nodes[node_index]
        return self.order[node.start : node.start + node.count]

    def level_stats(self) -> list[dict[str, int | float]]:
        levels: list[dict[str, int | float]] = []
        current = [self.root]
        level = 0
        while current:
            next_level: list[int] = []
            leaf_count = 0
            leaf_triangles = 0
            for node_index in current:
                node = self.nodes[node_index]
                if node.is_leaf:
                    leaf_count += 1
                    leaf_triangles += node.count
                else:
                    next_level.append(node.left)
                    next_level.append(node.right)
            average = leaf_triangles / leaf_count if leaf_count else 0.0
            levels.append(
                {
                    "level": level,
                    "node_count": len(current),
                    "leaf_count": leaf_count,
                    "internal_count": len(current) - leaf_count,
                    "leaf_triangle_count": leaf_triangles,
                    "average_leaf_triangles": average,
                }
            )
            current = next_level
            level += 1
        return levels

    def total_leaf_triangles(self) -> int:
        return sum(self.nodes[index].count for index in self.leaves())

    def average_leaf_triangles(self) -> float:
        leaves = list(self.leaves())
        return self.total_leaf_triangles() / len(leaves) if leaves else 0.0

    def validate(self) -> None:
        if not self.nodes:
            raise AssertionError("BVH has no nodes")
        seen_primitives: set[int] = set()
        reachable: set[int] = set()
        stack = [self.root]
        if self.nodes[self.root].parent != -1:
            raise AssertionError("root node has a parent")
        while stack:
            node_index = stack.pop()
            if node_index in reachable:
                raise AssertionError(f"node {node_index} is reachable twice")
            reachable.add(node_index)
            node = self.nodes[node_index]
            if node.is_leaf:
                if node.count <= 0 or node.count > self.max_leaf_size:
                    raise AssertionError(f"leaf {node_index} has an invalid count")
                primitives = self.order[node.start : node.start + node.count]
                if len(primitives) != node.count:
                    raise AssertionError(f"leaf {node_index} order range is invalid")
                for primitive in primitives:
                    if primitive in seen_primitives:
                        raise AssertionError(f"primitive {primitive} appears twice")
                    seen_primitives.add(primitive)
                    if not node.bounds.contains_aabb(
                        self._triangle_bounds(primitive)
                    ):
                        raise AssertionError("leaf bounds do not contain its triangle")
            else:
                if node.left < 0 or node.right < 0:
                    raise AssertionError(f"internal node {node_index} has no children")
                left = self.nodes[node.left]
                right = self.nodes[node.right]
                if left.parent != node_index or right.parent != node_index:
                    raise AssertionError("child parent links are inconsistent")
                expected = left.bounds.merged(right.bounds)
                if expected != node.bounds:
                    raise AssertionError(f"node {node_index} bounds are stale")
                stack.append(node.left)
                stack.append(node.right)
        if seen_primitives != set(range(self.primitive_count)):
            raise AssertionError("BVH does not reference every primitive exactly once")
        if self.root not in reachable:
            raise AssertionError("BVH root is not reachable")

    def _triangle_bounds(self, primitive: int) -> AABB:
        return self.triangle_bounds[primitive]

    def summary(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "max_leaf_size": self.max_leaf_size,
            "sah_bins": self.sah_bins,
            "build_time_ms": self.build_time_ms,
            "node_count": len(self.nodes),
            "leaf_count": sum(1 for _ in self.leaves()),
            "max_depth": len(self.level_stats()) - 1,
            "average_leaf_triangles": self.average_leaf_triangles(),
            "levels": self.level_stats(),
        }


class BVHBuilder:
    def __init__(
        self,
        triangles: list[Triangle],
        strategy: str,
        max_leaf_size: int = 8,
        sah_bins: int = 16,
    ) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        if max_leaf_size < 1:
            raise ValueError("max_leaf_size must be at least one")
        if sah_bins < 2:
            raise ValueError("sah_bins must be at least two")
        self.triangles = triangles
        self.strategy = strategy
        self.max_leaf_size = max_leaf_size
        self.sah_bins = sah_bins
        self.nodes: list[Node] = []
        self.order: list[int] = []
        self.primitive_to_leaf = [-1] * len(triangles)
        self.triangle_bounds = [triangle.bounds for triangle in triangles]
        self.morton_codes: list[int] = []

    def build(self) -> BVH:
        if not self.triangles:
            raise ValueError("cannot build a BVH without triangles")
        start_time = time.perf_counter()
        ids = list(range(len(self.triangles)))
        if self.strategy == "lbvh":
            self._prepare_morton_codes()
            ids.sort(key=lambda primitive: (self.morton_codes[primitive], primitive))
            root = self._build_lbvh(ids, -1)
        elif self.strategy == "sah":
            root = self._build_sah(ids, -1)
        else:
            root = self._build_median(ids, -1)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return BVH(
            nodes=self.nodes,
            order=self.order,
            primitive_to_leaf=self.primitive_to_leaf,
            triangle_bounds=self.triangle_bounds,
            root_index=root,
            strategy=self.strategy,
            max_leaf_size=self.max_leaf_size,
            build_time_ms=elapsed_ms,
            sah_bins=self.sah_bins,
        )

    def _new_node(self, bounds: AABB, parent: int) -> int:
        node_index = len(self.nodes)
        self.nodes.append(Node(bounds=bounds, parent=parent))
        return node_index

    def _make_leaf(self, ids: list[int], parent: int) -> int:
        bounds = union_bounds([self.triangle_bounds[primitive] for primitive in ids])
        node_index = self._new_node(bounds, parent)
        node = self.nodes[node_index]
        node.start = len(self.order)
        node.count = len(ids)
        self.order.extend(ids)
        for primitive in ids:
            self.primitive_to_leaf[primitive] = node_index
        return node_index

    def _finish_internal(
        self, node_index: int, left: int, right: int
    ) -> int:
        node = self.nodes[node_index]
        node.left = left
        node.right = right
        node.start = self.nodes[left].start
        node.count = self.nodes[left].count + self.nodes[right].count
        node.bounds = self.nodes[left].bounds.merged(self.nodes[right].bounds)
        return node_index

    def _group_bounds(self, ids: list[int]) -> AABB:
        return union_bounds([self.triangle_bounds[primitive] for primitive in ids])

    def _longest_centroid_axis(self, ids: list[int]) -> int:
        points = tuple(self.triangles[primitive].centroid for primitive in ids)
        bounds = AABB.from_points(points)
        extents = (bounds.extent(0), bounds.extent(1), bounds.extent(2))
        return max(range(3), key=lambda axis: extents[axis])

    def _median_partition(self, ids: list[int]) -> tuple[list[int], list[int]]:
        axis = self._longest_centroid_axis(ids)
        ordered = sorted(
            ids, key=lambda primitive: (self.triangles[primitive].centroid[axis], primitive)
        )
        middle = len(ordered) // 2
        return ordered[:middle], ordered[middle:]

    def _build_median(self, ids: list[int], parent: int) -> int:
        if len(ids) <= self.max_leaf_size:
            return self._make_leaf(ids, parent)
        node_index = self._new_node(self._group_bounds(ids), parent)
        left_ids, right_ids = self._median_partition(ids)
        left = self._build_median(left_ids, node_index)
        right = self._build_median(right_ids, node_index)
        return self._finish_internal(node_index, left, right)

    def _prepare_morton_codes(self) -> None:
        centroids = [triangle.centroid for triangle in self.triangles]
        bounds = AABB.from_points(tuple(centroids))
        extents = [max(bounds.extent(axis), EPSILON) for axis in range(3)]
        self.morton_codes = []
        for centroid in centroids:
            code = 0
            for axis in range(3):
                coordinate = int(
                    (centroid[axis] - bounds.min[axis]) / extents[axis] * 1023.0
                )
                coordinate = min(1023, max(0, coordinate))
                code |= coordinate << (axis * 10)
            self.morton_codes.append(code)

    def _build_lbvh(self, ids: list[int], parent: int) -> int:
        if len(ids) <= self.max_leaf_size:
            return self._make_leaf(ids, parent)
        first_code = self.morton_codes[ids[0]]
        last_code = self.morton_codes[ids[-1]]
        different = first_code ^ last_code
        if different == 0:
            node_index = self._new_node(self._group_bounds(ids), parent)
            left_ids, right_ids = self._median_partition(ids)
            left = self._build_lbvh(left_ids, node_index)
            right = self._build_lbvh(right_ids, node_index)
            return self._finish_internal(node_index, left, right)
        bit = different.bit_length() - 1
        low = 0
        high = len(ids)
        while low < high:
            middle = (low + high) // 2
            if (self.morton_codes[ids[middle]] >> bit) & 1:
                high = middle
            else:
                low = middle + 1
        split = low
        if split == 0 or split == len(ids):
            split = len(ids) // 2
        node_index = self._new_node(self._group_bounds(ids), parent)
        left = self._build_lbvh(ids[:split], node_index)
        right = self._build_lbvh(ids[split:], node_index)
        return self._finish_internal(node_index, left, right)

    def _bin_index(
        self, centroid_value: float, minimum: float, extent: float
    ) -> int:
        raw = int((centroid_value - minimum) / extent * self.sah_bins)
        return min(self.sah_bins - 1, max(0, raw))

    def _best_sah_split(
        self, ids: list[int], node_bounds: AABB
    ) -> tuple[int, int] | None:
        total_area = node_bounds.surface_area
        if total_area <= EPSILON:
            return None
        best_cost = float("inf")
        best: tuple[int, int] | None = None
        for axis in range(3):
            centroid_bounds = AABB.from_points(
                tuple(self.triangles[primitive].centroid for primitive in ids)
            )
            extent = centroid_bounds.extent(axis)
            if extent <= EPSILON:
                continue
            counts = [0] * self.sah_bins
            bounds: list[AABB | None] = [None] * self.sah_bins
            minimum = centroid_bounds.min[axis]
            for primitive in ids:
                triangle = self.triangles[primitive]
                bin_index = self._bin_index(
                    triangle.centroid[axis], minimum, extent
                )
                counts[bin_index] += 1
                triangle_bound = self.triangle_bounds[primitive]
                if bounds[bin_index] is None:
                    bounds[bin_index] = triangle_bound
                else:
                    bounds[bin_index] = bounds[bin_index].merged(triangle_bound)

            left_counts = [0] * self.sah_bins
            left_bounds: list[AABB | None] = [None] * self.sah_bins
            running_count = 0
            running_bound: AABB | None = None
            for bin_index in range(self.sah_bins):
                running_count += counts[bin_index]
                if bounds[bin_index] is not None:
                    if running_bound is None:
                        running_bound = bounds[bin_index]
                    else:
                        running_bound = running_bound.merged(bounds[bin_index])
                left_counts[bin_index] = running_count
                left_bounds[bin_index] = running_bound

            right_counts = [0] * self.sah_bins
            right_bounds: list[AABB | None] = [None] * self.sah_bins
            running_count = 0
            running_bound = None
            for bin_index in range(self.sah_bins - 1, -1, -1):
                running_count += counts[bin_index]
                if bounds[bin_index] is not None:
                    if running_bound is None:
                        running_bound = bounds[bin_index]
                    else:
                        running_bound = running_bound.merged(bounds[bin_index])
                right_counts[bin_index] = running_count
                right_bounds[bin_index] = running_bound

            for split_bin in range(self.sah_bins - 1):
                left_count = left_counts[split_bin]
                right_count = right_counts[split_bin + 1]
                left_bound = left_bounds[split_bin]
                right_bound = right_bounds[split_bin + 1]
                if left_count == 0 or right_count == 0:
                    continue
                if left_bound is None or right_bound is None:
                    continue
                cost = 1.0 + (
                    left_bound.surface_area * left_count
                    + right_bound.surface_area * right_count
                ) / total_area
                if cost < best_cost:
                    best_cost = cost
                    best = (axis, split_bin)
        return best

    def _sah_partition(
        self, ids: list[int], axis: int, split_bin: int
    ) -> tuple[list[int], list[int]]:
        centroid_bounds = AABB.from_points(
            tuple(self.triangles[primitive].centroid for primitive in ids)
        )
        extent = centroid_bounds.extent(axis)
        minimum = centroid_bounds.min[axis]
        left_ids: list[int] = []
        right_ids: list[int] = []
        for primitive in ids:
            bin_index = self._bin_index(
                self.triangles[primitive].centroid[axis], minimum, extent
            )
            if bin_index <= split_bin:
                left_ids.append(primitive)
            else:
                right_ids.append(primitive)
        if not left_ids or not right_ids:
            return self._median_partition(ids)
        return left_ids, right_ids

    def _build_sah(self, ids: list[int], parent: int) -> int:
        if len(ids) <= self.max_leaf_size:
            return self._make_leaf(ids, parent)
        node_bounds = self._group_bounds(ids)
        best = self._best_sah_split(ids, node_bounds)
        if best is None:
            left_ids, right_ids = self._median_partition(ids)
        else:
            left_ids, right_ids = self._sah_partition(ids, best[0], best[1])
        node_index = self._new_node(node_bounds, parent)
        left = self._build_sah(left_ids, node_index)
        right = self._build_sah(right_ids, node_index)
        return self._finish_internal(node_index, left, right)


def build_bvh(
    triangles: list[Triangle],
    strategy: str = "sah",
    max_leaf_size: int = 8,
    sah_bins: int = 16,
) -> BVH:
    return BVHBuilder(
        triangles=triangles,
        strategy=strategy,
        max_leaf_size=max_leaf_size,
        sah_bins=sah_bins,
    ).build()
