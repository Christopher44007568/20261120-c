"""Distance-field soft shadows on a sphere + ground scene.

Implements the classic IQ-style SDF soft-shadow ray march:

    res   = min(res, w * h / t)          # soft shadow factor in [0, 1]
    pen   = min(pen,     h / t)          # angular penumbra estimate (rad)
    t    += step_scale * max(h, eps)

where h is the occluder SDF distance and t is the travelled ray distance.
The module sweeps the soft factor w and the step-size scale, validates the
SDF gradient by finite differences, predicts the ground penumbra width from
the gradient, and writes every table/figure to ./artifacts.
"""

from __future__ import annotations

import os

import numpy as np

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
os.makedirs(ARTIFACTS, exist_ok=True)

# ---------------------------------------------------------------------------
# Scene: sphere of radius R resting on the y = 0 ground plane.
# ---------------------------------------------------------------------------
SPHERE_C = np.array([0.0, 1.0, 0.0])
SPHERE_R = 1.0
LIGHT_DIR = np.array([2.0, 3.0, 1.0])
LIGHT_DIR = LIGHT_DIR / np.linalg.norm(LIGHT_DIR)

HIT_EPS = 2e-3
T_MIN = 1e-3
T_MAX = 12.0
MAX_STEPS = 256


def sdf_sphere(p: np.ndarray) -> np.ndarray:
    """Signed distance to the sphere (occluder)."""
    return np.linalg.norm(p - SPHERE_C, axis=-1) - SPHERE_R


def sdf_ground(p: np.ndarray) -> np.ndarray:
    return p[..., 1]


def sdf_scene(p: np.ndarray) -> np.ndarray:
    """Union SDF of sphere and ground (used for gradient validation)."""
    return np.minimum(sdf_sphere(p), sdf_ground(p))


def finite_diff_gradient(p: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    """Central-difference gradient of the scene SDF at points p (..., 3)."""
    p = np.asarray(p, dtype=np.float64)
    g = np.zeros_like(p)
    for axis in range(3):
        offset = np.zeros(3)
        offset[axis] = eps
        g[..., axis] = (
            sdf_scene(p + offset) - sdf_scene(p - offset)
        ) / (2.0 * eps)
    return g


def analytic_gradient(p: np.ndarray) -> np.ndarray:
    """Analytic gradient of the min-union SDF (for cross-checking)."""
    p = np.asarray(p, dtype=np.float64)
    d_sphere = sdf_sphere(p)
    d_ground = sdf_ground(p)
    g_sphere = (p - SPHERE_C) / np.linalg.norm(p - SPHERE_C, axis=-1, keepdims=True)
    g_ground = np.zeros_like(p)
    g_ground[..., 1] = 1.0
    return np.where((d_sphere <= d_ground)[..., None], g_sphere, g_ground)


def soft_shadow(
    origins: np.ndarray,
    soft_factor: float = 16.0,
    step_scale: float = 1.0,
) -> dict[str, np.ndarray]:
    """Vectorized soft-shadow march for an array of ground origin points.

    Only the sphere acts as an occluder: the ground is the shading surface,
    so shadow rays use the sphere SDF with a small t-offset bias.

    Returns shadow factor, step count, minimum angular penumbra h/t and the
    (t, h) at which that minimum occurred, plus a hit flag.
    """
    pts = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
    n = pts.shape[0]

    t = np.full(n, T_MIN, dtype=np.float64)
    active = np.ones(n, dtype=bool)
    shadow = np.ones(n, dtype=np.float64)
    penumbra = np.full(n, np.inf, dtype=np.float64)
    t_at_min = np.zeros(n, dtype=np.float64)
    h_at_min = np.zeros(n, dtype=np.float64)
    steps = np.zeros(n, dtype=np.int64)
    hit = np.zeros(n, dtype=bool)

    for _ in range(MAX_STEPS):
        idx = np.flatnonzero(active)
        if idx.size == 0:
            break
        ray_pts = pts[idx] + LIGHT_DIR * t[idx, None]
        h = sdf_sphere(ray_pts)
        t_now = t[idx]

        hit_now = h < HIT_EPS
        exterior = ~hit_now

        # h/t is only meaningful outside the occluder; ignore interior steps
        # (overshoot inside the SDF would yield negative penumbra angles).
        if np.any(exterior):
            idx_ext = idx[exterior]
            ratio = h[exterior] / t_now[exterior]
            improved = ratio < penumbra[idx_ext]
            sub = idx_ext[improved]
            penumbra[sub] = ratio[improved]
            t_at_min[sub] = t_now[exterior][improved]
            h_at_min[sub] = h[exterior][improved]
            shadow[idx_ext] = np.minimum(
                shadow[idx_ext], np.minimum(1.0, soft_factor * ratio)
            )

        steps[idx] += 1

        if np.any(hit_now):
            idx_hit = idx[hit_now]
            hit[idx_hit] = True
            shadow[idx_hit] = 0.0
            penumbra[idx_hit] = np.inf
            active[idx_hit] = False

        t[idx[exterior]] += step_scale * np.maximum(h[exterior], HIT_EPS)
        active[idx[exterior]] = t[idx[exterior]] <= T_MAX

    shadow = np.clip(shadow, 0.0, 1.0)
    return {
        "shadow": shadow,
        "steps": steps,
        "penumbra_angle": penumbra,
        "t_at_min": t_at_min,
        "h_at_min": h_at_min,
        "hit": hit,
    }
def analytic_tangent_boundary() -> float:
    """Ground x-coordinate (z = 0 scanline) where the light ray grazes sphere.

    A line from ground point (x, 0, 0) along LIGHT_DIR is tangent to the
    sphere when the quadratic |p + s L - C|^2 = R^2 has zero discriminant.
    """
    lx, ly, lz = LIGHT_DIR
    cx, cy, cz = SPHERE_C
    r2 = SPHERE_R**2
    # b(x) = L . ((x,0,0) - C); c(x) = |(x,0,0) - C|^2 - R^2
    # discriminant b^2 - c = 0 gives a quadratic in x.
    b0 = -lx * cx - ly * cy - lz * cz
    b1 = lx
    c0 = cx**2 + cy**2 + cz**2 - r2
    c1 = -2.0 * cx
    c2 = 1.0
    A = b1**2 - c2
    B = 2.0 * b0 * b1 - c1
    Cc = b0**2 - c0
    roots = np.roots([A, B, Cc])
    real_roots = roots[np.abs(roots.imag) < 1e-9].real
    # Light points toward decreasing x (lx > 0 means rays go +x here); the
    # relevant boundary is the positive-x tangent contact.
    return float(np.max(real_roots))


def analytic_penumbra_angle(x: np.ndarray) -> np.ndarray:
    """Angular half-extent (rad) of the sphere seen from a ground point."""
    x = np.asarray(x, dtype=np.float64)
    ground = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=-1)
    d = np.linalg.norm(ground - SPHERE_C, axis=-1)
    # Clamp handles points inside the sphere (none for this scene, but safe).
    return np.arcsin(np.clip(SPHERE_R / d, -1.0, 1.0))


def closest_approach_distance(x: np.ndarray) -> np.ndarray:
    """Perpendicular distance from the light ray (ground point x) to C."""
    x = np.asarray(x, dtype=np.float64)
    ground = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=-1)
    rel = ground - SPHERE_C
    s_star = -rel @ LIGHT_DIR
    closest = ground + s_star[:, None] * LIGHT_DIR
    return np.linalg.norm(closest - SPHERE_C, axis=-1)


def gradient_penumbra_width(x_boundary: float) -> tuple[float, float, float]:
    """Predict ground penumbra width from the SDF gradient at the boundary.

    At the grazing point the ray is tangent, so the sphere SDF gradient is
    perpendicular to LIGHT_DIR.  Moving the ground origin by dx translates
    the whole ray, and the ratio that drives the shadow factor is

        h/t(dx) ~ |grad h . e_x| * dx / t*

    where t* is the ray distance from the ground point to the tangent
    contact.  The 1/t* factor is essential: the penumbra angle is h/t, not
    h alone.  Inverting, an angular span Delta(h/t) maps to the ground width

        width = Delta(h/t) * t* / |grad h . e_x|.

    The 0.05..0.95 shadow band would span 0.9/w, but shadow = min(1, w h/t)
    clamps at h/t = 1/w, so for w >= 1 the effective span is 0.95/w.
    """
    ground = np.array([x_boundary, 0.0, 0.0])
    s_star = -((ground - SPHERE_C) @ LIGHT_DIR)
    tangent_point = ground + s_star * LIGHT_DIR
    grad = (tangent_point - SPHERE_C) / np.linalg.norm(tangent_point - SPHERE_C)
    grad_x_magnitude = abs(float(grad[0]))
    return grad, grad_x_magnitude, float(s_star)


def predicted_transition_width(
    soft_factor: float, grad_x: float, t_star: float
) -> float:
    """Clamp-aware, gradient-based width of the 0.05..0.95 ground band."""
    upper = min(0.95, 1.0)
    lower = 0.05
    return ((upper - lower) / soft_factor) * t_star / grad_x


def analytic_ht_vs_dx(dx: np.ndarray, x_boundary: float) -> np.ndarray:
    """Exact h/t of the light ray from ground point (x_boundary + dx, 0, 0)."""
    dx = np.asarray(dx, dtype=np.float64)
    ground = np.stack(
        [x_boundary + dx, np.zeros_like(dx), np.zeros_like(dx)], axis=-1
    )
    rel = ground - SPHERE_C
    s_star = -rel @ LIGHT_DIR
    closest = ground + s_star[:, None] * LIGHT_DIR
    h = np.linalg.norm(closest - SPHERE_C, axis=-1) - SPHERE_R
    return h / s_star


def analytic_transition_width(soft_factor: float, x_boundary: float) -> float:
    """Exact ground width by inverting the analytic h/t curve with bisection."""
    lower = 0.05 / soft_factor
    upper = min(0.95, 1.0) / soft_factor

    def solve(target: float) -> float:
        lo, hi = 0.0, 0.45
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if analytic_ht_vs_dx(np.array([mid]), x_boundary)[0] > target:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    return solve(upper) - solve(lower)


def validate_gradient() -> dict[str, float]:
    """Check finite-difference vs analytic gradients and unit-length norm."""
    rng = np.random.default_rng(7)
    probe = rng.uniform(-2.5, 2.5, size=(400, 3))
    probe[:, 1] = np.abs(probe[:, 1]) + 0.05
    g_num = finite_diff_gradient(probe)
    g_ana = analytic_gradient(probe)
    norm_err = float(np.max(np.abs(np.linalg.norm(g_num, axis=-1) - 1.0)))
    angle_err = float(
        np.max(np.linalg.norm(g_num - g_ana, axis=-1))
    )
    return {"max_norm_error": norm_err, "max_gradient_error": angle_err}
