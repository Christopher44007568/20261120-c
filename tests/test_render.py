import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quadmesh.generate import make_organic_ring
from quadmesh.raster_validation import validate
from quadmesh.render_compare import (
    FrameConfig,
    build_suite,
    conditional_conclusion,
    estimate_frame,
    repeatability_check,
)


class RenderBudgetTests(unittest.TestCase):
    def test_1080p_1x_known_budget(self):
        row = estimate_frame(FrameConfig(width=1920, height=1080, samples=1))
        self.assertEqual(row["deferred_bytes_per_pixel"], 32)
        self.assertEqual(row["visibility_bytes_per_pixel"], 20)
        self.assertAlmostEqual(row["memory_saving_percent"], 37.5)
        self.assertEqual(row["deferred_traffic_per_covered_pixel"], 56)
        self.assertEqual(row["visibility_traffic_per_covered_pixel"], 52)
        self.assertAlmostEqual(row["traffic_saving_percent"], 100.0 * 4.0 / 56.0)

    def test_visibility_memory_is_lower_for_all_frames(self):
        suite = build_suite()
        self.assertTrue(all(row["memory_saving_bytes"] > 0 for row in suite["frames"]))

    def test_msaa_increases_total_bandwidth_saving(self):
        one = estimate_frame(FrameConfig(samples=1))
        four = estimate_frame(FrameConfig(samples=4))
        self.assertGreater(four["traffic_saving_percent"], one["traffic_saving_percent"])
        self.assertAlmostEqual(four["traffic_saving_percent"], 31.25)

    def test_cache_penalty_can_reverse_no_msaa_bandwidth(self):
        row = estimate_frame(FrameConfig(samples=1, material_cache_penalty=16))
        self.assertLess(row["traffic_saving_percent"], 0.0)
        conclusion = conditional_conclusion(build_suite())
        self.assertTrue(conclusion["vis_bandwidth_loses_without_msaa_when"])

    def test_model_is_bit_repeatable(self):
        result = repeatability_check(runs=3)
        self.assertTrue(result["bit_identical"])
        self.assertEqual(result["unique_hashes"], 1)

    def test_raster_cross_check_is_repeatable(self):
        mesh, _ = make_organic_ring(84, 16)
        result = validate(mesh, width=120, height=68, repeats=2)
        self.assertTrue(result["all_repeatable"])
        self.assertTrue(all(row["covered_pixels"] > 0 for row in result["rows"]))
        self.assertTrue(all(0.0 < row["coverage"] < 1.0 for row in result["rows"]))


if __name__ == "__main__":
    unittest.main()
