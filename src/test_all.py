"""Self-contained correctness tests for every module (no test framework)."""
from math import isclose

from mesh import make_icosahedron, make_torus, torus_smooth_point
from pn_triangles import build_pn_patches, tessellate
from catmull_clark import subdivide, subdivide_tris, compact
from continuity import (check_edge_control_points, check_shared_edge_samples,
                        check_tessellation_watertight)
from volume_render import (analytic_transmittance, delta_tracking,
                           ray_march, Rng)


def test_pn_partition_of_unity():
    patches, _ = build_pn_patches(make_icosahedron())
    for degree in (2, 3):
        vals = patches[0]._bernstein(degree, 0.2, 0.3, 0.5)
        assert isclose(sum(vals.values()), 1.0, abs_tol=1e-12)


def test_pn_corners_interpolate():
    mesh = make_icosahedron()
    patches, vnormals = build_pn_patches(mesh)
    p = patches[0]
    from vec3 import length, sub
    assert length(sub(p.b[(3, 0, 0)], mesh.vertices[mesh.faces[0][0]])) < 1e-12
    pos, nrm = p.evaluate(1.0, 0.0, 0.0)
    assert length(sub(pos, p.b[(3, 0, 0)])) < 1e-10
    assert length(sub(nrm, p.nn[(2, 0, 0)])) < 1e-10


def test_tessellation_counts():
    mesh = make_torus()
    for level in (1, 2, 4):
        _, faces, _ = tessellate(mesh, level)
        assert len(faces) == len(mesh.faces) * level * level


def test_continuity():
    for mesh in (make_icosahedron(), make_torus()):
        r1 = check_edge_control_points(mesh)
        assert r1["geometry_ok"] and r1["normal_ok"]
        r2 = check_shared_edge_samples(mesh)
        assert r2["max_edge_position_gap"] < 1e-12
        assert r2["max_edge_normal_angle_rad"] < 1e-5
        v, f, _ = tessellate(mesh, 4)
        assert check_tessellation_watertight(v, f)["watertight"]


def test_catmul_clark_topology():
    mesh = make_icosahedron()
    v, q = compact(*subdivide(mesh.vertices, mesh.faces, 2))
    edges = set()
    for f in q:
        for a in range(4):
            edges.add(tuple(sorted((f[a], f[(a + 1) % 4]))))
    assert len(v) - len(edges) + len(q) == 2  # Euler characteristic of sphere
    vt, ft = subdivide_tris(mesh.vertices, mesh.faces, 2)
    # Each triangle yields 3 quads per level; level 2 -> 12 quads,
    # each split into 2 triangles -> 24 triangles per input face.
    assert len(ft) == len(mesh.faces) * 24


def test_volume_transport():
    # homogeneous marcher reproduces Beer-Lambert exactly
    t, steps = ray_march(2.0, 0.25, mode="homogeneous")
    assert isclose(t, analytic_transmittance(2.0, mode="homogeneous"))
    assert steps == 8
    # delta tracking converges to the analytic value within Monte Carlo error
    rng = Rng(42)
    est = sum(delta_tracking(rng, 2.0, mode="homogeneous")[0]
              for _ in range(200000)) / 200000
    assert isclose(est, analytic_transmittance(2.0), rel_tol=0.05)
    # heterogeneous midpoint rule is strictly better than left rule at dt=0.5
    tl, _ = ray_march(2.0, 0.5, mode="heterogeneous", rule="left")
    tm, _ = ray_march(2.0, 0.5, mode="heterogeneous", rule="midpoint")
    truth = analytic_transmittance(2.0, mode="heterogeneous")
    assert abs(tm - truth) < abs(tl - truth)


def test_torus_ground_truth():
    p = torus_smooth_point(0.7, 1.3)
    assert len(p) == 3


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")
