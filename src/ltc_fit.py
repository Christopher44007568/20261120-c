"""Fit Linearly Transformed Cosine (LTC) matrices to isotropic GGX and
tabulate the matrix parameters as a curve over roughness.

Parameterization (Heitz et al. 2016):
    M = [[m00, 0, m02],
         [0, m11, 0 ],
         [m20, 0, 1  ]]
The fitted distribution is D_ltc(L) = D_o(w) * |invM| / |invM.L|^3 with
w = normalize(invM.L) and D_o the clamped cosine / pi.
"""
import math


# ---------- 3x3 helpers (flat 9-tuples, row major) ----------

def mat_from_params(p):
    m00, m02, m11, m20 = p
    return (m00, 0.0, m02,
            0.0, m11, 0.0,
            m20, 0.0, 1.0)


def mat_inv(m):
    a, b, c, d, e, f, g, h, i = m
    A = e * i - f * h
    B = -(d * i - f * g)
    C = d * h - e * g
    det = a * A + b * B + c * C
    if abs(det) < 1e-12:
        return None, 0.0
    inv = (A / det, -(b * i - c * h) / det, (b * f - c * e) / det,
           B / det, (a * i - c * g) / det, -(a * f - c * d) / det,
           C / det, -(a * h - b * g) / det, (a * e - b * d) / det)
    return inv, det


def mat_mul_vec(m, v):
    return (m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
            m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2])


# ---------- GGX target ----------

def ggx_cos_weighted(view, light, alpha):
    """Cosine-weighted GGX BRDF: f(V,L) * (N.L), N = +Z."""
    nl = light[2]
    nv = view[2]
    if nl <= 0.0 or nv <= 0.0:
        return 0.0
    hx, hy, hz = view[0] + light[0], view[1] + light[1], view[2] + light[2]
    norm = math.sqrt(hx * hx + hy * hy + hz * hz)
    if norm == 0.0:
        return 0.0
    nh = hz / norm
    a2 = alpha * alpha
    ddenom = nh * nh * (a2 - 1.0) + 1.0
    D = a2 / (math.pi * ddenom * ddenom)

    def g1(ndot):
        t = math.sqrt(1.0 + a2 * (1.0 - ndot * ndot) / (ndot * ndot))
        return 2.0 / (1.0 + t)

    G = g1(nv) * g1(nl)
    return D * G / (4.0 * nv)  # * nl cancels the 1/(nl) of the BRDF


def ltc_eval(params, light):
    m = mat_from_params(params)
    inv, det = mat_inv(m)
    if inv is None:
        return 0.0
    w = mat_mul_vec(inv, light)
    length = math.sqrt(w[0] * w[0] + w[1] * w[1] + w[2] * w[2])
    if length < 1e-12:
        return 0.0
    z = w[2] / length
    d_o = max(z, 0.0) / math.pi
    return d_o * (1.0 / abs(det)) / (length ** 3)


# ---------- sampling ----------

def hemisphere_samples(n_theta=12, n_phi=16):
    pts = []
    for i in range(n_theta):
        cos_t = (i + 0.5) / n_theta
        sin_t = math.sqrt(1.0 - cos_t * cos_t)
        for j in range(n_phi):
            phi = 2.0 * math.pi * (j + 0.5) / n_phi
            pts.append((sin_t * math.cos(phi), sin_t * math.sin(phi), cos_t))
    return pts


# ---------- Nelder-Mead ----------

def nelder_mead(func, x0, step=0.1, iters=200, tol=1e-9):
    n = len(x0)
    simplex = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step
        simplex.append(p)
    vals = [func(p) for p in simplex]
    for _ in range(iters):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        simplex = [simplex[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol * (1.0 + abs(vals[0])):
            break
        centroid = [sum(simplex[i][k] for i in range(n)) / n for k in range(n)]
        worst = simplex[-1]
        refl = [centroid[k] + (centroid[k] - worst[k]) for k in range(n)]
        f_refl = func(refl)
        if f_refl < vals[0]:
            exp = [centroid[k] + 2.0 * (refl[k] - centroid[k]) for k in range(n)]
            f_exp = func(exp)
            simplex[-1], vals[-1] = (exp, f_exp) if f_exp < f_refl else (refl, f_refl)
        elif f_refl < vals[-2]:
            simplex[-1], vals[-1] = refl, f_refl
        else:
            con = [centroid[k] + 0.5 * (worst[k] - centroid[k]) for k in range(n)]
            f_con = func(con)
            if f_con < vals[-1]:
                simplex[-1], vals[-1] = con, f_con
            else:
                best = simplex[0]
                for i in range(1, n + 1):
                    simplex[i] = [best[k] + 0.5 * (simplex[i][k] - best[k])
                                  for k in range(n)]
                    vals[i] = func(simplex[i])
    best = min(range(n + 1), key=lambda i: vals[i])
    return simplex[best], vals[best]


def fit_ltc(view, alpha, samples, init, d_cos=1.0 / 12.0, d_phi=2.0 * math.pi / 16.0):
    target = [ggx_cos_weighted(view, l, alpha) for l in samples]
    # amplitude (reflectance) = integral of the cosine-weighted BRDF over d_omega
    amplitude = sum(target) * d_cos * d_phi
    if amplitude > 1e-12:
        target = [t / amplitude for t in target]
    norm = sum(t * t for t in target) or 1.0

    def cost(p):
        m00, m02, m11, m20 = p
        det = m11 * (m00 - m02 * m20)
        if m00 <= 1e-3 or m11 <= 1e-3 or det <= 1e-6:
            return 1e6 + 1e4 * (abs(min(m00, 0.0)) + abs(min(m11, 0.0)))
        err = 0.0
        for l, t in zip(samples, target):
            d = ltc_eval(p, l) - t
            err += d * d
        return err / norm

    params, err = nelder_mead(cost, init, step=0.1, iters=300)
    return params, err, amplitude
