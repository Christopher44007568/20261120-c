"""Naive dual contouring with QEF minimisation (Ju et al. 2002)."""
import numpy as np
from scipy.optimize import lsq_linear

from fields import gradient

# 12 edges of a cube as pairs of corner offsets.
_CORNERS = np.array(
    [[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)], dtype=int
)
_EDGES = [
    (a, b)
    for a in range(8)
    for b in range(a + 1, 8)
    if np.sum(np.abs(_CORNERS[a] - _CORNERS[b])) == 1
]


def _qef(points, normals, lo, hi):
    """Solve the quadratic error function constrained to the cell [lo, hi]."""
    A = normals
    b = np.einsum("ij,ij->i", normals, points)
    AtA = A.T @ A + 1e-6 * np.eye(3)
    Atb = A.T @ b + 1e-6 * points.mean(axis=0)
    try:
        x = np.linalg.solve(AtA, Atb)
    except np.linalg.LinAlgError:
        x = points.mean(axis=0)
    if np.all(x >= lo) and np.all(x <= hi):
        return x
    # Unconstrained minimiser left the cell: solve the box-constrained
    # least-squares problem instead of naively clamping each coordinate.
    mass = points.mean(axis=0)
    A_aug = np.vstack([A, 1e-3 * np.eye(3)])
    b_aug = np.concatenate([b, 1e-3 * mass])
    res = lsq_linear(A_aug, b_aug, bounds=(lo, hi), tol=1e-12)
    return res.x


def dual_contour(f, bounds=(-1.3, 1.3), n=64):
    """Polygonise the zero level set of f on an n^3 cell grid.

    Returns (verts, faces, active_cells).
    """
    lo, hi = bounds
    axis = np.linspace(lo, hi, n + 1)
    gx, gy, gz = np.meshgrid(axis, axis, axis, indexing="ij")
    nodes = np.stack([gx, gy, gz], axis=-1)
    vals = f(nodes.reshape(-1, 3)).reshape(n + 1, n + 1, n + 1)
    inside = vals < 0.0
    h = (hi - lo) / n

    cell_vert = {}
    verts = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                cube = inside[i : i + 2, j : j + 2, k : k + 2].reshape(-1)
                if cube.all() or not cube.any():
                    continue
                cvals = vals[i : i + 2, j : j + 2, k : k + 2].reshape(-1)
                pts, nrms = [], []
                for a, b in _EDGES:
                    if cube[a] == cube[b]:
                        continue
                    ca, cb = _CORNERS[a], _CORNERS[b]
                    pa = nodes[i + ca[0], j + ca[1], k + ca[2]]
                    pb = nodes[i + cb[0], j + cb[1], k + cb[2]]
                    va, vb = cvals[a], cvals[b]
                    t = va / (va - vb)
                    p = pa + t * (pb - pa)
                    nrm = gradient(f, p)
                    norm = np.linalg.norm(nrm)
                    if norm < 1e-12:
                        continue
                    pts.append(p)
                    nrms.append(nrm / norm)
                if not pts:
                    continue
                clo = nodes[i, j, k]
                chi = clo + h
                v = _qef(np.array(pts), np.array(nrms), clo, chi)
                cell_vert[(i, j, k)] = len(verts)
                verts.append(v)

    faces = _emit_quads(inside, cell_vert, n)
    verts = np.array(verts).reshape(-1, 3)
    faces = _fix_orientation(verts, faces, f)
    return verts, faces, len(cell_vert)


def _emit_quads(inside, cell_vert, n):
    """One quad per sign-changing grid edge shared by 4 active cells."""
    faces = []
    # For an edge along `axis` starting at node (i,j,k), the 4 adjacent
    # cells are offset by (0/-1) in the other two axes.
    for axis in range(3):
        others = [a for a in range(3) if a != axis]
        offsets = [(0, 0), (-1, 0), (-1, -1), (0, -1)]
        idx = np.indices((n + 1,) * 3).reshape(3, -1).T
        for node in idx:
            i, j, k = node
            if node[axis] >= n:
                continue
            a_in = inside[i, j, k]
            b = list(node)
            b[axis] += 1
            b_in = inside[tuple(b)]
            if a_in == b_in:
                continue
            quad = []
            for d0, d1 in offsets:
                c = list(node)
                c[others[0]] += d0
                c[others[1]] += d1
                if any(c[a] < 0 or c[a] >= n for a in range(3)):
                    quad = None
                    break
                vid = cell_vert.get(tuple(c))
                if vid is None:
                    quad = None
                    break
                quad.append(vid)
            if quad is None:
                continue
            if not a_in:
                quad = quad[::-1]
            faces.append((quad[0], quad[1], quad[2]))
            faces.append((quad[0], quad[2], quad[3]))
    return faces


def _fix_orientation(verts, faces, f):
    """Ensure triangle normals align with the outward field gradient."""
    out = []
    for tri in faces:
        p0, p1, p2 = verts[list(tri)]
        nrm = np.cross(p1 - p0, p2 - p0)
        g = gradient(f, (p0 + p1 + p2) / 3.0)
        if np.dot(nrm, g) < 0:
            tri = (tri[0], tri[2], tri[1])
        out.append(tri)
    return np.array(out, dtype=np.int64)
