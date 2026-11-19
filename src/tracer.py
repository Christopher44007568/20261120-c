"""Wavefront volume path tracer with next-event direct lighting.

Renders an orthographic view of a box-shaped participating medium above a
Lambertian ground plane.  Two integration modes are supported:

* "uniform"     : deterministic-step ray marching with O(dt) quadrature bias.
* "exponential" : unbiased Woodcock/delta tracking with free-flight sampling.

The tracer accumulates luminance and the number of medium evaluations per
pixel so that noise and stepping cost can be compared directly.
"""

import numpy as np

from .ray import intersect_box, intersect_plane
from .sampling import exponential_ratio
def _isotropic(rng, n):
    z = rng.uniform(-1.0, 1.0, n)
    phi = rng.uniform(0.0, 2.0 * np.pi, n)
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.stack((r * np.cos(phi), r * np.sin(phi), z), axis=1)


def _camera_rays(width, height, view, rng):
    lo, hi = view["bounds"]
    jx = rng.uniform(size=width * height).reshape(height, width)
    jy = rng.uniform(size=width * height).reshape(height, width)
    xs = np.linspace(lo[0], hi[0], width + 1)[:-1]
    ys = np.linspace(lo[1], hi[1], height + 1)[:-1]
    dx = (hi[0] - lo[0]) / width
    dy = (hi[1] - lo[1]) / height
    px = xs[None, :] + (jx + 0.5) * dx
    py = ys[:, None] + (jy + 0.5) * dy
    origins = np.stack([px.ravel(), py.ravel(),
                        np.full(width * height, view["z"])], axis=1)
    dirs = np.zeros_like(origins)
    dirs[:, 2] = -1.0
    return origins, dirs


def _shadow_transmittance(medium, origins, dirs, dist, rng):
    """Fraction of light surviving from a scatter vertex toward the light."""
    t_enter, t_exit = intersect_box(origins, dirs, medium.bounds)
    t_exit = np.minimum(t_exit, dist)
    nan = np.isnan(t_enter)
    weight, _ = exponential_ratio(origins, dirs,
                                  np.where(nan, 0.0, t_enter),
                                  np.where(nan, 0.0, t_exit), medium, rng)
    return np.where(nan, 1.0, weight)


def _next_scatter_uniform(medium, origins, dirs, t_enter, t_exit, dt, rng):
    """Standard ray marching: one extinction evaluation per fixed-size cell.

    Transmittance is integrated quadrature-style while a single per-ray
    uniform draw selects the first scattering cell via inverse CDF sampling.
    """
    n = origins.shape[0]
    t = t_enter + rng.uniform(size=n) * dt
    steps = np.zeros(n, dtype=np.int64)
    scattered = np.zeros(n, dtype=bool)
    terminated = np.zeros(n, dtype=bool)
    tau_target = rng.exponential(size=n)
    tau = np.zeros(n)
    max_iters = int(np.ceil(np.nanmax(np.where(np.isnan(t_enter), 0.0,
                                               t_exit - t_enter)) / dt)) + 2
    for _ in range(max_iters):
        run = ~scattered & ~terminated & ~np.isnan(t) & (t < t_exit)
        if not run.any():
            break
        points = origins[run] + t[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        steps[run] += 1
        tau[run] += sigma * dt
        hit = run & (tau >= tau_target)
        scattered[hit] = True
        # Stop marching once transmittance becomes negligible; the path then
        # contributes zero energy instead of crossing the remaining empty cells.
        terminated[run & ~hit & (tau > 20.0)] = True
        t[run] += dt
    trans = np.where(terminated, 0.0,
                     np.where(scattered, 0.0, np.exp(-np.minimum(tau, 20.0))))
    t_scatter = np.where(scattered, np.maximum(t_enter, t - dt), t_exit)
    return t_scatter, trans, steps, scattered | terminated

def _next_scatter_ratio(medium, origins, dirs, t_enter, t_exit, rng):
    """Woodcock free-flight sampling paired with ratio-tracking transmittance.

    The scatter vertex uses delta tracking (real collision probability
    sigma_t / majorant), while the transmittance returned for rays that leave
    the box is the unbiased ratio-tracking product of (1 - sigma_t/majorant).
    The two estimates are independent of each other.
    """
    n = origins.shape[0]
    majorant = medium.majorant

    # Channel 1: continuous transmittance.  A homogeneous medium has an
    # analytic Beer-Lambert answer; a heterogeneous one uses ratio tracking,
    # which stays well behaved because its density field is sparse.
    t = t_enter.copy()
    weight = np.ones(n)
    steps = np.zeros(n, dtype=np.int64)
    if hasattr(medium, "analytic_transmittance"):
        length = np.where(np.isnan(t_enter), 0.0, t_exit - t_enter)
        weight = np.exp(-medium.sigma_t * length)
        weight = np.where(np.isnan(t_enter), 1.0, weight)
    else:
        null_majorant = majorant * 1.0001 + 1e-6
        for _ in range(256):
            run = ~np.isnan(t) & (t < t_exit)
            if not run.any():
                break
            t[run] += rng.exponential(size=run.sum()) / null_majorant
            run = ~np.isnan(t) & (t < t_exit)
            if not run.any():
                break
            points = origins[run] + t[run, None] * dirs[run]
            sigma = medium.sigma_at(points)
            steps[run] += 1
            weight[run] *= 1.0 - np.clip(sigma / null_majorant, 0.0, 1.0)
    t = np.where(np.isnan(t_enter), t_exit, t)

    # Channel 2: delta tracking to locate the first real scattering collision.
    t2 = t_enter.copy()
    scattered = np.zeros(n, dtype=bool)
    for _ in range(256):
        run = ~scattered & ~np.isnan(t2) & (t2 < t_exit)
        if not run.any():
            break
        t2[run] += rng.exponential(size=run.sum()) / majorant
        run = ~scattered & ~np.isnan(t2) & (t2 < t_exit)
        if not run.any():
            break
        points = origins[run] + t2[run, None] * dirs[run]
        sigma = medium.sigma_at(points)
        steps[run] += 1
        hit_local = rng.uniform(size=run.sum()) < (sigma / majorant)
        scattered[np.flatnonzero(run)[hit_local]] = True

    # The ratio weight is an independent transmittance estimate and must not
    # be zeroed when the separate delta-tracking channel finds a collision.
    trans = weight
    t_scatter = np.where(scattered, t2, t_exit)
    return t_scatter, trans, steps, scattered


def render(medium, view, width=168, height=168, mode="exponential", dt=0.08,
           max_bounces=3, seed=0,
           sun_dir=None, sun_radiance=1.0, ambient=0.6,
           ground_z=0.0, ground_albedo=0.7):
    """Render one frame; returns luminance image, per-pixel step counts and stats."""
    rng = np.random.Generator(np.random.PCG64(seed))
    if sun_dir is None:
        sun_dir = np.array([0.35, 0.25, -0.9])
    sun_dir = sun_dir / np.linalg.norm(sun_dir)
    origins, dirs = _camera_rays(width, height, view, rng)
    n = origins.shape[0]

    radiance = np.zeros(n)
    steps_total = np.zeros(n, dtype=np.int64)
    throughput = np.ones(n)
    active = np.ones(n, dtype=bool)

    for bounce in range(max_bounces + 1):
        if not active.any():
            break
        idx = np.flatnonzero(active)
        o, d = origins[idx], dirs[idx]

        t_ground = intersect_plane(o, d, ground_z)
        t_enter, t_exit = intersect_box(o, d, medium.bounds)
        in_medium = ~np.isnan(t_enter)
        ground_first = ~in_medium | (t_ground < t_enter)

        # ----- surface path: Lambertian ground hit -------------------------
        g_hit = ground_first & ~np.isnan(t_ground)
        if g_hit.any():
            gi = idx[g_hit]
            hit = o[g_hit] + t_ground[g_hit, None] * d[g_hit]
            light_dir = np.broadcast_to(-sun_dir, hit.shape).copy()
            t_to_sun = np.full(hit.shape[0], 1e6)
            shadow = _shadow_transmittance(medium, hit + 1e-4 * light_dir,
                                           light_dir, t_to_sun, rng)
            direct = ground_albedo * (sun_radiance * shadow + ambient)
            radiance[gi] += throughput[gi] * direct
            active[gi] = False

        # ----- volume path --------------------------------------------------
        v_hit = ~ground_first & in_medium
        if not v_hit.any():
            continue
        vi = idx[v_hit]
        vo, vd = o[v_hit], d[v_hit]
        ve, vx = t_enter[v_hit], t_exit[v_hit]

        if mode == "uniform":
            t_sc, trans, steps, scattered = _next_scatter_uniform(
                medium, vo, vd, ve, vx, dt, rng)
        else:
            t_sc, trans, steps, scattered = _next_scatter_ratio(
                medium, vo, vd, ve, vx, rng)
        steps_total[vi] += steps

        # Mutually exclusive Monte Carlo paths (energy conserving):
        #   * a ray that collides inside the medium -> scattering (NEE) or
        #     absorption (path dies);
        #   * a ray that traverses the whole segment -> reaches the ground
        #     carrying unit weight.  The collision probability is already
        #     encoded by the binary delta-tracking outcome (collision vs not),
        #     so no extra transmittance factor may be applied here.
        escaped = ~scattered
        if escaped.any():
            ei = vi[escaped]
            exit_p = vo[escaped] + vx[escaped, None] * vd[escaped]
            tg = intersect_plane(exit_p, vd[escaped], ground_z)
            ok = ~np.isnan(tg)
            e2 = ei[ok]
            # The camera segment's `trans` already carries the full slab
            # attenuation; apply only the ground BRDF and light radiance here
            # so the same medium is never counted twice on a single path.
            direct = ground_albedo * (sun_radiance + ambient)
            w = throughput[e2]
            radiance[e2] += w * direct
            active[e2] = False

        # scattered vertices: next-event estimation + phase bounce
        sc = scattered
        if sc.any():
            si = vi[sc]
            vertex = vo[sc] + t_sc[sc, None] * vd[sc]
            light_dir = np.broadcast_to(-sun_dir, vertex.shape).copy()
            shadow = _shadow_transmittance(medium, vertex, light_dir,
                                           np.full(vertex.shape[0], 1e6), rng)
            # Isotropic phase: the 1/(4pi) phase value times the 4pi solid
            # angle of the ambient environment integrates to one, so the NEE
            # estimate at a collision is throughput * albedo * light.
            radiance[si] += (throughput[si] * medium.albedo *
                             (sun_radiance * shadow + ambient))

            # A collision is absorption (path terminates) with probability
            # 1 - albedo; only surviving scattering vertices continue.
            absorbed = rng.uniform(size=si.shape[0]) >= medium.albedo
            active[si[absorbed]] = False

            # continue the path with a fresh isotropic phase sample
            survivors = ~absorbed
            sv = si[survivors]
            new_dirs = _isotropic(rng, sv.shape[0])
            origins[sv] = vertex[survivors] + 1e-4 * new_dirs
            dirs[sv] = new_dirs
            if mode == "uniform":
                # Continued weight: collision probability appears in the next
                # vertex's nee term, throughput keeps transmittance * albedo.
                throughput[sv] *= medium.albedo
            else:
                throughput[sv] *= medium.albedo
            active[sv] = True

    image = radiance.reshape(height, width)
    step_map = steps_total.reshape(height, width)
    return image, step_map


def render_surface_only(view, width=168, height=168, seed=0,
                        sun_dir=None, sun_radiance=1.0, ambient=0.6,
                        ground_z=0.0, ground_albedo=0.7):
    """Surface-only reference: every camera ray hits the Lambertian ground."""
    rng = np.random.Generator(np.random.PCG64(seed))
    if sun_dir is None:
        sun_dir = np.array([0.35, 0.25, -0.9])
    sun_dir = sun_dir / np.linalg.norm(sun_dir)
    origins, dirs = _camera_rays(width, height, view, rng)
    t_ground = intersect_plane(origins, dirs, ground_z)
    hit = origins + np.nan_to_num(t_ground, nan=0.0)[:, None] * dirs
    light_dir = np.broadcast_to(-sun_dir, hit.shape).copy()
    radiance = ground_albedo * (sun_radiance + ambient)
    image = np.broadcast_to(radiance, (width * height,)).reshape(height, width)
    return image.copy(), np.zeros((height, width), dtype=np.int64)
