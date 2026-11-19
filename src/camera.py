"""Minimal perspective camera producing view/projection matrices."""
from __future__ import annotations

import numpy as np


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    view = np.eye(4)
    view[0, :3] = s
    view[1, :3] = u
    view[2, :3] = -f
    view[0, 3] = -s @ eye
    view[1, 3] = -u @ eye
    view[2, 3] = f @ eye
    return view


def perspective(fov_y_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / np.tan(np.radians(fov_y_deg) / 2.0)
    proj = np.zeros((4, 4))
    proj[0, 0] = f / aspect
    proj[1, 1] = f
    proj[2, 2] = (far + near) / (near - far)
    proj[2, 3] = (2.0 * far * near) / (near - far)
    proj[3, 2] = -1.0
    return proj


def project(points: np.ndarray, view: np.ndarray, proj: np.ndarray,
            width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Project Nx3 world points to pixel coords; return xy and visibility mask."""
    n = points.shape[0]
    homo = np.concatenate([points, np.ones((n, 1))], axis=1)
    clip = homo @ (proj @ view).T
    w = clip[:, 3]
    ndc = clip[:, :3] / w[:, None]
    visible = (w > 0.01) & (np.abs(ndc[:, 0]) <= 1.05) & (np.abs(ndc[:, 1]) <= 1.05)
    px = (ndc[:, 0] * 0.5 + 0.5) * width
    py = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * height
    depth = ndc[:, 2]
    return np.stack([px, py, depth], axis=1), visible


def orbit_camera(elevation_deg: float, azimuth_deg: float, distance: float = 26.0) -> np.ndarray:
    el = np.radians(elevation_deg)
    az = np.radians(azimuth_deg)
    eye = distance * np.array([
        np.cos(el) * np.cos(az),
        np.cos(el) * np.sin(az),
        np.sin(el),
    ])
    return look_at(eye, np.zeros(3), np.array([0.0, 0.0, 1.0]))
