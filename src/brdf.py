"""Ashikhmin velvet/cloth BRDF with anisotropic fiber-direction scattering,
plus an anisotropic GGX model for comparison. Pure stdlib.

Frames: n = surface normal (macro), t = fiber tangent direction (unit, in
surface plane), b = bitangent = cross(n, t).
"""
import math
import random

PI = math.pi


# ---------- vec3 helpers ----------
def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a):
    l = math.sqrt(dot(a, a))
    return (a[0] / l, a[1] / l, a[2] / l)


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


# ---------- Ashikhmin velvet (Ashikhmin & Premoze 2007), isotropic ----------
# fr = (28/(23 pi)) * rho * (1 - Rs) * p(h) / (4 (ci + co - ci co))
# p(h) = 1 / (pi (1 + a * theta_h^2)), theta_h = angle(h, n)
VELVET_NORM = 28.0 / (23.0 * PI)


def velvet_p_isotropic(cos_hn, a):
    th = math.acos(clamp(cos_hn, -1.0, 1.0))
    return 1.0 / (PI * (1.0 + a * th * th))


def velvet_denominator(ci, co):
    return 4.0 * (ci + co - ci * co)


def velvet_isotropic(wi, wo, n, rho, a, rs=0.3):
    ci, co = dot(wi, n), dot(wo, n)
    if ci <= 0.0 or co <= 0.0:
        return 0.0
    h = norm((wi[0] + wo[0], wi[1] + wo[1], wi[2] + wo[2]))
    p = velvet_p_isotropic(dot(h, n), a)
    return VELVET_NORM * rho * (1.0 - rs) * p / velvet_denominator(ci, co)


# ---------- Anisotropic fiber velvet ----------
# Fibers run along t, so micro-normals lie near the plane perpendicular to
# the fiber. The half-vector distribution is therefore concentrated where
# h.t ~ 0:  p(h) = K / (1 + a * tan^2(gamma)),  tan^2(gamma) = u^2/(1-u^2),
# u = h.t. K is normalized numerically so p integrates to 1 over the
# hemisphere. The Ashikhmin retroreflective denominator keeps the hemispherical
# reflectance <= 1 (energy conserving), verified numerically in validate.py.

_norm_cache = {}


def _p_aniso_unnorm(h, t, n, a):
    hn = dot(h, n)
    if hn <= 0.0:
        return 0.0
    u = clamp(dot(h, t), -1.0, 1.0)
    u2 = u * u
    if u2 >= 1.0:
        return 0.0
    tan2 = u2 / (1.0 - u2)
    return 1.0 / (1.0 + a * tan2)


def _p_aniso_norm_const(t, n, a, n_theta=64, n_phi=128):
    key = (round(a, 6),)
    # normalization is frame-invariant (depends only on a), cache by a
    if key in _norm_cache:
        return _norm_cache[key]
    b = norm(cross(n, t))
    total = 0.0
    for i in range(n_theta):
        ct = (i + 0.5) / n_theta
        st = math.sqrt(1.0 - ct * ct)
        for j in range(n_phi):
            ph = 2.0 * PI * (j + 0.5) / n_phi
            h = (st * math.cos(ph) * t[0] + st * math.sin(ph) * b[0] + ct * n[0],
                 st * math.cos(ph) * t[1] + st * math.sin(ph) * b[1] + ct * n[1],
                 st * math.cos(ph) * t[2] + st * math.sin(ph) * b[2] + ct * n[2])
            total += _p_aniso_unnorm(h, t, n, a)  # d_omega = d(cos theta) d phi
    total *= (2.0 * PI / n_phi) / n_theta
    k = 1.0 / total
    _norm_cache[key] = k
    return k


def velvet_p_aniso(h, t, n, a):
    return _p_aniso_norm_const(t, n, a) * _p_aniso_unnorm(h, t, n, a)


def velvet_aniso(wi, wo, n, t, rho, a, rs=0.3):
    ci, co = dot(wi, n), dot(wo, n)
    if ci <= 0.0 or co <= 0.0:
        return 0.0
    h = norm((wi[0] + wo[0], wi[1] + wo[1], wi[2] + wo[2]))
    p = velvet_p_aniso(h, t, n, a)
    return VELVET_NORM * rho * (1.0 - rs) * p / velvet_denominator(ci, co)


# ---------- Anisotropic GGX (Walter et al.) for comparison ----------
def ggx_aniso(wi, wo, n, t, alpha_x, alpha_y, f0=0.3):
    ci, co = dot(wi, n), dot(wo, n)
    if ci <= 0.0 or co <= 0.0:
        return 0.0
    b = norm(cross(n, t))
    h = norm((wi[0] + wo[0], wi[1] + wo[1], wi[2] + wo[2]))
    hn, ht, hb = dot(h, n), dot(h, t), dot(h, b)
    if hn <= 0.0:
        return 0.0
    d_den = (ht * ht) / (alpha_x * alpha_x) + (hb * hb) / (alpha_y * alpha_y) + hn * hn
    d = 1.0 / (PI * alpha_x * alpha_y * d_den * d_den)

    def g1(w):
        cw = dot(w, n)
        wt, wb = dot(w, t), dot(w, b)
        a2 = (wt * alpha_x) ** 2 + (wb * alpha_y) ** 2
        tw2 = a2 / (cw * cw)
        return 2.0 / (1.0 + math.sqrt(1.0 + tw2))

    g = g1(wi) * g1(wo)
    ch = clamp(dot(wi, h))
    f = f0 + (1.0 - f0) * (1.0 - ch) ** 5
    return d * g * f / (4.0 * ci * co)


# ---------- Sampling ----------
def sample_velvet_aniso(wi, n, t, a, rng):
    """Sample wo from the anisotropic velvet lobe: sample h ~ p_aniso via
    rejection sampling on the hemisphere, reflect wi about h.
    Returns (wo, pdf_wo)."""
    b = norm(cross(n, t))
    k = _p_aniso_norm_const(t, n, a)
    while True:
        # uniform hemisphere sample
        u1, u2 = rng.random(), rng.random()
        ct = u1
        st = math.sqrt(1.0 - ct * ct)
        ph = 2.0 * PI * u2
        h = (st * math.cos(ph) * t[0] + st * math.sin(ph) * b[0] + ct * n[0],
             st * math.cos(ph) * t[1] + st * math.sin(ph) * b[1] + ct * n[1],
             st * math.cos(ph) * t[2] + st * math.sin(ph) * b[2] + ct * n[2])
        p = velvet_p_aniso(h, t, n, a)
        if rng.random() * k <= p:  # p <= K since unnorm <= 1
            break
    ih = dot(wi, h)
    if ih <= 0.0:
        return None, 0.0
    wo = (2.0 * ih * h[0] - wi[0],
          2.0 * ih * h[1] - wi[1],
          2.0 * ih * h[2] - wi[2])
    if dot(wo, n) <= 0.0:
        return None, 0.0
    pdf_h = p  # p is normalized over the hemisphere
    pdf_wo = pdf_h / (4.0 * ih)
    return wo, pdf_wo
