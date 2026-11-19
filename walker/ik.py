"""Planar two-link leg IK with geometric joint-angle reporting."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LegGeometry:
    thigh_m: float = 0.48
    shank_m: float = 0.48
    foot_length_m: float = 0.24
    ankle_height_m: float = 0.07

    @property
    def reach_m(self) -> float:
        return self.thigh_m + self.shank_m


@dataclass
class LegPose:
    hip: np.ndarray
    knee: np.ndarray
    ankle: np.ndarray
    foot_pitch_rad: float
    knee_bend_deg: float
    hip_flexion_deg: float
    knee_flexion_deg: float
    ankle_dorsiflexion_deg: float
    reach_ratio: float
    reached: bool


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        return np.array([0.0, -1.0])
    return vector / norm


def solve_leg(
    hip: np.ndarray,
    ankle: np.ndarray,
    geometry: LegGeometry,
    foot_pitch_rad: float = 0.0,
) -> LegPose:
    """Solve hip/knee/ankle angles in the sagittal plane.

    The knee is chosen anterior to the hip-ankle line. ``foot_pitch_rad`` is
    the absolute sole pitch measured from +x, so a flat sole has pitch zero.
    """

    hip = np.asarray(hip, dtype=float)
    ankle = np.asarray(ankle, dtype=float)
    l1 = float(geometry.thigh_m)
    l2 = float(geometry.shank_m)
    delta = ankle - hip
    distance = float(np.linalg.norm(delta))
    reach = l1 + l2
    reached = bool(distance <= reach + 1e-12 and distance >= abs(l1 - l2) - 1e-12)

    safe_distance = float(np.clip(distance, abs(l1 - l2) + 1e-9, reach - 1e-9))
    direction = _unit(delta)
    line_angle = float(np.arctan2(direction[1], direction[0]))

    cos_knee = (l1 * l1 + safe_distance * safe_distance - l2 * l2) / (
        2.0 * l1 * safe_distance
    )
    alpha = float(np.arccos(np.clip(cos_knee, -1.0, 1.0)))
    thigh_angle = line_angle + alpha
    knee = hip + l1 * np.array([np.cos(thigh_angle), np.sin(thigh_angle)])

    shank_angle = float(np.arctan2(ankle[1] - knee[1], ankle[0] - knee[0]))
    interior = (l1 * l1 + l2 * l2 - safe_distance * safe_distance) / (2.0 * l1 * l2)
    knee_bend = float(np.pi - np.arccos(np.clip(interior, -1.0, 1.0)))

    hip_flexion = np.rad2deg(thigh_angle + np.pi / 2.0)
    knee_flexion = np.rad2deg(knee_bend)
    ankle_dorsi = np.rad2deg(foot_pitch_rad - (shank_angle + np.pi / 2.0))
    ankle_dorsi = float((ankle_dorsi + 180.0) % 360.0 - 180.0)

    return LegPose(
        hip=hip,
        knee=knee,
        ankle=ankle,
        foot_pitch_rad=float(foot_pitch_rad),
        knee_bend_deg=float(np.rad2deg(knee_bend)),
        hip_flexion_deg=float(hip_flexion),
        knee_flexion_deg=float(knee_flexion),
        ankle_dorsiflexion_deg=ankle_dorsi,
        reach_ratio=distance / reach,
        reached=reached,
    )


def sole_points(
    ankle: np.ndarray,
    foot_pitch_rad: float,
    geometry: LegGeometry,
    count: int = 7,
) -> np.ndarray:
    """World-space points along the rigid sole, heel first."""

    ankle = np.asarray(ankle, dtype=float)
    s = np.linspace(-geometry.foot_length_m / 2.0, geometry.foot_length_m / 2.0, count)
    c = np.cos(foot_pitch_rad)
    sn = np.sin(foot_pitch_rad)
    h = geometry.ankle_height_m
    x = ankle[0] + s * c + h * sn
    z = ankle[1] + s * sn - h * c
    return np.column_stack([x, z])
