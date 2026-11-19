"""走道连通性检查：膨胀障碍物后的栅格 BFS。"""

from __future__ import annotations

from collections import deque

from .geometry import Rect
from .room import Room


def build_free_grid(
    room: Room,
    obstacles: list[Rect],
    cell: float,
    walkway_width: float,
) -> list[list[bool]]:
    """生成自由栅格。

    障碍物按 walkway_width/2 膨胀，等价于把行人半径取为 walkway_width/2，
    因而 BFS 得到的可通行路径天然满足最小走道宽度。
    返回 blocked[row][col]，True 表示占用/不可通行。
    """
    cols = max(1, round(room.w / cell))
    rows = max(1, round(room.h / cell))
    margin = walkway_width / 2.0
    inflated = [r.inflated(margin) for r in obstacles]
    blocked = [[False] * cols for _ in range(rows)]
    for row in range(rows):
        cy = (row + 0.5) * cell
        for col in range(cols):
            cx = (col + 0.5) * cell
            if cx >= room.w or cy >= room.h:
                blocked[row][col] = True
                continue
            for rect in inflated:
                if rect.x <= cx <= rect.x1 and rect.y <= cy <= rect.y1:
                    blocked[row][col] = True
                    break
    return blocked


def bfs_reach(
    blocked: list[list[bool]], start: tuple[int, int]
) -> set[tuple[int, int]]:
    rows, cols = len(blocked), len(blocked[0])
    seen: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()
    if not blocked[start[1]][start[0]]:
        seen.add(start)
        queue.append(start)
    while queue:
        col, row = queue.popleft()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = col + dc, row + dr
            if 0 <= nc < cols and 0 <= nr < rows and not blocked[nr][nc]:
                neighbor = (nc, nr)
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return seen


def check_room_connectivity(
    room: Room,
    placed_rects: list[Rect],
    cell: float = 0.1,
    walkway_width: float = 0.6,
) -> dict:
    """检查房间内所有门的门槛点是否互相连通。

    单门房间检查门到房间内部是否存在可达区域。
    """
    blocked = build_free_grid(room, placed_rects, cell, walkway_width)
    cols = len(blocked[0])
    rows = len(blocked)
    thresholds = room.door_thresholds()
    if not thresholds:
        center = (cols // 2, rows // 2)
        reach = bfs_reach(blocked, center)
        free_cells = sum(1 for r in blocked for v in r if not v)
        return {
            "connected": len(reach) > 0,
            "reachable_cells": len(reach),
            "free_cells": free_cells,
            "blocked_grid": blocked,
        }

    def to_cell(point: tuple[float, float]) -> tuple[int, int]:
        px, py = point
        return min(cols - 1, max(0, int(px / cell))), min(
            rows - 1, max(0, int(py / cell))
        )

    start = to_cell(thresholds[0])
    if blocked[start[1]][start[0]]:
        free_cells = sum(1 for r in blocked for v in r if not v)
        return {
            "connected": False,
            "reachable_cells": 0,
            "free_cells": free_cells,
            "blocked_grid": blocked,
        }
    reach = bfs_reach(blocked, start)
    targets = [to_cell(p) for p in thresholds[1:]]
    connected = all(t in reach for t in targets)
    free_cells = sum(1 for r in blocked for v in r if not v)
    return {
        "connected": connected,
        "reachable_cells": len(reach),
        "free_cells": free_cells,
        "blocked_grid": blocked,
    }
