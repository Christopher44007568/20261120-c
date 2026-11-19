"""Surface subdivision: PN-triangles and Catmull-Clark (with creases)."""
from __future__ import annotations

import numpy as np


def _pn_control_points(p, n):
    """Cubic Bezier control net for one triangle (Vlachos et al. 2001)."""
    p1, p2, p3 = p
    n1, n2, n3 = n

    def w(a, b, na):
        return float(np.dot(b - a, na))

    b300, b030, b003 = p1, p2, p3
    b210 = (2 * p1 + p2 - w(p1, p2, n1) * n1) / 3.0
    b120 = (2 * p2 + p1 - w(p2, p1, n2) * n2) / 3.0
    b021 = (2 * p2 + p3 - w(p2, p3, n2) * n2) / 3.0
    b012 = (2 * p3 + p2 - w(p3, p2, n3) * n3) / 3.0
    b102 = (2 * p3 + p1 - w(p3, p1, n3) * n3) / 3.0
    b201 = (2 * p1 + p3 - w(p1, p3, n1) * n1) / 3.0
    e = (b210 + b120 + b021 + b012 + b102 + b201) / 6.0
    v = (p1 + p2 + p3) / 3.0
    b111 = e + (e - v) / 2.0
    return dict(b300=b300, b030=b030, b003=b003, b210=b210, b120=b120,
                b021=b021, b012=b012, b102=b102, b201=b201, b111=b111)


def _pn_normal_control(p, n):
    p1, p2, p3 = p
    n1, n2, n3 = n

    def mid(na, nb, pa, pb):
        d = pb - pa
        v = 2.0 * float(np.dot(d, na + nb)) / max(float(np.dot(d, d)), 1e-30)
        h = na + nb - v * d
        ln = np.linalg.norm(h)
        if ln < 1e-12:
            s = na + nb
            return s / max(np.linalg.norm(s), 1e-12)
        return h / ln

    return dict(n200=n1, n020=n2, n002=n3,
                n110=mid(n1, n2, p1, p2),
                n011=mid(n2, n3, p2, p3),
                n101=mid(n3, n1, p3, p1))


def pn_eval(cp, cn, u, v, w):
    """Evaluate PN position and normal at barycentric (u, v, w)."""
    b = cp
    pt = (b["b300"] * u**3 + b["b030"] * v**3 + b["b003"] * w**3
          + 3 * b["b210"] * u * u * v + 3 * b["b120"] * u * v * v
          + 3 * b["b021"] * v * v * w + 3 * b["b012"] * v * w * w
          + 3 * b["b102"] * w * w * u + 3 * b["b201"] * w * u * u
          + 6 * b["b111"] * u * v * w)
    nm = (cn["n200"] * u * u + cn["n020"] * v * v + cn["n002"] * w * w
          + 2 * (cn["n110"] * u * v + cn["n011"] * v * w + cn["n101"] * w * u))
    ln = np.linalg.norm(nm)
    return pt, (nm / ln if ln > 1e-12 else nm)


def pn_subdivide(positions, normals, triangles, m):
    """Subdivide every triangle into an m-segment PN patch grid.

    Returns (points, normals, tris, face_of_point). Points of adjacent
    faces are not welded; edge coincidence is verified separately.
    """
    pts, nms, tris, face_of = [], [], [], []
    for f, tri in enumerate(triangles):
        p = positions[tri]
        n = normals[tri]
        cp = _pn_control_points(p, n)
        cn = _pn_normal_control(p, n)
        index = {}
        for i in range(m + 1):
            for j in range(m + 1 - i):
                u, v = i / m, j / m
                pt, nm = pn_eval(cp, cn, u, v, 1.0 - u - v)
                index[(i, j)] = len(pts)
                pts.append(pt)
                nms.append(nm)
                face_of.append(f)
        for i in range(m):
            for j in range(m - i):
                a = index[(i, j)]
                b = index[(i + 1, j)]
                c = index[(i, j + 1)]
                tris.append([a, b, c])
                if i + j + 2 <= m:
                    d = index[(i + 1, j + 1)]
                    tris.append([b, d, c])
    return (np.array(pts), np.array(nms), np.array(tris, dtype=np.int64),
            np.array(face_of, dtype=np.int64))


def catmull_clark(positions, quads, levels, sharp_edges=None):
    """Catmull-Clark subdivision of a quad mesh.

    sharp_edges: set of (i, j) index pairs treated as infinitely sharp
    creases. Boundary edges are always treated as creases.
    Returns (positions, quads) after `levels` refinement steps.
    """
    sharp = set()
    if sharp_edges:
        for a, b in sharp_edges:
            sharp.add((min(a, b), max(a, b)))
    pos = [np.asarray(p, dtype=float) for p in positions]
    faces = [list(q) for q in quads]
    for _ in range(levels):
        edge_faces: dict[tuple, list[int]] = {}
        for fi, q in enumerate(faces):
            for k in range(4):
                a, b = q[k], q[(k + 1) % 4]
                edge_faces.setdefault((min(a, b), max(a, b)), []).append(fi)
        face_pts = []
        for q in faces:
            face_pts.append(sum(pos[v] for v in q) / 4.0)
        v_faces: dict[int, list[int]] = {}
        v_edges: dict[int, list[tuple]] = {}
        for fi, q in enumerate(faces):
            for v in q:
                v_faces.setdefault(v, []).append(fi)
        for e in edge_faces:
            for v in e:
                v_edges.setdefault(v, []).append(e)
        # Updated vertices first: index v stays aligned with old vertex id.
        new_pos = []
        for v in range(len(pos)):
            crease = [e for e in v_edges[v]
                      if len(edge_faces[e]) == 1 or e in sharp]
            if len(crease) == 2:
                others = [e[0] if e[1] == v else e[1] for e in crease]
                nv = (6.0 * pos[v] + pos[others[0]] + pos[others[1]]) / 8.0
            elif len(crease) > 2:
                nv = pos[v]
            else:
                fl = v_faces[v]
                n = len(fl)
                f_avg = sum(face_pts[f] for f in fl) / n
                mids = []
                for e in v_edges[v]:
                    a, b = e
                    mids.append((pos[a] + pos[b]) / 2.0)
                r_avg = sum(mids) / len(mids)
                nv = (f_avg + 2.0 * r_avg + (n - 3.0) * pos[v]) / n
            new_pos.append(nv)
        edge_pt_idx = {}
        for e, fl in edge_faces.items():
            a, b = e
            if len(fl) == 2 and e not in sharp:
                ep = (pos[a] + pos[b] + face_pts[fl[0]] + face_pts[fl[1]]) / 4.0
            else:  # boundary or sharp crease edge
                ep = (pos[a] + pos[b]) / 2.0
            edge_pt_idx[e] = len(new_pos)
            new_pos.append(ep)
        # Propagate sharpness: each sharp edge splits into two sharp child
        # edges (endpoint -> edge point), so creases survive further levels.
        new_sharp = set()
        for e in sharp:
            if e in edge_pt_idx:
                a, b = e
                m = edge_pt_idx[e]
                new_sharp.add((min(a, m), max(a, m)))
                new_sharp.add((min(m, b), max(m, b)))
        face_base = len(new_pos)
        new_pos.extend(face_pts)
        new_faces = []
        for fi, q in enumerate(faces):
            fc = face_base + fi
            for k in range(4):
                v = q[k]
                e_prev = (min(q[k - 1], v), max(q[k - 1], v))
                e_next = (min(v, q[(k + 1) % 4]), max(v, q[(k + 1) % 4]))
                new_faces.append([v, edge_pt_idx[e_next],
                                  fc, edge_pt_idx[e_prev]])
        pos = new_pos
        faces = new_faces
        sharp = new_sharp
    return np.array(pos), np.array(faces, dtype=np.int64)
