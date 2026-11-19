"""Test meshes: planar grid, Gaussian bump, and a 90-degree crease fold."""
import math
from .mesh import Mesh, vsub, vcross, vdot, vnorm


def grid_mesh(n=4, height_fn=None):
    """Triangulated (n+1)x(n+1) open grid on the unit square."""
    verts, faces = [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x, y = i / n, j / n
            z = height_fn(x, y) if height_fn else 0.0
            verts.append((x, y, z))
    def vid(i, j):
        return j * (n + 1) + i
    for j in range(n):
        for i in range(n):
            a, b = vid(i, j), vid(i + 1, j)
            c, d = vid(i, j + 1), vid(i + 1, j + 1)
            faces.append((a, b, d))
            faces.append((a, d, c))
    return Mesh(verts, faces)


def bump_mesh(n=4, amp=0.25, sigma=0.25):
    def bump(x, y):
        r2 = (x - 0.5) ** 2 + (y - 0.5) ** 2
        return amp * math.exp(-r2 / (2.0 * sigma * sigma))
    return grid_mesh(n, bump)


def fold_mesh(n=4, angle_deg=90.0):
    """Two planar strips joined along the y-axis at a dihedral angle."""
    theta = math.radians(angle_deg)
    verts, faces = [], []
    for j in range(n + 1):
        for i in range(n + 1):
            verts.append((-1.0 + i / n, j / n, 0.0))
    def lid(i, j):
        return j * (n + 1) + i
    base = len(verts)
    for j in range(n + 1):
        for i in range(1, n + 1):
            x = (i / n) * math.cos(theta)
            z = (i / n) * math.sin(theta)
            verts.append((x, j / n, z))
    def rid(i, j):
        return base + j * n + (i - 1)
    for j in range(n):
        for i in range(n):
            a, b = lid(i, j), lid(i + 1, j)
            c, d = lid(i, j + 1), lid(i + 1, j + 1)
            faces.append((a, b, d))
            faces.append((a, d, c))
    for j in range(n):
        for i in range(n):
            a = lid(n, j) if i == 0 else rid(i, j)
            b = rid(i + 1, j)
            c = lid(n, j + 1) if i == 0 else rid(i, j + 1)
            d = rid(i + 1, j + 1)
            faces.append((a, b, d))
            faces.append((a, d, c))
    crease = [(lid(n, j), lid(n, j + 1)) for j in range(n)]
    return Mesh(verts, faces, crease_edges=crease), crease


def dihedral_at_crease(mesh, crease):
    """Mean dihedral angle (degrees) across the given crease edges."""
    angles = []
    for (a, b) in crease:
        faces = mesh.edge_faces.get(frozenset((a, b)), [])
        if len(faces) != 2:
            continue
        c = mesh.opposite(a, b, faces[0])
        d = mesh.opposite(a, b, faces[1])
        pa, pb = mesh.vertices[a], mesh.vertices[b]
        pc, pd = mesh.vertices[c], mesh.vertices[d]
        e = vsub(pb, pa)
        n1 = vcross(e, vsub(pc, pa))
        n2 = vcross(e, vsub(pd, pa))
        cosang = vdot(n1, n2) / (vnorm(n1) * vnorm(n2))
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosang)))))
    return sum(angles) / len(angles) if angles else float("nan")
