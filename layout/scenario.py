"""Fixed demonstration board: endpoints, obstacles, two signal layers."""

from .geometry import Board, Obstacle, Pin

DEMO_OBSTACLES = [
    Obstacle(0, 5, 3, 9, 7),
    Obstacle(0, 11, 8, 15, 12),
    Obstacle(1, 2, 6, 6, 10),
    Obstacle(1, 10, 1, 14, 5),
    Obstacle(0, 0, 10, 3, 14),
]

DEMO_PINS = [
    Pin("clk", 0, 1, 1),
    Pin("clk", 1, 16, 13),
    Pin("data", 0, 2, 8),
    Pin("data", 1, 15, 2),
    Pin("ctrl", 0, 16, 1),
    Pin("ctrl", 0, 1, 14),
    Pin("pwr", 1, 3, 13),
    Pin("pwr", 0, 14, 14),
    Pin("sense", 0, 17, 7),
    Pin("sense", 1, 1, 2),
]


def build_demo_board():
    board = Board(18, 15, 2, DEMO_OBSTACLES)
    board.check_pins(DEMO_PINS)
    return board, DEMO_PINS
