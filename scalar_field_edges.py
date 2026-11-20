"""Scalar-field reconstruction across sharp edges.

Ground truth: 2D field with a sharp (discontinuous) sinusoidal edge plus
a smooth background.  A coarse grid sampling is reconstructed on a fine
grid with (a) plain bilinear interpolation and (b) an edge-aware
anisotropic interpolation that limits blending across the edge normal.
Reports reconstruction error and edge sharpness for both.
"""
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def ground_truth(x, y):
    """Sharp step along a sinusoidal edge + smooth background."""
    edge = 0.5 + 0.15 * np.sin(4 * np.pi * x)
    step = (y > edge).astype(float)
    background = 0.3 * x + 0.1 * np.sin(2 * np.pi * y)
    return step + background


def sample_coarse(n=17):
    xs = np.linspace(0, 1, n)
    xx, yy = np.meshgrid(xs, xs, indexing="ij")
    return xs, ground_truth(xx, yy)


def coarse_normals(xs, f):
    """Unit edge normals from the gradient of the coarse field."""
    h = xs[1] - xs[0]
    gx, gy = np.gradient(f, h, edge_order=2)
    # smooth the gradient a little for stability
    k = np.ones(3) / 3.0
    gx = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 0, gx)
    gx = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 1, gx)
    gy = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 0, gy)
    gy = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 1, gy)
    norm = np.hypot(gx, gy) + 1e-12
    return gx / norm, gy / norm


def bilinear_at(xs, f, px, py):
    n = len(xs)
    h = xs[1] - xs[0]
    fx = np.clip(px / h, 0, n - 1 - 1e-12)
    fy = np.clip(py / h, 0, n - 1 - 1e-12)
    i, j = int(fx), int(fy)
    u, v = fx - i, fy - j
    return ((1 - u) * (1 - v) * f[i, j] + u * (1 - v) * f[i + 1, j]
            + (1 - u) * v * f[i, j + 1] + u * v * f[i + 1, j + 1])


def reconstruct_bilinear(xs, f, xf, yf):
    out = np.zeros((len(xf), len(yf)))
    for a, px in enumerate(xf):
        for b, py in enumerate(yf):
            out[a, b] = bilinear_at(xs, f, px, py)
    return out


def reconstruct_edge_aware(xs, f, nx, ny, xf, yf, sigma_cells=0.35):
    """Anisotropic weights: suppress corners lying across the edge normal."""
    n = len(xs)
    h = xs[1] - xs[0]
    sigma = sigma_cells * h
    out = np.zeros((len(xf), len(yf)))
    for a, px in enumerate(xf):
        for b, py in enumerate(yf):
            fx = np.clip(px / h, 0, n - 1 - 1e-12)
            fy = np.clip(py / h, 0, n - 1 - 1e-12)
            i, j = int(fx), int(fy)
            u, v = fx - i, fy - j
            w = {(0, 0): (1 - u) * (1 - v), (1, 0): u * (1 - v),
                 (0, 1): (1 - u) * v, (1, 1): u * v}
            # edge normal at the target point (bilinear from coarse normals)
            npx = sum(w[(di, dj)] * nx[i + di, j + dj]
                      for di in (0, 1) for dj in (0, 1))
            npy = sum(w[(di, dj)] * ny[i + di, j + dj]
                      for di in (0, 1) for dj in (0, 1))
            nl = np.hypot(npx, npy)
            num, den = 0.0, 0.0
            for (di, dj), wij in w.items():
                cx, cy = xs[i + di], xs[j + dj]
                d_normal = (cx - px) * npx + (cy - py) * npy
                ww = wij * np.exp(-0.5 * (d_normal / sigma) ** 2)
                num += ww * f[i + di, j + dj]
                den += ww
            out[a, b] = num / den
    return out


def transition_width(xf, yf, f, lo=0.1, hi=0.9):
    """Mean 10-90% rise width of the step (background removed) per column."""
    widths = []
    for a in range(len(xf)):
        col = f[a, :] - (0.3 * xf[a] + 0.1 * np.sin(2 * np.pi * yf))
        mask = (col > lo) & (col < hi)
        widths.append(mask.sum() * (yf[1] - yf[0]))
    return float(np.mean(widths))


def main():
    xs, fc = sample_coarse(n=17)
    nx, ny = coarse_normals(xs, fc)
    nf = 257
    xf = np.linspace(0, 1, nf)
    yf = np.linspace(0, 1, nf)
    xxf, yyf = np.meshgrid(xf, yf, indexing="ij")
    gt = ground_truth(xxf, yyf)

    rec_bl = reconstruct_bilinear(xs, fc, xf, yf)
    rec_ea = reconstruct_edge_aware(xs, fc, nx, ny, xf, yf)

    print("== Scalar-field reconstruction with sharp edge ==")
    print(f"  coarse grid: {len(xs)}x{len(xs)}, fine grid: {nf}x{nf}")
    print(f"  {'method':<12}{'RMSE':>10}{'MAE':>10}{'max err':>10}"
          f"{'10-90% width':>14}")
    results = {}
    for name, rec in (("bilinear", rec_bl), ("edge-aware", rec_ea)):
        err = rec - gt
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mae = float(np.mean(np.abs(err)))
        emax = float(np.max(np.abs(err)))
        width = transition_width(xf, yf, rec)
        results[name] = (rmse, width)
        print(f"  {name:<12}{rmse:>10.5f}{mae:>10.5f}{emax:>10.5f}"
              f"{width:>14.5f}")
    gt_width = transition_width(xf, yf, gt)
    print(f"  ground-truth 10-90% width: {gt_width:.5f} (1-2 fine pixels)")

    sharper = results["edge-aware"][1] < results["bilinear"][1]
    better = results["edge-aware"][0] < results["bilinear"][0]
    print(f"  edge-aware sharper (narrower transition): {sharper}")
    print(f"  edge-aware lower RMSE: {better}")

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    vmin, vmax = gt.min(), gt.max()
    panels = [(gt, "ground truth"), (rec_bl, "bilinear"),
              (rec_ea, "edge-aware")]
    for k, (data, title) in enumerate(panels):
        ax = axes[0, k]
        im = ax.imshow(data.T, origin="lower", extent=[0, 1, 0, 1],
                       vmin=vmin, vmax=vmax, cmap="viridis")
        ax.set_title(title)
        fig.colorbar(im, ax=ax, fraction=0.046)
    for k, (data, title) in enumerate(panels[1:]):
        ax = axes[1, k + 1]
        im = ax.imshow(np.abs(data - gt).T, origin="lower",
                       extent=[0, 1, 0, 1], cmap="hot")
        ax.set_title(f"|error| {title}")
        fig.colorbar(im, ax=ax, fraction=0.046)
    mid = nf // 2
    ax = axes[1, 0]
    ax.plot(yf, gt[mid, :], "k-", label="ground truth", lw=1.5)
    ax.plot(yf, rec_bl[mid, :], "b--", label="bilinear", lw=1.2)
    ax.plot(yf, rec_ea[mid, :], "r-.", label="edge-aware", lw=1.2)
    ax.set_title(f"cross-section x={xf[mid]:.2f}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig("artifacts/scalar_field_edges.png", dpi=150)
    print("figure saved: artifacts/scalar_field_edges.png")

    if not (sharper and better):
        raise SystemExit("edge-aware reconstruction did not improve results")


if __name__ == "__main__":
    main()
