"""户型库与家具目录（尺寸单位：米）。"""

from __future__ import annotations

from .room import Furniture, FurnitureType, Opening, OpeningKind, Room

DOOR = OpeningKind.DOOR
WINDOW = OpeningKind.WINDOW


def _f(name: str, w: float, h: float, wall: bool = False, blocks: bool = False,
       color: str = "#9bb8d3", rotate: bool = True) -> Furniture:
    return Furniture(
        FurnitureType(name, w, h, must_touch_wall=wall, blocks_window=blocks, color=color),
        allow_rotation=rotate,
    )


def bedroom_furniture() -> list[Furniture]:
    return [
        _f("双人床", 2.0, 1.5, wall=True, blocks=True, color="#c2a878"),
        _f("衣柜", 1.8, 0.6, wall=True, blocks=True, color="#8d6e63"),
        _f("书桌", 1.2, 0.6, wall=True, color="#a1887f"),
        _f("床头柜", 0.5, 0.4, wall=True, color="#bcaaa4"),
        _f("书椅", 0.5, 0.5, color="#7986cb"),
    ]


def living_furniture() -> list[Furniture]:
    return [
        _f("三人沙发", 2.2, 0.9, wall=True, blocks=True, color="#7e9ec4"),
        _f("茶几", 1.2, 0.6, color="#a3b8cc"),
        _f("电视柜", 1.8, 0.4, wall=True, blocks=True, color="#6d7b8d"),
        _f("书架", 1.0, 0.35, wall=True, blocks=True, color="#90a4ae"),
        _f("单人椅", 0.7, 0.7, color="#9fa8da"),
    ]


def small_bedroom_furniture() -> list[Furniture]:
    return [
        _f("单人床", 2.0, 1.0, wall=True, blocks=True, color="#c2a878"),
        _f("小衣柜", 1.2, 0.55, wall=True, blocks=True, color="#8d6e63"),
        _f("书桌", 1.0, 0.55, wall=True, color="#a1887f"),
        _f("书椅", 0.5, 0.5, color="#7986cb"),
    ]


def studio_furniture() -> list[Furniture]:
    return [
        _f("沙发床", 2.0, 0.9, wall=True, blocks=True, color="#7e9ec4"),
        _f("折叠桌", 1.2, 0.6, color="#a3b8cc"),
        _f("电视柜", 1.5, 0.4, wall=True, blocks=True, color="#6d7b8d"),
        _f("衣柜", 1.2, 0.6, wall=True, blocks=True, color="#8d6e63"),
        _f("餐椅", 0.45, 0.45, color="#9fa8da"),
        _f("书架", 0.8, 0.3, wall=True, blocks=True, color="#90a4ae"),
    ]


def overloaded_furniture() -> list[Furniture]:
    """超出 9 平米房间承载能力的家具组合，用于验证不可行检测。"""
    return [
        _f("双人床", 2.0, 1.5, wall=True, blocks=True, color="#c2a878"),
        _f("大衣柜", 2.0, 0.8, wall=True, blocks=True, color="#8d6e63"),
        _f("书桌", 1.4, 0.7, wall=True, color="#a1887f"),
        _f("书架", 1.2, 0.4, wall=True, blocks=True, color="#90a4ae"),
        _f("沙发", 1.8, 0.8, wall=True, blocks=True, color="#7e9ec4"),
        _f("茶几", 1.0, 0.6, color="#a3b8cc"),
        _f("斗柜", 0.8, 0.5, wall=True, color="#bcaaa4"),
    ]


def build_apartments() -> dict[str, list[Room]]:
    one_bedroom = [
        Room(
            "客厅", 0.0, 0.0, 5.0, 4.0,
            [Opening(DOOR, "S", 1.8, 0.9), Opening(WINDOW, "N", 2.8, 1.8)],
            living_furniture(),
        ),
        Room(
            "主卧", 5.0, 0.0, 3.6, 3.8,
            [Opening(DOOR, "S", 0.4, 0.85), Opening(WINDOW, "N", 1.0, 1.5)],
            bedroom_furniture(),
        ),
    ]

    two_bedroom = [
        Room(
            "客厅", 0.0, 0.0, 4.5, 4.2,
            [Opening(DOOR, "S", 1.6, 0.9),
             Opening(DOOR, "E", 1.4, 0.85),
             Opening(WINDOW, "N", 1.5, 1.6)],
            living_furniture(),
        ),
        Room(
            "主卧", 4.5, 0.5, 3.4, 3.5,
            [Opening(DOOR, "W", 0.5, 0.85), Opening(WINDOW, "N", 0.9, 1.4)],
            bedroom_furniture(),
        ),
        Room(
            "次卧", 0.5, 4.2, 2.8, 2.6,
            [Opening(DOOR, "S", 0.3, 0.8), Opening(WINDOW, "N", 0.7, 1.2)],
            small_bedroom_furniture(),
        ),
    ]

    studio = [
        Room(
            "开间", 0.0, 0.0, 3.6, 3.2,
            [Opening(DOOR, "S", 0.3, 0.85), Opening(WINDOW, "N", 1.2, 1.5)],
            studio_furniture(),
        ),
    ]

    overloaded = [
        Room(
            "超载小屋", 0.0, 0.0, 3.0, 3.0,
            [Opening(DOOR, "S", 0.3, 0.8), Opening(WINDOW, "N", 1.0, 1.2)],
            overloaded_furniture(),
        ),
    ]

    return {
        "一居室": one_bedroom,
        "两居室": two_bedroom,
        "紧凑开间": studio,
        "超载压力测试": overloaded,
    }


def door_links(plan: list[Room]) -> list[tuple[str, str]]:
    """户型内通过门相连的房间对（简化为共享墙的门配对，用于整体连通校验）。"""
    links: list[tuple[str, str]] = []
    for i in range(len(plan)):
        for j in range(i + 1, len(plan)):
            a, b = plan[i], plan[j]
            adjacent = (
                abs(a.x - b.x) < 0.01
                or abs(a.y - b.y) < 0.01
                or abs(a.bounds.x1 - b.x) < 0.01
                or abs(a.bounds.y1 - b.y) < 0.01
            )
            if adjacent and a.doors() and b.doors():
                links.append((a.name, b.name))
    return links


def build_search_instances() -> dict[str, Room]:
    """候选数量受控的搜索实例，保证朴素枚举可完整跑完。

    通过放大候选步长与候选上限，把每件家具的候选数压到 3~6 个，
    理论排列空间在数千量级，朴素与裁剪两种模式均可完整枚举。
    """
    tiny = Room(
        "微型客厅", 0.0, 0.0, 3.2, 2.8,
        [Opening(DOOR, "S", 0.3, 0.8), Opening(WINDOW, "N", 1.0, 1.2)],
        [
            _f("沙发", 1.6, 0.7, wall=True, blocks=True, color="#7e9ec4"),
            _f("边柜", 1.0, 0.4, wall=True, blocks=True, color="#8d6e63"),
            _f("茶几", 0.9, 0.5, color="#a3b8cc"),
            _f("单椅", 0.5, 0.5, color="#9fa8da"),
        ],
    )
    tight = Room(
        "紧凑卧室", 0.0, 0.0, 2.8, 2.6,
        [Opening(DOOR, "S", 0.2, 0.75), Opening(WINDOW, "N", 0.8, 1.0)],
        [
            _f("单人床", 1.9, 0.9, wall=True, blocks=True, color="#c2a878"),
            _f("衣柜", 1.0, 0.5, wall=True, blocks=True, color="#8d6e63"),
            _f("书桌", 0.9, 0.5, wall=True, color="#a1887f"),
        ],
    )
    corridor = Room(
        "窄走廊房", 0.0, 0.0, 2.4, 3.6,
        [
            Opening(DOOR, "S", 0.2, 0.7),
            Opening(DOOR, "N", 1.5, 0.7),
            Opening(WINDOW, "E", 1.2, 1.0),
        ],
        [
            _f("高柜", 1.2, 0.5, wall=True, blocks=True, color="#8d6e63"),
            _f("矮柜", 1.0, 0.45, wall=True, blocks=True, color="#a1887f"),
            _f("边桌", 0.8, 0.45, color="#a3b8cc"),
        ],
    )
    return {"微型客厅": tiny, "紧凑卧室": tight, "窄走廊房": corridor}
