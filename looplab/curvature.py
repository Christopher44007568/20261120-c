"""Discrete curvature estimators on triangle meshes."""
import math
from .mesh import vsub, vdot, vcross, vnorm


def _angle(p, a, b):
    u, v = vsub(a, p), vsub(b, p)
    nu, nv = vnorm(u), vnorm(v)
    if nu * nv < 1e-30:
        return 0.0
    return math.acos(max(-1.0, min(1.0, vdot(u, v) / (nu * nv))))


def _cot(p, a, b):
    u, v = vsub(a, p), vsub(b, p)
    cr = vnorm(vcross(u, v))
    if cr < 1e-30:
        return 0.0
    return vdot(u, v) / cr


def curvature(mesh):
    """Return (gaussian, mean) curvature per vertex."""
    n = len(mesh.vertices)
    angle_sum = [0.0] * n
    area = [0.0] * n
    lap = [(0.0, 0.0, 0.0)] * n
    for (a, b, c) in mesh.faces:
        pa, pb, pc = (mesh.vertices[i] for i in (a, b, c))
        fa = 0.5 * vnorm(vcross(vsub(pb, pa), vsub(pc, pa)))
        angles = (_angle(pa, pb, pc), _angle(pb, pc, pa), _angle(pc, pa, pb))
        for idx, ang in zip((a, b, c), angles):
            angle_sum[idx] += ang
            area[idx] += fa / 3.0  # barycentric area (stable, sufficient here)
        for (i, j, k) in ((a, b, c), (b, c, a), (c, a, b)):
            cot = _cot(mesh.vertices[k], mesh.vertices[i], mesh.vertices[j])
            w = vsub(mesh.vertices[j], mesh.vertices[i])
            li = lap[i]
            lap[i] = (li[0] + cot * w[0], li[1] + cot * w[1], li[2] + cot * w[2])
    gaussian, mean = [], []
    for v in range(n):
        a = max(area[v], 1e-30)
        defect = (math.pi if v in mesh.boundary_vertices else 2.0 * math.pi)
        gaussian.append((defect - angle_sum[v]) / a)
        mean.append(0.25 * vnorm(lap[v]) / a)
    return gaussian, mean


def curvature_stats(mesh, interior_only=True):
    g, h = curvature(mesh)
    idx = [v for v in range(len(mesh.vertices))
           if not interior_only or v not in mesh.boundary_vertices]
    if not idx:
        idx = list(range(len(mesh.vertices)))
    gs = [abs(g[v]) for v in idx]
    hs = [h[v] for v in idx]
    return {
        "max|K|": max(gs), "mean|K|": sum(gs) / len(gs),
        "max|H|": max(hs), "mean|H|": sum(hs) / len(hs),
    }
