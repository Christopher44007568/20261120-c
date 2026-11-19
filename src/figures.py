"""Matplotlib figure generation matching the reference artifact layout."""

import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .experiments.common import DATA_DIR, FIG_DIR


def _read_csv(name):
    with open(f"{DATA_DIR}/{name}") as fh:
        return list(csv.DictReader(fh))


def _float(rows, key):
    return np.array([float(r[key]) for r in rows])


def fig1_transmittance():
    rows = _read_csv("transmittance_curves.csv")
    d = _float(rows, "depth")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.4, 5.88))
    ax1.plot(d, _float(rows, "truth"), "k-", lw=3, label="Beer-Lambert (analytic)")
    ax1.plot(d, _float(rows, "uniform_mean"), "o--", ms=7,
             label="uniform stepping (dt=0.08)")
    ax1.plot(d, _float(rows, "exponential_mean"), "s--", ms=7,
             label="exponential (ratio tracking)")
    ax1.set_title("Transmittance vs depth (homogeneous medium)", fontsize=18)
    ax1.set_xlabel("optical path depth d", fontsize=15)
    ax1.set_ylabel("transmittance T", fontsize=15)
    ax1.legend(fontsize=14)
    ax1.grid(alpha=0.3)

    ax2.plot(d, _float(rows, "uniform_var"), "o-", label="uniform ratio")
    ax2.plot(d, _float(rows, "exponential_var"), "s-", label="exponential ratio")
    ax2.plot(d, _float(rows, "exp_bernoulli_var"), "^-",
             label="exponential delta (RR)")
    ax2.plot(d, _float(rows, "uniform_bernoulli_var"), "d-", label="uniform (RR)")
    ax2.set_title("Estimator variance vs depth", fontsize=18)
    ax2.set_xlabel("optical path depth d", fontsize=15)
    ax2.set_ylabel("per-sample variance of T", fontsize=15)
    ax2.legend(fontsize=14)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig1_transmittance_depth.png", dpi=100)
    plt.close(fig)


def fig2_noise():
    rows = [r for r in _read_csv("noise_variance.csv") if r["field"] == "smoke"]
    names = [r["estimator"] for r in rows]
    mse = _float(rows, "mse")
    seconds = _float(rows, "seconds")
    efficiency = _float(rows, "efficiency")
    colors = ["#d62728", "#ff7f0e", "#bcbd22", "#2ca02c", "#1f77b4", "#9467bd"]

    fig, axes = plt.subplots(1, 3, figsize=(19.6, 6.16))
    y = np.arange(len(names))[::-1]
    axes[0].barh(y, mse, color=colors)
    axes[0].set_yticks(y, names, fontsize=13)
    axes[0].set_xscale("log")
    axes[0].set_title("Noise+bias MSE (smoke plume)", fontsize=18)
    axes[0].set_xlabel("MSE of batch-mean transmittance", fontsize=14)
    axes[0].grid(axis="x", alpha=0.3)

    axes[1].barh(y, seconds, color=colors)
    axes[1].set_yticks(y, names, fontsize=13)
    axes[1].set_title("Compute cost", fontsize=18)
    axes[1].set_xlabel("wall time [s] for 160k rays", fontsize=14)
    axes[1].grid(axis="x", alpha=0.3)

    axes[2].barh(y, efficiency, color=colors)
    axes[2].set_yticks(y, names, fontsize=13)
    axes[2].set_title("Efficiency (higher = better)", fontsize=18)
    axes[2].set_xlabel("efficiency 1 / (MSE x time)", fontsize=14)
    axes[2].grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig2_noise_variance.png", dpi=100)
    plt.close(fig)


def _render_panels(frames, field, title_prefix, fig_name, profile_name):
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 11.9))
    images = {}
    for col, mode in enumerate(["exponential", "uniform"]):
        image, step_map = frames[field][mode]
        images[mode] = image
        ax = axes[0, col]
        ax.imshow(image, cmap="gray", vmin=0, vmax=np.percentile(image, 99.5))
        ax.set_title(f"{title_prefix}: {mode} stepping render", fontsize=16)
        ax.set_xticks([])
        ax.set_yticks([])

        ax = axes[1, col]
        vmax = np.percentile(step_map, 99)
        mesh = ax.imshow(step_map, cmap="magma", vmin=0, vmax=vmax)
        ax.set_title(
            f"steps per pixel (mean={step_map[step_map > 0].mean():.1f})",
            fontsize=16)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(mesh, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/{fig_name}", dpi=100)
    plt.close(fig)

    image = images["exponential"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.04))
    h, w = image.shape
    # A fixed central window keeps the bright box edges (transmitted ground
    # light) out of the luminance profiles.
    lo_col, hi_col = w // 3, 2 * w // 3
    central = image[:, lo_col:hi_col]
    row_mean = central.mean(axis=1)
    ax1.plot(row_mean, np.arange(h), lw=2)
    ax1.invert_yaxis()
    ax1.set_title(f"{title_prefix}: vertical luminance profile", fontsize=18)
    ax1.set_xlabel("mean row luminance", fontsize=15)
    ax1.set_ylabel("pixel row", fontsize=15)
    ax1.grid(alpha=0.3)

    center_row = image[h // 2, lo_col:hi_col]
    ax2.plot(center_row, lw=2)
    ax2.set_title(f"{title_prefix}: horizontal profile through center", fontsize=18)
    ax2.set_xlabel("pixel column", fontsize=15)
    ax2.set_ylabel("luminance", fontsize=15)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/{profile_name}", dpi=100)
    plt.close(fig)


def fig3_smoke(frames):
    _render_panels(frames, "smoke", "smoke plume",
                   "fig3_smoke_render.png", "fig3b_smoke_profiles.png")


def fig4_cloud(frames):
    _render_panels(frames, "cloud", "cloud/fog",
                   "fig4_cloud_render.png", "fig4b_cloud_profiles.png")


def fig5_surface(images, metrics):
    fig, axes = plt.subplots(1, 3, figsize=(18.2, 5.32))
    axes[0].imshow(images["surface"], cmap="gray", vmin=0, vmax=1.8)
    axes[0].set_title("surface path only (no medium)", fontsize=17)
    axes[1].imshow(images["absorption"], cmap="gray", vmin=0, vmax=1.8)
    axes[1].set_title("absorption-only volume path", fontsize=17)
    for ax in axes[:2]:
        ax.set_xticks([])
        ax.set_yticks([])

    ratio = images["ratio_absorb"][images["mask"]]
    ratio = ratio[np.isfinite(ratio)]
    axes[2].hist(ratio, bins=40, color="#5a9ed6", alpha=0.85,
                 label="absorption: L_vol / L_surf")
    axes[2].axvline(metrics["scattering_energy_ratio"], color="red",
                    ls="--", lw=2.5,
                    label=f"scattering energy ratio="
                          f"{metrics['scattering_energy_ratio']:.3f}")
    axes[2].axvline(metrics["beer_lambert_energy_T"], color="green",
                    ls=":", lw=3,
                    label=f"Beer-Lambert T={metrics['beer_lambert_energy_T']:.3f}")
    axes[2].set_title("surface consistency", fontsize=17)
    axes[2].set_xlabel("radiance ratio", fontsize=15)
    axes[2].legend(fontsize=12)
    axes[2].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig5_surface_consistency.png", dpi=100)
    plt.close(fig)
