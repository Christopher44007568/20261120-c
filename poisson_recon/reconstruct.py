"""Poisson reconstruction backends and point-cloud helpers."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.fft import dctn, idctn
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class ReconstructionResult:
    vertices: np.ndarray
    faces: np.ndarray
    backend: str
    runtime_s: float
    metadata: dict[str, Any]


_OPEN3D: Any | None = None
_OPEN3D_ERROR: str | None = None


def _load_open3d() -> Any | None:
    global _OPEN3D, _OPEN3D_ERROR
    if _OPEN3D is not None:
        return _OPEN3D
    try:
        import open3d as o3d

        _OPEN3D = o3d
        return o3d
    except Exception as first_error:
        _OPEN3D_ERROR = str(first_error)
    try:
        import libusb_package

        ctypes.CDLL(
            libusb_package.get_library_path(), mode=ctypes.RTLD_GLOBAL
        )
        import open3d as o3d

        _OPEN3D = o3d
        return o3d
    except Exception as second_error:
        _OPEN3D_ERROR = f"{_OPEN3D_ERROR}; {second_error}"
        return None


def open3d_available() -> bool:
    return _load_open3d() is not None


def open3d_error() -> str | None:
    _load_open3d()
    return _OPEN3D_ERROR


def _open3d_poisson(
    points: np.ndarray,
    normals: np.ndarray,
    depth: int,
    scale: float,
    linear_fit: bool,
) -> ReconstructionResult:
    o3d = _load_open3d()
    if o3d is None:
        raise RuntimeError(f"Open3D unavailable: {_OPEN3D_ERROR}")
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=float))
    cloud.normals = o3d.utility.Vector3dVector(np.asarray(normals, dtype=float))
    start = time.perf_counter()
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        cloud, depth=int(depth), scale=float(scale), linear_fit=bool(linear_fit)
    )
    runtime = time.perf_counter() - start
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    density = np.asarray(densities, dtype=float)
    return ReconstructionResult(
        vertices=vertices,
        faces=faces,
        backend="open3d_poisson",
        runtime_s=runtime,
        metadata={
            "depth": int(depth),
            "scale": float(scale),
            "linear_fit": bool(linear_fit),
            "density_min": float(density.min()) if density.size else None,
            "density_max": float(density.max()) if density.size else None,
            "density_mean": float(density.mean()) if density.size else None,
        },
    )


def _splat_normals(
    points: np.ndarray, normals: np.ndarray, lo: np.ndarray, h: float, n: int
) -> np.ndarray:
    grid = (points - lo) / h - 0.5
    base = np.floor(grid).astype(int)
    frac = grid - base
    field = np.zeros((3, n, n, n), dtype=float)
    weight = np.zeros((n, n, n), dtype=float)
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                ix = base[:, 0] + dx
                iy = base[:, 1] + dy
                iz = base[:, 2] + dz
                wx = frac[:, 0] if dx else 1.0 - frac[:, 0]
                wy = frac[:, 1] if dy else 1.0 - frac[:, 1]
                wz = frac[:, 2] if dz else 1.0 - frac[:, 2]
                w = wx * wy * wz
                valid = (
                    (ix >= 0)
                    & (ix < n)
                    & (iy >= 0)
                    & (iy < n)
                    & (iz >= 0)
                    & (iz < n)
                )
                if not np.any(valid):
                    continue
                np.add.at(weight, (ix[valid], iy[valid], iz[valid]), w[valid])
                for axis in range(3):
                    np.add.at(
                        field[axis],
                        (ix[valid], iy[valid], iz[valid]),
                        w[valid] * normals[valid, axis],
                    )
    field /= np.maximum(weight, 1e-12)
    return field


def _screened_poisson(
    points: np.ndarray,
    normals: np.ndarray,
    grid_n: int = 128,
    padding: float = 0.12,
    screening: float = 1.0,
) -> ReconstructionResult:
    """Small screened-Poisson solver on a regular DCT grid (fallback)."""

    start = time.perf_counter()
    points = np.asarray(points, dtype=float)
    normals = np.asarray(normals, dtype=float)
    low = points.min(axis=0) - padding
    high = points.max(axis=0) + padding
    span = float(np.max(high - low))
    low = 0.5 * (low + high) - 0.5 * span
    high = low + span
    n = int(grid_n)
    h = span / n
    field = _splat_normals(points, normals, low, h, n)
    divergence = np.zeros((n, n, n), dtype=float)
    divergence[1:-1, 1:-1, 1:-1] = (
        field[0, 2:, 1:-1, 1:-1] - field[0, :-2, 1:-1, 1:-1]
    ) / (2.0 * h)
    divergence[1:-1, 1:-1, 1:-1] += (
        field[1, 1:-1, 2:, 1:-1] - field[1, 1:-1, :-2, 1:-1]
    ) / (2.0 * h)
    divergence[1:-1, 1:-1, 1:-1] += (
        field[2, 1:-1, 1:-1, 2:] - field[2, 1:-1, 1:-1, :-2]
    ) / (2.0 * h)
    divergence -= divergence.mean()
    k = np.arange(n)
    eig = -4.0 * np.sin(np.pi * k / (2.0 * n)) ** 2 / (h * h)
    denominator = eig[:, None, None] + eig[None, :, None] + eig[None, None, :]
    denominator -= screening
    transformed = dctn(divergence, type=2, norm="ortho")
    chi = idctn(transformed / denominator, type=2, norm="ortho")

    grid = (points - low) / h - 0.5
    base = np.floor(grid).astype(int)
    frac = grid - base
    samples = []
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                ix = np.clip(base[:, 0] + dx, 0, n - 1)
                iy = np.clip(base[:, 1] + dy, 0, n - 1)
                iz = np.clip(base[:, 2] + dz, 0, n - 1)
                wx = frac[:, 0] if dx else 1.0 - frac[:, 0]
                wy = frac[:, 1] if dy else 1.0 - frac[:, 1]
                wz = frac[:, 2] if dz else 1.0 - frac[:, 2]
                samples.append(wx * wy * wz * chi[ix, iy, iz])
    iso = float(np.median(np.sum(samples, axis=0)))
    vertices, faces, _, _ = marching_cubes(chi, level=iso, spacing=(h, h, h))
    vertices += low
    runtime = time.perf_counter() - start
    return ReconstructionResult(
        vertices=vertices,
        faces=faces,
        backend="screened_poisson_dct",
        runtime_s=runtime,
        metadata={
            "grid_n": n,
            "grid_spacing_m": h,
            "screening": float(screening),
            "iso_value": iso,
        },
    )


def poisson_reconstruct(
    points: np.ndarray,
    normals: np.ndarray,
    depth: int = 8,
    scale: float = 1.1,
    linear_fit: bool = False,
    fallback_grid: int = 128,
) -> ReconstructionResult:
    try:
        return _open3d_poisson(points, normals, depth, scale, linear_fit)
    except Exception as error:
        result = _screened_poisson(points, normals, grid_n=fallback_grid)
        result.metadata["open3d_failure"] = str(error)
        return result


def safe_poisson_reconstruct(
    points: np.ndarray,
    normals: np.ndarray,
    depth: int = 8,
    scale: float = 1.1,
    timeout_s: float = 180.0,
) -> ReconstructionResult:
    """Run reconstruction in a child process, with in-process fallback."""

    points = np.asarray(points, dtype=float)
    normals = np.asarray(normals, dtype=float)
    with tempfile.TemporaryDirectory(prefix="poisson-worker-") as directory:
        source = os.path.join(directory, "input.npz")
        destination = os.path.join(directory, "output.npz")
        np.savez(source, points=points, normals=normals, depth=depth, scale=scale)
        environment = os.environ.copy()
        environment["PYTHONPATH"] = ROOT + os.pathsep + environment.get("PYTHONPATH", "")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "poisson_recon.worker",
                source,
                destination,
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if completed.returncode == 0 and os.path.exists(destination):
            data = np.load(destination)
            return ReconstructionResult(
                vertices=np.asarray(data["vertices"], dtype=float),
                faces=np.asarray(data["faces"], dtype=np.int64),
                backend=str(data["backend"]),
                runtime_s=float(data["runtime_s"]),
                metadata=json.loads(str(data["metadata"])),
            )
        result = _screened_poisson(points, normals, grid_n=128)
        message = completed.stderr.strip().splitlines()
        result.metadata["worker_failure"] = (
            message[-1] if message else f"worker exit code {completed.returncode}"
        )
        return result
