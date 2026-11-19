"""Fit a directional environment with a non-negative ASG mixture."""

from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np
from scipy.optimize import least_squares

from .model import (
    ASG,
    DirectionalEnvironment,
    angles_from_direction,
    direction_from_angles,
    evaluate_lobes,
)


@dataclass(frozen=True)
class FittedEnvironment:
    lobes: tuple[ASG, ...]
    ambient: float
    fit_time_s: float
    nfev: int

    def radiance(self, directions: np.ndarray) -> np.ndarray:
        return self.ambient + evaluate_lobes(self.lobes, directions)


def _encode(params: np.ndarray) -> FittedEnvironment:
    lobe_count = (params.shape[0] - 1) // 6
    lobes: list[ASG] = []
    for index in range(lobe_count):
        start = 6 * index
        azimuth, elevation, log_u, log_v, rotation, log_amplitude = params[start : start + 6]
        lobes.append(
            ASG(
                center=direction_from_angles(float(azimuth), float(elevation)),
                sigma_u=float(np.exp(log_u)),
                sigma_v=float(np.exp(log_v)),
                rotation=float(rotation),
                amplitude=float(np.exp(log_amplitude)),
            )
        )
    return FittedEnvironment(
        lobes=tuple(lobes),
        ambient=float(np.exp(params[-1])),
        fit_time_s=0.0,
        nfev=0,
    )


def _initial_component(direction: np.ndarray, amplitude: float) -> np.ndarray:
    azimuth, elevation = angles_from_direction(direction)
    return np.array(
        [
            azimuth,
            np.clip(elevation, -0.5 * np.pi + 0.02, 0.5 * np.pi - 0.02),
            np.log(0.16),
            np.log(0.30),
            0.0,
            np.log(max(amplitude, 1e-3)),
        ],
        dtype=np.float64,
    )


def _grow_params(
    params: np.ndarray,
    target: np.ndarray,
    grid: np.ndarray,
    target_lobe_count: int,
) -> np.ndarray:
    params = params.copy()
    for _ in range(target_lobe_count - (params.shape[0] - 1) // 6):
        current = _encode(params)
        residual = target - current.radiance(grid)
        peak_index = int(np.argmax(residual))
        peak = max(float(residual[peak_index]), 0.02)
        component = _initial_component(grid[peak_index], 0.75 * peak)
        params = np.concatenate((params[:-1], component, params[-1:]))
    return params


def _bounds(lobe_count: int) -> tuple[np.ndarray, np.ndarray]:
    lower: list[float] = []
    upper: list[float] = []
    for _ in range(lobe_count):
        lower.extend(
            [
                -np.pi,
                -0.5 * np.pi + 0.02,
                np.log(0.035),
                np.log(0.035),
                -np.pi,
                np.log(1e-5),
            ]
        )
        upper.extend(
            [
                np.pi,
                0.5 * np.pi - 0.02,
                np.log(0.85),
                np.log(0.85),
                np.pi,
                np.log(60.0),
            ]
        )
    lower.append(np.log(1e-5))
    upper.append(np.log(5.0))
    return np.asarray(lower), np.asarray(upper)


def fit_asg_mixture(
    environment: DirectionalEnvironment,
    lobe_counts: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 12, 16),
    fit_samples: int = 1536,
    max_nfev: int = 260,
) -> dict[int, FittedEnvironment]:
    """Fit one environment and return models for each requested mixture size."""
    # A Fibonacci lattice with a small offset avoids aligning with validation.
    indices = np.arange(fit_samples, dtype=np.float64)
    z = 1.0 - 2.0 * (indices + 0.5 + 0.137) / fit_samples
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = indices * (np.pi * (3.0 - np.sqrt(5.0))) + 0.31
    grid = np.column_stack((radius * np.cos(phi), radius * np.sin(phi), z))
    target = environment.radiance(grid)
    weight = 1.0 / np.sqrt(target + 0.20)
    params = np.array([np.log(max(environment.ambient, 1e-4))])
    results: dict[int, FittedEnvironment] = {}

    for requested_count in sorted(lobe_counts):
        params = _grow_params(params, target, grid, requested_count)
        lower, upper = _bounds(requested_count)
        params = np.clip(params, lower + 1e-8, upper - 1e-8)

        def residual(vector: np.ndarray) -> np.ndarray:
            model = _encode(vector).radiance(grid)
            return (model - target) * weight

        started = time.perf_counter()
        optimization = least_squares(
            residual,
            params,
            bounds=(lower, upper),
            method="trf",
            x_scale="jac",
            ftol=2e-7,
            xtol=2e-7,
            gtol=2e-7,
            max_nfev=max_nfev,
            verbose=0,
        )
        elapsed = time.perf_counter() - started
        params = optimization.x
        encoded = _encode(params)
        results[requested_count] = FittedEnvironment(
            lobes=encoded.lobes,
            ambient=encoded.ambient,
            fit_time_s=elapsed,
            nfev=int(optimization.nfev),
        )
    return results
