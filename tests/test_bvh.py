from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from bvh.benchmark import run_benchmark
from bvh.builders import build_bvh
from bvh.dynamic import DynamicBVH
from bvh.geometry import Ray
from bvh.mesh import (
    generate_random_mesh,
    load_mesh,
    make_fixed_mesh,
    save_mesh,
)
from bvh.traversal import intersect_brute_force, traverse


ROOT = Path(__file__).resolve().parents[1]
RANDOM_MESH = ROOT / "data" / "random_mesh.json"
FIXED_MESH = ROOT / "data" / "fixed_mesh.json"


class BuildAndTraversalTests(unittest.TestCase):
    def test_all_strategies_build_valid_fixed_mesh(self) -> None:
        triangles = load_mesh(FIXED_MESH).triangles()
        for strategy in ("sah", "median", "lbvh"):
            with self.subTest(strategy=strategy):
                bvh = build_bvh(triangles, strategy, max_leaf_size=2)
                bvh.validate()
                self.assertEqual(bvh.primitive_count, 12)
                self.assertEqual(bvh.total_leaf_triangles(), 12)
                levels = bvh.level_stats()
                self.assertEqual(
                    sum(int(level["node_count"]) for level in levels),
                    len(bvh.reachable_nodes()),
                )
                self.assertEqual(
                    sum(int(level["leaf_count"]) for level in levels),
                    sum(1 for _ in bvh.leaves()),
                )

    def test_fixed_mesh_known_intersection(self) -> None:
        triangles = load_mesh(FIXED_MESH).triangles()
        ray = Ray((0.0, 0.0, -5.0), (0.0, 0.0, 1.0))
        for strategy in ("sah", "median", "lbvh"):
            with self.subTest(strategy=strategy):
                bvh = build_bvh(triangles, strategy, max_leaf_size=2)
                result = traverse(bvh, triangles, [ray])
                hit = result.hits[0]
                self.assertIsNotNone(hit)
                assert hit is not None
                self.assertAlmostEqual(hit.t, 4.0)
                self.assertEqual(hit.triangle_index, 0)

    def test_fixed_mesh_default_parameter_counts(self) -> None:
        triangles = load_mesh(FIXED_MESH).triangles()
        ray = Ray((0.0, 0.0, -5.0), (0.0, 0.0, 1.0))
        expected = {
            "sah": (9, 5, 5, 4),
            "median": (7, 4, 7, 12),
            "lbvh": (9, 5, 6, 6),
        }
        for strategy, values in expected.items():
            with self.subTest(strategy=strategy):
                bvh = build_bvh(triangles, strategy, max_leaf_size=4)
                stats = traverse(bvh, triangles, [ray]).stats
                self.assertEqual(
                    (
                        len(bvh.nodes),
                        sum(1 for _ in bvh.leaves()),
                        stats.node_visits,
                        stats.triangle_tests,
                    ),
                    values,
                )

    def test_bvh_hits_match_brute_force(self) -> None:
        triangles = load_mesh(FIXED_MESH).triangles()
        rays = [
            Ray((0.0, 0.0, -5.0), (0.0, 0.0, 1.0)),
            Ray((3.0, 2.0, 4.0), (-0.6, -0.4, -0.8)),
            Ray((-2.0, 0.5, 2.5), (0.5, -0.1, -0.7)),
        ]
        for strategy in ("sah", "median", "lbvh"):
            bvh = build_bvh(triangles, strategy, max_leaf_size=2)
            result = traverse(bvh, triangles, rays)
            for index, ray in enumerate(rays):
                expected = intersect_brute_force(triangles, ray)
                actual = result.hits[index]
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    assert actual is not None
                    self.assertAlmostEqual(actual.t, expected.t)
                    self.assertEqual(
                        actual.triangle_index, expected.triangle_index
                    )

    def test_repeated_build_has_identical_counts(self) -> None:
        triangles = generate_random_mesh(
            triangle_count=192, dense_triangle_count=96
        ).triangles()
        for strategy in ("sah", "median", "lbvh"):
            first = build_bvh(triangles, strategy, max_leaf_size=4)
            second = build_bvh(triangles, strategy, max_leaf_size=4)
            self.assertEqual(len(first.nodes), len(second.nodes))
            self.assertEqual(first.order, second.order)
            self.assertEqual(
                first.primitive_to_leaf, second.primitive_to_leaf
            )


class DynamicRebuildTests(unittest.TestCase):
    def test_local_rebuild_keeps_tree_valid(self) -> None:
        triangles = generate_random_mesh(
            triangle_count=192, dense_triangle_count=96
        ).triangles()
        dynamic = DynamicBVH(triangles, strategy="sah", max_leaf_size=4)
        leaf = next(dynamic.bvh.leaves())
        primitives = dynamic.bvh.subtree_primitives(leaf)
        stats = dynamic.translate_primitives(primitives, (0.05, 0.02, 0.0))
        dynamic.bvh.validate()
        self.assertTrue(stats.local_rebuild)
        self.assertGreaterEqual(stats.overlap_volume, 0.0)
        self.assertEqual(stats.rebuilt_primitive_count, len(primitives))
        self.assertLess(stats.rebuilt_node_count, len(dynamic.bvh.nodes))
        ray = Ray(
            (0.0, 0.0, -12.0),
            (0.0, 0.0, 1.0),
        )
        actual = traverse(dynamic.bvh, triangles, [ray]).hits[0]
        expected = intersect_brute_force(triangles, ray)
        if expected is None:
            self.assertIsNone(actual)
        else:
            assert actual is not None
            self.assertAlmostEqual(actual.t, expected.t)


class ReproducibilityTests(unittest.TestCase):
    def test_generated_random_mesh_matches_checked_in_json(self) -> None:
        generated = generate_random_mesh(
            triangle_count=1536,
            seed=20261120,
            dense_triangle_count=768,
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "random_mesh.json"
            save_mesh(generated, target)
            self.assertEqual(target.read_bytes(), RANDOM_MESH.read_bytes())

    def test_fixed_mesh_matches_checked_in_json(self) -> None:
        fixed = make_fixed_mesh()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "fixed_mesh.json"
            save_mesh(fixed, target)
            self.assertEqual(target.read_bytes(), FIXED_MESH.read_bytes())

    def test_benchmark_claim_and_deterministic_counters(self) -> None:
        mesh = load_mesh(RANDOM_MESH)
        result = run_benchmark(
            mesh,
            bvh_parameters={"build_repeats": 1, "traversal_repeats": 1},
            dynamic_parameters={"frames": 2},
        )
        comparison = result["comparison"]
        self.assertTrue(comparison["all_nearest_hits_equal"])
        self.assertTrue(comparison["sah_faster_in_dense_region"])
        self.assertEqual(comparison["sah_focus_node_visits"], 45399)
        self.assertEqual(comparison["sah_focus_triangle_tests"], 17264)
        self.assertEqual(comparison["median_focus_node_visits"], 52150)
        self.assertEqual(comparison["median_focus_triangle_tests"], 23136)
        self.assertEqual(comparison["lbvh_focus_node_visits"], 253669)
        self.assertEqual(comparison["lbvh_focus_triangle_tests"], 188229)
        self.assertEqual(
            result["strategies"]["sah"]["traversal"]["hit_count"], 394
        )
        self.assertTrue(result["dynamic"]["summary"]["all_frames_local"])
        self.assertGreater(
            result["dynamic"]["summary"]["total_overlap_volume"], 0.0
        )
        self.assertTrue(result["dynamic"]["summary"]["final_bvh_valid"])

    def test_checked_in_benchmark_artifact_is_valid_json(self) -> None:
        path = ROOT / "artifacts" / "benchmark.json"
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["schema"], "bvh-benchmark-v1")
        self.assertTrue(data["validation"]["dense_region_claim_holds"])


if __name__ == "__main__":
    unittest.main()
