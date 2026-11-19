import math
import unittest

from proctree.plant import LSystemParams, generate, rewrite


BUSH = LSystemParams(
    name="bush",
    axiom="X",
    rules={
        "X": "F+[[XL]-XL]-F[-FXL]+L",
        "F": "FF",
    },
    angle_deg=25.0,
    step=1.0,
)

TREE = LSystemParams(
    name="tree",
    axiom="F",
    rules={"F": "F[+F]F[-F][F]"},
    angle_deg=22.5,
    step=1.0,
)


class PlantTests(unittest.TestCase):
    def test_rewrite_deterministic_and_grows(self):
        self.assertEqual(rewrite(BUSH, 0), "X")
        s1 = rewrite(BUSH, 1)
        self.assertEqual(s1, "F+[[XL]-XL]-F[-FXL]+L")
        lengths = [len(rewrite(BUSH, d)) for d in range(1, 5)]
        self.assertEqual(lengths, sorted(lengths))
        self.assertGreater(lengths[-1], lengths[0])

    def test_generation_collects_hierarchy_and_box(self):
        plant = generate(BUSH, 4)
        self.assertTrue(plant.segments)
        self.assertTrue(plant.leaves)
        levels = plant.level_counts
        self.assertEqual(min(levels), 0)
        for seg in plant.segments:
            self.assertGreaterEqual(seg.end[1], plant.bbox[1] - 1e-9)
            self.assertLessEqual(seg.end[1], plant.bbox[3] + 1e-9)
        xmin, ymin, xmax, ymax = plant.bbox
        self.assertGreater(xmax, xmin)
        self.assertGreater(ymax, ymin)

    def test_deeper_trees_add_instances_monotonically(self):
        totals = []
        for depth in range(2, 6):
            plant = generate(TREE, depth)
            totals.append(plant.summary()["total_instances"])
        self.assertEqual(totals, sorted(totals))
        self.assertGreater(totals[-1], totals[0])

    def test_rule_params_change_distribution(self):
        narrow = LSystemParams("n", "F", {"F": "F[+F]F[-F][F]"}, 12.0, 1.0)
        wide = LSystemParams("w", "F", {"F": "F[+F]F[-F][F]"}, 38.0, 1.0)
        a = generate(narrow, 4)
        b = generate(wide, 4)
        self.assertEqual(len(a.segments), len(b.segments))
        self.assertGreater(a.bbox_size[1], a.bbox_size[0])
        self.assertLess(a.bbox_size[0], b.bbox_size[0])

    def test_timing_recorded(self):
        plant = generate(BUSH, 3)
        self.assertGreaterEqual(plant.elapsed_ms, 0.0)
        self.assertTrue(math.isfinite(plant.elapsed_ms))


if __name__ == "__main__":
    unittest.main()
