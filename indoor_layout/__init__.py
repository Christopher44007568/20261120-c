"""程序化室内布局引擎（纯标准库实现）。"""

from .geometry import Rect
from .room import Room, Opening, FurnitureType, Furniture, OpeningKind
from .solver import SolverParams, solve_room, RoomSolution
from .connectivity import check_room_connectivity

__all__ = [
    "Rect",
    "Room",
    "Opening",
    "FurnitureType",
    "Furniture",
    "OpeningKind",
    "SolverParams",
    "solve_room",
    "RoomSolution",
    "check_room_connectivity",
]
