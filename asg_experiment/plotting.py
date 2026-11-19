"""Figures for the ASG fitting and integration experiment."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .model import DirectionalEnvironment, direction_from_angles


def _save(figure: plt.Figure, path_without_suffix: Path) -> None:
    figure.tight_layout()
    figure.savefig(path_without_suffix.with_suffix(".png"), dpi=170, bbox_inches="tight")
    figure.savefig(path_without_suffix.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def plot_error_curves(
    scan: list[dict[str, float]],
    sh_comparison: list[dict[str, float]],
    path: Path,
) -> None:
    counts = [row["n_gauss"] for row in scan]
    figure, axis = plt.subplots(figsize=(8.4, 5.0))
    axis.semilogy(counts, [row["environment_nrmse"] for row in scan], "o-", label="env radiance NRMSE")
    axis.semilogy(counts, [row["brightness_rel_l1"] for row in scan], "s-", label="brightness relative L1")
    sh8 = next(row for row in sh_comparison if row["sh_degree"] == 8)
    sh12 = next(row for row in sh_comparison if row["sh_degree"] == 12)
    axis.axhline(sh8["brightness_rel_l1"], color="tab:red", linestyle="--", label="SH degree 8")
    axis.axhline(sh12["brightness_rel_l1"], color="tab:purple", linestyle=":", label="SH degree 12")
    axis.set_xlabel("number of anisotropic Gaussians")
    axis.set_ylabel("relative error (lower is better)")
    axis.set_xticks(counts)
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(frameon=False)
    axis.set_title("Reconstruction error vs. ASG count")
    _save(figure, path)


def plot_time_curve(scan: list[dict[str, float]], path: Path) -> None:
    counts = [row["n_gauss"] for row in scan]
    figure, axis = plt.subplots(figsize=(8.4, 4.6))
    axis.plot(counts, [row["fit_time_ms"] for row in scan], "o-", label="fit time")
    axis.set_xlabel("number of anisotropic Gaussians")
    axis.set_ylabel("fit time (ms)")
    axis.set_xticks(counts)
    axis.grid(True, alpha=0.25)
    axis2 = axis.twinx()
    axis2.plot(
        counts,
        [row["integration_us_per_normal"] for row in scan],
        "s--",
        color="tab:orange",
        label="analytic integral / normal",
    )
    axis2.set_ylabel("analytic integral (us / normal)")
    lines = axis.get_lines() + axis2.get_lines()
    axis.legend(lines, [line.get_label() for line in lines], frameon=False)
    axis.set_title("Cost vs. ASG count (log scale fit time)")
    axis.set_yscale("log")
    _save(figure, path)


def _equirectangular_grid(longitude_count: int = 180, latitude_count: int = 90):
    longitudes = np.linspace(-np.pi, np.pi, longitude_count, endpoint=True)
    latitudes = np.linspace(-0.5 * np.pi, 0.5 * np.pi, latitude_count, endpoint=True)
    longitude_grid, latitude_grid = np.meshgrid(longitudes, latitudes)
    cos_latitude = np.cos(latitude_grid)
    directions = np.stack(
        (
            cos_latitude * np.cos(longitude_grid),
            cos_latitude * np.sin(longitude_grid),
            np.sin(latitude_grid),
        ),
        axis=-1,
    ).reshape(-1, 3)
    return np.degrees(longitude_grid), np.degrees(latitude_grid), directions


def plot_environment_maps(
    environment: DirectionalEnvironment,
    models: Mapping[int, object],
    selected_counts: tuple[int, int, int, int],
    path: Path,
) -> None:
    longitude, latitude, directions = _equirectangular_grid()
    truth = environment.radiance(directions).reshape(longitude.shape)
    panels = [("ground truth", truth)]
    for count in selected_counts:
        panel = models[count].radiance(directions).reshape(longitude.shape)
        panels.append((f"N = {count}", panel))
    panels.append(("N = 4 absolute error", np.abs(panels[2][1] - truth)))

    figure, axes = plt.subplots(2, 3, figsize=(12.6, 6.8), sharex=True, sharey=True)
    for axis, (title, image) in zip(axes.ravel(), panels):
        if title.startswith("N = 4 absolute"):
            mesh = axis.pcolormesh(
                longitude,
                latitude,
                image,
                shading="auto",
                cmap="magma",
                rasterized=True,
            )
        else:
            mesh = axis.pcolormesh(
                longitude,
                latitude,
                image,
                shading="auto",
                cmap="inferno",
                vmin=0.0,
                vmax=truth.max(),
                rasterized=True,
            )
        axis.set_title(title, fontsize=10)
        axis.set_xlabel("longitude (deg)")
        axis.set_ylabel("latitude (deg)")
        figure.colorbar(mesh, ax=axis, fraction=0.045, pad=0.02)
    figure.suptitle("Directional environment reconstruction", fontsize=13)
    _save(figure, path)


def plot_brightness_maps(
    reference_callable: Callable[[np.ndarray], np.ndarray],
    brightness_callables: Mapping[int, Callable[[np.ndarray], np.ndarray]],
    selected_counts: tuple[int, int, int, int],
    path: Path,
) -> None:
    longitude, latitude, directions = _equirectangular_grid(150, 76)
    truth = reference_callable(directions).reshape(longitude.shape)
    panels = [("reference (MC-validated)", truth)]
    for count in selected_counts:
        panel = brightness_callables[count](directions).reshape(longitude.shape)
        panels.append((f"N = {count}", panel))
    panels.append(("N = 4 absolute error", np.abs(panels[2][1] - truth)))

    figure, axes = plt.subplots(2, 3, figsize=(12.6, 6.8), sharex=True, sharey=True)
    for axis, (title, image) in zip(axes.ravel(), panels):
        if title.startswith("N = 4 absolute"):
            mesh = axis.pcolormesh(
                longitude,
                latitude,
                image,
                shading="auto",
                cmap="magma",
                rasterized=True,
            )
        else:
            mesh = axis.pcolormesh(
                longitude,
                latitude,
                image,
                shading="auto",
                cmap="viridis",
                vmin=0.0,
                vmax=truth.max(),
                rasterized=True,
            )
        axis.set_title(title, fontsize=10)
        axis.set_xlabel("longitude (deg)")
        axis.set_ylabel("latitude (deg)")
        figure.colorbar(mesh, ax=axis, fraction=0.045, pad=0.02)
    figure.suptitle("Reconstructed brightness integral", fontsize=13)
    _save(figure, path)


def plot_brightness_profiles(
    reference_callable: Callable[[np.ndarray], np.ndarray],
    brightness_callables: Mapping[int, Callable[[np.ndarray], np.ndarray]],
    counts: tuple[int, ...],
    path: Path,
) -> None:
    azimuth = np.linspace(-np.pi, np.pi, 241)
    elevation = np.deg2rad(20.0)
    normals = np.array(
        [direction_from_angles(float(angle), elevation) for angle in azimuth]
    )
    figure, axis = plt.subplots(figsize=(9.0, 4.8))
    axis.plot(np.degrees(azimuth), reference_callable(normals), color="black", linewidth=2.2, label="reference")
    colors = ("tab:red", "tab:orange", "tab:green", "tab:blue", "tab:brown")
    for count, color in zip(counts, colors):
        axis.plot(
            np.degrees(azimuth),
            brightness_callables[count](normals),
            color=color,
            linewidth=1.4,
            label=f"N = {count}",
        )
    axis.axhline(0.0, color="0.65", linewidth=0.8)
    axis.set_xlabel("azimuth at 20 deg elevation (deg)")
    axis.set_ylabel("brightness integral")
    axis.grid(True, alpha=0.25)
    axis.legend(frameon=False, ncol=5, fontsize=8)
    axis.set_title("Brightness angular profile: underfitting is smooth, not oscillatory")
    _save(figure, path)
