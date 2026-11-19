import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parallax.geometry import box_exit, normalize
from parallax.mesh_quality import uniformity_report
from parallax.probe import ReflectionProbe, offset_metrics, wall_penetration
from parallax.remesh import organic_quad_mesh, organic_tri_mesh
from parallax.seam import (blended_direction, limiting_discontinuity,
                           overlap_weight)
from experiments.exp2_seams import adjacent_probes


class TestRayBox(unittest.TestCase):
    def test_exit_distance_face(self):
        lo, hi = np.array([-2.0, -2.0, -2.0]), np.array([2.0, 2.0, 2.0])
        p = np.zeros(3)
        t = box_exit(p, normalize([1.0, 0.0, 0.0]), lo, hi)
        self.assertAlmostEqual(t, 2.0, places=10)

    def test_diagonal_exit(self):
        lo, hi = np.array([-2.0, -2.0, -2.0]), np.array([2.0, 2.0, 2.0])
        t = box_exit(np.zeros(3), normalize([1.0, 1.0, 1.0]), lo, hi)
        self.assertAlmostEqual(t, 2.0 * np.sqrt(3.0), places=10)


class TestBPR(unittest.TestCase):
    def setUp(self):
        self.lo = np.array([-4.0, -3.0, -2.0])
        self.hi = np.array([4.0, 3.0, 2.0])
        self.probe = ReflectionProbe("p", np.zeros(3), self.lo, self.hi)

    def test_box_hit_lies_on_boundary(self):
        p = np.array([1.0, 0.5, -0.5])
        for r in [normalize(v) for v in
                  ([1, 1, 0], [-1, 0.2, 1], [0.3, -0.9, 0.4])]:
            hit = self.probe.box_hit(p, r)
            on_face = np.any(np.isclose(hit, self.lo) | np.isclose(hit, self.hi))
            self.assertTrue(on_face, f"hit {hit} not on a box face")
            self.assertTrue(np.all(hit >= self.lo - 1e-9))
            self.assertTrue(np.all(hit <= self.hi + 1e-9))

    def test_bpr_zero_error_when_box_matches_room(self):
        p = np.array([1.5, -0.8, 0.6])
        rng = np.random.default_rng(0)
        for r in rng.normal(size=(12, 3)):
            metrics = offset_metrics(self.probe, p, r, self.lo, self.hi)
            self.assertAlmostEqual(metrics["box"]["world_offset"], 0.0, places=8)
            self.assertAlmostEqual(metrics["box"]["angular_error_deg"], 0.0, places=8)
            self.assertGreater(metrics["uncorrected"]["angular_error_deg"], 0.0)


class TestWall(unittest.TestCase):
    def test_fitted_probe_never_penetrates(self):
        lo = np.array([2.0, -5.0, -4.0])
        hi = np.array([8.0, 5.0, 4.0])
        probe = ReflectionProbe("wall", np.array([5.0, 0, 0]), lo, hi)
        normal, d = np.array([1.0, 0.0, 0.0]), 8.0
        rng = np.random.default_rng(2)
        dirs = rng.normal(size=(16, 3))
        dirs[:, 0] = np.abs(dirs[:, 0]) + 0.5
        for offset in (0.25, 0.5, 1.0, 2.0):
            p = np.array([d - offset, 0.4, -0.6])
            for r in dirs:
                result = wall_penetration(probe, p, r, normal, d)
                self.assertFalse(result["leaks"])
                self.assertLessEqual(result["penetration"], 1e-9)

    def test_oversized_probe_does_leak(self):
        lo = np.array([2.0, -5.0, -4.0])
        hi = np.array([9.5, 5.0, 4.0])  # extends 1.5 m past the wall
        probe = ReflectionProbe("bad", np.array([5.0, 0, 0]), lo, hi)
        p = np.array([7.5, 0.4, -0.6])
        result = wall_penetration(probe, p, normalize([1, 0.2, 0.1]),
                                  np.array([1.0, 0, 0]), 8.0)
        self.assertTrue(result["leaks"])
        self.assertAlmostEqual(result["penetration"], 1.5, places=6)


class TestSeamBlend(unittest.TestCase):
    def test_weights_complementary_and_continuous_at_faces(self):
        probes = adjacent_probes(half=4.0, overlap=2.0)
        for x in (-1.0, 0.0, 1.0):
            p = np.array([x, 0.0, 0.0])
            wl = overlap_weight(probes, 0, p)
            wr = overlap_weight(probes, 1, p)
            self.assertAlmostEqual(wl + wr, 1.0, places=10)
        # At the overlap faces a leaving/entering probe must hit exactly 0/1.
        self.assertAlmostEqual(overlap_weight(probes, 0, np.array([1.0, 0, 0])),
                               0.0, places=10)
        self.assertAlmostEqual(overlap_weight(probes, 1, np.array([-1.0, 0, 0])),
                               0.0, places=10)

    def test_blend_continuous_under_refinement(self):
        probes = adjacent_probes(half=4.0, overlap=2.0)
        r = normalize([0.35, 0.8, 0.48])
        xs = np.linspace(-1.5, 1.5, 121)
        epsilons = (1e-3, 1e-4, 1e-5)
        hard, soft = limiting_discontinuity(probes, 0, xs, r, epsilons)
        # Hard switch: finite L2 gap that does not shrink (true C0 seam).
        self.assertGreater(hard[-1], 0.9)
        self.assertAlmostEqual(hard[-1], hard[0], delta=0.05)
        # Blend: gap proportional to epsilon -> converges to zero.
        ratios = [s / e for s, e in zip(soft, epsilons)]
        self.assertLess(soft[-1], 1e-4)
        self.assertTrue(np.allclose(ratios, ratios[0], rtol=1e-3))


class TestRemesh(unittest.TestCase):
    def test_quad_mesh_uniform_and_watertight(self):
        points, quads = organic_quad_mesh(resolution=12)
        report = uniformity_report(points, quads)
        self.assertTrue(report["watertight"])
        self.assertEqual(report["vertices_per_face"], 4)
        self.assertLess(report["edge_cv"], 0.12)
        self.assertLess(report["aspect_max"], 1.5)

    def test_triangle_input_is_watertight(self):
        points, faces = organic_tri_mesh(subdivisions=2)
        report = uniformity_report(points, faces)
        self.assertTrue(report["watertight"])
        self.assertEqual(report["vertices_per_face"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
