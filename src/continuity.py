"""Verify PN-triangle continuity: shared edge control points, G1 normals,
and watertight tessellation (no cracks)."""
from vec3 import dot, length, normalize, sub
from pn_triangles import build_pn_patches


def _edge_info(mesh):
    """Map undirected edge -> list of (face index, local edge id, reversed)."""
    info = {}
    for fi, (a, b, c) in enumerate(mesh.faces):
        for local, (p, q) in enumerate(((a, b), (b, c), (c, a))):
            key = tuple(sorted((p, q)))
            reversed_ = (p, q) != key
            info.setdefault(key, []).append((fi, local, reversed_))
    return info


def check_edge_control_points(mesh, tol=1e-12):
    """Adjacent PN patches must share identical edge control points."""
    patches, _ = build_pn_patches(mesh)
    info = _edge_info(mesh)
    worst_geom = worst_normal = 0.0
    n_checked = 0
    for key, entries in info.items():
        if len(entries) != 2:
            continue
        (f0, e0, rev0), (f1, e1, rev1) = entries
        g0 = patches[f0].edge_geometry_points(e0)
        g1 = patches[f1].edge_geometry_points(e1)
        n0 = patches[f0].edge_normal_points(e0)
        n1 = patches[f1].edge_normal_points(e1)
        if rev0 != rev1:
            g1, n1 = g1[::-1], n1[::-1]
        for x, y in zip(g0, g1):
            worst_geom = max(worst_geom, length(sub(x, y)))
        for x, y in zip(n0, n1):
            worst_normal = max(worst_normal, length(sub(x, y)))
        n_checked += 1
    return {
        "edges_checked": n_checked,
        "max_geometry_point_gap": worst_geom,
        "max_normal_point_gap": worst_normal,
        "geometry_ok": worst_geom < tol,
        "normal_ok": worst_normal < tol,
    }


def check_shared_edge_samples(mesh, samples=24):
    """Sample both sides of every shared edge and compare position/normal."""
    from math import acos
    patches, _ = build_pn_patches(mesh)
    info = _edge_info(mesh)
    worst_pos = worst_normal_angle = 0.0
    # Barycentric triples moving from the edge's first endpoint to its second,
    # matching PNTriangle.edge_geometry_points ordering.
    bary_edge = (
        lambda t: (1.0 - t, t, 0.0),   # edge 0: p0 -> p1
        lambda t: (0.0, 1.0 - t, t),   # edge 1: p1 -> p2
        lambda t: (t, 0.0, 1.0 - t),   # edge 2: p2 -> p0
    )
    for key, entries in info.items():
        if len(entries) != 2:
            continue
        (f0, e0, rev0), (f1, e1, rev1) = entries
        for s in range(1, samples):
            t = s / samples
            t1 = 1.0 - t if (rev0 != rev1) else t
            uvw0 = bary_edge[e0](t)
            uvw1 = bary_edge[e1](t1)
            p0, n0 = patches[f0].evaluate(*uvw0)
            p1, n1 = patches[f1].evaluate(*uvw1)
            worst_pos = max(worst_pos, length(sub(p0, p1)))
            cosang = max(-1.0, min(1.0, dot(normalize(n0), normalize(n1))))
            worst_normal_angle = max(worst_normal_angle, acos(cosang))
    return {
        "max_edge_position_gap": worst_pos,
        "max_edge_normal_angle_rad": worst_normal_angle,
        "max_edge_normal_angle_deg": worst_normal_angle * 180.0 / 3.141592653589793,
    }


def check_tessellation_watertight(verts, faces, tol=1e-9):
    """Every edge of a closed tessellated mesh must occur exactly twice,
    using exact shared vertices (indices) — the strongest no-crack test."""
    edge_count = {}
    for (a, b, c) in faces:
        for e in ((a, b), (b, c), (c, a)):
            key = tuple(sorted(e))
            edge_count[key] = edge_count.get(key, 0) + 1
    boundary = [e for e, n in edge_count.items() if n != 2]
    return {
        "unique_edges": len(edge_count),
        "boundary_edges": len(boundary),
        "watertight": len(boundary) == 0,
    }
