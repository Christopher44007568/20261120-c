from __future__ import annotations

import math
import unittest

from bbh_geodesic.bvh import BoneBVH
from bbh_geodesic.culling import benchmark_depths, brute_force, cull, make_cameras
from bbh_geodesic.geodesic import (
    analytic_circle_path,
    build_surface,
    minimum_clearance,
    nearest_vertex,
    polyline_length,
    shortest_path,
)
from bbh_geodesic.geometry import AABB
from bbh_geodesic.rig import RunRig


class GeometryTests(unittest.TestCase):
    def test_aabb_union_and_containment(self):
        boxes = [
            AABB((-1.0, 0.0, 2.0), (0.0, 1.0, 3.0)),
            AABB((2.0, -2.0, -1.0), (4.0, 0.0, 0.0)),
        ]
        merged = AABB.from_boxes(boxes)
        self.assertTrue(all(merged.contains_box(box) for box in boxes))
        self.assertEqual(merged.minimum, (-1.0, -2.0, -1.0))
        self.assertEqual(merged.maximum, (4.0, 1.0, 3.0))


class RunRigBvhTests(unittest.TestCase):
    def test_pose_updates_and_fit_invariants(self):
        rig = RunRig(frame_count=24)
        bvh = BoneBVH(rig)
        volumes = []
        for sample in rig.frames():
            bvh.update(sample.points)
            report = bvh.validate_fit(sample.points)
            self.assertEqual(report["containment_ratio"], 1.0)
            self.assertEqual(report["subtree_contained_ratio"], 1.0)
            self.assertTrue(report["hierarchy_contains_children"])
            self.assertEqual(report["max_outside_distance"], 0.0)
            volumes.append(bvh.root.box.volume)
        self.assertGreater(max(volumes) - min(volumes), 1.0)

    def test_layer_volumes_and_self_timing_are_consistent(self):
        rig = RunRig(frame_count=8)
        bvh = BoneBVH(rig)
        sample = rig.pose(0.0)
        bvh.update(sample.points, collect_timing=True)
        rows = bvh.layer_metrics(bvh.last_timing)
        self.assertEqual([row["depth"] for row in rows], list(range(7)))
        self.assertTrue(all(float(row["total_volume_m3"]) > 0.0 for row in rows))
        self.assertAlmostEqual(
            sum(float(row["update_ms_per_frame"]) for row in rows),
            sum(bvh.last_timing.values()) / 1_000_000.0,
            places=9,
        )

    def test_culling_is_safe_exact_and_monotonic(self):
        rig = RunRig(frame_count=12)
        bvh = BoneBVH(rig)
        frames = [sample.points for sample in rig.frames()]
        bvh.update(frames[0])
        cameras = make_cameras(bvh)
        rows, validation = benchmark_depths(bvh, frames, cameras)
        self.assertTrue(validation["safe"])
        self.assertTrue(validation["exact_at_full_depth"])
        rates = [float(row["culling_rate"]) for row in rows]
        self.assertTrue(all(a <= b + 1e-12 for a, b in zip(rates, rates[1:])))
        self.assertGreater(rates[-1], rates[0])

        bvh.update(frames[0])
        for frustum in cameras:
            brute = brute_force(bvh, frustum)
            self.assertEqual(cull(bvh.root, frustum, 6), brute)


class GeodesicTests(unittest.TestCase):
    def test_analytic_circle_path_uses_tangents_and_arc(self):
        start = (-1.40, -0.52)
        goal = (1.40, -0.52)
        result = analytic_circle_path(start, goal, (0.0, 0.0), 0.60)
        self.assertTrue(result["blocked"])
        self.assertAlmostEqual(float(result["distance"]), 2.8046055912, places=9)
        self.assertAlmostEqual(
            polyline_length([(x, y, 0.0) for x, y in result["points"]]),
            float(result["distance"]),
            places=5,
        )

    def test_flat_mesh_distance_matches_analytic(self):
        start_xy, goal_xy = (-1.40, -0.52), (1.40, -0.52)
        mesh = build_surface(spacing=0.04)
        start = mesh.vertices[nearest_vertex(mesh, (*start_xy, 0.0))]
        goal = mesh.vertices[nearest_vertex(mesh, (*goal_xy, 0.0))]
        distance, points, _ = shortest_path(mesh, start, goal)
        reference = float(
            analytic_circle_path(start_xy, goal_xy, (0.0, 0.0), 0.60)["distance"]
        )
        self.assertLess(abs(distance - reference) / reference, 0.015)
        self.assertGreaterEqual(minimum_clearance(points), 0.60 - 1e-9)

    def test_curved_mesh_convergence_and_clearance(self):
        start_xy, goal_xy = (-1.40, -0.52), (1.40, -0.52)
        distances = []
        for spacing in (0.04, 0.02):
            mesh = build_surface(spacing=spacing, curved=True)
            start = mesh.vertices[nearest_vertex(mesh, (*start_xy, 0.0))]
            goal = mesh.vertices[nearest_vertex(mesh, (*goal_xy, 0.0))]
            distance, points, _ = shortest_path(mesh, start, goal)
            self.assertGreaterEqual(minimum_clearance(points), 0.60 - 1e-9)
            self.assertGreater(distance, math.dist(start_xy, goal_xy))
            distances.append(distance)
        self.assertLess(abs(distances[1] - distances[0]) / distances[1], 0.001)


if __name__ == "__main__":
    unittest.main()
