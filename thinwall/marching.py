"""Marching-tetrahedra isosurface extraction + watertightness check."""
import math

CUBE_TETS = [
    (0, 5, 1, 6), (0, 1, 2, 6), (0, 2, 3, 6),
    (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6),
]

CORNERS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
           (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]


def sample_field(field, bounds, res):
    """Sample scalar field on a regular grid."""
    (x0, y0, z0), (x1, y1, z1) = bounds
    nx, ny, nz = res
    dx = ((x1 - x0) / (nx - 1), (y1 - y0) / (ny - 1),
          (z1 - z0) / (nz - 1))
    vals = {}
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                p = (x0 + i * dx[0], y0 + j * dx[1], z0 + k * dx[2])
                vals[(i, j, k)] = field(p)
    return vals, dx, (x0, y0, z0)


def extract_isosurface(field, bounds, res, iso=0.0):
    """Return (vertices, triangles) of the iso-surface."""
    vals, dx, org = sample_field(field, bounds, res)
    nx, ny, nz = res
    verts, tris = [], []
    vcache = {}

    def pos(idx):
        return (org[0] + idx[0] * dx[0], org[1] + idx[1] * dx[1],
                org[2] + idx[2] * dx[2])

    def edge_vertex(ia, ib):
        key = (min(ia, ib), max(ia, ib))
        if key in vcache:
            return vcache[key]
        fa, fb = vals[ia], vals[ib]
        t = 0.5 if abs(fb - fa) < 1e-15 else (iso - fa) / (fb - fa)
        pa, pb = pos(ia), pos(ib)
        v = (pa[0] + (pb[0] - pa[0]) * t,
             pa[1] + (pb[1] - pa[1]) * t,
             pa[2] + (pb[2] - pa[2]) * t)
        verts.append(v)
        vcache[key] = len(verts) - 1
        return len(verts) - 1

    for i in range(nx - 1):
        for j in range(ny - 1):
            for k in range(nz - 1):
                cube = [(i + c[0], j + c[1], k + c[2]) for c in CORNERS]
                for tet in CUBE_TETS:
                    idx = [cube[t] for t in tet]
                    inside = [n for n in range(4) if vals[idx[n]] < iso]
                    if not inside or len(inside) == 4:
                        continue
                    _emit_tet(idx, inside, edge_vertex, tris)
    return verts, tris


def _emit_tet(idx, inside, edge_vertex, tris):
    if len(inside) == 1:
        a = inside[0]
        b, c, d = [n for n in range(4) if n != a]
        tris.append((edge_vertex(idx[a], idx[b]),
                     edge_vertex(idx[a], idx[c]),
                     edge_vertex(idx[a], idx[d])))
    elif len(inside) == 3:
        a = [n for n in range(4) if n not in inside][0]
        b, c, d = inside
        tris.append((edge_vertex(idx[a], idx[b]),
                     edge_vertex(idx[a], idx[d]),
                     edge_vertex(idx[a], idx[c])))
    else:
        a, b = inside
        c, d = [n for n in range(4) if n not in inside]
        v0 = edge_vertex(idx[a], idx[c])
        v1 = edge_vertex(idx[a], idx[d])
        v2 = edge_vertex(idx[b], idx[c])
        v3 = edge_vertex(idx[b], idx[d])
        tris.append((v0, v2, v1))
        tris.append((v1, v2, v3))


def check_watertight(tris):
    """Every edge shared by exactly 2 triangles means no holes."""
    from collections import Counter
    edges = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted(e))] += 1
    boundary = [e for e, n in edges.items() if n == 1]
    nonmanifold = [e for e, n in edges.items() if n > 2]
    return {
        "num_triangles": len(tris),
        "num_edges": len(edges),
        "boundary_edges": len(boundary),
        "nonmanifold_edges": len(nonmanifold),
        "watertight": not boundary and not nonmanifold,
    }


def euler_characteristic(verts, tris):
    edges = set()
    used = set()
    for a, b, c in tris:
        used.update((a, b, c))
        for e in ((a, b), (b, c), (c, a)):
            edges.add(tuple(sorted(e)))
    return len(used) - len(edges) + len(tris)
