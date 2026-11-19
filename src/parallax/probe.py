"""Reflection probe sampling: uncorrected, plane and box parallax correction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import box_exit, normalize, ray_plane


@dataclass
class ReflectionProbe:
    """A cubemap probe with an optional parallax-correction influence box.

    ``center`` is the cubemap capture position. ``lo``/``hi`` define the
    axis-aligned influence box used by box projected reflection (BPR).
    """

    name: str
    center: np.ndarray
    lo: np.ndarray
    hi: np.ndarray

    def __post_init__(self):
        self.center = np.asarray(self.center, dtype=float)
        self.lo = np.asarray(self.lo, dtype=float)
        self.hi = np.asarray(self.hi, dtype=float)

    @property
    def size(self) -> np.ndarray:
        return self.hi - self.lo

    @property
    def volume(self) -> float:
        return float(np.prod(self.size))

    def contains(self, p: np.ndarray) -> bool:
        p = np.asarray(p, dtype=float)
        return bool(np.all(p >= self.lo - 1e-9) and np.all(p <= self.hi + 1e-9))

    def uncorrected_direction(self, p: np.ndarray, reflect_dir: np.ndarray) -> np.ndarray:
        """Naive sampling: treat the shading point as if it were the probe."""
        return normalize(reflect_dir)

    def box_direction(self, p: np.ndarray, reflect_dir: np.ndarray) -> np.ndarray:
        """Box projected reflection direction actually used to fetch the cubemap."""
        r = normalize(reflect_dir)
        t = box_exit(p, r, self.lo, self.hi)
        hit = p + t * r
        return normalize(hit - self.center)

    def box_hit(self, p: np.ndarray, reflect_dir: np.ndarray) -> np.ndarray:
        r = normalize(reflect_dir)
        t = box_exit(p, r, self.lo, self.hi)
        return p + t * r

    def plane_direction(self, p: np.ndarray, reflect_dir: np.ndarray,
                        normal: np.ndarray, d: float):
        """Single-plane parallax correction; returns None when the ray misses."""
        r = normalize(reflect_dir)
        t = ray_plane(p, r, normal, d)
        if t is None:
            return None
        hit = p + t * r
        return normalize(hit - self.center), hit


def true_reflection_hit(p: np.ndarray, reflect_dir: np.ndarray,
                        lo: np.ndarray, hi: np.ndarray):
    """Ground-truth specular hit on the surrounding room box."""
    r = normalize(reflect_dir)
    t = box_exit(p, r, lo, hi)
    return p + t * r


def offset_metrics(probe: ReflectionProbe, p: np.ndarray, reflect_dir: np.ndarray,
                   room_lo: np.ndarray, room_hi: np.ndarray):
    """World-space and angular offsets of every sampling scheme vs ground truth.

    Returns a dict with, per scheme, the implied geometry hit, its distance
    from the true reflected hit and the angular error of the fetch direction.
    """
    from .geometry import angle_between

    p = np.asarray(p, dtype=float)
    r = normalize(reflect_dir)
    truth = true_reflection_hit(p, r, room_lo, room_hi)

    # Uncorrected: geometry assumed to be infinitely far away along r.
    uncorr_dir = probe.uncorrected_direction(p, r)
    far_t = np.linalg.norm(truth - p) + np.linalg.norm(probe.center - p)
    uncorr_hit = probe.center + uncorr_dir * far_t

    box_hit = probe.box_hit(p, r)
    box_dir = normalize(box_hit - probe.center)

    return {
        "truth_hit": truth,
        "uncorrected": {
            "dir": uncorr_dir,
            "hit": uncorr_hit,
            "world_offset": float(np.linalg.norm(uncorr_hit - truth)),
            "angular_error_deg": np.degrees(angle_between(uncorr_dir, truth - probe.center)),
        },
        "box": {
            "dir": box_dir,
            "hit": box_hit,
            "world_offset": float(np.linalg.norm(box_hit - truth)),
            "angular_error_deg": np.degrees(angle_between(box_dir, truth - probe.center)),
        },
    }


def wall_penetration(probe: ReflectionProbe, p: np.ndarray, reflect_dir: np.ndarray,
                     wall_normal: np.ndarray, wall_d: float):
    """Signed distance of the reflected hit behind a wall plane.

    Positive value means the hit leaks through the wall (outside the room);
    zero means the hit stays on the interior side.
    """
    r = normalize(reflect_dir)
    t = box_exit(p, r, probe.lo, probe.hi)
    hit = p + t * r
    plane_value = float(np.dot(wall_normal, hit) - wall_d)
    return {
        "hit": hit,
        "t": t,
        "signed_distance": plane_value,
        "penetration": max(0.0, plane_value),
        "leaks": plane_value > 1e-9,
    }
