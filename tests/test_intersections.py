from __future__ import annotations

import unittest

import numpy as np

from mesh_offset.intersections import (
    count_self_intersections,
    triangles_intersect_proper,
)


class TriangleIntersectionTests(unittest.TestCase):
    def test_crossing_triangles_intersect(self):
        a = np.array([[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [0.0, 1.0, 0.0]])
        b = np.array([[0.0, -0.5, -1.0], [0.0, 0.5, -1.0], [0.0, 0.0, 1.0]])
        self.assertTrue(triangles_intersect_proper(a, b))

    def test_point_contact_is_not_a_proper_intersection(self):
        a = np.array([[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [0.0, 1.0, 0.0]])
        b = np.array([[0.0, 0.0, 0.0], [0.2, 0.0, 0.5], [0.0, 0.2, 0.5]])
        self.assertFalse(triangles_intersect_proper(a, b))

    def test_coplanar_overlap_and_separation(self):
        a = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        overlap = np.array(
            [[0.2, 0.2, 0.0], [0.8, 0.2, 0.0], [0.2, 0.8, 0.0]]
        )
        separated = np.array(
            [[2.0, 2.0, 0.0], [3.0, 2.0, 0.0], [2.0, 3.0, 0.0]]
        )
        self.assertTrue(triangles_intersect_proper(a, overlap))
        self.assertFalse(triangles_intersect_proper(a, separated))

    def test_adjacent_triangles_are_excluded(self):
        vertices = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ]
        )
        faces = np.array([[0, 1, 2], [1, 3, 2]])
        report = count_self_intersections(vertices, faces)
        self.assertEqual(report.count, 0)


if __name__ == "__main__":
    unittest.main()
