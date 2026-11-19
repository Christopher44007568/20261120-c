"""Triangle mesh with boundary / crease topology queries."""
import math


class Mesh:
    def __init__(self, vertices, faces, crease_edges=None):
        self.vertices = [tuple(map(float, v)) for v in vertices]
        self.faces = [tuple(f) for f in faces]
        self.crease_edges = set()
        for e in (crease_edges or []):
            self.crease_edges.add(frozenset(e))
        self._build_topology()

    def _build_topology(self):
        self.edge_faces = {}
        self.neighbors = {i: set() for i in range(len(self.vertices))}
        for f in self.faces:
            for k in range(3):
                a, b = f[k], f[(k + 1) % 3]
                self.edge_faces.setdefault(frozenset((a, b)), []).append(f)
                self.neighbors[a].add(b)
                self.neighbors[b].add(a)
        self.boundary_edges = {e for e, fs in self.edge_faces.items() if len(fs) == 1}
        self.boundary_vertices = set()
        for e in self.boundary_edges:
            self.boundary_vertices.update(e)
        self.crease_vertices = set()
        for e in self.crease_edges:
            self.crease_vertices.update(e)

    def is_sharp_edge(self, a, b):
        e = frozenset((a, b))
        return e in self.crease_edges or e in self.boundary_edges

    def sharp_neighbors(self, v):
        """Neighbors connected to v by a boundary or crease edge."""
        return [u for u in self.neighbors[v] if self.is_sharp_edge(v, u)]

    def opposite(self, a, b, face):
        for c in face:
            if c != a and c != b:
                return c
        raise ValueError("edge not in face")


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vnorm(a):
    return math.sqrt(vdot(a, a))


def vdist(a, b):
    return vnorm(vsub(a, b))
