from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm, colors
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

from .mesh_ops import TriangleMesh
from .uv_mapping import UVMap, face_stretch_values, pack_uv_islands, texture_stretch


PALETTE = np.asarray(
    [
        "#4C78A8",
        "#F58518",
        "#54A24B",
        "#E45756",
        "#72B7B2",
        "#B279A2",
        "#EECA3B",
        "#9D755D",
        "#FF9DA6",
        "#7F7F7F",
        "#8CD17D",
        "#A0CBE8",
    ]
)


def _setup_3d(ax, mesh: TriangleMesh) -> None:
    points = mesh.vertices
    center = (points.min(axis=0) + points.max(axis=0)) / 2.0
    span = points.max(axis=0) - points.min(axis=0)
    ax.set_xlim(center[0] - span[0] / 2, center[0] + span[0] / 2)
    ax.set_ylim(center[1] - span[1] / 2, center[1] + span[1] / 2)
    ax.set_zlim(center[2] - span[2] / 2, center[2] + span[2] / 2)
    ax.set_box_aspect(tuple(span))
    ax.set_proj_type("ortho")
    ax.view_init(elev=38, azim=-58)
    ax.set_axis_off()
    ax.set_facecolor("white")


def _seam_segments(mesh: TriangleMesh, labels: np.ndarray, adjacency: np.ndarray):
    seam_mask = labels[adjacency[:, 0]] != labels[adjacency[:, 1]]
    segments = []
    for a, b in adjacency[seam_mask]:
        shared = np.intersect1d(mesh.faces[a], mesh.faces[b])
        if len(shared) == 2:
            segments.append(mesh.vertices[shared])
    return segments


def plot_segmentation(
    mesh: TriangleMesh,
    entries: list[tuple[str, np.ndarray, float]],
    adjacency: np.ndarray,
    path: Path,
) -> None:
    ncols = 2 if len(entries) > 1 else 1
    nrows = int(np.ceil(len(entries) / ncols))
    fig = plt.figure(figsize=(6.3 * ncols, 4.7 * nrows), dpi=170)
    for index, (title, labels, stretch_p95) in enumerate(entries, start=1):
        ax = fig.add_subplot(nrows, ncols, index, projection="3d")
        for label in np.unique(labels):
            faces = np.flatnonzero(labels == label)
            polygons = [mesh.vertices[mesh.faces[face]] for face in faces]
            collection = Poly3DCollection(
                polygons,
                facecolor=PALETTE[int(label) % len(PALETTE)],
                edgecolor="none",
                alpha=0.92,
            )
            ax.add_collection3d(collection)
        seams = _seam_segments(mesh, labels, adjacency)
        if seams:
            ax.add_collection3d(
                Line3DCollection(seams, colors="#171717", linewidths=0.48, alpha=0.95)
            )
        _setup_3d(ax, mesh)
        ax.set_title(
            f"{title}\n{len(np.unique(labels))} UV islands | p95 stretch {stretch_p95:.3f}",
            fontsize=11,
            pad=2,
        )
    fig.suptitle("Normal + geodesic clustering vs. spectral clustering", fontsize=15)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_stretch_maps(
    mesh: TriangleMesh,
    entries: list[tuple[str, UVMap]],
    path: Path,
) -> None:
    norm = colors.Normalize(vmin=1.0, vmax=1.42)
    cmap = plt.get_cmap("turbo")
    ncols = min(3, len(entries))
    nrows = int(np.ceil(len(entries) / ncols))
    fig = plt.figure(figsize=(4.5 * ncols, 3.9 * nrows), dpi=170)
    for index, (title, uv) in enumerate(entries, start=1):
        ax = fig.add_subplot(nrows, ncols, index, projection="3d")
        values = face_stretch_values(mesh, uv)
        polygons = [mesh.vertices[face] for face in mesh.faces]
        facecolors = cmap(norm(np.clip(values, 1.0, 1.42)))
        collection = Poly3DCollection(
            polygons,
            facecolors=facecolors,
            edgecolor="none",
            linewidths=0.0,
        )
        ax.add_collection3d(collection)
        _setup_3d(ax, mesh)
        quality = texture_stretch(mesh, uv)
        ax.set_title(
            f"{title}\nmean {quality['mean']:.3f} | p95 "
            f"{quality['p95']:.3f}",
            fontsize=10,
        )
    scalar = cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array(np.asarray([1.0, 1.42]))
    cbar = fig.colorbar(scalar, ax=fig.axes, shrink=0.55, pad=0.015)
    cbar.set_label("L2 texture stretch (1 = isometric)")
    fig.suptitle("Texture stretch: planar projection vs. segmented UV charts", fontsize=15)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_uv_atlas(
    mesh: TriangleMesh,
    entries: list[tuple[str, np.ndarray, UVMap]],
    path: Path,
) -> None:
    fig, axes = plt.subplots(1, len(entries), figsize=(11.5, 5.3), dpi=170)
    if len(entries) == 1:
        axes = [axes]
    for ax, (title, labels, uv) in zip(axes, entries):
        packed = pack_uv_islands(uv.face_uv, labels)
        for label in np.unique(labels):
            faces = np.flatnonzero(labels == label)
            polygons = packed[faces]
            ax.add_collection(
                PolyCollection(
                    polygons,
                    facecolor=PALETTE[int(label) % len(PALETTE)],
                    edgecolor="white",
                    linewidth=0.12,
                )
            )
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{title}\n{len(np.unique(labels))} packed islands")
        for spine in ax.spines.values():
            spine.set_color("#777777")
    fig.suptitle("Generated UV islands (shelf-packed for inspection)", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_soft_shadow(result: dict, path: Path) -> None:
    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(12.2, 4.8), dpi=170, gridspec_kw={"width_ratios": [1, 1]}
    )
    x = np.asarray(result["receiver_x"])
    ax_left.plot(
        x,
        result["reference_visibility"],
        color="#111111",
        linewidth=2.5,
        label="analytic reference",
    )
    for step, color in zip(
        (0.10, 0.05, 0.025, 0.0025),
        ("#E45756", "#F58518", "#4C78A8", "#54A24B"),
    ):
        ax_left.plot(
            x,
            result["profiles"][step],
            color=color,
            linewidth=1.1,
            alpha=0.85,
            label=f"step {step:g}",
        )
    ax_left.set_xlim(-0.45, 0.75)
    ax_left.set_xlabel("receiver position x")
    ax_left.set_ylabel("visibility")
    ax_left.set_ylim(-0.02, 1.02)
    ax_left.grid(alpha=0.22)
    ax_left.legend(fontsize=8, ncol=2)
    ax_left.set_title("Soft-shadow transition profile")

    rows = result["rows"]
    steps = np.asarray([row["step"] for row in rows])
    samples = np.asarray([row["average_steps"] for row in rows])
    error = np.asarray([row["relative_error"] * 100.0 for row in rows])
    ax_right.plot(steps, samples, "o-", color="#4C78A8", label="average march steps")
    ax_right.set_xscale("log")
    ax_right.invert_xaxis()
    ax_right.set_xlabel("step size (world units)")
    ax_right.set_ylabel("average steps / ray", color="#4C78A8")
    ax_right.tick_params(axis="y", labelcolor="#4C78A8")
    ax_right.grid(alpha=0.22)

    ax_error = ax_right.twinx()
    ax_error.plot(steps, error, "s--", color="#E45756", label="penumbra error")
    ax_error.set_ylabel("penumbra width error (%)", color="#E45756")
    ax_error.tick_params(axis="y", labelcolor="#E45756")
    recommended = result["recommended"]
    ax_right.axvline(recommended["step"], color="#333333", linestyle=":", linewidth=1.2)
    ax_right.set_title(
        f"Recommended step {recommended['step']:g}: "
        f"{recommended['average_steps']:.0f} steps, "
        f"{recommended['relative_error'] * 100:.1f}% width error",
        fontsize=10,
    )
    fig.suptitle("Fixed-step soft-shadow ray marching: cost vs. penumbra accuracy", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
