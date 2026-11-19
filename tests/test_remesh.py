import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quadmesh.generate import make_organic_leaf, make_organic_ring
from quadmesh.metrics import evaluate_pair
from quadmesh.remesh import greedy_quad_pairing, quad_quality


class QuadRemeshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ring_source, cls.ring_reference = make_organic_ring(84, 16)
        cls.ring_output, cls.ring_pairing = greedy_quad_pairing(cls.ring_source, min_score=0.31)
        cls.ring_metrics = evaluate_pair(cls.ring_source, cls.ring_output)

        cls.leaf_source, cls.leaf_reference = make_organic_leaf(40, 24)
        cls.leaf_output, cls.leaf_pairing = greedy_quad_pairing(cls.leaf_source, min_score=0.31)
        cls.leaf_metrics = evaluate_pair(cls.leaf_source, cls.leaf_output)

    def test_ring_is_pure_manifold_quads_without_fallback(self):
        self.assertEqual(self.ring_pairing["fallback"], 0)
        self.assertTrue(all(len(face) == 4 for face in self.ring_output.faces))
        manifold = self.ring_metrics["manifold"]
        self.assertEqual(manifold["nonmanifold_edges"], 0)
        self.assertEqual(manifold["degenerate_faces"], 0)
        self.assertTrue(manifold["closed"])

    def test_leaf_is_pure_manifold_quads_without_fallback(self):
        self.assertEqual(self.leaf_pairing["fallback"], 0)
        self.assertTrue(all(len(face) == 4 for face in self.leaf_output.faces))
        manifold = self.leaf_metrics["manifold"]
        self.assertEqual(manifold["nonmanifold_edges"], 0)
        self.assertEqual(manifold["degenerate_faces"], 0)
        self.assertEqual(manifold["boundary_edges"], len(self.leaf_output.boundary_edges()))

    def test_all_authored_quads_are_recovered(self):
        expected = {tuple(sorted(face)) for face in self.ring_reference.faces}
        actual = {tuple(sorted(face)) for face in self.ring_output.faces}
        self.assertEqual(expected, actual)
        expected_leaf = {tuple(sorted(face)) for face in self.leaf_reference.faces}
        actual_leaf = {tuple(sorted(face)) for face in self.leaf_output.faces}
        self.assertEqual(expected_leaf, actual_leaf)

    def test_feature_edges_are_retained(self):
        for metrics in (self.ring_metrics, self.leaf_metrics):
            retention = metrics["feature_retention"]
            self.assertEqual(retention["exact_rate"], 1.0)
            self.assertEqual(retention["length_weighted_rate"], 1.0)
            self.assertEqual(retention["geometric_coverage_rate"], 1.0)
            self.assertEqual(retention["max_deviation"], 0.0)

    def test_distribution_thresholds(self):
        for metrics in (self.ring_metrics, self.leaf_metrics):
            self.assertLessEqual(metrics["output_edge_length"]["cv"], 0.20)
            self.assertGreaterEqual(metrics["quality"]["mean"], 0.90)
            self.assertGreaterEqual(metrics["quality"]["p05"], 0.75)
            self.assertGreaterEqual(metrics["angles_within_15_deg_of_90"], 0.95)
            self.assertGreaterEqual(metrics["quality_ge_0_7"], 0.99)

    def test_quad_quality_is_one_for_square(self):
        from quadmesh.geometry import Mesh

        mesh = Mesh(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            [(0, 1, 2, 3)],
        )
        self.assertAlmostEqual(quad_quality(mesh.vertices, mesh.faces[0]), 1.0)


if __name__ == "__main__":
    unittest.main()
