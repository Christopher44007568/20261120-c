"""Plots for the Poisson noise-robustness benchmark."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


SHAPE_COLORS = {"sphere": "#1f77b4", "bumpy_sphere": "#d62728"}
SHAPE_LABELS = {"sphere": "sphere", "bumpy_sphere": "bumpy sphere"}


def _save(fig: plt.Figure, path: str | Path, tight: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if tight:
        fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_noise_curve(
    summary: list[dict[str, Any]],
    checks: dict[str, Any],
    path: str | Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    for shape in sorted({row["shape"] for row in summary}):
        color = SHAPE_COLORS.get(shape, "#333333")
        for method, linestyle, marker, label in (
            ("poisson", "-", "o", "Poisson"),
            ("raw_points", "--", "s", "raw points"),
        ):
            rows = [
                row
                for row in summary
                if row["shape"] == shape and row["method"] == method
            ]
            rows = sorted(rows, key=lambda row: row["noise_mm"])
            x = np.array([row["noise_mm"] for row in rows])
            y = np.array([row["radial_rmse_mm_mean"] for row in rows])
            y_std = np.array([row["radial_rmse_mm_std"] for row in rows])
            axes[0].errorbar(
                x,
                y,
                yerr=y_std,
                color=color,
                ls=linestyle,
                marker=marker,
                ms=4,
                lw=1.8,
                capsize=2,
                label=f"{SHAPE_LABELS.get(shape, shape)} {label}",
            )
    axes[0].set_xlabel("positional noise sigma (mm), radius = 500 mm")
    axes[0].set_ylabel("radial RMSE (mm)")
    axes[0].set_title("Poisson reconstruction under increasing point noise")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=7.5, ncol=2)

    for shape in sorted({row["shape"] for row in summary}):
        poisson = {
            round(row["noise_mm"], 6): row
            for row in summary
            if row["shape"] == shape and row["method"] == "poisson"
        }
        raw = {
            round(row["noise_mm"], 6): row
            for row in summary
            if row["shape"] == shape and row["method"] == "raw_points"
        }
        levels = sorted(key for key in poisson if key > 0.0)
        improvement = [
            raw[key]["radial_rmse_mm_mean"] / poisson[key]["radial_rmse_mm_mean"]
            for key in levels
        ]
        axes[1].plot(
            levels,
            improvement,
            color=SHAPE_COLORS.get(shape, "#333333"),
            marker="o",
            ms=4,
            label=SHAPE_LABELS.get(shape, shape),
        )
    axes[1].axhline(1.0, color="#333333", ls="--", lw=1.0)
    axes[1].set_xlabel("positional noise sigma (mm)")
    axes[1].set_ylabel("raw / Poisson radial RMSE")
    axes[1].set_title("Noise suppression factor (>1 means Poisson is better)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)
    notes = []
    for shape, check in checks.items():
        notes.append(
            f"{SHAPE_LABELS.get(shape, shape)}: max-noise RMSE "
            f"{check['max_noise_rmse_mm']:.2f} mm, "
            f"improvement x{check['max_noise_improvement_factor']:.2f}"
        )
    fig.text(0.5, 0.005, " | ".join(notes), ha="center", fontsize=8)
    _save(fig, path)


def plot_examples(
    examples: dict[str, dict[str, Any]], path: str | Path
) -> None:
    if not examples:
        return
    keys = [key for key in ("0.000", "0.020", "0.040") if key in examples]
    fig = plt.figure(figsize=(13.5, 4.6))
    for index, key in enumerate(keys, start=1):
        example = examples[key]
        axis = fig.add_subplot(1, len(keys), index, projection="3d")
        noise_mm = example["noise_fraction"] * 500.0
        if index < len(keys):
            points = example["points"]
            step = max(1, len(points) // 6000)
            points = points[::step]
            radius = np.linalg.norm(points, axis=1)
            error = (radius - 0.5) * 1000.0
            axis.scatter(
                points[:, 0],
                points[:, 1],
                points[:, 2],
                c=error,
                cmap="coolwarm",
                vmin=-40,
                vmax=40,
                s=1.2,
                alpha=0.75,
            )
            axis.set_title(f"input cloud, sigma={noise_mm:.0f} mm")
        else:
            vertices = example["mesh_vertices"]
            faces = example["mesh_faces"]
            axis.plot_trisurf(
                vertices[:, 0],
                vertices[:, 1],
                faces,
                vertices[:, 2],
                color="#8fb3d9",
                alpha=0.92,
                linewidth=0.0,
                antialiased=True,
            )
            axis.set_title(
                f"Poisson mesh, sigma={noise_mm:.0f} mm\n"
                f"{len(vertices)} vertices"
            )
        axis.set_box_aspect((1, 1, 1))
        axis.set_xticks([])
        axis.set_yticks([])
        axis.set_zticks([])
    fig.subplots_adjust(top=0.84, bottom=0.02, wspace=0.05)
    _save(fig, path, tight=False)
