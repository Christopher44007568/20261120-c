from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indoor_layout.apartments import build_apartments
from indoor_layout.geometry import Rect, count_pairwise_collisions
from indoor_layout.connectivity import check_room_connectivity
from indoor_layout.room import Furniture, FurnitureType, Opening, OpeningKind, Room
from indoor_layout.solver import SolverParams, generate_candidates, solve_room


class GeometryTests(unittest.TestCase):
    def test_intersection_and_collision(self):
        self.assertTrue(Rect(0, 0, 2, 2).intersects(Rect(1, 1, 2, 2)))
        self.assertFalse(Rect(0, 0, 1, 1).intersects(Rect(1, 0, 1, 1)))
        self.assertEqual(
            Rect(0, 0, 2, 2).intersection_area(Rect(1, 1, 2, 2)), 1.0
        )
        rects = [Rect(0, 0, 1, 1), Rect(0.5, 0.5, 1, 1), Rect(3, 3, 1, 1)]
        self.assertEqual(count_pairwise_collisions(rects), 1)

    def test_rotation_keeps_center(self):
        rect = Rect(1, 2, 3, 1)
        rotated = rect.rotated()
        self.assertEqual((rotated.w, rotated.h), (1, 3))
        self.assertAlmostEqual(rotated.cx, rect.cx)
        self.assertAlmostEqual(rotated.cy, rect.cy)


class OpeningTests(unittest.TestCase):
    def setUp(self):
        self.room = Room("r", 0, 0, 4, 3)

    def test_door_keepout(self):
        door = Opening(OpeningKind.DOOR, "S", 1.0, 0.9)
        keep = door.keepout_rect(4, 3, 0.8)
        self.assertEqual(keep, Rect(1.0, 0.0, 0.9, 0.8))

    def test_candidates_avoid_door_and_window(self):
        room = Room(
            "r", 0, 0, 4, 3,
            [
                Opening(OpeningKind.DOOR, "S", 1.0, 0.9),
                Opening(OpeningKind.WINDOW, "N", 1.0, 1.5),
            ],
        )
        furniture = Furniture(FurnitureType("柜", 1.0, 0.5, must_touch_wall=True))
        params = SolverParams()
        keepouts = room.keepout_rects(
            params.door_clearance, params.window_clearance
        )
        for candidate in generate_candidates(room, furniture, params):
            self.assertFalse(any(candidate.intersects(k) for k in keepouts))


class ConnectivityTests(unittest.TestCase):
    def test_wall_across_room_blocks_door_to_door(self):
        room = Room(
            "r", 0, 0, 3, 3,
            [
                Opening(OpeningKind.DOOR, "S", 0.4, 0.8),
                Opening(OpeningKind.DOOR, "N", 1.8, 0.8),
            ],
        )
        wall = [Rect(0, 1.4, 3, 0.3)]
        result = check_room_connectivity(room, wall, cell=0.1, walkway_width=0.4)
        self.assertFalse(result["connected"])

    def test_empty_room_connected(self):
        room = Room(
            "r", 0, 0, 3, 3,
            [Opening(OpeningKind.DOOR, "S", 0.4, 0.8)],
        )
        result = check_room_connectivity(room, [], cell=0.1, walkway_width=0.6)
        self.assertTrue(result["connected"])


class SolverTests(unittest.TestCase):
    def test_all_nominal_plans_feasible(self):
        plans = build_apartments()
        params = SolverParams()
        for plan_name, rooms in plans.items():
            if plan_name == "超载压力测试":
                continue
            for room in rooms:
                sol = solve_room(room, params)
                self.assertEqual(sol.collisions, 0, f"{plan_name}/{room.name}")
                self.assertTrue(sol.connected, f"{plan_name}/{room.name}")
                self.assertTrue(sol.feasible, f"{plan_name}/{room.name}")
                self.assertEqual(len(sol.placed), len(room.furniture))

    def test_overloaded_room_reports_violation_or_relaxation(self):
        room = build_apartments()["超载压力测试"][0]
        sol = solve_room(room, SolverParams(restarts=6))
        self.assertFalse(sol.feasible)
        self.assertTrue(sol.collisions > 0 or not sol.connected)
        self.assertTrue(sol.note)

    def test_walkway_width_param_tightens_space(self):
        room = build_apartments()["紧凑开间"][0]
        wide = solve_room(room, SolverParams(walkway_width=0.9))
        narrow = solve_room(room, SolverParams(walkway_width=0.4))
        self.assertGreaterEqual(
            narrow.reachable_cells, wide.reachable_cells
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
