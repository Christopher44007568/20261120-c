"""网格楼层：WALL / ROOM / CORRIDOR 三类单元。

房间沿走廊两侧排布并逐一对走廊开门，
用 BFS 验证所有房间可互相到达，同时统计房间面积与重叠碰撞数。
"""

from collections import deque
from dataclasses import dataclass

WALL = 0
ROOM = 1
CORRIDOR = 2


@dataclass
class Room:
    room_id: str
    top: int
    left: int
    height: int
    width: int

    @property
    def area(self):
        return self.height * self.width

    def cells(self):
        for row in range(self.top, self.top + self.height):
            for col in range(self.left, self.left + self.width):
                yield row, col


class FloorPlan:
    def __init__(self, height, width):
        self.height = height
        self.width = width
        self.grid = [[WALL] * width for _ in range(height)]
        self.rooms = []

    def carve_room(self, room):
        for row, col in room.cells():
            if self.grid[row][col] != WALL:
                raise ValueError(f"房间 {room.room_id} 与既有单元重叠")
        for row, col in room.cells():
            self.grid[row][col] = ROOM
        self.rooms.append(room)

    def carve_corridor(self, row, col_start, col_end):
        for col in range(col_start, col_end + 1):
            if self.grid[row][col] == WALL:
                self.grid[row][col] = CORRIDOR

    def open_door(self, row, col):
        if self.grid[row][col] == ROOM:
            self.grid[row][col] = CORRIDOR

    def walkable_cells(self):
        for row in range(self.height):
            for col in range(self.width):
                if self.grid[row][col] != WALL:
                    yield row, col

    def room_collisions(self):
        """统计房间矩形两两重叠的单元对数（不相交则为 0）。"""
        collisions = 0
        for index, room_a in enumerate(self.rooms):
            for room_b in self.rooms[index + 1:]:
                overlap_h = max(0, min(room_a.top + room_a.height,
                                       room_b.top + room_b.height) -
                                max(room_a.top, room_b.top))
                overlap_w = max(0, min(room_a.left + room_a.width,
                                       room_b.left + room_b.width) -
                                max(room_a.left, room_b.left))
                collisions += overlap_h * overlap_w
        return collisions

    def connectivity(self):
        """BFS：返回 (是否全连通, 房间可达集合)。"""
        if not self.rooms:
            return False, set()
        start = next(iter(self.walkable_cells()))
        seen = {start}
        queue = deque([start])
        while queue:
            row, col = queue.popleft()
            for drow, dcol in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (row + drow, col + dcol)
                if 0 <= nxt[0] < self.height and 0 <= nxt[1] < self.width \
                        and nxt not in seen and self.grid[nxt[0]][nxt[1]] != WALL:
                    seen.add(nxt)
                    queue.append(nxt)
        reachable = {room.room_id for room in self.rooms
                     if any(cell in seen for cell in room.cells())}
        return len(reachable) == len(self.rooms), reachable


def generate_floor_plan(room_specs, grid_width=28):
    """room_specs: [(room_id, height, width), ...]，走廊固定在中间行。"""
    top_height = max(spec[1] for spec in room_specs)
    bottom_height = max((spec[1] for spec in room_specs[1::2]), default=4)
    corridor_row = top_height + 1
    height = corridor_row + 1 + bottom_height + 1
    plan = FloorPlan(height, grid_width)
    plan.carve_corridor(corridor_row, 1, grid_width - 2)
    col = 1
    for index, (room_id, room_h, room_w) in enumerate(room_specs):
        if col + room_w >= grid_width - 1:
            col = 1
        top = corridor_row - room_h if index % 2 == 0 \
            else corridor_row + 1
        room = Room(room_id, top, col, room_h, room_w)
        plan.carve_room(room)
        door_row = corridor_row - 1 if index % 2 == 0 else corridor_row + 1
        plan.open_door(door_row, col)
        col += room_w + 2
    return plan


def check_layout(plan):
    connected, reachable = plan.connectivity()
    return {
        "rooms": len(plan.rooms),
        "total_area": sum(room.area for room in plan.rooms),
        "room_areas": {room.room_id: room.area for room in plan.rooms},
        "collisions": plan.room_collisions(),
        "connected": connected,
        "reachable": sorted(reachable),
        "grid_size": (plan.height, plan.width),
    }
