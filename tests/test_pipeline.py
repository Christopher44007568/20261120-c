from __future__ import annotations

import unittest

import numpy as np

from mesh_offset.geometry import make_holey_plate, mesh_stats, vertex_normals
from mesh_offset.sdf import SignedDistanceGrid
from mesh_offset.shelling import build_offset_surfaces, build_shell
from mesh_offset.validation import validate_shell


class ShellPipelineTests(unittest.TestCase):
    def test_holey_plate_is_closed_genus_four(self):
        mesh, metadata = make_holey_plate()
        stats = mesh_stats(mesh)
        self.assertTrue(stats.watertight)
        self.assertEqual(stats.boundary_edges, 0)
        self.assertEqual(stats.nonmanifold_edges, 0)
        self.assertEqual(stats.genus, 4)
        self.assertEqual(metadata["through_holes"], 4)

    def test_angle_weighted_normals_are_unit_length(self):
        mesh, _ = make_holey_plate()
        normals = vertex_normals(mesh.vertices, mesh.faces)
        lengths = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(lengths, 1.0, atol=1e-10)

    def test_shell_repairs_self_intersections_and_stays_continuous(self):
        mesh, _ = make_holey_plate()
        grid = SignedDistanceGrid.from_mesh(mesh, 0.12, 0.42)
        surfaces = build_offset_surfaces(
            mesh,
            grid,
            0.12,
            edge_length=0.12,
            simplify_tolerance=0.004,
        )
        shell = build_shell(surfaces)
        result = validate_shell(surfaces, shell, mesh, expected_genus=4)

        self.assertGreaterEqual(surfaces.repair_count, 0)
        self.assertEqual(result.final_self_intersections, 0)
        self.assertEqual(result.shell_surface_components, 2)
        self.assertTrue(result.shell_surface_watertight)
        self.assertTrue(result.volume_consistent)
        self.assertTrue(result.inner_outer_continuous)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
