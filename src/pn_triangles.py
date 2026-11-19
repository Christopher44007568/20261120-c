"""PN-Triangles (Vlachos et al. 2001).

Each input triangle becomes a cubic Bezier triangle for geometry (10 control
points) plus a quadratic Bezier triangle for the normal field (6 control
points).  Edge control points depend only on the two shared vertices and their
normals, so neighbouring patches meet exactly (C0 geometry, G1 normals) with
no cracks.
"""
from math import factorial

from vec3 import add, dot, normalize, scale, sub


def _b301(p0, p1, n0):
    """Edge control point adjacent to p0 along edge p0->p1."""
    w = sub(p1, p0)
    return add(add(p0, scale(w, 1.0 / 3.0)),
               scale(n0, dot(scale(n0, -1.0), w) * 2.0 / 3.0))


def _n_edge(n0, n1):
    """Quadratic normal control point on edge (n0, n1), normalized."""
    return normalize(add(n0, n1))


class PNTriangle:
    def __init__(self, p0, p1, p2, n0, n1, n2):
        # Geometry control points, index = (i, j, k), i+j+k = 3,
        # flat index b = j*4 + k - j*(j-1)//2 ... use explicit dict instead.
        self.b = {}
        self.b[(3, 0, 0)] = tuple(p0)
        self.b[(0, 3, 0)] = tuple(p1)
        self.b[(0, 0, 3)] = tuple(p2)
        self.b[(2, 1, 0)] = tuple(_b301(p0, p1, n0))
        self.b[(1, 2, 0)] = tuple(_b301(p1, p0, n1))
        self.b[(0, 2, 1)] = tuple(_b301(p1, p2, n1))
        self.b[(0, 1, 2)] = tuple(_b301(p2, p1, n2))
        self.b[(1, 0, 2)] = tuple(_b301(p2, p0, n2))
        self.b[(2, 0, 1)] = tuple(_b301(p0, p2, n0))
        e = scale(add(add(self.b[(2, 1, 0)], self.b[(1, 2, 0)]),
                      add(self.b[(0, 2, 1)], self.b[(0, 1, 2)])),
                  1.0 / 2.0)
        e = add(e, scale(add(self.b[(1, 0, 2)], self.b[(2, 0, 1)]), 1.0 / 2.0))
        e = sub(scale(e, 1.0 / 3.0),
                scale(add(add(p0, p1), p2), 1.0 / 18.0))
        self.b[(1, 1, 1)] = tuple(e)

        # Normal control points, i+j+k = 2.
        self.nn = {
            (2, 0, 0): tuple(normalize(n0)),
            (0, 2, 0): tuple(normalize(n1)),
            (0, 0, 2): tuple(normalize(n2)),
            (1, 1, 0): tuple(_n_edge(n0, n1)),
            (0, 1, 1): tuple(_n_edge(n1, n2)),
            (1, 0, 1): tuple(_n_edge(n0, n2)),
        }

    @staticmethod
    def _bernstein(degree, u, v, w):
        out = {}
        for i in range(degree + 1):
            for j in range(degree + 1 - i):
                k = degree - i - j
                c = factorial(degree) // (factorial(i) * factorial(j)
                                          * factorial(k))
                out[(i, j, k)] = c * (u ** i) * (v ** j) * (w ** k)
        return out

    def evaluate(self, u, v, w):
        """Position and shading normal at barycentric (u, v, w)."""
        p = (0.0, 0.0, 0.0)
        for key, coef in self._bernstein(3, u, v, w).items():
            p = add(p, scale(self.b[key], coef))
        nraw = (0.0, 0.0, 0.0)
        for key, coef in self._bernstein(2, u, v, w).items():
            nraw = add(nraw, scale(self.nn[key], coef))
        return p, normalize(nraw)

    def edge_geometry_points(self, edge):
        """Shared edge geometry control points (4) for continuity checks.
        edge 0: p0-p1, edge 1: p1-p2, edge 2: p2-p0."""
        if edge == 0:
            keys = [(3, 0, 0), (2, 1, 0), (1, 2, 0), (0, 3, 0)]
        elif edge == 1:
            keys = [(0, 3, 0), (0, 2, 1), (0, 1, 2), (0, 0, 3)]
        else:
            keys = [(0, 0, 3), (1, 0, 2), (2, 0, 1), (3, 0, 0)]
        return [self.b[k] for k in keys]

    def edge_normal_points(self, edge):
        if edge == 0:
            keys = [(2, 0, 0), (1, 1, 0), (0, 2, 0)]
        elif edge == 1:
            keys = [(0, 2, 0), (0, 1, 1), (0, 0, 2)]
        else:
            keys = [(0, 0, 2), (1, 0, 1), (2, 0, 0)]
        return [self.nn[k] for k in keys]


def build_pn_patches(mesh):
    """One PNTriangle per mesh face using area-weighted vertex normals."""
    normals = mesh.vertex_normals()
    patches = []
    for (i0, i1, i2) in mesh.faces:
        patches.append(PNTriangle(
            mesh.vertices[i0], mesh.vertices[i1], mesh.vertices[i2],
            normals[i0], normals[i1], normals[i2]))
    return patches, normals


def tessellate(mesh, level):
    """Uniformly tessellate every PN patch into level^2 small triangles.
    Returns (vertices, faces, normals) of the refined triangle mesh.
    Vertices on shared edges are welded so the output is watertight."""
    patches, _ = build_pn_patches(mesh)
    verts, norms, faces = [], [], []
    L = level
    weld = {}

    def get_index(p, n):
        key = (round(p[0], 10), round(p[1], 10), round(p[2], 10))
        if key not in weld:
            weld[key] = len(verts)
            verts.append(p)
            norms.append(n)
        return weld[key]

    for patch in patches:
        index = {}
        for a in range(L + 1):
            for bb in range(L + 1 - a):
                c = L - a - bb
                u, v, w = a / L, bb / L, c / L
                p, n = patch.evaluate(u, v, w)
                index[(a, bb, c)] = get_index(p, n)
        for a in range(L):
            for bb in range(L - a):
                i = index[(a, bb, L - a - bb)]
                j = index[(a + 1, bb, L - a - bb - 1)]
                k = index[(a, bb + 1, L - a - bb - 1)]
                faces.append((i, j, k))
                if a + bb < L - 1:
                    m = index[(a + 1, bb + 1, L - a - bb - 2)]
                    faces.append((j, m, k))
    return verts, faces, norms
