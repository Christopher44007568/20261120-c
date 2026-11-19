import unittest

from floorplan.layout import FloorPlan, Room, WALL, ROOM, CORRIDOR, \
    generate_floor_plan, check_layout


class FloorPlanTest(unittest.TestCase):
    def test_generated_plan_connected_without_collisions(self):
        specs = [("R1", 4, 5), ("R2", 5, 4), ("R3", 4, 6),
                 ("R4", 3, 5), ("R5", 5, 6), ("R6", 4, 4)]
        report = check_layout(generate_floor_plan(specs))
        self.assertEqual(report["rooms"], 6)
        self.assertEqual(report["collisions"], 0)
        self.assertTrue(report["connected"])
        self.assertEqual(len(report["reachable"]), 6)
        self.assertEqual(report["total_area"],
                         sum(h * w for _, h, w in specs))

    def test_overlap_detection(self):
        plan = FloorPlan(8, 8)
        plan.carve_room(Room("A", 1, 1, 3, 3))
        with self.assertRaises(ValueError):
            plan.carve_room(Room("B", 2, 2, 3, 3))

    def test_disconnected_rooms_without_corridor(self):
        plan = FloorPlan(8, 12)
        plan.carve_room(Room("A", 0, 0, 2, 2))
        plan.carve_room(Room("B", 5, 9, 2, 2))
        connected, reachable = plan.connectivity()
        self.assertFalse(connected)
        self.assertEqual(len(reachable), 1)

    def test_door_links_room_to_corridor(self):
        plan = FloorPlan(7, 12)
        plan.carve_corridor(3, 1, 10)
        plan.carve_room(Room("A", 0, 2, 3, 3))
        plan.open_door(2, 2)
        self.assertEqual(plan.grid[2][2], CORRIDOR)
        connected, _ = plan.connectivity()
        self.assertTrue(connected)


if __name__ == "__main__":
    unittest.main()
