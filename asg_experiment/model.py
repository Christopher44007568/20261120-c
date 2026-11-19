"""Anisotropic spherical Gaussian (ASG) primitives and the test environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


def normalize(vector: np.ndarray, axis: int = -1) -> np.ndarray:
    """Return unit vectors while leaving the input untouched."""
    vector = np.asarray(vector, dtype=np.float64)
    length = np.linalg.norm(vector, axis=axis, keepdims=True)
    if np.any(length < 1e-15):
        raise ValueError("cannot normalize a zero vector")
    return vector / length


def fibonacci_sphere(count: int, offset: float = 0.0) -> np.ndarray:
    """Generate an equal-area deterministic sampling of the unit sphere."""
    index = np.arange(count, dtype=np.float64)
    z = 1.0 - 2.0 * (index + 0.5 + offset) / count
    z = np.clip(z, -1.0, 1.0)
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = index * (np.pi * (3.0 - np.sqrt(5.0)))
    return np.column_stack((radius * np.cos(phi), radius * np.sin(phi), z))


def random_sphere(count: int, seed: int = 7) -> np.ndarray:
    """Uniform random directions on S^2."""
    rng = np.random.default_rng(seed)
    z = rng.uniform(-1.0, 1.0, size=count)
    phi = rng.uniform(0.0, 2.0 * np.pi, size=count)
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.column_stack((radius * np.cos(phi), radius * np.sin(phi), z))


def direction_from_angles(azimuth: float, elevation: float) -> np.ndarray:
    cos_elevation = np.cos(elevation)
    return np.array(
        [
            cos_elevation * np.cos(azimuth),
            cos_elevation * np.sin(azimuth),
            np.sin(elevation),
        ],
        dtype=np.float64,
    )


def angles_from_direction(direction: Iterable[float]) -> tuple[float, float]:
    x, y, z = normalize(np.asarray(list(direction), dtype=np.float64))
    return float(np.arctan2(y, x)), float(np.arcsin(np.clip(z, -1.0, 1.0)))


def directional_basis(axis: np.ndarray, rotation: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Build an orthonormal tangent basis rotated by ``rotation`` radians."""
    axis = normalize(np.asarray(axis, dtype=np.float64))
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(axis[2])) > 0.94:
        reference = np.array([1.0, 0.0, 0.0])
    tangent_u = normalize(np.cross(reference, axis))
    tangent_v = np.cross(axis, tangent_u)
    if rotation:
        cos_r, sin_r = np.cos(rotation), np.sin(rotation)
        rotated_u = cos_r * tangent_u + sin_r * tangent_v
        rotated_v = -sin_r * tangent_u + cos_r * tangent_v
        tangent_u, tangent_v = rotated_u, rotated_v
    return tangent_u, tangent_v


@dataclass(frozen=True)
class ASG:
    """An unnormalized Bingham-style anisotropic spherical Gaussian.

    ``G(w) = amplitude * exp(-0.5 * ((u.w/sigma_u)^2
                                  + (v.w/sigma_v)^2))
             * max(center.w, 0)``
    where ``(u, v, center)`` is an orthonormal frame. The hemispherical smooth
    term removes the antipodal peak and follows the ASG definition of Xu et al.
    (2013). The maximum value is approximately ``amplitude`` at ``center``.
    """

    center: np.ndarray
    sigma_u: float
    sigma_v: float
    rotation: float
    amplitude: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "center", normalize(np.asarray(self.center, dtype=np.float64)))
        if self.sigma_u <= 0.0 or self.sigma_v <= 0.0:
            raise ValueError("ASG widths must be positive")

    @property
    def basis(self) -> tuple[np.ndarray, np.ndarray]:
        return directional_basis(self.center, self.rotation)

    @property
    def anisotropy(self) -> float:
        return max(self.sigma_u, self.sigma_v) / min(self.sigma_u, self.sigma_v)

    def evaluate(self, directions: np.ndarray) -> np.ndarray:
        directions = np.asarray(directions, dtype=np.float64)
        tangent_u, tangent_v = self.basis
        component_u = directions @ tangent_u / self.sigma_u
        component_v = directions @ tangent_v / self.sigma_v
        return self.amplitude * np.exp(
            -0.5 * (component_u**2 + component_v**2)
        ) * np.maximum(directions @ self.center, 0.0)

    @property
    def lambda_u(self) -> float:
        return 1.0 / (2.0 * self.sigma_u**2)

    @property
    def lambda_v(self) -> float:
        return 1.0 / (2.0 * self.sigma_v**2)

    @property
    def azimuth(self) -> float:
        return angles_from_direction(self.center)[0]

    @property
    def elevation(self) -> float:
        return angles_from_direction(self.center)[1]


def evaluate_lobes(lobes: Iterable[ASG], directions: np.ndarray) -> np.ndarray:
    """Evaluate and sum a collection of ASG lobes."""
    directions = np.asarray(directions, dtype=np.float64)
    result = np.zeros(directions.shape[0], dtype=np.float64)
    for lobe in lobes:
        result += lobe.evaluate(directions)
    return result


@dataclass(frozen=True)
class DirectionalEnvironment:
    """A synthetic, strongly directional radiance field used as ground truth."""

    lobes: tuple[ASG, ...]
    ambient: float = 0.10

    def radiance(self, directions: np.ndarray) -> np.ndarray:
        return self.ambient + evaluate_lobes(self.lobes, directions)

    @classmethod
    def studio(cls) -> "DirectionalEnvironment":
        degrees = np.pi / 180.0
        definitions = (
            ((25.0, 18.0), (0.100, 0.320), 20.0, 14.0),
            ((5.0, 5.0), (0.075, 0.220), -25.0, 8.5),
            ((-118.0, 28.0), (0.120, 0.420), 0.0, 5.0),
            ((150.0, -12.0), (0.400, 0.620), 0.0, 2.2),
            ((-20.0, 72.0), (0.200, 0.130), 35.0, 3.0),
            ((-35.0, -38.0), (0.220, 0.380), 15.0, 1.6),
        )
        lobes = tuple(
            ASG(
                center=direction_from_angles(azimuth * degrees, elevation * degrees),
                sigma_u=widths[0],
                sigma_v=widths[1],
                rotation=rotation * degrees,
                amplitude=amplitude,
            )
            for (azimuth, elevation), widths, rotation, amplitude in definitions
        )
        return cls(lobes=lobes, ambient=0.10)
