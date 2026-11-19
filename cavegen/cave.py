"""Cave field thresholding and marching-cubes surface extraction."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.measure import marching_cubes

from .noise import fbm_noise_3d


@dataclass
class CaveResult:
    threshold: float
    air_voxels: int          # voxels classified as cave (air)
    solid_voxels: int        # voxels classified as rock
    total_voxels: int
    vertices: int            # marching-cubes mesh vertex count
    faces: int               # marching-cubes mesh triangle count
    mask: np.ndarray         # boolean air mask


def generate_field(
    shape: tuple[int, int, int],
    frequency: float,
    seed: int = 0,
    octaves: int = 3,
) -> np.ndarray:
    """Cave density field in [0, 1]; low values become open cave space."""
    return fbm_noise_3d(shape, frequency=frequency, seed=seed, octaves=octaves)


def extract_cave(field: np.ndarray, threshold: float) -> CaveResult:
    """Threshold the field and extract the cave wall isosurface."""
    mask = field < threshold
    air = int(mask.sum())
    total = int(mask.size)
    if 0 < air < total:
        # Pad so the isosurface closes at the domain boundary.
        padded = np.pad(field, 1, mode="constant", constant_values=1.0)
        verts, faces, _, _ = marching_cubes(padded, level=threshold)
        n_v, n_f = int(len(verts)), int(len(faces))
    else:
        n_v, n_f = 0, 0
    return CaveResult(
        threshold=threshold,
        air_voxels=air,
        solid_voxels=total - air,
        total_voxels=total,
        vertices=n_v,
        faces=n_f,
        mask=mask,
    )


def carve_vertical_shaft(mask: np.ndarray, radius: int = 3) -> np.ndarray:
    """Carve a guaranteed vertical main channel through the mask center."""
    nx, ny, _ = mask.shape
    cx, cy = nx // 2, ny // 2
    yy, xx = np.mgrid[0:ny, 0:nx]
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    out = mask.copy()
    out[disk.T, :] = True
    return out
