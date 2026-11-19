"""Approximation error of PN-triangle and Catmull-Clark refinements against
the analytic torus ground truth, stratified by local curvature variation."""
from math import acos, cos, pi, sin

from vec3 import dot, length, normalize, sub
from mesh import (torus_curvatures, torus_smooth_normal,
                  torus_smooth_point)
from pn_triangles import tessellate as pn_tessellate
from catmull_clark import subdivide_tris


def _nearest_torus_params(point, R, r, iters=12):
    """Project a point onto the analytic torus via Gauss-Newton on (u, v)."""
    # Coarse global search first: avoids local minima inside the torus hole.
    best = None
    nu, nv = 24, 12
    for iu in range(nu):
        u0 = 2.0 * pi * iu / nu
        for iv in range(nv):
            v0 = 2.0 * pi * iv / nv - pi
            q = torus_smooth_point(u0, v0, R, r)
            d = length(sub(point, q))
            if best is None or d < best[0]:
                best = (d, u0, v0)
    _, u, v = best
    for _ in range(iters):
        cu, su, cv, sv = cos(u), sin(u), cos(v), sin(v)
        q = torus_smooth_point(u, v, R, r)
        rvec = sub(point, q)
        # Jacobian columns: d/du, d/dv
        du = (-(R + r * cv) * su, (R + r * cv) * cu, 0.0)
        dv = (-r * sv * cu, -r * sv * su, r * cv)
        auu, avv = dot(du, du), dot(dv, dv)
        u += dot(rvec, du) / auu
        v += dot(rvec, dv) / avv
        v = max(-pi, min(pi, v))
    return u, v


def curvature_variation(u, v, R, r):
    """|d(k_azimuthal)/dv|: high where curvature changes fastest
    (outer/inner equator of the torus)."""
    cv, sv = cos(v), sin(v)
    denom = (R + r * cv) ** 2
    return abs(r * sv * R / denom)


def sample_errors(vertices, normals, R, r):
    """For every refined vertex, project to the torus and measure errors."""
    rows = []
    for idx, p in enumerate(vertices):
        u, v = _nearest_torus_params(p, R, r)
        q = torus_smooth_point(u, v, R, r)
        n_ref = torus_smooth_normal(u, v)
        pos_err = length(sub(p, q))
        cosang = max(-1.0, min(1.0, dot(normalize(normals[idx]), n_ref)))
        nrm_err = acos(cosang)
        k1, k2 = torus_curvatures(u, v, R, r)
        dk = curvature_variation(u, v, R, r)
        rows.append((pos_err, nrm_err, dk, abs(k1 - k2), v))
    return rows


def _stats(values):
    if not values:
        return (0.0, 0.0, 0.0)
    s = sorted(values)
    mean = sum(s) / len(s)
    rms = (sum(x * x for x in s) / len(s)) ** 0.5
    return (max(s), mean, rms)


def stratified_report(rows, n_bins=3):
    """Split samples into bins of curvature variation and summarize."""
    dks = sorted(r[2] for r in rows)
    cuts = [dks[int(len(dks) * q / n_bins)] for q in range(1, n_bins)]
    bins = [[] for _ in range(n_bins)]
    for row in rows:
        b = 0
        while b < len(cuts) and row[2] > cuts[b]:
            b += 1
        bins[min(b, n_bins - 1)].append(row)
    labels = ("low |dk|", "mid |dk|", "high |dk|")
    report = []
    for label, bucket in zip(labels, bins):
        pos = _stats([r[0] for r in bucket])
        nrm = _stats([r[1] for r in bucket])
        report.append({
            "bin": label,
            "samples": len(bucket),
            "pos_max": pos[0], "pos_rms": pos[2],
            "normal_max_deg": nrm[0] * 180.0 / pi,
            "normal_rms_deg": nrm[2] * 180.0 / pi,
        })
    return report


def compare_methods(mesh, R, r, level=4):
    """PN-triangles vs Catmull-Clark at matched triangle budgets."""
    pn_v, pn_f, pn_n = pn_tessellate(mesh, level)
    cc_v, cc_f = subdivide_tris(mesh.vertices, mesh.faces, level)
    # CC has no stored normals: use area-weighted vertex normals of result.
    from mesh import Mesh
    cc_n = Mesh(cc_v, cc_f).vertex_normals()
    pn_rows = sample_errors(pn_v, pn_n, R, r)
    cc_rows = sample_errors(cc_v, cc_n, R, r)
    return {
        "pn": {"tris": len(pn_f), "rows": pn_rows,
               "report": stratified_report(pn_rows)},
        "cc": {"tris": len(cc_f), "rows": cc_rows,
               "report": stratified_report(cc_rows)},
    }


def matched_budget_compare(mesh, R, r):
    """Equal triangle count (16 tris per input face): PN level 4 vs CC level 2
    (CC quads split into 2 triangles each)."""
    from mesh import Mesh
    pn_v, pn_f, pn_n = pn_tessellate(mesh, 4)
    cc_v, cc_f = subdivide_tris(mesh.vertices, mesh.faces, 2)
    cc_n = Mesh(cc_v, cc_f).vertex_normals()
    return {
        "pn_tris": len(pn_f),
        "cc_tris": len(cc_f),
        "pn_report": stratified_report(sample_errors(pn_v, pn_n, R, r)),
        "cc_report": stratified_report(sample_errors(cc_v, cc_n, R, r)),
    }
