from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indoor_layout.apartments import build_search_instances
from indoor_layout.culling import naive_search, pruned_search
from indoor_layout.solver import SolverParams


class CullingTests(unittest.TestCase):
    def setUp(self):
        self.params = SolverParams(grid_step=1.0, max_candidates=12)

    def test_pruning_keeps_same_valid_count(self):
        for room in build_search_instances().values():
            naive = naive_search(room, self.params, node_cap=10 ** 9)
            pruned = pruned_search(room, self.params, stop_at_first=False)
            self.assertEqual(
                naive.valid_arrangements,
                pruned.valid_arrangements,
                room.name,
            )

    def test_pruning_visits_fewer_or_equal_nodes(self):
        for room in build_search_instances().values():
            naive = naive_search(room, self.params, node_cap=10 ** 9)
            pruned = pruned_search(room, self.params, stop_at_first=False)
            self.assertLessEqual(pruned.nodes_visited, naive.nodes_visited)
            self.assertGreater(pruned.pruned_branches, 0)

    def test_stop_at_first_finds_one(self):
        room = next(iter(build_search_instances().values()))
        pruned = pruned_search(room, self.params, stop_at_first=True)
        self.assertEqual(pruned.valid_arrangements, 1)
        self.assertTrue(pruned.found_first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
