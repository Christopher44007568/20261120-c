"""Skin subsurface scattering analysis.

Provides a diffusion profile for skin SSS with per-RGB scatter radii,
performs screen-space blurring of a synthetic face irradiance, validates
translucency differences between a thin ear and a thick cheek, and
compares the diffusion profile against a Gaussian approximation using a
Monte Carlo reference.

Outputs (written to artifacts/):
  sss_profiles.png        diffusion profile vs Gaussian vs MC reference
  sss_blur_comparison.png screen-space blur luminance comparison
  sss_translucency.png    thin-ear vs thick-cheek backlit translucency
  sss_report.json         scatter radii, translucency, luminance errors
"""

import json
import os

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Skin optical properties (1/mm), typical fair skin.
# ---------------------------------------------------------------------------
SIGMA_S_PRIME = np.array([0.74, 0.88, 1.01])   # reduced scattering, RGB
SIGMA_A = np.array([0.032, 0.170, 0.480])      # absorption, RGB
ETA = 1.4                                       # relative index of refraction
CHANNELS = ("R", "G", "B")
LUMA = np.array([0.2126, 0.7152, 0.0722])       # Rec. 709 luma weights

ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")

EAR_THICKNESS_MM = 2.0
CHEEK_THICKNESS_MM = 12.0


def boundary_constant(eta):
    """Fresnel boundary constant A for the dipole (Jensen 2001)."""
    f_dr = -1.44 / eta**2 + 0.71 / eta + 0.668 + 0.0636 * eta
    return (1.0 + f_dr) / (1.0 - f_dr) ** 2


def diffusion_params(sigma_a, sigma_sp):
    """Return (sigma_t_prime, alpha_prime, sigma_tr, l_d, D, A)."""
    sigma_tp = sigma_a + sigma_sp
    alpha_p = sigma_sp / sigma_tp
    sigma_tr = np.sqrt(3.0 * sigma_a * sigma_tp)
    l_d = 1.0 / sigma_tr
    D = 1.0 / (3.0 * sigma_tp)
    A = boundary_constant(ETA)
    return sigma_tp, alpha_p, sigma_tr, l_d, D, A


def dipole_profile(r, sigma_a, sigma_sp):
    """Jensen et al. (2001) dipole diffusion reflectance profile R(r) [1/mm^2]."""
    sigma_tp, alpha_p, sigma_tr, _, _, A = diffusion_params(sigma_a, sigma_sp)
    z_r = 1.0 / sigma_tp
    z_v = z_r * (1.0 + 4.0 / 3.0 * A)
    d_r = np.sqrt(r * r + z_r * z_r)
    d_v = np.sqrt(r * r + z_v * z_v)
    R = alpha_p / (4.0 * np.pi) * (
        z_r * (sigma_tr * d_r + 1.0) * np.exp(-sigma_tr * d_r) / d_r**3
        + z_v * (sigma_tr * d_v + 1.0) * np.exp(-sigma_tr * d_v) / d_v**3
    )
    return R


def profile_second_moment(r, R):
    """<r^2> of a radially symmetric profile sampled on r."""
    w = 2.0 * np.pi * r
    norm = np.trapezoid(R * w, r)
    m2 = np.trapezoid(R * r * r * w, r)
    return m2 / norm


def gaussian_profile(r, sigma):
    return np.exp(-r * r / (2.0 * sigma * sigma)) / (2.0 * np.pi * sigma * sigma)


# ---------------------------------------------------------------------------
# Monte Carlo reference: vectorized photon random walk (isotropic scattering
# with the reduced scattering coefficient, Fresnel boundary at eta).
# ---------------------------------------------------------------------------
def _fresnel_reflectance(cos_i, eta):
    """Unpolarized Fresnel reflectance; cos_i measured in the denser medium."""
    sin_t2 = eta * eta * (1.0 - cos_i * cos_i)
    tir = sin_t2 >= 1.0
    cos_t = np.sqrt(np.maximum(0.0, 1.0 - np.minimum(sin_t2, 1.0)))
    rs = ((eta * cos_i - cos_t) / (eta * cos_i + cos_t)) ** 2
    rp = ((eta * cos_t - cos_i) / (eta * cos_t + cos_i)) ** 2
    r = 0.5 * (rs + rp)
    return np.where(tir, 1.0, r)


def mc_random_walk(sigma_a, sigma_sp, thickness_mm, n_photons, rng,
                   rr_threshold=1e-4, rr_chance=0.1):
    """Simulate photons entering a slab (thickness_mm; np.inf = half-space).

    Returns (reflect_r_mm, reflect_w, transmit_r_mm, transmit_w):
    exit radii and weights of photons leaving through the entry / far side.
    """
    sigma_t = sigma_a + sigma_sp
    albedo = sigma_sp / sigma_t
    inv_eta = 1.0 / ETA

    n = n_photons
    pos = np.zeros((n, 3))
    # Collimated normal incidence; refracted straight in, weight reduced.
    dirv = np.tile(np.array([0.0, 0.0, 1.0]), (n, 1))
    weight = np.full(n, 1.0 - _fresnel_reflectance(np.array([1.0]), ETA)[0])
    alive = np.ones(n, dtype=bool)

    refl_r, refl_w, trans_r, trans_w = [], [], [], []

    while True:
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        m = idx.size
        step = -np.log(1.0 - rng.random(m)) / sigma_t
        pos[idx] += dirv[idx] * step[:, None]
        z = pos[idx, 2]

        # Boundary crossings.
        hit_back = z < 0.0
        hit_front = z > thickness_mm
        for hit, sign, acc_r, acc_w in ((hit_back, -1.0, refl_r, refl_w),
                                        (hit_front, 1.0, trans_r, trans_w)):
            if not np.any(hit):
                continue
            hidx = idx[hit]
            # Move photon back to the boundary plane.
            overshoot = np.where(sign < 0, -pos[hidx, 2], pos[hidx, 2] - thickness_mm)
            mu = np.abs(dirv[hidx, 2])
            mu = np.maximum(mu, 1e-6)
            pos[hidx] -= dirv[hidx] * (overshoot / mu)[:, None]
            r_fres = _fresnel_reflectance(mu, inv_eta)
            w = weight[hidx]
            rad = np.hypot(pos[hidx, 0], pos[hidx, 1])
            acc_r.append(rad)
            acc_w.append(w * (1.0 - r_fres))
            # Reflected fraction continues inside, mirrored.
            weight[hidx] = w * r_fres
            dirv[hidx, 2] *= -1.0
            pos[hidx, 2] = np.clip(pos[hidx, 2], 0.0, thickness_mm)

        # Absorption (analog via weight) and isotropic scattering.
        weight[idx] *= albedo
        cos_t = 2.0 * rng.random(m) - 1.0
        sin_t = np.sqrt(np.maximum(0.0, 1.0 - cos_t * cos_t))
        phi = 2.0 * np.pi * rng.random(m)
        ux, uy, uz = dirv[idx, 0], dirv[idx, 1], dirv[idx, 2]
        # Build orthonormal basis around current direction.
        ax = np.where(np.abs(uz) < 0.9, np.ones(m), np.zeros(m))
        ay = 1.0 - ax
        # t1 = normalize(cross(dir, a)), a = (ax, ay, 0)
        c1x = uy * 0.0 - uz * ay
        c1y = uz * ax - ux * 0.0
        c1z = ux * ay - uy * ax
        n1 = np.sqrt(c1x * c1x + c1y * c1y + c1z * c1z)
        n1 = np.maximum(n1, 1e-12)
        t1x, t1y, t1z = c1x / n1, c1y / n1, c1z / n1
        t2x = uy * t1z - uz * t1y
        t2y = uz * t1x - ux * t1z
        t2z = ux * t1y - uy * t1x
        sp, cp = sin_t * np.cos(phi), sin_t * np.sin(phi)
        dirv[idx, 0] = sp * t1x + cp * t2x + cos_t * ux
        dirv[idx, 1] = sp * t1y + cp * t2y + cos_t * uy
        dirv[idx, 2] = sp * t1z + cp * t2z + cos_t * uz

        # Russian roulette.
        low = weight[idx] < rr_threshold
        if np.any(low):
            lidx = idx[low]
            survive = rng.random(lidx.size) < rr_chance
            weight[lidx[survive]] /= rr_chance
            alive[lidx[~survive]] = False

    def _gather(acc_r, acc_w):
        if not acc_r:
            return np.empty(0), np.empty(0)
        return np.concatenate(acc_r), np.concatenate(acc_w)

    rr_, rw_ = _gather(refl_r, refl_w)
    tr_, tw_ = _gather(trans_r, trans_w)
    return rr_, rw_, tr_, tw_


def mc_profile(r_exit, w_exit, r_edges):
    """Histogram exit radii into a radial profile R(r) [1/mm^2]."""
    counts, _ = np.histogram(r_exit, bins=r_edges, weights=w_exit)
    r_c = 0.5 * (r_edges[:-1] + r_edges[1:])
    ring_area = np.pi * (r_edges[1:] ** 2 - r_edges[:-1] ** 2)
    return r_c, counts / ring_area


def smooth_mc_profile(r, R, window=9, poly=2):
    """Lightly smooth a noisy MC radial profile in log space."""
    from scipy.signal import savgol_filter
    floor = max(float(np.max(R)) * 1e-7, 1e-12)
    logR = np.log10(np.maximum(R, floor))
    w_ = min(window, len(R) // 2 * 2 - 1)
    if w_ <= poly:
        return R
    sm = savgol_filter(logR, w_, poly)
    # Keep the measured total energy.
    out = 10.0 ** sm
    norm = np.trapezoid(R * 2 * np.pi * r, r)
    s_norm = np.trapezoid(out * 2 * np.pi * r, r)
    if s_norm > 0:
        out *= norm / s_norm
    return out


# ---------------------------------------------------------------------------
# Diffusion-theory slab transmission profile T(r, d) via the image series
# (extrapolated boundary conditions, isotropic point source at z0 = 1/sigma_t').
# ---------------------------------------------------------------------------
def slab_transmission_profile(r, d, sigma_a, sigma_sp, n_images=12):
    """Transmitted current profile T(r, d) [1/mm^2] through a slab of
    thickness d for a normally incident pencil beam (diffusion theory)."""
    sigma_tp, _, sigma_tr, _, D, A = diffusion_params(sigma_a, sigma_sp)
    z0 = 1.0 / sigma_tp
    z_b = 2.0 * A * D
    L = d + 2.0 * z_b
    T = np.zeros_like(r, dtype=float)
    for k in range(-n_images, n_images + 1):
        # Positive sources and negative image sources.
        z_pos = z0 + 2.0 * k * L
        z_neg = -z0 - 2.0 * z_b + 2.0 * k * L
        for z_s, sign in ((z_pos, 1.0), (z_neg, -1.0)):
            dz = d - z_s
            rho = np.sqrt(r * r + dz * dz)
            rho = np.maximum(rho, 1e-9)
            # Current through plane z=d: J = -D dPhi/dz with
            # Phi = exp(-sigma_tr rho) / (4 pi D rho).
            T += sign * dz * (sigma_tr * rho + 1.0) * np.exp(-sigma_tr * rho) \
                / (4.0 * np.pi * rho**3)
    return np.maximum(T, 0.0)


def slab_transmission_total(d, sigma_a, sigma_sp):
    """Total diffuse transmittance of a slab (1D diffusion, laterally
    infinite) -- used for the scalar translucency output."""
    sigma_tp, _, sigma_tr, _, D, A = diffusion_params(sigma_a, sigma_sp)
    z0 = 1.0 / sigma_tp
    z_b = 2.0 * A * D
    mu = sigma_tr
    num = np.sinh(mu * (z0 + z_b)) * np.cosh(mu * z_b)
    den = np.sinh(mu * (d + 2.0 * z_b))
    return num / den


# ---------------------------------------------------------------------------
# Screen-space blurring helpers.
# ---------------------------------------------------------------------------
def make_kernel(profile_r, profile_R, shape, mm_per_px):
    """Sample a radial profile onto a centered 2D FFT kernel grid and
    normalize it to unit sum (energy conserving)."""
    h, w = shape
    fy = (np.arange(h) - h // 2) * mm_per_px
    fx = (np.arange(w) - w // 2) * mm_per_px
    rr = np.sqrt(fy[:, None] ** 2 + fx[None, :] ** 2)
    k = np.interp(rr, profile_r, profile_R, left=profile_R[0], right=0.0)
    k = np.fft.ifftshift(k)
    s = k.sum()
    if s > 0:
        k /= s
    return k


def fft_convolve(img, kernel):
    return np.real(np.fft.ifft2(np.fft.fft2(img) * np.fft.fft2(kernel)))


def make_face_irradiance(shape, mm_per_px):
    """Synthetic frontal irradiance: head silhouette with a nose shadow
    seam, plus a thin protruding ear on the left side."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    cx, cy = w * 0.55, h * 0.52
    head = ((xx - cx) / (0.30 * w)) ** 2 + ((yy - cy) / (0.38 * h)) ** 2 <= 1.0
    # Thin ear: narrow ellipse protruding from the left of the head.
    ear_cx = cx - 0.30 * w
    ear = ((xx - ear_cx) / (0.055 * w)) ** 2 + ((yy - cy) / (0.13 * h)) ** 2 <= 1.0
    mask = head | ear
    irradiance = mask.astype(float)
    # Nose shadow seam: a dark vertical line slightly right of center.
    seam = (np.abs(xx - (cx + 0.02 * w)) < 1.5) & head
    irradiance[seam] = 0.02
    # Soft shading falloff toward the silhouette.
    dist_head = np.sqrt(((xx - cx) / (0.30 * w)) ** 2 + ((yy - cy) / (0.38 * h)) ** 2)
    shade = np.clip(1.15 - 0.35 * dist_head, 0.55, 1.0)
    irradiance *= np.where(mask, shade, 0.0)
    return irradiance, mask


def thin_edge_band(mask, width_px=6):
    """Band of pixels just inside the silhouette boundary."""
    from scipy.ndimage import binary_erosion
    inner = binary_erosion(mask, iterations=width_px)
    return mask & ~inner


# ---------------------------------------------------------------------------
# Main analysis.
# ---------------------------------------------------------------------------
IMG_SHAPE = (256, 256)
MM_PER_PX = 0.5
N_PHOTONS = 1_500_000


def luminance(rgb):
    return rgb @ LUMA


def error_metrics(estimate, reference, region):
    diff = (estimate - reference)[region]
    ref = reference[region]
    rmse = float(np.sqrt(np.mean(diff * diff)))
    max_abs = float(np.max(np.abs(diff)))
    denom = float(np.sqrt(np.mean(ref * ref)))
    rel = rmse / denom if denom > 0 else 0.0
    return {"rmse": rmse, "max_abs": max_abs, "rel_rmse": rel}


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    rng = np.random.default_rng(20261120)

    # ---- 1. Diffusion profile, per-RGB scatter radii, Gaussian match ------
    r_fine = np.linspace(0.0, 25.0, 4001)
    r_edges = np.linspace(0.0, 25.0, 251)
    profiles = {}
    mc_reflectance = {}
    for c, sa, ssp in zip(CHANNELS, SIGMA_A, SIGMA_S_PRIME):
        _, _, _, l_d, _, _ = diffusion_params(sa, ssp)
        R_diff = dipole_profile(r_fine, sa, ssp)
        sigma_g = np.sqrt(0.5 * profile_second_moment(r_fine, R_diff))
        R_gauss = gaussian_profile(r_fine, sigma_g)

        rr, rw, _, _ = mc_random_walk(sa, ssp, np.inf, N_PHOTONS, rng)
        rw = rw / N_PHOTONS
        r_mc, R_mc = mc_profile(rr, rw, r_edges)
        R_mc = smooth_mc_profile(r_mc, R_mc)
        mc_reflectance[c] = float(rw.sum())

        profiles[c] = {
            "l_d": float(l_d), "sigma_g": float(sigma_g),
            "r": r_fine, "diffusion": R_diff, "gaussian": R_gauss,
            "r_mc": r_mc, "mc": R_mc,
        }
        print(f"[{c}] l_d={l_d:.4f} mm  sigma_g={sigma_g:.4f} mm  "
              f"Rd_mc={mc_reflectance[c]:.4f}")

    # ---- 2. Screen-space blur of the synthetic face irradiance ------------
    irradiance, face_mask = make_face_irradiance(IMG_SHAPE, MM_PER_PX)
    blurred = {"diffusion": np.zeros(IMG_SHAPE + (3,)),
               "gaussian": np.zeros(IMG_SHAPE + (3,)),
               "mc": np.zeros(IMG_SHAPE + (3,))}
    for i, c in enumerate(CHANNELS):
        p = profiles[c]
        for name, key in (("diffusion", "diffusion"), ("gaussian", "gaussian")):
            k = make_kernel(p["r"], p[key], IMG_SHAPE, MM_PER_PX)
            blurred[name][:, :, i] = fft_convolve(irradiance, k)
        k = make_kernel(p["r_mc"], p["mc"], IMG_SHAPE, MM_PER_PX)
        blurred["mc"][:, :, i] = fft_convolve(irradiance, k)

    luma_mc = luminance(blurred["mc"])
    luma_diff = luminance(blurred["diffusion"])
    luma_gauss = luminance(blurred["gaussian"])

    edge_band = thin_edge_band(face_mask, width_px=6)
    lum_err = {
        "full_head": {
            "diffusion": error_metrics(luma_diff, luma_mc, face_mask),
            "gaussian": error_metrics(luma_gauss, luma_mc, face_mask),
        },
        "thin_edge": {
            "diffusion": error_metrics(luma_diff, luma_mc, edge_band),
            "gaussian": error_metrics(luma_gauss, luma_mc, edge_band),
        },
    }

    # ---- 3. Translucency: thin ear (2 mm) vs thick cheek (12 mm) ---------
    from scipy.ndimage import binary_erosion

    h, w = IMG_SHAPE
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    ear_mask = ((xx - 0.22 * w) / (0.09 * w)) ** 2 \
        + ((yy - 0.5 * h) / (0.22 * h)) ** 2 <= 1.0
    cheek_mask = ((xx - 0.62 * w) / (0.20 * w)) ** 2 \
        + ((yy - 0.52 * h) / (0.26 * h)) ** 2 <= 1.0
    regions = {"thin_ear": (ear_mask, EAR_THICKNESS_MM),
               "thick_cheek": (cheek_mask, CHEEK_THICKNESS_MM)}

    # Transmission profiles per channel and thickness.
    trans_profiles = {}
    for c, sa, ssp in zip(CHANNELS, SIGMA_A, SIGMA_S_PRIME):
        trans_profiles[c] = {}
        for label, d in (("ear", EAR_THICKNESS_MM), ("cheek", CHEEK_THICKNESS_MM)):
            T_diff = slab_transmission_profile(r_fine, d, sa, ssp)
            T_tot = slab_transmission_total(d, sa, ssp)
            sigma_t = np.sqrt(0.5 * profile_second_moment(r_fine, T_diff))
            T_gauss = T_tot * gaussian_profile(r_fine, sigma_t)
            _, _, tr, tw = mc_random_walk(sa, ssp, d, N_PHOTONS, rng)
            tw = tw / N_PHOTONS
            r_mc, T_mc = mc_profile(tr, tw, r_edges)
            T_mc = smooth_mc_profile(r_mc, T_mc)
            trans_profiles[c][label] = {
                "diffusion": T_diff, "gaussian": T_gauss, "mc": (r_mc, T_mc),
                "total_diffusion": float(T_tot),
                "total_mc": float(tw.sum()),
                "sigma_t": float(sigma_t),
            }
        print(f"[{c}] T(ear): diff={trans_profiles[c]['ear']['total_diffusion']:.4f} "
              f"mc={trans_profiles[c]['ear']['total_mc']:.4f}  "
              f"T(cheek): diff={trans_profiles[c]['cheek']['total_diffusion']:.4f} "
              f"mc={trans_profiles[c]['cheek']['total_mc']:.4f}")

    # Backlit luminance images: blur each region mask with the matching
    # transmission kernel and sum regions.
    backlit = {"diffusion": np.zeros(IMG_SHAPE + (3,)),
               "gaussian": np.zeros(IMG_SHAPE + (3,)),
               "mc": np.zeros(IMG_SHAPE + (3,))}
    for i, c in enumerate(CHANNELS):
        for label, (mask_r, _) in (("ear", regions["thin_ear"]),
                                   ("cheek", regions["thick_cheek"])):
            tp = trans_profiles[c][label]
            src = mask_r.astype(float)
            k = make_kernel(r_fine, tp["diffusion"], IMG_SHAPE, MM_PER_PX)
            backlit["diffusion"][:, :, i] += \
                tp["total_diffusion"] * fft_convolve(src, k)
            k = make_kernel(r_fine, tp["gaussian"], IMG_SHAPE, MM_PER_PX)
            backlit["gaussian"][:, :, i] += \
                tp["total_diffusion"] * fft_convolve(src, k)
            k = make_kernel(tp["mc"][0], tp["mc"][1], IMG_SHAPE, MM_PER_PX)
            backlit["mc"][:, :, i] += tp["total_mc"] * fft_convolve(src, k)

    back_luma = {k: luminance(v) for k, v in backlit.items()}

    # Scalar translucency = mean luminance over the region interior.
    translucency = {}
    for name, (mask_r, _) in regions.items():
        interior = binary_erosion(mask_r, iterations=8)
        translucency[name] = {
            "reference_mc": float(back_luma["mc"][interior].mean()),
            "diffusion": float(back_luma["diffusion"][interior].mean()),
            "gaussian": float(back_luma["gaussian"][interior].mean()),
        }
    translucency["ear_to_cheek_ratio"] = {
        k: translucency["thin_ear"][k] / translucency["thick_cheek"][k]
        for k in ("reference_mc", "diffusion", "gaussian")
    }

    # Luminance error in the backlit thin-edge band around the ear.
    from scipy.ndimage import binary_dilation
    ear_band = binary_dilation(ear_mask, iterations=6) & ~binary_erosion(ear_mask, iterations=6)
    lum_err["backlit_thin_edge"] = {
        "diffusion": error_metrics(back_luma["diffusion"], back_luma["mc"], ear_band),
        "gaussian": error_metrics(back_luma["gaussian"], back_luma["mc"], ear_band),
    }

    # ---- 4. Plots ----------------------------------------------------------
    colors = {"R": "tab:red", "G": "tab:green", "B": "tab:blue"}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    fig.suptitle("Diffusion profile vs Gaussian vs Monte Carlo reference")
    for ax, c in zip(axes, CHANNELS):
        p = profiles[c]
        ax.semilogy(p["r_mc"], np.maximum(p["mc"], 1e-6), "k-", lw=1.6,
                    label="MC reference")
        ax.semilogy(p["r"], p["diffusion"], color=colors[c], lw=1.8,
                    label="diffusion profile")
        ax.semilogy(p["r"], p["gaussian"], "--", color=colors[c], lw=1.4,
                    alpha=0.6, label="Gaussian approx")
        ax.set_title(f"{c}  (l_d={p['l_d']:.2f} mm)")
        ax.set_xlabel("r (mm)")
        ax.set_xlim(0, 12)
        ax.set_ylim(1e-6, 3.0)
        if c == "R":
            ax.set_ylabel("R(r)  [1/mm^2]")
            ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(ARTIFACTS, "sss_profiles.png"), dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14, 8.6))
    fig.suptitle("Screen-space SSS blur: luminance comparison")
    panels = [
        (irradiance, "frontal irradiance", (0, 0), 1.0),
        (luma_mc, "MC reference blur", (0, 1), 1.0),
        (luma_diff, "diffusion profile blur", (0, 2), 1.0),
        (luma_gauss, "Gaussian approx blur", (1, 0), 1.0),
        (np.abs(luma_diff - luma_mc), "|diffusion - MC|", (1, 1), None),
        (np.abs(luma_gauss - luma_mc), "|Gaussian - MC|", (1, 2), None),
    ]
    for img, title, (r_, c_), vmax in panels:
        ax = axes[r_, c_]
        im = ax.imshow(img, cmap="inferno", vmin=0.0,
                       vmax=vmax if vmax else img.max())
        ax.set_title(title, fontsize=10)
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(os.path.join(ARTIFACTS, "sss_blur_comparison.png"), dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
    fig.suptitle(f"Translucency: thin ear ({EAR_THICKNESS_MM:.0f} mm) vs "
                 f"thick cheek ({CHEEK_THICKNESS_MM:.0f} mm)")
    vmax = max(back_luma["mc"].max(), 1e-6)
    for ax, key, title in (
            (axes[0], "mc", "backlit luminance: MC reference"),
            (axes[1], "diffusion", "backlit luminance: diffusion"),
            (axes[2], "gaussian", "backlit luminance: Gaussian")):
        ax.imshow(back_luma[key], cmap="inferno", vmin=0.0, vmax=vmax)
        ax.axhline(h // 2, color="c", lw=0.5, alpha=0.6)
        ax.set_title(title, fontsize=9)
        ax.axis("off")
    x_mm = (np.arange(w) - w / 2) * MM_PER_PX
    axes[3].plot(x_mm, back_luma["mc"][h // 2], "k-", lw=1.6, label="MC reference")
    axes[3].plot(x_mm, back_luma["diffusion"][h // 2], "r-", lw=1.4, label="diffusion")
    axes[3].plot(x_mm, back_luma["gaussian"][h // 2], "b--", lw=1.2, label="Gaussian")
    axes[3].set_title("slice through ear & cheek", fontsize=9)
    axes[3].set_xlabel("x (mm)")
    axes[3].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(ARTIFACTS, "sss_translucency.png"), dpi=130)
    plt.close(fig)

    # ---- 5. Report ------------------------------------------------------
    report = {
        "scatter_radii_mm": {c: round(profiles[c]["l_d"], 4) for c in CHANNELS},
        "gaussian_sigma_mm": {c: round(profiles[c]["sigma_g"], 4) for c in CHANNELS},
        "mc_diffuse_reflectance": {c: round(mc_reflectance[c], 4) for c in CHANNELS},
        "translucency": {
            name: {k: round(v, 5) for k, v in vals.items()}
            for name, vals in translucency.items()
        },
        "luminance_error": lum_err,
        "conclusions": {
            "thin_edge_more_natural":
                lum_err["thin_edge"]["diffusion"]["rmse"]
                < lum_err["thin_edge"]["gaussian"]["rmse"],
            "backlit_thin_edge_more_natural":
                lum_err["backlit_thin_edge"]["diffusion"]["rmse"]
                < lum_err["backlit_thin_edge"]["gaussian"]["rmse"],
            "ear_brighter_than_cheek":
                translucency["thin_ear"]["diffusion"]
                > translucency["thick_cheek"]["diffusion"],
        },
    }
    with open(os.path.join(ARTIFACTS, "sss_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
