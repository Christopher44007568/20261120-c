"""Matplotlib figures and GIF rendering for the walking analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Circle

from .gait import SimulationResult
from .ik import sole_points


COLORS = {"left": "#1f77b4", "right": "#d62728", "terrain": "#4c4c4c"}


def _save(fig: plt.Figure, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_stride_vs_slope(
    rows: list[dict[str, Any]], path: str | Path, continuity: dict[str, Any]
) -> None:
    ordered = sorted(rows, key=lambda row: row["slope_deg"])
    slope = np.array([row["slope_deg"] for row in ordered])
    stride = np.array([row["stride_m"] for row in ordered])
    measured = np.array([row["measured_stride_m"] for row in ordered])
    contact = np.array([row["contact_max_abs_m"] for row in ordered]) * 1000.0
    reach = np.array([row["reach_ratio_max"] for row in ordered])

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.0), sharex=True)
    ax = axes[0]
    ax.plot(slope, stride, color="#111111", lw=2.2, label="model stride")
    ax.plot(slope, measured, "--", color="#2ca02c", lw=1.4, label="measured stride")
    ax.axvline(0.0, color="#888888", lw=0.8)
    ax.fill_betweenx(
        [stride.min() - 0.03, stride.max() + 0.03],
        0,
        slope.max(),
        color="#f2c14e",
        alpha=0.10,
        label="uphill",
    )
    ax.fill_betweenx(
        [stride.min() - 0.03, stride.max() + 0.03],
        slope.min(),
        0,
        color="#5b8ff9",
        alpha=0.10,
        label="downhill",
    )
    ax.set_ylim(stride.min() - 0.03, stride.max() + 0.03)
    ax.set_ylabel("stride (m/cycle)")
    ax.set_title("Stride length changes continuously with terrain slope")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower center", ncol=4, fontsize=7.5, framealpha=0.9)
    ax.text(
        0.98,
        0.95,
        f"max adjacent jump = {continuity['max_adjacent_stride_jump_m']*1000:.3f} mm\n"
        f"max 2nd difference = {continuity['max_second_difference_m']*1000:.3f} mm",
        transform=ax.transAxes,
        fontsize=8,
        ha="right",
        va="top",
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#cccccc"},
    )

    ax2 = axes[1]
    contact_floor = np.maximum(contact, 1e-15)
    ax2.plot(
        slope,
        contact_floor,
        color="#d62728",
        marker="o",
        ms=2.5,
        label="contact error (FP floor shown at 1e-15)",
    )
    ax2.axhline(1.0, color="#333333", ls="--", lw=1.0, label="1 mm tolerance")
    ax2.set_yscale("log")
    ax2.set_ylim(1e-15, 10.0)
    ax2.set_ylabel("max sole contact error (mm)")
    ax2.grid(alpha=0.25)
    ax2b = ax2.twinx()
    ax2b.plot(slope, reach, color="#1f77b4", lw=1.2, alpha=0.8, label="IK reach ratio")
    ax2b.set_ylabel("max IK reach ratio")
    ax2b.set_ylim(0.75, 1.02)
    handles = ax2.get_lines() + ax2b.get_lines()
    ax2.legend(handles, [line.get_label() for line in handles], fontsize=8, loc="best")
    ax2.set_xlabel("terrain slope (deg), + is uphill")
    _save(fig, path)


def plot_joint_angles(
    results: dict[str, SimulationResult], path: str | Path
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(9.0, 8.2), sharex=True)
    keys = [
        ("hip_flexion_deg", "hip flexion (deg)"),
        ("knee_flexion_deg", "knee flexion (deg)"),
        ("ankle_dorsiflexion_deg", "ankle dorsiflexion (deg)"),
    ]
    labels = {"-20.0": "downhill -20 deg", "0.0": "level 0 deg", "20.0": "uphill +20 deg"}
    colors = {"-20.0": "#5b8ff9", "0.0": "#555555", "20.0": "#f2a900"}
    for slope_key, result in results.items():
        cycle = result.params.cycle_s
        rows = [
            row
            for row in result.rows
            if row["side"] == "left" and row["time_s"] <= cycle + 1e-9
        ]
        phase = np.array([row["phase"] for row in rows])
        order = np.argsort(phase)
        for axis, (key, _) in zip(axes, keys):
            values = np.array([row[key] for row in rows])
            axis.plot(
                phase[order],
                values[order],
                color=colors.get(slope_key, "#333333"),
                lw=1.8,
                label=labels.get(slope_key, slope_key),
            )
    beta = next(iter(results.values())).params.stance_fraction
    for axis, (_, ylabel) in zip(axes, keys):
        axis.axvspan(0.0, beta, color="#d9ead3", alpha=0.35)
        axis.axvspan(beta, 1.0, color="#fce5cd", alpha=0.25)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.22)
        axis.legend(fontsize=8, loc="best")
    axes[0].set_title("Left-leg joint angles over one gait cycle (shaded: stance | swing)")
    axes[-1].set_xlabel("gait phase")
    axes[-1].set_xlim(0.0, 1.0)
    _save(fig, path)


def plot_foot_trajectory(
    results: dict[str, SimulationResult], path: str | Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6))
    labels = {"-20.0": "downhill -20 deg", "0.0": "level", "20.0": "uphill +20 deg"}
    colors = {"-20.0": "#5b8ff9", "0.0": "#555555", "20.0": "#f2a900"}
    for slope_key, result in results.items():
        cycle = result.params.cycle_s
        rows = [
            row
            for row in result.rows
            if row["side"] == "left" and row["time_s"] <= cycle + 1e-9
        ]
        x = np.array([row["ankle_x_m"] for row in rows])
        z = np.array([row["ankle_z_m"] for row in rows])
        terrain_z = np.array([row["terrain_z_m"] for row in rows])
        phase = np.array([row["phase"] for row in rows])
        color = colors.get(slope_key, "#333333")
        axes[0].plot(x - x[0], z - z[0], color=color, lw=1.8, label=labels.get(slope_key, slope_key))
        x_line = np.linspace(x.min() - 0.15, x.max() + 0.15, 200)
        axes[0].plot(
            x_line - x[0],
            result.terrain.height(x_line) - z[0],
            color=color,
            lw=0.8,
            alpha=0.35,
        )
        axes[1].plot(
            phase,
            z - terrain_z,
            color=color,
            lw=1.6,
            label=labels.get(slope_key, slope_key),
        )
    axes[0].set_title("Ankle trajectory relative to start")
    axes[0].set_xlabel("forward displacement (m)")
    axes[0].set_ylabel("vertical displacement (m)")
    axes[0].set_aspect("equal", adjustable="datalim")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].set_title("Ankle height above local terrain")
    axes[1].set_xlabel("gait phase")
    axes[1].set_ylabel("height above terrain (m)")
    axes[1].grid(alpha=0.25)
    axes[1].set_xlim(0.0, 1.0)
    axes[1].legend(fontsize=8)
    _save(fig, path)


def plot_gait_phases(
    results: dict[str, SimulationResult], path: str | Path
) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 3.6))
    labels = {"20.0": "uphill +20", "0.0": "level", "-20.0": "downhill -20"}
    keys = [key for key in labels if key in results]
    for row_index, slope_key in enumerate(keys):
        result = results[slope_key]
        beta = result.params.stance_fraction
        y = row_index
        ax.barh(y + 0.17, beta, left=0.0, height=0.28, color="#4c78a8", alpha=0.85)
        ax.barh(y - 0.17, 0.5, left=0.5, height=0.28, color="#e45756", alpha=0.85)
        ax.barh(
            y - 0.17,
            beta - 0.5,
            left=0.0,
            height=0.28,
            color="#e45756",
            alpha=0.85,
        )
        ax.barh(y + 0.17, 1.0 - beta, left=beta, height=0.28, color="#4c78a8", alpha=0.22)
        ax.barh(
            y - 0.17,
            1.0 - beta,
            left=beta - 0.5,
            height=0.28,
            color="#e45756",
            alpha=0.22,
        )
        ax.text(1.02, y, f"S={result.stride_m:.3f} m", va="center", fontsize=8)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([labels[key] for key in keys])
    ax.set_xlim(0.0, 1.18)
    ax.set_ylim(-0.6, len(keys) - 0.4)
    ax.set_xlabel("gait cycle phase")
    ax.set_title("Stance windows: left (blue) and right (red); pale = swing")
    ax.grid(axis="x", alpha=0.25)
    _save(fig, path)


def _frame_groups(result: SimulationResult) -> list[dict[str, Any]]:
    grouped: dict[float, dict[str, Any]] = {}
    for row in result.rows:
        key = round(row["time_s"], 9)
        grouped.setdefault(key, {})[row["side"]] = row
    return [{"time_s": key, **grouped[key]} for key in sorted(grouped)]


def animate_scenario(
    result: SimulationResult, path: str | Path, fps: int = 30
) -> None:
    groups = _frame_groups(result)
    x_min = min(row["ankle_x_m"] for row in result.rows) - 0.55
    x_max = max(row["ankle_x_m"] for row in result.rows) + 0.55
    x_line = np.linspace(x_min, x_max, 400)
    terrain_line = result.terrain.height(x_line)
    y_min = float(terrain_line.min()) - 0.12
    y_max = float(terrain_line.max()) + 1.85

    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    ax.fill_between(x_line, y_min, terrain_line, color="#d6c3a5", alpha=0.55)
    ax.plot(x_line, terrain_line, color=COLORS["terrain"], lw=1.8)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.18)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    title = ax.set_title("")
    status = ax.text(
        0.015,
        0.985,
        "",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "#cccccc"},
    )
    artists: dict[str, Any] = {}
    for side in ("left", "right"):
        artists[f"leg_{side}"], = ax.plot([], [], color=COLORS[side], lw=2.4)
        artists[f"foot_{side}"], = ax.plot([], [], color=COLORS[side], lw=4.0, solid_capstyle="round")
        artists[f"joint_{side}"], = ax.plot([], [], "o", color=COLORS[side], ms=4.0)
    artists["torso"], = ax.plot([], [], color="#222222", lw=4.0, solid_capstyle="round")
    artists["head"] = Circle((0, 0), 0.07, color="#222222", alpha=0.85)
    ax.add_patch(artists["head"])

    def draw(index: int) -> list[Any]:
        frame = groups[index]
        left = frame["left"]
        hip = np.array([left["hip_x_m"], left["hip_z_m"]])
        for side in ("left", "right"):
            row = frame[side]
            hip_s = np.array([row["hip_x_m"], row["hip_z_m"]])
            knee = np.array([row["knee_x_m"], row["knee_z_m"]])
            ankle = np.array([row["ankle_x_m"], row["ankle_z_m"]])
            pitch = np.deg2rad(row["foot_pitch_deg"])
            sole = sole_points(ankle, pitch, result.params.leg, count=2)
            artists[f"leg_{side}"].set_data(
                [hip_s[0], knee[0], ankle[0]], [hip_s[1], knee[1], ankle[1]]
            )
            artists[f"foot_{side}"].set_data(sole[:, 0], sole[:, 1])
            artists[f"joint_{side}"].set_data(
                [knee[0], ankle[0]], [knee[1], ankle[1]]
            )
            artists[f"leg_{side}"].set_alpha(1.0 if row["stance"] else 0.72)
            artists[f"foot_{side}"].set_alpha(1.0 if row["stance"] else 0.55)
        torso_top = hip + np.array([0.04, 0.52])
        artists["torso"].set_data([hip[0], torso_top[0]], [hip[1], torso_top[1]])
        artists["head"].center = (torso_top[0] + 0.02, torso_top[1] + 0.09)
        stance_contact = max(
            left["contact_abs_m"] if left["stance"] else 0.0,
            frame["right"]["contact_abs_m"] if frame["right"]["stance"] else 0.0,
        )
        title.set_text(
            f"{result.terrain.name} slope {result.slope_deg:+.0f} deg | "
            f"stride {result.stride_m:.3f} m | cycle {result.params.cycle_s:.2f} s"
        )
        status.set_text(
            f"t = {frame['time_s']:.2f} s | L phase {left['phase']:.2f} "
            f"({left['phase_name']}) | R phase {frame['right']['phase']:.2f} "
            f"({frame['right']['phase_name']})\n"
            f"max stance contact error {stance_contact*1000:.3f} mm | "
            f"speed {result.speed_mps:.3f} m/s"
        )
        return list(artists.values())

    animation = FuncAnimation(
        fig, draw, frames=len(groups), interval=1000.0 / fps, blit=False
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    animation.save(path, writer=PillowWriter(fps=fps))
    plt.close(fig)
