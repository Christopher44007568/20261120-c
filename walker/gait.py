"""Procedural gait-phase generator with slope-adaptive foot trajectories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .ik import LegGeometry, LegPose, solve_leg, sole_points
from .terrain import Terrain, make_terrain


@dataclass(frozen=True)
class GaitParams:
    cycle_s: float = 1.0
    stance_fraction: float = 0.62
    base_stride_m: float = 0.72
    hip_height_m: float = 0.90
    leg: LegGeometry = field(default_factory=LegGeometry)
    swing_clearance_m: float = 0.12
    uphill_stride_coeff: float = 0.22
    downhill_stride_coeff: float = 0.12
    slope_reference_deg: float = 14.0

    def validate(self) -> None:
        if not 0.5 < self.stance_fraction < 1.0:
            raise ValueError("stance_fraction must be in (0.5, 1.0) for walking")
        if self.cycle_s <= 0.0 or self.base_stride_m <= 0.0:
            raise ValueError("cycle_s and base_stride_m must be positive")


def _smoothstep(u: np.ndarray | float) -> np.ndarray | float:
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (10.0 + u * (-15.0 + 6.0 * u))


def stride_for_slope(slope_deg: float, params: GaitParams | None = None) -> float:
    """Smooth, asymmetric slope-stride model.

    Uphill walking shortens the stride more strongly than downhill walking.
    The function is continuous at zero slope and saturates at steep angles.
    """

    params = params or GaitParams()
    angle = np.deg2rad(float(slope_deg))
    reference = np.deg2rad(params.slope_reference_deg)
    scaled = angle / reference
    # A softplus split keeps the uphill/downhill asymmetry but makes the
    # transition at zero slope smooth (C-infinity), so stride has no kink.
    up = np.log1p(np.exp(scaled)) - np.log(2.0)
    down = np.log1p(np.exp(-scaled)) - np.log(2.0)
    reduction = params.uphill_stride_coeff * np.tanh(up) ** 2
    reduction += params.downhill_stride_coeff * np.tanh(down) ** 2
    return float(params.base_stride_m * (1.0 - reduction))


@dataclass
class FootState:
    phase: float
    stance: bool
    ankle: np.ndarray
    pitch_rad: float
    stride_m: float
    reach_x_m: float


def foot_state(
    t: float,
    side_offset: float,
    hip_x: float,
    speed: float,
    stride: float,
    terrain: Terrain,
    params: GaitParams,
) -> FootState:
    """Return the foot target at time ``t`` for one side."""

    cycle = params.cycle_s
    beta = params.stance_fraction
    geometry = params.leg
    phase = float((t / cycle + side_offset) % 1.0)
    half_span = beta * stride / 2.0
    stance = phase < beta
    ankle_height = geometry.ankle_height_m

    if stance:
        reach_x = half_span * (1.0 - 2.0 * phase / beta)
        foot_x = hip_x + reach_x
        pitch = float(terrain.angle_at(foot_x))
        foot_z = float(terrain.height(foot_x)) + ankle_height / np.cos(pitch)
    else:
        u = (phase - beta) / (1.0 - beta)
        blend = float(_smoothstep(u))
        reach_x = -half_span + 2.0 * half_span * blend
        foot_x = hip_x + reach_x
        time_since_toe_off = (phase - beta) * cycle
        time_to_land = (1.0 - phase) * cycle
        x_toe_off = hip_x - speed * time_since_toe_off - half_span
        x_land = hip_x + speed * time_to_land + half_span
        pitch_toe = float(terrain.angle_at(x_toe_off))
        pitch_land = float(terrain.angle_at(x_land))
        z_toe = float(terrain.height(x_toe_off)) + ankle_height / np.cos(pitch_toe)
        z_land = float(terrain.height(x_land)) + ankle_height / np.cos(pitch_land)
        bump = params.swing_clearance_m * np.sin(np.pi * u)
        foot_z = (1.0 - blend) * z_toe + blend * z_land + bump
        pitch = (1.0 - blend) * pitch_toe + blend * pitch_land

    return FootState(
        phase=phase,
        stance=stance,
        ankle=np.array([foot_x, foot_z], dtype=float),
        pitch_rad=float(pitch),
        stride_m=float(stride),
        reach_x_m=float(reach_x),
    )


def _joint_stats(rows: list[dict[str, Any]], side: str) -> dict[str, float]:
    subset = [row for row in rows if row["side"] == side]
    out: dict[str, float] = {}
    for key in ("hip_flexion_deg", "knee_flexion_deg", "ankle_dorsiflexion_deg"):
        values = np.array([row[key] for row in subset], dtype=float)
        out[f"{key}_min"] = float(values.min())
        out[f"{key}_max"] = float(values.max())
        out[f"{key}_rom"] = float(values.max() - values.min())
    out["peak_knee_flexion_deg"] = out["knee_flexion_deg_max"]
    return out


@dataclass
class SimulationResult:
    slope_deg: float
    terrain: Terrain
    params: GaitParams
    stride_m: float
    measured_stride_m: float
    speed_mps: float
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


def simulate_scenario(
    slope_deg: float,
    params: GaitParams | None = None,
    terrain: Terrain | None = None,
    duration_cycles: float = 2.0,
    sample_hz: float = 240.0,
    start_x: float = 0.0,
) -> SimulationResult:
    params = params or GaitParams()
    params.validate()
    terrain = terrain or make_terrain("plane", slope_deg)
    stride = stride_for_slope(slope_deg, params)
    speed = stride / params.cycle_s
    duration = duration_cycles * params.cycle_s
    count = int(round(duration * sample_hz)) + 1
    times = np.linspace(0.0, duration, count)
    beta = params.stance_fraction
    geometry = params.leg
    rows: list[dict[str, Any]] = []
    previous_stance_x: dict[str, float | None] = {"left": None, "right": None}
    slip: dict[str, float] = {"left": 0.0, "right": 0.0}

    for t in times:
        hip_x = start_x + speed * float(t)
        hip_z = float(terrain.height(hip_x)) + params.hip_height_m
        hip = np.array([hip_x, hip_z])
        for side, offset in (("left", 0.0), ("right", 0.5)):
            state = foot_state(
                float(t), offset, hip_x, speed, stride, terrain, params
            )
            pose: LegPose = solve_leg(hip, state.ankle, geometry, state.pitch_rad)
            sole = sole_points(pose.ankle, pose.foot_pitch_rad, geometry)
            signed = terrain.signed_distance(sole)
            abs_contact = float(np.max(np.abs(signed)))
            rmse_contact = float(np.sqrt(np.mean(signed**2)))
            lift = float(np.min(signed))

            if state.stance:
                if previous_stance_x[side] is not None:
                    slip[side] += abs(float(state.ankle[0]) - previous_stance_x[side])
                previous_stance_x[side] = float(state.ankle[0])
            else:
                previous_stance_x[side] = None

            rows.append(
                {
                    "time_s": float(t),
                    "side": side,
                    "phase": state.phase,
                    "stance": bool(state.stance),
                    "phase_name": "stance" if state.stance else "swing",
                    "hip_x_m": float(hip[0]),
                    "hip_z_m": float(hip[1]),
                    "knee_x_m": float(pose.knee[0]),
                    "knee_z_m": float(pose.knee[1]),
                    "ankle_x_m": float(pose.ankle[0]),
                    "ankle_z_m": float(pose.ankle[1]),
                    "foot_pitch_deg": float(np.rad2deg(pose.foot_pitch_rad)),
                    "hip_flexion_deg": pose.hip_flexion_deg,
                    "knee_flexion_deg": pose.knee_flexion_deg,
                    "ankle_dorsiflexion_deg": pose.ankle_dorsiflexion_deg,
                    "reach_ratio": pose.reach_ratio,
                    "reached": pose.reached,
                    "contact_abs_m": abs_contact if state.stance else 0.0,
                    "contact_rmse_m": rmse_contact if state.stance else 0.0,
                    "contact_signed_min_m": float(signed.min()),
                    "contact_signed_max_m": float(signed.max()),
                    "foot_lift_m": lift,
                    "terrain_z_m": float(terrain.height(state.ankle[0])),
                }
            )

    start_state = foot_state(
        0.0, 0.0, start_x, speed, stride, terrain, params
    )
    end_state = foot_state(
        params.cycle_s, 0.0, start_x + stride, speed, stride, terrain, params
    )
    measured_stride = float(end_state.ankle[0] - start_state.ankle[0])
    stance_rows = [row for row in rows if row["stance"]]
    contact_values = np.array([row["contact_abs_m"] for row in stance_rows])
    contact_rmse = np.array([row["contact_rmse_m"] for row in stance_rows])
    swing_rows = [row for row in rows if not row["stance"]]
    clearance = max((row["foot_lift_m"] for row in swing_rows), default=0.0)
    reach_max = max(row["reach_ratio"] for row in rows)
    all_reached = all(row["reached"] for row in rows)

    summary: dict[str, Any] = {
        "slope_deg": float(slope_deg),
        "terrain": terrain.name,
        "cycle_s": params.cycle_s,
        "stance_s": beta * params.cycle_s,
        "swing_s": (1.0 - beta) * params.cycle_s,
        "double_support_s": max(0.0, 2.0 * beta - 1.0) * params.cycle_s,
        "duty_factor": beta,
        "cadence_steps_per_min": 120.0 / params.cycle_s,
        "stride_m": stride,
        "step_m": stride / 2.0,
        "measured_stride_m": measured_stride,
        "speed_mps": speed,
        "contact_max_abs_m": float(contact_values.max()) if contact_values.size else 0.0,
        "contact_rmse_m": float(np.sqrt(np.mean(contact_rmse**2)))
        if contact_rmse.size
        else 0.0,
        "contact_penetration_max_m": float(
            min((row["contact_signed_min_m"] for row in stance_rows), default=0.0)
        ),
        "contact_gap_max_m": float(
            max((row["contact_signed_max_m"] for row in stance_rows), default=0.0)
        ),
        "foot_slip_max_m": float(max(slip.values())),
        "swing_clearance_max_m": float(clearance),
        "reach_ratio_max": float(reach_max),
        "all_reached": bool(all_reached),
        "frames": len(rows),
    }
    summary["left"] = _joint_stats(rows, "left")
    summary["right"] = _joint_stats(rows, "right")
    return SimulationResult(
        slope_deg=float(slope_deg),
        terrain=terrain,
        params=params,
        stride_m=stride,
        measured_stride_m=measured_stride,
        speed_mps=speed,
        rows=rows,
        summary=summary,
    )
