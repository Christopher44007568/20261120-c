"""候选位置裁剪（约束传播剪枝）前后的排列搜索对比。

问题：为 N 件家具各选一个候选位置，要求全部互不碰撞且门间走道连通。
- 朴素枚举：不做任何剪枝，完整展开排列空间；
- 裁剪搜索：前向检查（当前位置与已放置家具碰撞即剪枝），
  可选的提前连通性检查，以及首个可行解即停止。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from .connectivity import check_room_connectivity
from .geometry import Rect, count_pairwise_collisions
from .room import Room
from .solver import SolverParams, _greedy_place, generate_candidates


@dataclass
class SearchStats:
    mode: str
    candidate_space: int
    nodes_visited: int
    leaves_evaluated: int
    valid_arrangements: int
    compile_ms: float
    first_frame_ms: float
    pruned_branches: int
    found_first: bool
    capped: bool = False


def _candidate_table(room: Room, params: SolverParams) -> dict[str, list[Rect]]:
    return {
        furniture.name: generate_candidates(room, furniture, params)
        for furniture in room.furniture
    }


def _legal_partial(names: list[str], layout: dict[str, Rect]) -> bool:
    rects = [layout[name] for name in names if name in layout]
    return count_pairwise_collisions(rects) == 0


def pruned_search(
    room: Room,
    params: SolverParams,
    stop_at_first: bool = True,
    early_connectivity: bool = False,
) -> SearchStats:
    """约束传播裁剪搜索：碰撞前向检查 + 可选提前连通性剪枝。"""
    started = time.perf_counter()
    table = _candidate_table(room, params)
    names = [f.name for f in room.furniture]
    names.sort(key=lambda n: len(table[n]))
    candidate_space = 1
    for options in table.values():
        candidate_space *= max(1, len(options))

    nodes = 0
    leaves = 0
    valid = 0
    pruned = 0
    first_frame = None
    layout: dict[str, Rect] = {}

    def backtrack(index: int) -> bool:
        nonlocal nodes, leaves, valid, pruned, first_frame
        if index == len(names):
            leaves += 1
            connected = check_room_connectivity(
                room, list(layout.values()), params.cell, params.walkway_width
            )["connected"]
            if connected:
                valid += 1
                if first_frame is None:
                    first_frame = (time.perf_counter() - started) * 1000.0
                return stop_at_first
            pruned += 1
            return False
        name = names[index]
        for rect in table[name]:
            nodes += 1
            layout[name] = rect
            placed_names = names[: index + 1]
            if not _legal_partial(placed_names, layout):
                pruned += 1
                continue
            if early_connectivity and index < len(names) - 1:
                partial_rects = [layout[n] for n in placed_names]
                if not check_room_connectivity(
                    room, partial_rects, params.cell, params.walkway_width
                )["connected"]:
                    pruned += 1
                    continue
            if backtrack(index + 1):
                return True
        layout.pop(name, None)
        return False

    found = backtrack(0)
    compile_ms = (time.perf_counter() - started) * 1000.0
    return SearchStats(
        mode="裁剪搜索",
        candidate_space=candidate_space,
        nodes_visited=nodes,
        leaves_evaluated=leaves,
        valid_arrangements=valid,
        compile_ms=compile_ms,
        first_frame_ms=first_frame if first_frame is not None else compile_ms,
        pruned_branches=pruned,
        found_first=found,
    )


def naive_search(
    room: Room,
    params: SolverParams,
    node_cap: int = 200_000,
) -> SearchStats:
    """朴素枚举：无碰撞剪枝，全排列展开（受 node_cap 保护）。

    连通性只在完整排列（叶子）上评估；节点数在每次取值时累加。
    """
    started = time.perf_counter()
    table = _candidate_table(room, params)
    names = list(table.keys())
    candidate_space = 1
    for options in table.values():
        candidate_space *= max(1, len(options))

    nodes = 0
    leaves = 0
    valid = 0
    first_frame = None
    layout: dict[str, Rect] = {}
    capped = False

    def backtrack(index: int) -> bool:
        nonlocal nodes, leaves, valid, first_frame, capped
        if index == len(names):
            leaves += 1
            rects = list(layout.values())
            if count_pairwise_collisions(rects) == 0 and check_room_connectivity(
                room, rects, params.cell, params.walkway_width
            )["connected"]:
                valid += 1
                if first_frame is None:
                    first_frame = (time.perf_counter() - started) * 1000.0
            return False
        name = names[index]
        for rect in table[name]:
            nodes += 1
            layout[name] = rect
            if nodes > node_cap:
                capped = True
                return True
            if backtrack(index + 1):
                return True
        layout.pop(name, None)
        return False

    backtrack(0)
    compile_ms = (time.perf_counter() - started) * 1000.0
    return SearchStats(
        mode="朴素枚举",
        candidate_space=candidate_space,
        nodes_visited=nodes,
        leaves_evaluated=leaves,
        valid_arrangements=valid,
        compile_ms=compile_ms,
        first_frame_ms=first_frame if first_frame is not None else compile_ms,
        pruned_branches=0,
        found_first=valid > 0,
        capped=capped,
    )


def warm_greedy_first_frame(room: Room, params: SolverParams) -> float:
    """启发式贪心的首帧延迟作为参照基线。"""
    started = time.perf_counter()
    rng = random.Random(params.rng_seed)
    for _ in range(params.restarts):
        layout, collisions, _ = _greedy_place(room, params, rng, relax=False)
        if collisions == 0 and len(layout) == len(room.furniture):
            if check_room_connectivity(
                room, list(layout.values()), params.cell, params.walkway_width
            )["connected"]:
                return (time.perf_counter() - started) * 1000.0
    return (time.perf_counter() - started) * 1000.0
