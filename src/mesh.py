"""Triangle mesh data structure, normal estimation and low-poly generators."""
from math import cos, pi, sin, sqrt

from vec3 import add, cross, normalize, scale, sub


class Mesh:
    def __init__(self, vertices, faces, name="mesh"):
        self.vertices = [tuple(v) for v in vertices]
        self.faces = [tuple(f) for f in faces]
        self.name = name

    def face_normal(self, fi):
        i, j, k = self.faces[fi]
        return normalize(
            cross(sub(self.vertices[j], self.vertices[i]),
                  sub(self.vertices[k], self.vertices[i]))
        )

    def vertex_normals(self):
        """Area-weighted average of adjacent face normals."""
        acc = [(0.0, 0.0, 0.0) for _ in self.vertices]
        for (i, j, k) in self.faces:
            n = cross(sub(self.vertices[j], self.vertices[i]),
                      sub(self.vertices[k], self.vertices[i]))
            acc[i] = add(acc[i], n)
            acc[j] = add(acc[j], n)
            acc[k] = add(acc[k], n)
        return [normalize(n) for n in acc]

    def __repr__(self):
        return f"Mesh({self.name}, V={len(self.vertices)}, F={len(self.faces)})"


def make_icosahedron(radius=1.0):
    """Regular icosahedron: classic low-poly sphere (12 verts, 20 tris)."""
    t = (1.0 + sqrt(5.0)) / 2.0
    base = [
        (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
        (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
        (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
    ]
    verts = [scale(normalize(v), radius) for v in base]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return Mesh(verts, faces, "icosahedron")


def make_torus(R=1.0, r=0.4, nu=10, nv=6):
    """Low-poly torus. Smooth reference surface is the analytic torus
    x=(R+r cos v) cos u, y=(R+r cos v) sin u, z=r sin v."""
    verts, faces = [], []
    for i in range(nu):
        u = 2.0 * pi * i / nu
        for j in range(nv):
            v = 2.0 * pi * j / nv
            verts.append(((R + r * cos(v)) * cos(u),
                          (R + r * cos(v)) * sin(u),
                          r * sin(v)))

    def idx(i, j):
        return (i % nu) * nv + (j % nv)

    for i in range(nu):
        for j in range(nv):
            a, b = idx(i, j), idx(i + 1, j)
            c, d = idx(i + 1, j + 1), idx(i, j + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    return Mesh(verts, faces, f"torus_{nu}x{nv}")


def torus_smooth_point(u, v, R=1.0, r=0.4):
    cu, su, cv, sv = cos(u), sin(u), cos(v), sin(v)
    return ((R + r * cv) * cu, (R + r * cv) * su, r * sv)


def torus_smooth_normal(u, v):
    cu, su, cv, sv = cos(u), sin(u), cos(v), sin(v)
    return normalize((cv * cu, cv * su, sv))


def torus_curvatures(u, v, R=1.0, r=0.4):
    """Analytic principal curvatures of a torus (with sign convention)."""
    cv = cos(v)
    k_meridional = 1.0 / r
    k_azimuthal = cv / (R + r * cv)
    return k_meridional, k_azimuthal
