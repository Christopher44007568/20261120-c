"""Water-surface caustics via normal-based refraction and energy splatting."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

N_AIR, N_WATER = 1.0, 1.33

# (amplitude, kx, ky, omega, phase)
WAVES = [
    (0.055, 1.9, 0.4, 1.6, 0.0),
    (0.040, -1.1, 1.5, 2.3, 1.3),
    (0.030, 3.1, -2.2, 3.1, 2.1),
    (0.018, -4.0, -3.0, 4.2, 0.7),
    (0.012, 5.5, 1.0, 5.0, 4.0),
    (0.008, 9.0, 4.0, 6.0, 1.0),
    (0.006, -12.0, 7.0, 7.5, 2.5),
    (0.004, 16.0, -9.0, 9.0, 3.5),
    (0.003, -20.0, -14.0, 11.0, 5.0),
]


def height_field(res, t, extent=4.0):
    x = np.linspace(-extent, extent, res)
    xx, yy = np.meshgrid(x, x, indexing="xy")
    h = np.zeros_like(xx)
    for amp, kx, ky, om, ph in WAVES:
        h += amp * np.sin(kx * xx + ky * yy - om * t + ph)
    return xx, yy, h


def surface_normals(h, dx):
    dhy, dhx = np.gradient(h, dx)
    inv = 1.0 / np.sqrt(dhx**2 + dhy**2 + 1.0)
    return -dhx * inv, -dhy * inv, inv


def refract(inc, nrm, eta):
    """GLSL-style refraction; inc points toward the surface."""
    ix, iy, iz = inc
    nx, ny, nz = nrm
    dot_ni = nx * ix + ny * iy + nz * iz
    k = np.maximum(1.0 - eta * eta * (1.0 - dot_ni**2), 0.0)
    f = eta * dot_ni + np.sqrt(k)
    return eta * ix - f * nx, eta * iy - f * ny, eta * iz - f * nz


def bilinear_upsample(field, fine):
    """Upsample a coarse grid to fine x fine by bilinear interpolation."""
    coarse = field.shape[0]
    pos = np.linspace(0, coarse - 1, fine)
    i0 = np.floor(pos).astype(int)
    i1 = np.minimum(i0 + 1, coarse - 1)
    f = (pos - i0)[None, :]
    top = field[i0][:, i0] * (1 - f) + field[i0][:, i1] * f
    bot = field[i1][:, i0] * (1 - f) + field[i1][:, i1] * f
    g = f.T
    return top * (1 - g) + bot * g


def bilinear_splat(px, py, res, lim):
    """Deposit unit energy per ray into 4 neighboring bins (conserving)."""
    grid = np.zeros((res, res))
    u = (px + lim) / (2 * lim) * (res - 1)
    v = (py + lim) / (2 * lim) * (res - 1)
    i0 = np.floor(u).astype(int)
    j0 = np.floor(v).astype(int)
    fu, fv = u - i0, v - j0
    ok = (i0 >= 0) & (i0 < res - 1) & (j0 >= 0) & (j0 < res - 1)
    i0, j0, fu, fv = i0[ok], j0[ok], fu[ok], fv[ok]
    for di, dj, w in ((0, 0, (1 - fu) * (1 - fv)), (1, 0, fu * (1 - fv)),
                      (0, 1, (1 - fu) * fv), (1, 1, fu * fv)):
        np.add.at(grid, (i0 + di, j0 + dj), w)
    return grid


def caustic_frame(res, t, depth=2.0, extent=4.0, ray_res=768, recv_res=512):
    """Normals come from a res x res grid; rays are traced on a fixed fine
    grid so `res` only controls normal-field detail."""
    xx, yy, h = height_field(res, t, extent)
    dx = 2.0 * extent / (res - 1)
    nx, ny, nz = surface_normals(h, dx)
    nx = bilinear_upsample(nx, ray_res)
    ny = bilinear_upsample(ny, ray_res)
    nz = bilinear_upsample(nz, ray_res)
    hf = bilinear_upsample(h, ray_res)
    inv = 1.0 / np.sqrt(nx**2 + ny**2 + nz**2)
    nx, ny, nz = nx * inv, ny * inv, nz * inv
    xf = np.linspace(-extent, extent, ray_res)
    xx, yy = np.meshgrid(xf, xf, indexing="xy")
    eta = N_AIR / N_WATER
    dxr, dyr, dzr = refract((0.0, 0.0, -1.0), (nx, ny, nz), eta)
    s = (-depth - hf) / dzr
    hx = xx + s * dxr
    hy = yy + s * dyr
    lim = extent * 1.2
    grid = bilinear_splat(hx.ravel(), hy.ravel(), recv_res, lim)
    return grid / max(grid.mean(), 1e-9)


def save_map(bright, path, title):
    fig, ax = plt.subplots(figsize=(4, 4), dpi=110)
    ax.imshow(bright.T, origin="lower", cmap="afmhot",
              vmin=0, vmax=np.percentile(bright, 99.5))
    ax.set_title(title, fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def ncc(a, b):
    a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def detail_metric(bright):
    """High-frequency energy share: Laplacian power / total power."""
    lap = (-4 * bright + np.roll(bright, 1, 0) + np.roll(bright, -1, 0)
           + np.roll(bright, 1, 1) + np.roll(bright, -1, 1))
    return float((lap**2).sum() / ((bright**2).sum() + 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--res", type=int, default=256)
    ap.add_argument("--dt", type=float, default=0.35)
    ap.add_argument("--res-study", type=int, nargs="*",
                    default=[64, 128, 256, 512])
    ap.add_argument("--out", default="artifacts/caustics")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = {"res": args.res, "frames": []}
    prev = None
    for i in range(args.frames):
        t = i * args.dt
        t0 = time.perf_counter()
        bright = caustic_frame(args.res, t)
        sim_ms = (time.perf_counter() - t0) * 1e3
        t0 = time.perf_counter()
        save_map(bright, out / f"frame_{i:02d}.png",
                 f"t={t:.2f}s  res={args.res}")
        io_ms = (time.perf_counter() - t0) * 1e3
        entry = {"frame": i, "t": round(t, 3),
                 "sim_ms": round(sim_ms, 2), "io_ms": round(io_ms, 2),
                 "mean": round(float(bright.mean()), 3),
                 "max": round(float(bright.max()), 2),
                 "ncc_prev": (round(ncc(prev, bright), 4)
                              if prev is not None else None)}
        report["frames"].append(entry)
        print(f"frame {i}: sim={sim_ms:.1f}ms io={io_ms:.1f}ms "
              f"max={entry['max']} ncc_prev={entry['ncc_prev']}")
        prev = bright

    study = []
    for r in args.res_study:
        t0 = time.perf_counter()
        bright = caustic_frame(r, t=0.0)
        ms = (time.perf_counter() - t0) * 1e3
        save_map(bright, out / f"res_{r}.png", f"normal grid {r}x{r}")
        study.append({"res": r, "sim_ms": round(ms, 2),
                      "detail": round(detail_metric(bright), 5),
                      "max": round(float(bright.max()), 2)})
        print(f"res {r}: sim={ms:.1f}ms "
              f"detail={study[-1]['detail']} max={study[-1]['max']}")
    report["res_study"] = study

    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"wrote {out}/report.json")


if __name__ == "__main__":
    main()
