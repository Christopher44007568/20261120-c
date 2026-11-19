"""Closed-form ASG products, real spherical harmonics, and Monte Carlo references."""

from __future__ import annotations

from math import factorial
from typing import Iterable, Sequence

import numpy as np
from scipy.special import i0e, lpmv

from .model import ASG, DirectionalEnvironment, normalize


def _quadratic_matrix(lobe: ASG) -> np.ndarray:
    tangent_u, tangent_v = lobe.basis
    return lobe.lambda_u * np.outer(tangent_u, tangent_u) + lobe.lambda_v * np.outer(
        tangent_v, tangent_v
    )


def asg_integral(amplitude: float, lambda_u: float, lambda_v: float) -> float:
    """Closed-form ASG integral, Eq. 10 of Xu et al. (2013)."""
    if amplitude == 0.0:
        return 0.0
    lambda_large = max(float(lambda_u), float(lambda_v))
    lambda_small = min(float(lambda_u), float(lambda_v))
    if lambda_small <= 0.0:
        raise ValueError("ASG bandwidths must be positive")
    difference = lambda_large - lambda_small
    base = np.pi / np.sqrt(lambda_large * lambda_small)
    f_zero = 2.0 * np.pi * i0e(0.5 * difference)
    f_shift = 2.0 * np.pi * i0e(0.5 * (difference + difference / lambda_small))
    correction = np.exp(-lambda_small) / (2.0 * lambda_large)
    return float(
        amplitude
        * (base - correction * (f_zero + difference / lambda_small * f_shift))
    )


def asg_product(first: ASG, second: ASG) -> tuple[float, float, float, np.ndarray]:
    """Approximate two ASGs by one ASG, Eq. 13 of Xu et al. (2013)."""
    matrix = _quadratic_matrix(first) + _quadratic_matrix(second)
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    product_axis = eigenvectors[:, 0]
    if float(product_axis @ (first.center + second.center)) < 0.0:
        product_axis = -product_axis
    eigenvalue_small, eigenvalue_mid, eigenvalue_large = eigenvalues
    smooth = max(float(product_axis @ first.center), 0.0) * max(
        float(product_axis @ second.center), 0.0
    )
    amplitude = (
        first.amplitude
        * second.amplitude
        * smooth
        * float(np.exp(-eigenvalue_small))
    )
    lambda_u = max(float(eigenvalue_large - eigenvalue_small), 1e-12)
    lambda_v = max(float(eigenvalue_mid - eigenvalue_small), 1e-12)
    return amplitude, lambda_u, lambda_v, product_axis


def asg_pair_integral(first: ASG, second: ASG) -> float:
    """Closed-form integral of the product of two ASGs."""
    amplitude, lambda_u, lambda_v, _ = asg_product(first, second)
    return asg_integral(amplitude, lambda_u, lambda_v)


def asg_brightness(
    environment_lobes: Iterable[ASG],
    normals: np.ndarray,
    kernel_sigma_u: float,
    kernel_sigma_v: float,
    kernel_rotation: float = 0.0,
    ambient: float = 0.0,
) -> np.ndarray:
    """Evaluate ``integral L(w) K_n(w) dOmega`` with ASG-ASG products."""
    lobes = tuple(environment_lobes)
    normals = normalize(np.asarray(normals, dtype=np.float64))
    result = np.empty(normals.shape[0], dtype=np.float64)
    kernel_integral = ambient * asg_integral(
        1.0, 1.0 / (2.0 * kernel_sigma_u**2), 1.0 / (2.0 * kernel_sigma_v**2)
    )
    for index, normal in enumerate(normals):
        kernel = ASG(normal, kernel_sigma_u, kernel_sigma_v, kernel_rotation, 1.0)
        result[index] = kernel_integral + sum(
            asg_pair_integral(lobe, kernel) for lobe in lobes
        )
    return result


def real_sh_basis(directions: np.ndarray, max_degree: int) -> tuple[np.ndarray, list[tuple[int, int, str]]]:
    """Orthonormal real spherical harmonics through ``max_degree``."""
    directions = normalize(np.asarray(directions, dtype=np.float64))
    x, y, z = directions.T
    azimuth = np.arctan2(y, x)
    terms: list[tuple[int, int, str]] = []
    columns: list[np.ndarray] = []
    for degree in range(max_degree + 1):
        for order in range(degree + 1):
            normalization = np.sqrt(
                (2 * degree + 1)
                / (4.0 * np.pi)
                * factorial(degree - order)
                / factorial(degree + order)
            )
            associated = lpmv(order, degree, z)
            if order == 0:
                terms.append((degree, 0, "c"))
                columns.append(normalization * associated)
            else:
                scale = np.sqrt(2.0) * normalization * associated
                terms.append((degree, order, "c"))
                columns.append(scale * np.cos(order * azimuth))
                terms.append((degree, order, "s"))
                columns.append(scale * np.sin(order * azimuth))
    return np.column_stack(columns), terms


def sh_project(values: np.ndarray, basis: np.ndarray) -> np.ndarray:
    """Project samples on an equal-area sphere sampling."""
    values = np.asarray(values, dtype=np.float64)
    return (4.0 * np.pi / values.shape[0]) * (basis.T @ values)


def sh_kernel_coefficients(
    normals: np.ndarray,
    basis: np.ndarray,
    kernel_sigma_u: float,
    kernel_sigma_v: float,
    kernel_rotation: float,
    sampling_directions: np.ndarray,
) -> np.ndarray:
    normals = normalize(np.asarray(normals, dtype=np.float64))
    coefficients = np.empty((normals.shape[0], basis.shape[1]), dtype=np.float64)
    for index, normal in enumerate(normals):
        kernel = ASG(normal, kernel_sigma_u, kernel_sigma_v, kernel_rotation, 1.0)
        coefficients[index] = sh_project(kernel.evaluate(sampling_directions), basis)
    return coefficients


def sh_brightness(
    environment_coefficients: np.ndarray,
    kernel_coefficients: np.ndarray,
    max_degree: int | None = None,
    terms: Sequence[tuple[int, int, str]] | None = None,
) -> np.ndarray:
    if max_degree is not None:
        if terms is None:
            raise ValueError("terms are required when max_degree is given")
        selected = np.array([degree <= max_degree for degree, _, _ in terms])
        return kernel_coefficients[:, selected] @ environment_coefficients[selected]
    return kernel_coefficients @ environment_coefficients


def monte_carlo_brightness(
    environment: DirectionalEnvironment,
    normals: np.ndarray,
    kernel_sigma_u: float,
    kernel_sigma_v: float,
    sample_count: int = 1 << 20,
    seed: int = 20261120,
    chunk_size: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """Uniform-sphere Monte Carlo reference with block standard errors."""
    rng = np.random.default_rng(seed)
    z = rng.uniform(-1.0, 1.0, size=sample_count)
    phi = rng.uniform(0.0, 2.0 * np.pi, size=sample_count)
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    directions = np.column_stack((radius * np.cos(phi), radius * np.sin(phi), z))
    radiance = environment.radiance(directions)
    normals = normalize(np.asarray(normals, dtype=np.float64))
    values = np.empty(normals.shape[0], dtype=np.float64)
    standard_errors = np.empty(normals.shape[0], dtype=np.float64)
    block_count = 64
    block_size = sample_count // block_count
    solid_angle = 4.0 * np.pi

    for start in range(0, normals.shape[0], chunk_size):
        end = min(start + chunk_size, normals.shape[0])
        kernels = np.array(
            [
                ASG(normal, kernel_sigma_u, kernel_sigma_v, 0.0, 1.0).evaluate(directions)
                for normal in normals[start:end]
            ]
        )
        samples = radiance[None, :] * kernels * solid_angle
        values[start:end] = samples.mean(axis=1)
        blocks = samples[:, : block_count * block_size].reshape(end - start, block_count, block_size)
        block_means = blocks.mean(axis=2)
        standard_errors[start:end] = block_means.std(axis=1, ddof=1) / np.sqrt(block_count)
    return values, standard_errors
