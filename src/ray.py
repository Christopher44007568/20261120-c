"""Ray / axis-aligned-box intersection utilities (fully vectorised)."""

import numpy as np


def intersect_box(origins, dirs, bounds):
    """Slab intersection of rays with an axis aligned box.

    Parameters
    ----------
    origins, dirs : (N, 3) float arrays
    bounds : (2, 3) array, rows are min/max corners.

    Returns
    -------
    t_enter, t_exit : (N,) arrays; t_enter=nan when the ray misses the box.
    """
    lo, hi = bounds[0], bounds[1]
    safe_inv = np.where(np.abs(dirs) < 1e-12, 1e-12, dirs)
    inv = 1.0 / safe_inv
    t1 = (lo - origins) * inv
    t2 = (hi - origins) * inv
    tnear = np.minimum(t1, t2).max(axis=1)
    tfar = np.maximum(t1, t2).min(axis=1)
    hit = (tfar >= np.maximum(tnear, 0.0))
    t_enter = np.where(hit, np.maximum(tnear, 0.0), np.nan)
    t_exit = np.where(hit, tfar, np.nan)
    return t_enter, t_exit


def intersect_plane(origins, dirs, z: float):
    """Intersection distance with the horizontal plane z = const (z-up world)."""
    t = (z - origins[:, 2]) / np.where(np.abs(dirs[:, 2]) < 1e-12, 1e-12, dirs[:, 2])
    return np.where(t > 0.0, t, np.nan)
