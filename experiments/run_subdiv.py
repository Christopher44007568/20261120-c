"""PN-triangles vs Catmull-Clark on the draped cloth + sharp-edge tests."""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloth.mesh import ClothMesh, vertex_normals
from cloth.subdiv import (pn_subdivide, catmull_clark, _pn_control_points,
                          _pn_normal_control, pn_eval)
from cloth.metrics import (surface_error, normal_continuity,
                           normal_field_deviation, crack_gap,
                           dihedral_along_edges, interior_edges)

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "artifacts")


def weld(points, tris, tol=1e-9):
    """Weld coincident vertices; returns (points, tris, max_weld_gap)."""
    key = np.round(points / tol).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True,
                            return_inverse=True)
    # max gap between welded duplicates
    gap = 0.0
    order = np.argsort(inv)
    inv_s = inv[order]
    pts = points[order]
    start = 0
    while start < len(inv_s):
        end = start
        while end + 1 < len(inv_s) and inv_s[end + 1] == inv_s[start]:
            end += 1
        if end > start:
            cluster = pts[start:end + 1]
            d = np.linalg.norm(cluster - cluster[0], axis=1).max()
            gap = max(gap, float(d))
        start = end + 1
    return points[idx], inv[tris], gap


def coarse_grid(positions, nx, nz, stride=2):
    """Extract every `stride`-th vertex as a coarser regular grid."""
    ii = list(range(0, nx, stride))
    jj = list(range(0, nz, stride))
    idx = np.array([i * nz + j for i in ii for j in jj])
    cnx, cnz = len(ii), len(jj)
    pos = positions[idx]
    quads = []
    for a in range(cnx - 1):
        for b in range(cnz - 1):
            v = lambda x, y: x * cnz + y
            quads.append([v(a, b), v(a + 1, b), v(a + 1, b + 1), v(a, b + 1)])
    quads = np.array(quads)
    tris = []
    for q in quads:
        tris.append([q[0], q[1], q[2]])
        tris.append([q[0], q[2], q[3]])
    return pos, quads, np.array(tris), cnx, cnz


def pn_edge_crack(pos, normals, tris, m_samples=9):
    """Max gap between shared-edge curves of adjacent PN patches."""
    emap: dict[tuple, list[int]] = {}
    for fi, t in enumerate(tris):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            emap.setdefault((min(a, b), max(a, b)), []).append((fi, k))
    ts = np.linspace(0.0, 1.0, m_samples)
    worst = 0.0
    for (a, b), fl in emap.items():
        if len(fl) != 2:
            continue
        curves = []
        for fi, k in fl:
            t = tris[fi]
            # local vertices: k->a side, (k+1)%3->b side
            tri = [int(t[k]), int(t[(k + 1) % 3]), int(t[(k + 2) % 3])]
            p = pos[tri]
            n = normals[tri]
            cp = _pn_control_points(p, n)
            cn = _pn_normal_control(p, n)
            curve = []
            for tt in ts:
                # edge between local v0 (u=1) and v1 (v=1): (u,v,w)=(1-t,t,0)
                pt, _ = pn_eval(cp, cn, 1.0 - tt, tt, 0.0)
                curve.append(pt)
            curves.append(np.array(curve))
        # orient both curves a->b
        for c in curves:
            if np.linalg.norm(c[0] - pos[b]) < np.linalg.norm(c[0] - pos[a]):
                c[:] = c[::-1]
        worst = max(worst, crack_gap(curves[0], curves[1]))
    return worst


def pn_edge_normal_gap(pos, normals, tris):
    """Angle (deg) between adjacent patches' PN normals at edge midpoints."""
    emap: dict[tuple, list[int]] = {}
    for fi, t in enumerate(tris):
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            emap.setdefault((min(a, b), max(a, b)), []).append((fi, k))
    worst = 0.0
    for (a, b), fl in emap.items():
        if len(fl) != 2:
            continue
        ns = []
        for fi, k in fl:
            t = tris[fi]
            tri = [int(t[k]), int(t[(k + 1) % 3]), int(t[(k + 2) % 3])]
            cp = _pn_control_points(pos[tri], normals[tri])
            cn = _pn_normal_control(pos[tri], normals[tri])
            _, nm = pn_eval(cp, cn, 0.5, 0.5, 0.0)
            ns.append(nm)
        c = np.clip(np.dot(ns[0], ns[1]), -1.0, 1.0)
        worst = max(worst, float(np.degrees(np.arccos(c))))
    return worst


def cc_manifold_check(quads):
    """Every interior edge must have exactly 2 faces (no cracks/holes)."""
    emap: dict[tuple, int] = {}
    for q in quads:
        for k in range(4):
            a, b = int(q[k]), int(q[(k + 1) % 4])
            key = (min(a, b), max(a, b))
            emap[key] = emap.get(key, 0) + 1
    counts = np.array(list(emap.values()))
    return {"boundary_edges": int(np.sum(counts == 1)),
            "interior_edges": int(np.sum(counts == 2)),
            "nonmanifold_edges": int(np.sum(counts > 2))}


def folded_sheet(n=9, angle_deg=90.0):
    """Two n x n grids hinged along the x-axis at the given dihedral."""
    s = np.linspace(0, 1, n)
    ang = np.radians(angle_deg)
    # side 1 in the xy-plane (z=0), side 2 rotated by `ang` around x-axis
    p1 = np.stack(np.meshgrid(s, s, indexing="ij"), axis=-1).reshape(-1, 2)
    side1 = np.column_stack([p1[:, 0], p1[:, 1], np.zeros(len(p1))])
    p2 = np.stack(np.meshgrid(s, s, indexing="ij"), axis=-1).reshape(-1, 2)
    ca, sa = np.cos(ang), np.sin(ang)
    # side2 rotated by `ang` around the x-axis hinge: (x, y*ca, y*sa)
    side2 = np.column_stack([p2[:, 0], p2[:, 1] * ca, p2[:, 1] * sa])
    # share hinge vertices (y=0,z=0): side2 row j=0 equals side1 row j=0
    pos = [p for p in side1]
    vid2 = {}
    for i in range(n):
        for j in range(n):
            if j == 0:
                vid2[(i, j)] = i * n + 0  # hinge shared with side1
            else:
                vid2[(i, j)] = len(pos)
                pos.append(side2[i * n + j])
    pos = np.array(pos)
    quads = []
    for i in range(n - 1):
        for j in range(n - 1):
            quads.append([i * n + j, (i + 1) * n + j,
                          (i + 1) * n + j + 1, i * n + j + 1])
            # side2 wound so face normals stay on the same side of the sheet
            quads.append([vid2[(i, j)], vid2[(i, j + 1)],
                          vid2[(i + 1, j + 1)], vid2[(i + 1, j)]])
    hinge_edges = {(i * n, (i + 1) * n) for i in range(n - 1)}
    return pos, np.array(quads), hinge_edges


def quads_to_tris(quads):
    tris = []
    for q in quads:
        tris.append([q[0], q[1], q[2]])
        tris.append([q[0], q[2], q[3]])
    return np.array(tris)


def drape_comparison():
    d = np.load(os.path.join(ART, "drape_final.npz"))
    pos, nx, nz = d["positions"], int(d["nx"]), int(d["nz"])
    ref = pos
    cpos, cquads, ctris, cnx, cnz = coarse_grid(pos, nx, nz, stride=2)
    out = {}

    # PN-triangles on the coarse mesh
    cnrm = vertex_normals(cpos, ctris)
    m = 8
    ppts, pnrm, ptris, _ = pn_subdivide(cpos, cnrm, ctris, m)
    wpts, wtris, weld_gap = weld(ppts, ptris)
    key = np.round(ppts / 1e-9).astype(np.int64)
    _, widx = np.unique(key, axis=0, return_index=True)
    out["pn"] = {
        "n_points": len(ppts),
        "error": surface_error(ppts, ref),
        "crack_gap": pn_edge_crack(cpos, cnrm, ctris),
        "weld_gap": weld_gap,
        "edge_normal_gap_deg": pn_edge_normal_gap(cpos, cnrm, ctris),
        "normal_continuity": normal_continuity(wpts, wtris),
        "normal_field_dev": normal_field_deviation(wpts, wtris, pnrm[widx]),
    }

    # Catmull-Clark on the coarse mesh
    qpos, qquads = catmull_clark(cpos, cquads, levels=3)
    qtris = quads_to_tris(qquads)
    out["cc"] = {
        "n_points": len(qpos),
        "error": surface_error(qpos, ref),
        "manifold": cc_manifold_check(qquads),
        "normal_continuity": normal_continuity(qpos, qtris),
    }
    out["reference_normals"] = normal_continuity(
        ref, d["triangles"])
    return out, (cpos, cquads, ctris), (ppts, pnrm, ptris), (qpos, qquads)


def sharp_edge_test():
    pos, quads, hinge = folded_sheet(n=9, angle_deg=90.0)
    tris = quads_to_tris(quads)
    res = {}
    # CC smooth vs crease
    for name, sharp in [("cc_smooth", None), ("cc_crease", hinge)]:
        p, q = catmull_clark(pos, quads, levels=3, sharp_edges=sharp)
        t = quads_to_tris(q)
        emap = interior_edges(t)
        from cloth.metrics import face_normals
        f_n = face_normals(p, t)
        on_hinge, near_dh = [], []
        for e, fl in emap.items():
            if len(fl) != 2:
                continue
            a, b = e
            pa, pb = p[a], p[b]
            c = np.clip(np.dot(f_n[fl[0]], f_n[fl[1]]), -1.0, 1.0)
            ang = float(np.degrees(np.arccos(c)))
            if (abs(pa[1]) < 1e-12 and abs(pa[2]) < 1e-12
                    and abs(pb[1]) < 1e-12 and abs(pb[2]) < 1e-12):
                on_hinge.append(ang)
            mid = 0.5 * (p[a] + p[b])
            if np.hypot(mid[1], mid[2]) < 0.09:  # near the hinge line
                near_dh.append(ang)
        near_dh = np.array(near_dh)
        res[name] = {
            "on_hinge_edges": len(on_hinge),
            "on_hinge_dihedral_deg": float(np.mean(on_hinge)) if on_hinge else None,
            "fold_angle_max_deg": float(near_dh.max()),
        }
    # PN with smooth averaged normals vs split (duplicated hinge) normals
    vn_smooth = vertex_normals(pos, tris)
    n_side1 = np.array([0.0, 0.0, 1.0])
    n_side2 = np.array([0.0, -1.0, 0.0])  # 90-degree fold about x-axis
    hinge_verts = sorted({v for e in hinge for v in e})
    # Duplicated mesh: side-2 triangles reference hinge copies so each side
    # keeps its own (crease) normal at the hinge.
    pos_d = [p for p in pos]
    copy_of = {}
    for v in hinge_verts:
        copy_of[v] = len(pos_d)
        pos_d.append(pos[v])
    pos_d = np.array(pos_d)
    from cloth.metrics import face_normals
    f_n = face_normals(pos, tris)
    is_side1 = np.abs(f_n[:, 2]) > np.abs(f_n[:, 1])
    tris_d = tris.copy()
    for fi in range(len(tris_d)):
        if not is_side1[fi]:
            for k in range(3):
                if tris_d[fi, k] in copy_of:
                    tris_d[fi, k] = copy_of[tris_d[fi, k]]
    vn_split = np.zeros_like(pos_d)
    side_of_vert = {}
    for fi in range(len(tris_d)):
        n = n_side1 if is_side1[fi] else n_side2
        for k in range(3):
            v = tris_d[fi, k]
            side_of_vert[v] = n
    for v, n in side_of_vert.items():
        vn_split[v] = n
    res["pn"] = {}
    for name, p_in, t_in, vn in [("smooth", pos, tris, vn_smooth),
                                 ("split", pos_d, tris_d, vn_split)]:
        ppts, pnrm, ptris, face_of = pn_subdivide(p_in, vn, t_in, 6)
        near = np.linalg.norm(ppts[:, [1, 2]], axis=1) < 0.15
        side_pt = is_side1[face_of]

        def fit_normal(P):
            P = P - P.mean(axis=0)
            _, _, vt = np.linalg.svd(P, full_matrices=False)
            return vt[-1]

        n1 = fit_normal(ppts[near & side_pt])
        n2 = fit_normal(ppts[near & ~side_pt])
        c = np.clip(abs(np.dot(n1, n2)), -1.0, 1.0)
        dihedral = float(np.degrees(np.arccos(c)))
        # planarity: max distance of subdivided points from their side plane
        dev1 = np.abs((ppts[side_pt] - ppts[side_pt].mean(0)) @ n1).max()
        dev2 = np.abs((ppts[~side_pt] - ppts[~side_pt].mean(0)) @ n2).max()
        res["pn"][name] = {"dihedral_deg": dihedral,
                           "max_planar_dev": float(max(dev1, dev2))}
    return res


def render_subdiv(cpos, ctris, pn, cc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cloth.render import shaded_surface
    from cloth.pbd import RoundTable
    d = np.load(os.path.join(ART, "drape_final.npz"))
    table = RoundTable(float(d["table_r"]), float(d["table_h"]))
    fig = plt.figure(figsize=(16, 5))
    ax = fig.add_subplot(131, projection="3d")
    shaded_surface(ax, cpos, ctris, table=table, ground=False,
                   title="coarse control mesh (21x21)")
    ax = fig.add_subplot(132, projection="3d")
    shaded_surface(ax, pn[0], pn[2], table=table, ground=False,
                   title="PN-triangles (m=8)")
    ax = fig.add_subplot(133, projection="3d")
    qtris = quads_to_tris(cc[1])
    shaded_surface(ax, cc[0], qtris, table=table, ground=False,
                   title="Catmull-Clark (3 levels)")
    fig.savefig(os.path.join(ART, "subdiv_render.png"), dpi=140)
    plt.close(fig)


def render_wrinkles_smooth():
    """Smooth PN-subdivided render of the full draped cloth (wrinkles)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cloth.render import shaded_surface
    from cloth.pbd import RoundTable
    d = np.load(os.path.join(ART, "drape_final.npz"))
    pos, tris = d["positions"], d["triangles"]
    table = RoundTable(float(d["table_r"]), float(d["table_h"]))
    vn = vertex_normals(pos, tris)
    ppts, pnrm, ptris, _ = pn_subdivide(pos, vn, tris, 4)
    fig = plt.figure(figsize=(12, 5))
    for i, (elev, azim) in enumerate([(18, -60), (26, 105)]):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        shaded_surface(ax, ppts, ptris, table=table, ground=True,
                       elev=elev, azim=azim,
                       title="draped cloth, PN-smoothed render")
    fig.savefig(os.path.join(ART, "drape_wrinkles_smooth.png"), dpi=140)
    plt.close(fig)


def main():
    os.makedirs(ART, exist_ok=True)
    out, coarse, pn, cc = drape_comparison()
    sharp = sharp_edge_test()
    summary = {"drape": out, "sharp_edge": sharp}
    import json
    with open(os.path.join(ART, "subdiv_metrics.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    print(json.dumps(summary, indent=2, default=float))
    render_subdiv(coarse[0], coarse[2], pn, cc)
    render_wrinkles_smooth()


if __name__ == "__main__":
    main()
