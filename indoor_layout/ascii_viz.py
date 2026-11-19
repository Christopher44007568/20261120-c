"""终端 ASCII 平面图，用于无图形环境下的人工核查。"""

from __future__ import annotations

from .room import OpeningKind, Room
from .solver import RoomSolution


def render_room(room: Room, solution: RoomSolution, cell: float = 0.25) -> str:
    cols = int(round(room.w / cell))
    rows = int(round(room.h / cell))
    grid = [["·"] * cols for _ in range(rows)]

    for opening in room.openings:
        start = int(opening.offset / cell)
        length = max(1, int(round(opening.width / cell)))
        mark = "D" if opening.kind is OpeningKind.DOOR else "W"
        for k in range(start, min(cols, start + length)):
            if opening.wall == "S":
                grid[rows - 1][k] = mark
            elif opening.wall == "N":
                grid[0][k] = mark
            elif opening.wall == "W":
                grid[rows - 1 - k][0] = mark
            else:
                grid[rows - 1 - k][cols - 1] = mark

    labels = {}
    for index, furniture in enumerate(room.furniture, start=1):
        rect = solution.placed.get(furniture.name)
        if rect is None:
            continue
        c0 = int(rect.x / cell)
        c1 = min(cols, int(round(rect.x1 / cell)))
        r0 = rows - int(round(rect.y1 / cell))
        r1 = rows - int(rect.y / cell)
        for r in range(max(0, r0), min(rows, r1)):
            for c in range(max(0, c0), c1):
                grid[r][c] = str(index)
        labels[str(index)] = furniture.name

    lines = [f"{room.name} {room.w}x{room.h}m {room.area:.2f}m2"]
    lines.extend("".join(row) for row in grid)
    legend = ", ".join(f"{idx}={name}" for idx, name in labels.items())
    lines.append(f"图例 D=门 W=窗: {legend}")
    return "\n".join(lines)
