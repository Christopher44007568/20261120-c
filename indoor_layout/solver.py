"""约束驱动的家具布局求解器。

硬约束：
1. 家具完整落在房间内；
2. 不与门/窗禁放区相交（门开启净空、窗台净空）；
3. 家具之间不重叠（不可行户型退化为最小重叠的松弛布局）；
4. 靠墙家具必须贴墙；
5. 布置完成后门与门之间保持走道连通（满足最小走道宽度）。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .connectivity import check_room_connectivity
from .geometry import Rect, count_pairwise_collisions, total_overlap_area
from .room import Furniture, OpeningKind, Room


@dataclass
class SolverParams:
    restarts: int = 12
    grid_step: float = 0.25
    wall_gap: float = 0.02
    door_clearance: float = 0.8
    window_clearance: float = 0.6
    walkway_width: float = 0.6
    cell: float = 0.1
    max_candidates: int = 600
    rng_seed: int = 20261120


@dataclass
class RoomSolution:
    room_name: str
    placed: dict[str, Rect] = field(default_factory=dict)
    feasible: bool = False
    collisions: int = 0
    overlap_area: float = 0.0
    connected: bool = False
    reachable_cells: int = 0
    free_cells: int = 0
    attempts: int = 0
    elapsed_ms: float = 0.0
    relaxations: int = 0
    note: str = ""


def _orientations(furniture: Furniture) -> list[tuple[float, float]]:
    ftype = furniture.ftype
    base = [(ftype.w, ftype.h)]
    if furniture.allow_rotation and abs(ftype.w - ftype.h) > 1e-9:
        base.append((ftype.h, ftype.w))
    return base


def _wall_slots(room: Room, w: float, h: float, step: float, gap: float) -> list[Rect]:
    rects: list[Rect] = []
    for col in range(int((room.w - w) / step) + 1):
        x = col * step
        rects.append(Rect(x, gap, w, h))
        rects.append(Rect(x, room.h - h - gap, w, h))
    for row in range(int((room.h - h) / step) + 1):
        y = row * step
        rects.append(Rect(gap, y, w, h))
        rects.append(Rect(room.w - w - gap, y, w, h))
    return rects


def _interior_slots(room: Room, w: float, h: float, step: float) -> list[Rect]:
    rects: list[Rect] = []
    for col in range(int((room.w - w) / step) + 1):
        for row in range(int((room.h - h) / step) + 1):
            rects.append(Rect(col * step, row * step, w, h))
    return rects


def generate_candidates(room: Room, furniture: Furniture, params: SolverParams) -> list[Rect]:
    """生成满足边界约束的候选矩形（尚未做碰撞过滤）。"""
    keepouts = room.keepout_rects(params.door_clearance, params.window_clearance)
    bounds = room.local_bounds()
    candidates: list[Rect] = []
    for w, h in _orientations(furniture):
        if w > room.w + 1e-9 or h > room.h + 1e-9:
            continue
        slots = _wall_slots(room, w, h, params.grid_step, params.wall_gap)
        if not furniture.ftype.must_touch_wall:
            slots += _interior_slots(room, w, h, params.grid_step * 2)
        for rect in slots:
            if not bounds.contains(rect):
                continue
            if any(rect.intersects(k) for k in keepouts):
                continue
            candidates.append(rect)
    unique = list({(r.x, r.y, r.w, r.h): r for r in candidates}.values())
    if len(unique) > params.max_candidates:
        stride = len(unique) / params.max_candidates
        unique = [unique[int(i * stride)] for i in range(params.max_candidates)]
    return unique


def _candidate_cost(
    rect: Rect,
    room: Room,
    furniture: Furniture,
    placed: list[Rect],
    relax: bool,
) -> tuple[float, int, float]:
    """返回 (偏好代价, 碰撞数, 重叠面积)。碰撞数为硬约束过滤依据。"""
    collisions = 0
    overlap = 0.0
    for other in placed:
        if rect.intersects(other):
            collisions += 1
            overlap += rect.intersection_area(other)
    if collisions and not relax:
        return (0.0, collisions, overlap)
    preference = 0.0
    gap = 0.05
    touch = (
        rect.y <= gap
        or rect.y1 >= room.h - gap
        or rect.x <= gap
        or rect.x1 >= room.w - gap
    )
    if furniture.ftype.must_touch_wall:
        preference += 0.0 if touch else 100.0
    else:
        preference += 0.0 if touch else 0.5
    cx, cy = rect.cx, rect.cy
    preference += 0.02 * abs(cx - room.w / 2.0)
    preference += 0.02 * abs(cy - room.h / 2.0)
    return (preference + 10.0 * overlap, collisions, overlap)


def _order_furniture(room: Room, rng: random.Random) -> list[Furniture]:
    """大件、靠墙件优先放置，降低后期冲突；同优先级随机打破平局。"""
    return sorted(
        room.furniture,
        key=lambda f: (
            not f.ftype.must_touch_wall,
            -(f.ftype.w * f.ftype.h),
            rng.random(),
        ),
    )


def _greedy_place(
    room: Room, params: SolverParams, rng: random.Random, relax: bool
) -> tuple[dict[str, Rect], int, float]:
    layout: dict[str, Rect] = {}
    placed: list[Rect] = []
    total_collisions = 0
    total_overlap = 0.0
    for furniture in _order_furniture(room, rng):
        candidates = generate_candidates(room, furniture, params)
        if not candidates:
            continue
        scored: list[tuple[tuple[float, int, float], Rect]] = []
        for rect in candidates:
            cost, collisions, overlap = _candidate_cost(
                rect, room, furniture, placed, relax
            )
            if collisions and not relax:
                continue
            scored.append((cost, rect))
        if not scored:
            if relax:
                scored = [
                    (_candidate_cost(rect, room, furniture, placed, True), rect)
                    for rect in candidates
                ]
            else:
                continue
        rng.shuffle(scored)
        scored.sort(key=lambda item: item[0])
        _, best = scored[0]
        layout[furniture.name] = best
        placed.append(best)
        total_collisions += sum(1 for other in placed[:-1] if best.intersects(other))
        total_overlap += sum(
            best.intersection_area(other) for other in placed[:-1]
        )
    return layout, total_collisions, total_overlap


def _repair_connectivity(
    room: Room,
    layout: dict[str, Rect],
    params: SolverParams,
    rng: random.Random,
) -> dict[str, Rect]:
    """连通性修复：逐个家具尝试备选位置，直到门间走道恢复连通。"""
    current = dict(layout)
    if _is_connected(room, current, params):
        return current
    names = list(current.keys())
    rng.shuffle(names)
    for name in names:
        furniture = next(f for f in room.furniture if f.name == name)
        candidates = generate_candidates(room, furniture, params)
        rng.shuffle(candidates)
        others = [r for n, r in current.items() if n != name]
        legal = [r for r in candidates if not any(r.intersects(o) for o in others)]
        for rect in legal:
            trial = dict(current)
            trial[name] = rect
            if _is_connected(room, trial, params):
                return trial
    return current


def _is_connected(
    room: Room, layout: dict[str, Rect], params: SolverParams
) -> bool:
    return check_room_connectivity(
        room,
        list(layout.values()),
        cell=params.cell,
        walkway_width=params.walkway_width,
    )["connected"]


def solve_room(room: Room, params: SolverParams | None = None) -> RoomSolution:
    params = params or SolverParams()
    started = time.perf_counter()
    rng = random.Random(params.rng_seed)
    best: RoomSolution | None = None
    relaxations = 0
    attempts = 0

    for relax in (False, True):
        if relax:
            relaxations = 1
        for _ in range(params.restarts):
            attempts += 1
            seed = rng.randrange(1 << 30)
            local_rng = random.Random(seed)
            layout, collisions, overlap = _greedy_place(room, params, local_rng, relax)
            if len(layout) < len(room.furniture):
                continue
            layout = _repair_connectivity(room, layout, params, local_rng)
            conn = check_room_connectivity(
                room,
                list(layout.values()),
                cell=params.cell,
                walkway_width=params.walkway_width,
            )
            rects = list(layout.values())
            collisions = count_pairwise_collisions(rects)
            overlap = total_overlap_area(rects)
            solution = RoomSolution(
                room_name=room.name,
                placed=layout,
                feasible=(collisions == 0 and conn["connected"] and not relax),
                collisions=collisions,
                overlap_area=overlap,
                connected=conn["connected"],
                reachable_cells=conn["reachable_cells"],
                free_cells=conn["free_cells"],
                attempts=attempts,
                relaxations=relaxations,
            )
            if best is None or (
                solution.collisions,
                not solution.connected,
                solution.overlap_area,
            ) < (
                best.collisions,
                not best.connected,
                best.overlap_area,
            ):
                best = solution
            if solution.feasible:
                solution.elapsed_ms = (time.perf_counter() - started) * 1000.0
                return solution
        if best is not None and best.collisions == 0 and best.connected:
            break

    assert best is not None
    best.elapsed_ms = (time.perf_counter() - started) * 1000.0
    if best.collisions > 0:
        best.note = "空间不足，返回最小碰撞的松弛布局"
    elif not best.connected:
        best.note = "走道无法保持连通"
    return best
