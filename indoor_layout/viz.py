"""布局结果导出为 SVG（纯文本生成，无外部依赖）。"""

from __future__ import annotations

from .geometry import Rect
from .room import OpeningKind, Room
from .solver import RoomSolution


def _scale_color(color: str) -> str:
    return color


def room_svg(
    room: Room,
    solution: RoomSolution,
    path: str,
    px_per_m: int = 90,
) -> None:
    pad = 40
    width = int(room.w * px_per_m) + 2 * pad
    height = int(room.h * px_per_m) + 2 * pad

    def sx(value: float) -> float:
        return pad + value * px_per_m

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"',
        'font-family="sans-serif" font-size="11">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
    ]
    parts.append(
        f'<rect x="{sx(0)}" y="{sx(0)}" width="{room.w * px_per_m}" '
        f'height="{room.h * px_per_m}" fill="#f7f7f2" stroke="#333" stroke-width="3"/>'
    )
    for opening in room.openings:
        length = opening.width * px_per_m
        stroke = "#d9534f" if opening.kind is OpeningKind.DOOR else "#3a86ff"
        if opening.wall in ("S", "N"):
            x = sx(opening.offset)
            y = sx(0) if opening.wall == "S" else sx(room.h)
            parts.append(
                f'<line x1="{x}" y1="{y}" x2="{x + length}" y2="{y}" '
                f'stroke="{stroke}" stroke-width="5"/>'
            )
        else:
            x = sx(0) if opening.wall == "W" else sx(room.w)
            y = sx(opening.offset)
            parts.append(
                f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + length}" '
                f'stroke="{stroke}" stroke-width="5"/>'
            )
    for furniture in room.furniture:
        rect = solution.placed.get(furniture.name)
        if rect is None:
            continue
        color = _scale_color(furniture.ftype.color)
        parts.append(
            f'<rect x="{sx(rect.x):.1f}" y="{sx(rect.y):.1f}" '
            f'width="{rect.w * px_per_m:.1f}" height="{rect.h * px_per_m:.1f}" '
            f'rx="4" fill="{color}" stroke="#444" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{sx(rect.cx):.1f}" y="{sx(rect.cy):.1f}" '
            'text-anchor="middle" dominant-baseline="middle" fill="#222">'
            f"{furniture.name}</text>"
        )
    status = "可行" if solution.feasible else f"异常:{solution.note or '不连通'}"
    parts.append(
        f'<text x="{pad}" y="20" font-weight="bold">{room.name} '
        f"({room.area:.1f} m², 碰撞 {solution.collisions}, 连通 {solution.connected}, {status})</text>"
    )
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(parts))
