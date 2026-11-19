import unittest

from anim_compress.subdivision import (
    boundary_vertices,
    build_cube_mesh,
    build_quad_patch_mesh,
    build_tent_mesh,
    sharp_dihedral_degrees,
    sharp_edge_max_deviation,
    subdivide_mesh,
)


class SubdivisionTests(unittest.TestCase):
    def test_open_patch_keeps_boundary_and_adds_interior_vertices(self):
        mesh = build_quad_patch_mesh()
        result = subdivide_mesh(mesh, levels=2)
        for vertex in result.mesh.vertices:
            self.assertAlmostEqual(vertex[2], 0.0, places=12)
        self.assertGreater(result.stats["interior_vertices"], 0)
        self.assertGreater(result.stats["boundary_vertices"], 0)
        self.assertEqual(result.stats["faces"], 4 * 4 * 4)

    def test_closed_cube_has_only_interior_vertices(self):
        result = subdivide_mesh(build_cube_mesh(), levels=2)
        self.assertEqual(result.stats["boundary_vertices"], 0)
        self.assertEqual(result.stats["interior_vertices"], len(result.mesh.vertices))
        self.assertEqual(result.stats["faces"], 96)

    def test_sharp_ridge_is_preserved(self):
        mesh = build_tent_mesh()
        result = subdivide_mesh(mesh, levels=2)
        self.assertEqual(result.stats["sharp_edges"], 8)
        deviation = sharp_edge_max_deviation(
            result.mesh, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
        )
        self.assertAlmostEqual(deviation, 0.0, places=12)
        angles = sharp_dihedral_degrees(result.mesh)
        self.assertTrue(angles)
        for angle in angles:
            self.assertAlmostEqual(angle, 90.0, places=6)
        self.assertGreater(len(boundary_vertices(result.mesh)), 0)


if __name__ == "__main__":
    unittest.main()
