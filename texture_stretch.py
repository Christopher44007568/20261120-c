"""High-curvature mesh segmentation vs texture stretch.

Pipeline:
  1. Generate a bumpy-sphere mesh (high-curvature surface).
  2. Estimate per-face curvature from normal deviation.
  3. Baseline: one planar UV projection for the whole model.
  4. Segmented: curvature-weighted k-means on face normals splits the
     mesh into charts; each chart gets its own planar projection.
  5. Compare L2 texture stretch (1.0 = isometric) before/after.
"""

import math
import random


# ---------- small vec3 helpers ----------

def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vnorm(a):
    return math.sqrt(vdot(a, a))


def vnormalize(a):
    n = vnorm(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


# ---------- mesh generation ----------

def make_bumpy_sphere(n_theta=24, n_phi=48, amp=0.25, freq=6):
    """High-curvature surface: r = 1 + amp*sin(freq*theta)*cos(freq*phi)."""
    verts = []
    for i in range(n_theta + 1):
        theta = math.pi * i / n_theta
        for j in range(n_phi):
            phi = 2.0 * math.pi * j / n_phi
            r = 1.0 + amp * math.sin(freq * theta) * math.cos(freq * phi)
            verts.append(
                (
                    r * math.sin(theta) * math.cos(phi),
                    r * math.sin(theta) * math.sin(phi),
                    r * math.cos(theta),
                )
            )

    def vid(i, j):
        return i * n_phi + (j % n_phi)

    faces = []
    for i in range(n_theta):
        for j in range(n_phi):
            a, b = vid(i, j), vid(i, j + 1)
            c, d = vid(i + 1, j), vid(i + 1, j + 1)
            faces.append((a, c, b))
            faces.append((b, c, d))
    # Drop zero-area triangles at the poles (duplicate vertices).
    faces = [
        f for f in faces
        if vnorm(vcross(vsub(verts[f[1]], verts[f[0]]),
                        vsub(verts[f[2]], verts[f[0]]))) > 1e-9
    ]
    return verts, faces


def face_normal(verts, face):
    p0, p1, p2 = (verts[i] for i in face)
    return vnormalize(vcross(vsub(p1, p0), vsub(p2, p0)))


def estimate_curvature(verts, faces, normals):
    """Per-face curvature proxy: mean dihedral angle to adjacent faces."""
    edge_to_faces = {}
    for fi, face in enumerate(faces):
        for k in range(3):
            e = tuple(sorted((face[k], face[(k + 1) % 3])))
            edge_to_faces.setdefault(e, []).append(fi)
    curvature = [0.0] * len(faces)
    count = [0] * len(faces)
    for adjacent in edge_to_faces.values():
        if len(adjacent) != 2:
            continue
        f0, f1 = adjacent
        angle = math.acos(max(-1.0, min(1.0, vdot(normals[f0], normals[f1]))))
        curvature[f0] += angle
        curvature[f1] += angle
        count[f0] += 1
        count[f1] += 1
    return [curvature[i] / count[i] if count[i] else 0.0 for i in range(len(faces))]


# ---------- L2 texture stretch ----------

def triangle_stretch(p3d, p2d):
    """L2 stretch of the UV->surface map (Sander et al.; 1.0 = isometric).

    Builds an orthonormal frame on the 3D triangle, expresses both
    triangles as 2x2 edge matrices, and takes singular values of
    J = T_3d * inv(T_uv): how much a texel stretches on the surface.
    """
    (a3, b3, c3) = p3d
    (a2, b2, c2) = p2d
    e1 = vnormalize(vsub(b3, a3))
    e2 = vnormalize(vsub(vsub(c3, a3), vscale(e1, vdot(vsub(c3, a3), e1))))
    ab = vsub(b3, a3)
    ac = vsub(c3, a3)
    s = ((vdot(ab, e1), vdot(ac, e1)), (vdot(ab, e2), vdot(ac, e2)))
    t = ((b2[0] - a2[0], c2[0] - a2[0]), (b2[1] - a2[1], c2[1] - a2[1]))
    det = t[0][0] * t[1][1] - t[0][1] * t[1][0]
    if abs(det) < 1e-14:
        return float("inf")  # degenerate UV: infinite stretch
    tinv = ((t[1][1] / det, -t[0][1] / det), (-t[1][0] / det, t[0][0] / det))
    j = (
        (s[0][0] * tinv[0][0] + s[0][1] * tinv[1][0],
         s[0][0] * tinv[0][1] + s[0][1] * tinv[1][1]),
        (s[1][0] * tinv[0][0] + s[1][1] * tinv[1][0],
         s[1][0] * tinv[0][1] + s[1][1] * tinv[1][1]),
    )
    # singular values of J via eigenvalues of J^T J (2x2 closed form)
    m00 = j[0][0] ** 2 + j[1][0] ** 2
    m01 = j[0][0] * j[0][1] + j[1][0] * j[1][1]
    m11 = j[0][1] ** 2 + j[1][1] ** 2
    tr = m00 + m11
    dt = m00 * m11 - m01 * m01
    disc = math.sqrt(max(0.0, tr * tr / 4.0 - dt))
    l1 = tr / 2.0 + disc
    l2 = tr / 2.0 - disc
    return math.sqrt((l1 + l2) / 2.0)


# ---------- UV projection ----------

def plane_basis(normal):
    n = vnormalize(normal)
    ref = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = vnormalize(vcross(n, ref))
    v = vcross(n, u)
    return u, v


def project_faces(verts, faces, face_ids, normal, origin):
    """Planar UVs for the given faces onto the plane through `origin`."""
    u, v = plane_basis(normal)
    uv = {}
    for fi in face_ids:
        for idx in faces[fi]:
            if idx not in uv:
                d = vsub(verts[idx], origin)
                uv[idx] = (vdot(d, u), vdot(d, v))
    return uv


def mesh_centroid(verts):
    c = (0.0, 0.0, 0.0)
    for p in verts:
        c = vadd(c, p)
    return vscale(c, 1.0 / len(verts))


def tri_area_3d(p3d):
    return 0.5 * vnorm(vcross(vsub(p3d[1], p3d[0]), vsub(p3d[2], p3d[0])))


def tri_area_2d(p2d):
    return 0.5 * abs(
        (p2d[1][0] - p2d[0][0]) * (p2d[2][1] - p2d[0][1])
        - (p2d[2][0] - p2d[0][0]) * (p2d[1][1] - p2d[0][1])
    )


def stretch_report(verts, faces, uvs_per_face):
    """Stretch stats; UVs are first rescaled so total UV area matches
    total surface area, making charts comparable across methods."""
    area3d = 0.0
    area2d = 0.0
    for fi, face in enumerate(faces):
        area3d += tri_area_3d(tuple(verts[i] for i in face))
        area2d += tri_area_2d(uvs_per_face[fi])
    scale = math.sqrt(area3d / area2d) if area2d > 1e-14 else 1.0

    stretches = []
    degenerate = 0
    for fi, face in enumerate(faces):
        p3d = tuple(verts[i] for i in face)
        p2d = tuple((u * scale, v * scale) for (u, v) in uvs_per_face[fi])
        s = triangle_stretch(p3d, p2d)
        if math.isfinite(s):
            stretches.append(s)
        else:
            degenerate += 1
    mean = sum(stretches) / len(stretches)
    peak = max(stretches)
    over2 = sum(1 for s in stretches if s > 2.0) / len(faces) * 100.0
    return {"mean": mean, "max": peak, "pct_over_2x": over2,
            "degenerate": degenerate}


# ---------- curvature-aware segmentation ----------

def segment_charts(normals, curvature, k=8, iterations=25, curv_weight=2.0, seed=7):
    """K-means on face normals, features scaled by (1 + w*curvature).

    High-curvature faces are pushed apart in feature space, so charts
    split along sharp features instead of cutting through them.
    """
    rng = random.Random(seed)
    features = []
    for n, c in zip(normals, curvature):
        w = 1.0 + curv_weight * c
        features.append((n[0] * w, n[1] * w, n[2] * w))

    centroids = [features[i] for i in rng.sample(range(len(features)), k)]
    assign = [0] * len(features)
    for _ in range(iterations):
        changed = False
        for i, f in enumerate(features):
            best, best_d = 0, float("inf")
            for ci, c in enumerate(centroids):
                d = (f[0] - c[0]) ** 2 + (f[1] - c[1]) ** 2 + (f[2] - c[2]) ** 2
                if d < best_d:
                    best, best_d = ci, d
            if best != assign[i]:
                assign[i] = best
                changed = True
        sums = [[0.0, 0.0, 0.0, 0] for _ in range(k)]
        for a, f in zip(assign, features):
            s = sums[a]
            s[0] += f[0]
            s[1] += f[1]
            s[2] += f[2]
            s[3] += 1
        for ci, s in enumerate(sums):
            if s[3]:
                centroids[ci] = (s[0] / s[3], s[1] / s[3], s[2] / s[3])
        if not changed:
            break
    charts = {}
    for fi, a in enumerate(assign):
        charts.setdefault(a, []).append(fi)
    return list(charts.values())


# ---------- experiment ----------

def main():
    verts, faces = make_bumpy_sphere()
    normals = [face_normal(verts, f) for f in faces]
    curvature = estimate_curvature(verts, faces, normals)
    print(f"mesh: {len(verts)} verts, {len(faces)} faces")
    print(
        "curvature (dihedral, rad): mean=%.3f max=%.3f"
        % (sum(curvature) / len(curvature), max(curvature))
    )

    # Baseline: single planar projection for the whole model.
    center = mesh_centroid(verts)
    uv = project_faces(verts, faces, range(len(faces)), (0.0, 0.0, 1.0), center)
    base_uvs = [[uv[i] for i in face] for face in faces]
    base = stretch_report(verts, faces, base_uvs)
    print(
        "baseline (1 chart):  mean=%.3f max=%.1f faces>2x=%.1f%% degenerate=%d"
        % (base["mean"], base["max"], base["pct_over_2x"], base["degenerate"])
    )

    # Segmented: curvature-aware charts, one projection each.
    for k in (6, 12, 24):
        charts = segment_charts(normals, curvature, k=k)
        seg_uvs = [None] * len(faces)
        for chart in charts:
            cn = (0.0, 0.0, 0.0)
            cc = (0.0, 0.0, 0.0)
            for fi in chart:
                cn = vadd(cn, normals[fi])
                for idx in faces[fi]:
                    cc = vadd(cc, verts[idx])
            cn = vnormalize(cn)
            cc = vscale(cc, 1.0 / (3 * len(chart)))
            uv = project_faces(verts, faces, chart, cn, cc)
            for fi in chart:
                seg_uvs[fi] = [uv[i] for i in faces[fi]]
        seg = stretch_report(verts, faces, seg_uvs)
        drop = 100.0 * (1.0 - seg["mean"] / base["mean"])
        print(
            "segmented (k=%-2d): mean=%.3f max=%.1f faces>2x=%.1f%% "
            "degenerate=%d  mean stretch -%.1f%%"
            % (k, seg["mean"], seg["max"], seg["pct_over_2x"],
               seg["degenerate"], drop)
        )


if __name__ == "__main__":
    main()
