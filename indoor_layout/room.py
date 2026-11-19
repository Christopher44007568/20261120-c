"""房间、门窗开口与家具的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .geometry import Rect


class OpeningKind(Enum):
    DOOR = "door"
    WINDOW = "window"


@dataclass(frozen=True)
class Opening:
    """墙面上的开口。

    wall: 所属墙面 N(北/y=h)、S(南/y=0)、W(西/x=0)、E(东/x=w)
    offset: 沿墙面从左下角起算的位置（米）
    width: 开口宽度（米）
    """

    kind: OpeningKind
    wall: str
    offset: float
    width: float

    def keepout_rect(self, room_w: float, room_h: float, clearance: float) -> Rect:
        """开口向内延伸 clearance 米形成的禁放矩形。"""
        if self.wall == "S":
            return Rect(self.offset, 0.0, self.width, clearance)
        if self.wall == "N":
            return Rect(self.offset, room_h - clearance, self.width, clearance)
        if self.wall == "W":
            return Rect(0.0, self.offset, clearance, self.width)
        return Rect(room_w - clearance, self.offset, clearance, self.width)

    def threshold_point(self, room_w: float, room_h: float) -> tuple[float, float]:
        """开口内侧中心点，作为连通性检查的种子/目标点。"""
        mid = self.offset + self.width / 2.0
        eps = 0.05
        if self.wall == "S":
            return mid, eps
        if self.wall == "N":
            return mid, room_h - eps
        if self.wall == "W":
            return eps, mid
        return room_w - eps, mid


@dataclass(frozen=True)
class FurnitureType:
    name: str
    w: float
    h: float
    must_touch_wall: bool = False
    blocks_window: bool = False
    color: str = "#9bb8d3"


@dataclass
class Furniture:
    ftype: FurnitureType
    allow_rotation: bool = True
    placed: Rect | None = None

    @property
    def name(self) -> str:
        return self.ftype.name


@dataclass
class Room:
    name: str
    x: float
    y: float
    w: float
    h: float
    openings: list[Opening] = field(default_factory=list)
    furniture: list[Furniture] = field(default_factory=list)

    @property
    def bounds(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)

    @property
    def area(self) -> float:
        return self.w * self.h

    def local_bounds(self) -> Rect:
        return Rect(0.0, 0.0, self.w, self.h)

    def doors(self) -> list[Opening]:
        return [o for o in self.openings if o.kind is OpeningKind.DOOR]

    def windows(self) -> list[Opening]:
        return [o for o in self.openings if o.kind is OpeningKind.WINDOW]

    def keepout_rects(self, door_clearance: float, window_clearance: float) -> list[Rect]:
        rects = []
        for opening in self.openings:
            clearance = (
                door_clearance if opening.kind is OpeningKind.DOOR else window_clearance
            )
            rects.append(opening.keepout_rect(self.w, self.h, clearance))
        return rects

    def door_thresholds(self) -> list[tuple[float, float]]:
        return [o.threshold_point(self.w, self.h) for o in self.doors()]
