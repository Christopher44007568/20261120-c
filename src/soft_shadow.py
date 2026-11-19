from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d


@dataclass(frozen=True)
class ShadowScene:
    light_height: float = 1.2
    light_half_width: float = 0.32
    light_samples: int = 41
    occluder_center: tuple[float, float] = (0.15, 0.55)
    occluder_radius: float = 0.03
    receiver_min: float = -1.0
    receiver_max: float = 1.0
    receiver_samples: int = 1201


def _receivers(scene: ShadowScene) -> np.ndarray:
    return np.linspace(
        scene.receiver_min, scene.receiver_max, scene.receiver_samples
    )


def _light_samples(scene: ShadowScene) -> np.ndarray:
    return np.linspace(
        -scene.light_half_width, scene.light_half_width, scene.light_samples
    )


def _exact_blocked(scene: ShadowScene, x: float, light_x: float) -> bool:
    origin = np.asarray((x, 0.0))
    target = np.asarray((light_x, scene.light_height))
    direction = target - origin
    offset = origin - np.asarray(scene.occluder_center)
    a = float(direction @ direction)
    b = 2.0 * float(offset @ direction)
    c = float(offset @ offset - scene.occluder_radius**2)
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return False
    root = (-b - np.sqrt(discriminant)) / (2.0 * a)
    return 0.0 <= root <= 1.0


def _marched_blocked(
    scene: ShadowScene, x: float, light_x: float, step: float
) -> tuple[bool, int]:
    origin = np.asarray((x, 0.0))
    target = np.asarray((light_x, scene.light_height))
    direction = target - origin
    distance = float(np.linalg.norm(direction))
    count = max(int(np.ceil(distance / step)), 1)
    samples = origin + np.linspace(0.0, 1.0, count + 1)[:, None] * direction
    blocked = np.any(
        np.linalg.norm(samples - np.asarray(scene.occluder_center), axis=1)
        < scene.occluder_radius
    )
    return bool(blocked), count


def visibility_profile(
    scene: ShadowScene, step: float | None
) -> tuple[np.ndarray, float]:
    x_values = _receivers(scene)
    light = _light_samples(scene)
    visibility = np.zeros_like(x_values)
    step_counts = []
    for i, x in enumerate(x_values):
        visible = 0
        for light_x in light:
            if step is None:
                blocked = _exact_blocked(scene, float(x), float(light_x))
            else:
                blocked, count = _marched_blocked(
                    scene, float(x), float(light_x), step
                )
                step_counts.append(count)
            visible += int(not blocked)
        visibility[i] = visible / len(light)
    average_steps = float(np.mean(step_counts)) if step_counts else 0.0
    return visibility, average_steps


def penumbra_width(x_values: np.ndarray, visibility: np.ndarray) -> float:
    smoothed = gaussian_filter1d(visibility, sigma=3.0)
    transition = (smoothed > 0.05) & (smoothed < 0.95)
    if np.count_nonzero(transition) < 2:
        return 0.0
    return float(np.ptp(x_values[transition]))


def run_step_experiment(
    steps: tuple[float, ...] = (
        0.1000,
        0.0750,
        0.0500,
        0.0400,
        0.0300,
        0.0250,
        0.0200,
        0.0150,
        0.0100,
        0.0075,
        0.0050,
        0.0025,
    ),
) -> dict:
    scene = ShadowScene()
    x_values = _receivers(scene)
    reference, _ = visibility_profile(scene, None)
    reference_width = penumbra_width(x_values, reference)
    rows = []
    profiles = {}
    for step in steps:
        visibility, average_steps = visibility_profile(scene, step)
        width = penumbra_width(x_values, visibility)
        rows.append(
            {
                "step": step,
                "average_steps": average_steps,
                "penumbra_width": width,
                "penumbra_ratio": width / max(reference_width, 1e-12),
                "relative_error": abs(width - reference_width)
                / max(reference_width, 1e-12),
                "visibility_mse": float(np.mean((visibility - reference) ** 2)),
            }
        )
        profiles[step] = visibility.tolist()
    return {
        "scene": {
            "type": "receiver-plane + finite line light + circular occluder",
            "light_height": scene.light_height,
            "light_half_width": scene.light_half_width,
            "light_samples": scene.light_samples,
            "occluder_center": scene.occluder_center,
            "occluder_radius": scene.occluder_radius,
            "receiver_range": [scene.receiver_min, scene.receiver_max],
        },
        "reference_penumbra_width": reference_width,
        "receiver_x": x_values.tolist(),
        "reference_visibility": reference.tolist(),
        "rows": rows,
        "profiles": profiles,
    }


def recommended_step(result: dict) -> dict:
    eligible = [
        row
        for row in result["rows"]
        if row["relative_error"] <= 0.01 and row["visibility_mse"] <= 1e-4
    ]
    return min(eligible, key=lambda row: row["average_steps"])

