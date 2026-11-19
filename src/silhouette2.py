"""View-contour extraction by interpolating n.view = 0 across mesh edges.

Every contour crossing is stored per edge with the two incident faces; inside
each face the two/three crossings are connected.  Face adjacency then walks
the segments into closed contour loops without angular sorting, so the
polylines are valid for both flat low-poly and refined meshes.
"""
from math import atan2, pi, sqrt

from vec3 import cross, dot, lerp, normalize, sub as vsub


def _contour_loops(vertices, faces, normals, view):
    # Tiny deterministic epsilon avoids exact-zero degeneracies on symmetric
    # meshes while being far below any real signal.
    eps = 1e-9
    vals = [dot(normalize(n), view) + eps for n in normals]
    edge_faces = {}
    face_edges = [[] for _ in faces]
    for fi, (a, b, c) in enumerate(faces):
        for e in ((a, b), (b, c), (c, a)):
            key = tuple(sorted(e))
            edge_faces.setdefault(key, []).append(fi)
            face_edges[fi].append(key)

    crossing = {}
    for key in edge_faces:
        i, j = key
        if vals[i] * vals[j] < 0.0:
            t = vals[i] / (vals[i] - vals[j])
            crossing[key] = lerp(vertices[i], vertices[j], t)

    # Each face straddling the contour has exactly two crossing edges;
    # connect them into a segment.
    face_seg = {}
    for fi, keys in enumerate(face_edges):
        hits = [k for k in keys if k in crossing]
        if len(hits) == 2:
            face_seg[fi] = (hits[0], hits[1])

    # Walk segments across shared faces via edge -> faces adjacency.
    edge_seg_faces = {}
    for fi, (e0, e1) in face_seg.items():
        edge_seg_faces.setdefault(e0, []).append(fi)
        edge_seg_faces.setdefault(e1, []).append(fi)

    unused = set(face_seg)
    loops = []
    while unused:
        start_fi = unused.pop()
        start_edge = face_seg[start_fi][0]
        loop_pts = []
        cur_fi, enter_edge = start_fi, start_edge
        while True:
            e0, e1 = face_seg[cur_fi]
            exit_edge = e1 if enter_edge == e0 else e0
            loop_pts.append(crossing[enter_edge])
            nbrs = [f for f in edge_seg_faces[exit_edge] if f != cur_fi]
            if not nbrs:
                break
            cur_fi = nbrs[0]
            enter_edge = exit_edge
            if cur_fi == start_fi:
                break
            unused.discard(cur_fi)
        if len(loop_pts) >= 3:
            loops.append(loop_pts)
    return loops


def _turning(points):
    n = len(points)
    turns = []
    for i in range(n):
        p0, p1 = points[i - 1], points[i]
        p2 = points[(i + 1) % n]
        a0 = atan2(p1[1] - p0[1], p1[0] - p0[0])
        a1 = atan2(p2[1] - p1[1], p2[0] - p1[0])
        turns.append(abs((a1 - a0 + pi) % (2 * pi) - pi))
    return turns


def geometric_fallback(vertices, faces, view=(0.0, 0.0, 1.0)):
    """For flat shading where n.view never crosses zero: take edges where
    adjacent face normals straddle the view plane (classic silhouette)."""
    from vec3 import cross, sub as vsub
    face_n = []
    for (a, b, c) in faces:
        face_n.append(normalize(cross(vsub(vertices[b], vertices[a]),
                                      vsub(vertices[c], vertices[a]))))
    edge_table = {}
    for fi, (a, b, c) in enumerate(faces):
        for e in ((a, b), (b, c), (c, a)):
            edge_table.setdefault(tuple(sorted(e)), []).append(fi)
    pts = []
    seen = set()
    for key, flist in edge_table.items():
        if len(flist) != 2:
            continue
        d0, d1 = dot(face_n[flist[0]], view), dot(face_n[flist[1]], view)
        if d0 * d1 <= 0.0:
            for k in key:
                if k not in seen:
                    seen.add(k)
                    pts.append(vertices[k])
    return pts


def contour_report(vertices, faces, normals, ref_radius=None):
    view = (0.0, 0.0, 1.0)
    loops = _contour_loops(vertices, faces, normals, view)
    pts = [p for loop in loops for p in loop]
    method = "n.view zero-crossing"
    if len(pts) < 3:
        pts = sorted(geometric_fallback(vertices, faces, view),
                     key=lambda p: atan2(p[1], p[0]))
        method = "face-normal silhouette"
    if len(pts) < 3:
        return None
    turns = _turning(pts)
    max_turn, mean_turn = max(turns), sum(turns) / len(turns)
    rep = {
        "contour_points": len(pts),
        "contour_loops": len(loops),
        "method": method,
        "max_turn_deg": max_turn * 180.0 / pi,
        "mean_turn_deg": mean_turn * 180.0 / pi,
    }
    if ref_radius is not None:
        dev = [abs(sqrt(p[0] ** 2 + p[1] ** 2) - ref_radius) for p in pts]
        rep["radial_rms"] = sqrt(sum(d * d for d in dev) / len(dev))
        rep["radial_max"] = max(dev)
    return rep
