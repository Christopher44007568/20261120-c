import math
import unittest

import numpy as np

from walker.analysis import continuity_metrics, sweep_slopes
from walker.gait import GaitParams, simulate_scenario
from walker.terrain import WaveTerrain


class GaitModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = GaitParams()

    def test_cycle_and_flat_stride(self) -> None:
        result = simulate_scenario(
            0.0, params=self.params, duration_cycles=1.0, sample_hz=240.0
        )
        summary = result.summary
        self.assertAlmostEqual(summary["cycle_s"], 1.0)
        self.assertAlmostEqual(summary["stance_s"], 0.62)
        self.assertAlmostEqual(summary["swing_s"], 0.38)
        self.assertAlmostEqual(summary["double_support_s"], 0.24)
        self.assertAlmostEqual(summary["stride_m"], 0.72)
        self.assertAlmostEqual(summary["step_m"], 0.36)
        self.assertAlmostEqual(summary["measured_stride_m"], 0.72, places=12)
        self.assertEqual(summary["contact_max_abs_m"], 0.0)
        self.assertTrue(summary["all_reached"])

    def test_foot_contact_on_uphill_and_downhill(self) -> None:
        for slope in (-25.0, -20.0, -10.0, 0.0, 10.0, 20.0, 25.0):
            with self.subTest(slope=slope):
                result = simulate_scenario(
                    slope, params=self.params, duration_cycles=1.0, sample_hz=240.0
                )
                summary = result.summary
                self.assertLess(summary["contact_max_abs_m"], 1e-9)
                self.assertLess(summary["contact_rmse_m"], 1e-9)
                self.assertLess(summary["foot_slip_max_m"], 1e-9)
                self.assertLess(summary["reach_ratio_max"], 0.999)
                self.assertTrue(summary["all_reached"])
                self.assertAlmostEqual(
                    summary["measured_stride_m"],
                    summary["stride_m"],
                    places=12,
                )

    def test_joint_angles_are_finite_and_symmetric(self) -> None:
        result = simulate_scenario(
            15.0, params=self.params, duration_cycles=1.0, sample_hz=240.0
        )
        for row in result.rows:
            for key in (
                "hip_flexion_deg",
                "knee_flexion_deg",
                "ankle_dorsiflexion_deg",
            ):
                self.assertTrue(math.isfinite(row[key]))
            self.assertGreaterEqual(row["knee_flexion_deg"], 0.0)
            self.assertLess(row["knee_flexion_deg"], 160.0)
        left = result.summary["left"]
        right = result.summary["right"]
        self.assertGreater(left["hip_flexion_deg_rom"], 10.0)
        self.assertGreater(left["knee_flexion_deg_rom"], 10.0)
        self.assertAlmostEqual(
            left["knee_flexion_deg_rom"], right["knee_flexion_deg_rom"], places=9
        )

    def test_stride_continuous_and_monotone(self) -> None:
        rows = sweep_slopes(range(-25, 26), params=self.params, sample_hz=120.0)
        continuity = continuity_metrics(rows)
        self.assertTrue(continuity["continuous"])
        self.assertTrue(continuity["uphill_stride_monotone_decreasing"])
        self.assertTrue(
            continuity["downhill_stride_monotone_decreasing_with_abs_slope"]
        )
        self.assertAlmostEqual(continuity["stride_at_zero_m"], 0.72)
        self.assertLess(continuity["max_adjacent_stride_jump_m"], 0.01)
        self.assertLess(continuity["max_second_difference_m"], 0.001)
        self.assertLess(
            continuity["measured_vs_model_max_error_m"], 1e-12
        )
        by_slope = {round(row["slope_deg"]): row for row in rows}
        self.assertLess(by_slope[20]["stride_m"], by_slope[0]["stride_m"])
        self.assertLess(by_slope[-20]["stride_m"], by_slope[0]["stride_m"])
        self.assertLess(by_slope[20]["stride_m"], by_slope[-20]["stride_m"])

    def test_contact_on_smooth_wave_terrain(self) -> None:
        result = simulate_scenario(
            0.0,
            params=self.params,
            terrain=WaveTerrain(),
            duration_cycles=2.0,
            sample_hz=240.0,
        )
        self.assertLess(result.summary["contact_max_abs_m"], 0.003)
        self.assertTrue(result.summary["all_reached"])


if __name__ == "__main__":
    unittest.main()
