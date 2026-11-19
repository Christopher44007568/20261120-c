"""Loop and Butterfly subdivision schemes."""
import math
from .mesh import Mesh, vadd, vscale


def loop_beta(n):
    """Warren's beta for an interior vertex of valence n."""
    c = 3.0 / 8.0 + 0.25 * math.cos(2.0 * math.pi / n)
    return (5.0 / 8.0 - c * c) / n


def _loop_even(mesh, v):
    p = mesh.vertices[v]
    sharp = mesh.sharp_neighbors(v)
    if len(sharp) >= 2:
        # Boundary / crease rule: 3/4 self + 1/8 each sharp neighbor.
        b1, b2 = mesh.vertices[sharp[0]], mesh.vertices[sharp[1]]
        return vadd(vscale(p, 0.75), vscale(vadd(b1, b2), 0.125))
    n = len(mesh.neighbors[v])
    beta = loop_beta(n)
    acc = vscale(p, 1.0 - n * beta)
    for u in mesh.neighbors[v]:
        acc = vadd(acc, vscale(mesh.vertices[u], beta))
    return acc


def _loop_odd(mesh, a, b):
    pa, pb = mesh.vertices[a], mesh.vertices[b]
    faces = mesh.edge_faces[frozenset((a, b))]
    if mesh.is_sharp_edge(a, b) or len(faces) == 1:
        # Boundary / crease edge midpoint rule.
        return vscale(vadd(pa, pb), 0.5)
    c = mesh.opposite(a, b, faces[0])
    d = mesh.opposite(a, b, faces[1])
    acc = vscale(vadd(pa, pb), 3.0 / 8.0)
    acc = vadd(acc, vscale(vadd(mesh.vertices[c], mesh.vertices[d]), 1.0 / 8.0))
    return acc


def loop_subdivide(mesh):
    return _subdivide(mesh, _loop_even, _loop_odd)


def _butterfly_even(mesh, v):
    # Butterfly is interpolatory: old vertices stay put.
    return mesh.vertices[v]


def _butterfly_odd(mesh, a, b):
    pa, pb = mesh.vertices[a], mesh.vertices[b]
    faces = mesh.edge_faces[frozenset((a, b))]
    if mesh.is_sharp_edge(a, b) or len(faces) == 1:
        return vscale(vadd(pa, pb), 0.5)
    c = mesh.opposite(a, b, faces[0])
    d = mesh.opposite(a, b, faces[1])
    acc = vscale(vadd(pa, pb), 0.5)
    acc = vadd(acc, vscale(vadd(mesh.vertices[c], mesh.vertices[d]), 0.125))
    # Outer wing vertices of the standard 8-point butterfly stencil.
    outer = []
    for (x, y, f) in ((a, c, faces[0]), (b, c, faces[0]),
                      (a, d, faces[1]), (b, d, faces[1])):
        for e in mesh.edge_faces.get(frozenset((x, y)), []):
            w = mesh.opposite(x, y, e)
            if w not in (a, b, c, d) and w not in outer:
                outer.append(w)
    for w in outer[:4]:
        acc = vadd(acc, vscale(mesh.vertices[w], -1.0 / 16.0))
    return acc


def butterfly_subdivide(mesh):
    return _subdivide(mesh, _butterfly_even, _butterfly_odd)


def _subdivide(mesh, even_rule, odd_rule):
    new_vertices = list(mesh.vertices)
    edge_mid = {}
    for e in mesh.edge_faces:
        a, b = sorted(e)
        edge_mid[e] = len(new_vertices)
        new_vertices.append(odd_rule(mesh, a, b))
    for v in range(len(mesh.vertices)):
        new_vertices[v] = even_rule(mesh, v)
    new_faces = []
    for (a, b, c) in mesh.faces:
        ab = edge_mid[frozenset((a, b))]
        bc = edge_mid[frozenset((b, c))]
        ca = edge_mid[frozenset((c, a))]
        new_faces += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
    # Crease edges split into two crease edges; boundary is recomputed.
    new_crease = []
    for e in mesh.crease_edges:
        a, b = sorted(e)
        m = edge_mid[e]
        new_crease.append((a, m))
        new_crease.append((m, b))
    return Mesh(new_vertices, new_faces, new_crease)


def subdivide_levels(mesh, scheme, levels):
    """Return list of meshes, one per level (level 0 = input)."""
    fn = {"loop": loop_subdivide, "butterfly": butterfly_subdivide}[scheme]
    out = [mesh]
    for _ in range(levels):
        out.append(fn(out[-1]))
    return out
