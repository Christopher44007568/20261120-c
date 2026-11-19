"""Catmull-Clark subdivision for arbitrary polygon meshes (pure Python).

Each level produces a quad mesh: one face point per face, one edge point per
edge, one updated position per original vertex.  Triangulated output is also
provided so it can be compared directly against PN-triangle refinements.
"""
from vec3 import add, scale, sub


def _build_topology(faces):
    edge_faces = {}
    edge_key = {}
    vert_faces = [[] for _ in range(1 + max(i for f in faces for i in f))]
    for fi, face in enumerate(faces):
        n = len(face)
        for a in range(n):
            e = (face[a], face[(a + 1) % n])
            key = tuple(sorted(e))
            edge_faces.setdefault(key, []).append(fi)
            edge_key[e] = key
            edge_key[(e[1], e[0])] = key
            vert_faces[face[a]].append(fi)
    return edge_faces, edge_key, vert_faces


def subdivide_once(vertices, faces):
    """One Catmull-Clark step. Returns (new_vertices, new_quad_faces)."""
    edge_faces, edge_key, vert_faces = _build_topology(faces)
    verts = list(vertices)

    face_point = []
    for face in faces:
        p = (0.0, 0.0, 0.0)
        for vi in face:
            p = add(p, verts[vi])
        face_point.append(scale(p, 1.0 / len(face)))

    edge_point = {}
    for key, flist in edge_faces.items():
        mid = scale(add(verts[key[0]], verts[key[1]]), 0.5)
        favg = (0.0, 0.0, 0.0)
        for fi in flist:
            favg = add(favg, face_point[fi])
        favg = scale(favg, 1.0 / len(flist))
        edge_point[key] = scale(add(mid, favg), 0.5)

    new_vertex = []
    for vi, pos in enumerate(verts):
        flist = vert_faces[vi]
        n = len(flist)
        f_avg = (0.0, 0.0, 0.0)
        e_set = set()
        for fi in flist:
            f_avg = add(f_avg, face_point[fi])
            face = faces[fi]
            for a, vj in enumerate(face):
                if vj == vi:
                    e_set.add(edge_key[(vi, face[(a + 1) % len(face)])])
        f_avg = scale(f_avg, 1.0 / n)
        e_avg = (0.0, 0.0, 0.0)
        for key in e_set:
            e_avg = add(e_avg, edge_point[key])
        e_avg = scale(e_avg, 1.0 / n)
        new_vertex.append(add(add(scale(f_avg, 1.0 / n),
                                  scale(e_avg, 2.0 / n)),
                              scale(pos, (n - 3.0) / n)))

    # Indices 0..n-1 keep the updated original vertices; new points are
    # appended afterwards so face indices stay valid.
    out_v = new_vertex
    fp_index = []
    for p in face_point:
        fp_index.append(len(out_v))
        out_v.append(p)
    ep_index = {}
    for key, p in edge_point.items():
        ep_index[key] = len(out_v)
        out_v.append(p)

    new_faces = []
    for fi, face in enumerate(faces):
        n = len(face)
        for a in range(n):
            v0, v1 = face[a], face[(a + 1) % n]
            e_prev = ep_index[edge_key[(face[(a - 1) % n], v0)]]
            e_next = ep_index[edge_key[(v0, v1)]]
            new_faces.append((v0, e_next, fp_index[fi], e_prev))
    return out_v, new_faces


def subdivide(vertices, faces, levels):
    v, f = list(vertices), list(faces)
    for _ in range(levels):
        v, f = subdivide_once(v, f)
    return v, f


def triangulate(vertices, quad_faces):
    """Split every quad along its (0, 2) diagonal."""
    tris = []
    for (a, b, c, d) in quad_faces:
        tris.append((a, b, c))
        tris.append((a, c, d))
    return vertices, tris


def compact(vertices, faces):
    """Drop vertices that are not referenced and remap face indices."""
    used = sorted({i for face in faces for i in face})
    remap = {old: new for new, old in enumerate(used)}
    new_v = [vertices[i] for i in used]
    new_f = [tuple(remap[i] for i in face) for face in faces]
    return new_v, new_f


def subdivide_tris(vertices, tri_faces, levels):
    v, q = subdivide(vertices, tri_faces, levels)
    v, q = compact(v, q)
    return triangulate(v, q)
