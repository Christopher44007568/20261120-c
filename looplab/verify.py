"""Numerical verification of Loop / Butterfly subdivision rules."""
import math
from .mesh import vadd, vsub, vscale, vnorm
from .subdivision import (loop_subdivide, butterfly_subdivide, loop_beta,
                          subdivide_levels)
from .testmeshes import grid_mesh, fold_mesh, dihedral_at_crease

TOL = 1e-12


def _close(a, b, tol=TOL):
    return vnorm(vsub(a, b)) < tol


def check_interior_even_rule():
    """Interior even vertex: (1-n*b)v + b*sum(neighbors), Warren beta."""
    mesh = grid_mesh(4)
    v = 6  # interior vertex of the 5x5 grid (valence 6)
    assert v not in mesh.boundary_vertices
    n = len(mesh.neighbors[v])
    beta = loop_beta(n)
    expected = vscale(mesh.vertices[v], 1.0 - n * beta)
    for u in mesh.neighbors[v]:
        expected = vadd(expected, vscale(mesh.vertices[u], beta))
    got = loop_subdivide(mesh).vertices[v]
    ok = _close(expected, got)
    return ok, f"valence={n} beta={beta:.6f} err={vnorm(vsub(expected, got)):.2e}"


def check_boundary_even_rule():
    """Boundary even vertex: 3/4 v + 1/8 (b1 + b2)."""
    mesh = grid_mesh(4)
    v = 1  # bottom-edge boundary vertex
    assert v in mesh.boundary_vertices
    sharp = mesh.sharp_neighbors(v)
    expected = vadd(vscale(mesh.vertices[v], 0.75),
                    vscale(vadd(mesh.vertices[sharp[0]],
                                mesh.vertices[sharp[1]]), 0.125))
    got = loop_subdivide(mesh).vertices[v]
    ok = _close(expected, got)
    return ok, f"sharp_nbrs={len(sharp)} err={vnorm(vsub(expected, got)):.2e}"


def check_interior_odd_rule():
    """Interior odd vertex: 3/8(v0+v1) + 1/8(v2+v3)."""
    mesh = grid_mesh(4)
    edge = next(e for e, fs in mesh.edge_faces.items()
                if len(fs) == 2 and e not in mesh.boundary_edges)
    a, b = sorted(edge)
    fs = mesh.edge_faces[edge]
    c = mesh.opposite(a, b, fs[0])
    d = mesh.opposite(a, b, fs[1])
    expected = vadd(vscale(vadd(mesh.vertices[a], mesh.vertices[b]), 0.375),
                    vscale(vadd(mesh.vertices[c], mesh.vertices[d]), 0.125))
    sub = loop_subdivide(mesh)
    # The odd vertex sits at index len(verts)+position; find via midpoint map.
    idx = _odd_index(mesh, edge)
    got = sub.vertices[idx]
    ok = _close(expected, got)
    return ok, f"err={vnorm(vsub(expected, got)):.2e}"


def check_boundary_odd_rule():
    """Boundary odd vertex: exact midpoint 1/2(v0+v1)."""
    mesh = grid_mesh(4)
    edge = next(iter(mesh.boundary_edges))
    a, b = sorted(edge)
    expected = vscale(vadd(mesh.vertices[a], mesh.vertices[b]), 0.5)
    got = loop_subdivide(mesh).vertices[_odd_index(mesh, edge)]
    ok = _close(expected, got)
    return ok, f"err={vnorm(vsub(expected, got)):.2e}"


def _odd_index(mesh, edge):
    for i, e in enumerate(mesh.edge_faces):
        if e == edge:
            return len(mesh.vertices) + i
    raise KeyError(edge)


def check_affine_precision():
    """Loop on a tilted plane keeps every vertex exactly on the plane."""
    mesh = grid_mesh(4, height_fn=lambda x, y: 0.3 * x - 0.7 * y + 0.1)
    sub = subdivide_levels(mesh, "loop", 2)[-1]
    worst = 0.0
    for (x, y, z) in sub.vertices:
        worst = max(worst, abs(z - (0.3 * x - 0.7 * y + 0.1)))
    return worst < 1e-12, f"max plane deviation={worst:.2e}"


def check_butterfly_interpolatory():
    """Butterfly keeps all old vertices fixed (interpolating scheme)."""
    mesh = grid_mesh(3, height_fn=lambda x, y: 0.2 * x * y)
    sub = butterfly_subdivide(mesh)
    worst = max(vnorm(vsub(mesh.vertices[i], sub.vertices[i]))
                for i in range(len(mesh.vertices)))
    return worst == 0.0, f"max old-vertex drift={worst:.2e}"


def check_crease_preservation(levels=3):
    """Crease-tagged fold keeps its 90-degree dihedral; untagged smooths."""
    mesh, crease = fold_mesh(4, 90.0)
    tagged = subdivide_levels(mesh, "loop", levels)
    smooth = subdivide_levels(
        type(mesh)(mesh.vertices, mesh.faces), "loop", levels)
    # Rebuild crease indexing for the smoothed mesh is identical at level 0;
    # measure dihedral on the finest level along the refined crease polyline.
    d0 = dihedral_at_crease(mesh, crease)
    d_tagged = _refined_dihedral(tagged[-1], len(mesh.vertices))
    d_smooth = _refined_dihedral(smooth[-1], len(mesh.vertices))
    kept = abs(d_tagged - d0) < 1.0
    smoothed = d_smooth > d_tagged + 5.0
    detail = (f"original={d0:.2f}deg tagged_L{levels}={d_tagged:.2f}deg "
              f"untagged_L{levels}={d_smooth:.2f}deg")
    return (kept and smoothed), detail


def _refined_dihedral(mesh, n_original):
    """Dihedral across edges adjacent to the refined crease vertices."""
    from .testmeshes import dihedral_at_crease
    vals = []
    for e, fs in mesh.edge_faces.items():
        if len(fs) == 2:
            a, b = sorted(e)
            vals.append(dihedral_at_crease(mesh, [(a, b)]))
    return min(vals) if vals else float("nan")


def run_all():
    checks = [
        ("Loop interior even rule (Warren beta)", check_interior_even_rule),
        ("Loop boundary even rule (3/4,1/8,1/8)", check_boundary_even_rule),
        ("Loop interior odd rule (3/8,3/8,1/8,1/8)", check_interior_odd_rule),
        ("Loop boundary odd rule (midpoint)", check_boundary_odd_rule),
        ("Loop affine precision on tilted plane", check_affine_precision),
        ("Butterfly interpolatory (old verts fixed)",
         check_butterfly_interpolatory),
        ("Loop crease preservation vs smoothing", check_crease_preservation),
    ]
    results = []
    for name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as exc:  # surface failures as check failures
            ok, detail = False, f"EXCEPTION: {exc}"
        results.append((name, ok, detail))
    return results
