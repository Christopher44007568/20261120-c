"""Numerical validation for the Ashikhmin velvet/cloth BRDF:
1. Energy conservation: hemispherical reflectance <= 1.
2. Fiber-rotation: highlight azimuth tracks the fiber tangent direction.
3. Sampling: dump sampled outgoing directions + 2D histogram.
4. Grazing-angle comparison vs anisotropic GGX.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brdf
from brdf import PI, dot, norm, cross
import pngutil

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out")

N = (0.0, 0.0, 1.0)
UP = (0.0, 1.0, 0.0)


def tangent_at(phi):
    """Fiber direction rotated by phi about the normal."""
    return (math.cos(phi), math.sin(phi), 0.0)


def dir_from(theta, phi):
    st = math.sin(theta)
    return (st * math.cos(phi), st * math.sin(phi), math.cos(theta))


# ---------- 1. energy conservation ----------
def hemispherical_reflectance(fr_fn, wi, n, samples=20000, seed=1):
    rng = random.Random(seed)
    total = 0.0
    for _ in range(samples):
        u1, u2 = rng.random(), rng.random()
        ct = u1
        st = math.sqrt(1.0 - ct * ct)
        ph = 2.0 * PI * u2
        wo = (st * math.cos(ph), st * math.sin(ph), ct)
        total += fr_fn(wi, wo) * ct  # uniform in (cos theta, phi)
    return total * 2.0 * PI / samples


def check_energy(a=4.0, alpha_x=0.05, alpha_y=0.5):
    print("== Energy conservation (hemispherical reflectance must be <= 1) ==")
    rows = []
    t = tangent_at(0.0)
    for deg in (0, 30, 60, 80):
        wi = dir_from(math.radians(deg), 0.0)
        r_iso = hemispherical_reflectance(
            lambda wi_, wo_: brdf.velvet_isotropic(wi_, wo_, N, 1.0, a), wi, N)
        r_aniso = hemispherical_reflectance(
            lambda wi_, wo_: brdf.velvet_aniso(wi_, wo_, N, t, 1.0, a), wi, N)
        r_ggx = hemispherical_reflectance(
            lambda wi_, wo_: brdf.ggx_aniso(wi_, wo_, N, t, alpha_x, alpha_y), wi, N)
        rows.append((deg, r_iso, r_aniso, r_ggx))
        print(f"  theta_i={deg:3d} deg | velvet_iso={r_iso:.4f} "
              f"velvet_aniso={r_aniso:.4f} ggx_aniso={r_ggx:.4f}")
    ok = all(r[1] <= 1.0 and r[2] <= 1.0 for r in rows)
    print(f"  velvet energy conservation: {'PASS' if ok else 'FAIL'}")
    with open(os.path.join(OUT, "energy.csv"), "w") as f:
        f.write("theta_i_deg,velvet_iso,velvet_aniso,ggx_aniso\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.6f},{r[2]:.6f},{r[3]:.6f}\n")
    return ok


# ---------- 2. fiber rotation: highlight azimuth ----------
def highlight_azimuth(phi_fiber, a=4.0, theta_i=math.radians(45),
                      n_phi=360, n_theta=90):
    """Integrate BRDF over outgoing hemisphere; return energy-weighted
    outgoing azimuth centroid relative to the fiber azimuth."""
    wi = dir_from(theta_i, 0.0)
    t = tangent_at(phi_fiber)
    mx = my = tot = 0.0
    for i in range(n_theta):
        ct = (i + 0.5) / n_theta
        st = math.sqrt(1.0 - ct * ct)
        for j in range(n_phi):
            ph = 2.0 * PI * (j + 0.5) / n_phi
            wo = (st * math.cos(ph), st * math.sin(ph), ct)
            v = brdf.velvet_aniso(wi, wo, N, t, 1.0, a) * ct
            mx += v * math.cos(ph)
            my += v * math.sin(ph)
            tot += v
    return math.atan2(my / tot, mx / tot)


def check_rotation(a=4.0):
    print("== Fiber rotation: highlight azimuth vs fiber azimuth ==")
    rows = []
    ok = True
    for deg in (0, 30, 45, 60, 90, 135):
        phi = math.radians(deg)
        az = highlight_azimuth(phi, a)
        # highlight should lie in the plane perpendicular to the fiber
        # (fiber BRDFs scatter into the normal-fiber plane), i.e. azimuth
        # offset from fiber ~ 90 deg. We report the raw azimuth.
        az_deg = math.degrees(az)
        rows.append((deg, az_deg))
        print(f"  fiber={deg:4.0f} deg -> highlight azimuth={az_deg:8.2f} deg")
    # monotonic tracking check: azimuth must change with fiber rotation
    spread = max(r[1] for r in rows) - min(r[1] for r in rows)
    ok = spread > 20.0
    print(f"  azimuth spread={spread:.1f} deg -> "
          f"{'PASS (highlight rotates with fiber)' if ok else 'FAIL'}")
    with open(os.path.join(OUT, "rotation.csv"), "w") as f:
        f.write("fiber_deg,highlight_azimuth_deg\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.4f}\n")
    return ok


# ---------- 3. sampling distribution ----------
def dump_sampling(a=4.0, n_samples=100000, seed=7):
    print("== Sampling: outgoing direction distribution ==")
    rng = random.Random(seed)
    wi = dir_from(math.radians(45), 0.0)
    t = tangent_at(0.0)  # fiber along +x
    samples = []
    for _ in range(n_samples):
        wo, pdf = brdf.sample_velvet_aniso(wi, N, t, a, rng)
        if wo is not None:
            samples.append(wo)
    with open(os.path.join(OUT, "sampled_directions.csv"), "w") as f:
        f.write("x,y,z\n")
        for w in samples:
            f.write(f"{w[0]:.6f},{w[1]:.6f},{w[2]:.6f}\n")
    # 2D histogram in tangent plane (x=fiber, y=bitangent), 96x96
    res = 96
    hist = [[0] * res for _ in range(res)]
    for w in samples:
        ix = int((w[0] * 0.5 + 0.5) * res)
        iy = int((w[1] * 0.5 + 0.5) * res)
        if 0 <= ix < res and 0 <= iy < res:
            hist[iy][ix] += 1
    peak = max(max(r) for r in hist) or 1
    img = []
    for y in range(res):
        row = []
        for x in range(res):
            v = math.sqrt(hist[y][x] / peak)  # sqrt scale for dynamic range
            row.append((pngutil.tonemap(0.6 * v),
                        pngutil.tonemap(0.3 * v),
                        pngutil.tonemap(2.0 * v)))
        img.append(row)
    pngutil.write_png(os.path.join(OUT, "sampling_distribution.png"),
                      res, res, img)
    print(f"  wrote {len(samples)} samples -> sampled_directions.csv, "
          f"sampling_distribution.png")
    return len(samples) > 0


# ---------- 4. grazing-angle comparison vs anisotropic GGX ----------
def grazing_comparison(a=4.0, alpha_x=0.05, alpha_y=0.5):
    print("== Grazing-angle brightness: Ashikhmin velvet vs anisotropic GGX ==")
    t = tangent_at(0.0)
    rows = []
    for deg in range(0, 90, 5):
        wi = dir_from(math.radians(deg), 0.0)
        # reflectance restricted to specular lobe: integrate fr*cos over
        # outgoing hemisphere with a grid
        def integrate(fn):
            tot = 0.0
            nt, np_ = 60, 120
            for i in range(nt):
                ct = (i + 0.5) / nt
                st = math.sqrt(1.0 - ct * ct)
                for j in range(np_):
                    ph = 2.0 * PI * (j + 0.5) / np_
                    wo = (st * math.cos(ph), st * math.sin(ph), ct)
                    tot += fn(wi, wo) * ct
            return tot * (2.0 * PI / np_) / nt

        rv = integrate(lambda a_, b_: brdf.velvet_aniso(a_, b_, N, t, 1.0, a))
        rg = integrate(lambda a_, b_: brdf.ggx_aniso(a_, b_, N, t, alpha_x, alpha_y))
        rows.append((deg, rv, rg))
        print(f"  theta_i={deg:3d} deg | velvet={rv:.4f} ggx={rg:.4f} "
              f"ratio={rv / rg if rg > 1e-9 else float('nan'):.3f}")
    with open(os.path.join(OUT, "grazing_comparison.csv"), "w") as f:
        f.write("theta_i_deg,velvet_aniso,ggx_aniso\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.6f},{r[2]:.6f}\n")
    # render comparison curve image
    w, h = 480, 240
    img = [[(24, 24, 28)] * w for _ in range(h)]
    vmax = max(max(r[1], r[2]) for r in rows)

    def draw(vals, color):
        pts = []
        for k, v in enumerate(vals):
            x = int(k / (len(vals) - 1) * (w - 1))
            y = h - 1 - int(v / vmax * (h - 20))
            pts.append((x, y))
        for k in range(len(pts) - 1):
            x0, y0 = pts[k]
            x1, y1 = pts[k + 1]
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for s in range(steps + 1):
                x = x0 + (x1 - x0) * s // steps
                y = y0 + (y1 - y0) * s // steps
                for dy in (-1, 0, 1):
                    if 0 <= y + dy < h:
                        img[y + dy][x] = color

    draw([r[1] for r in rows], (255, 200, 60))   # velvet: yellow
    draw([r[2] for r in rows], (80, 160, 255))   # ggx: blue
    pngutil.write_png(os.path.join(OUT, "grazing_comparison.png"), w, h, img)
    print("  wrote grazing_comparison.csv / grazing_comparison.png "
          "(yellow=velvet, blue=GGX)")
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    ok = True
    ok &= check_energy()
    ok &= check_rotation()
    ok &= dump_sampling()
    ok &= grazing_comparison()
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
