"""Boundary seams between overlapping probes and distance-weighted blending."""

from __future__ import annotations

import numpy as np

from .geometry import normalize, smoothstep
from .probe import ReflectionProbe


def normalized_distance(probe: ReflectionProbe, p: np.ndarray) -> float:
    """0 at the probe center, 1 at the influence box boundary."""
    p = np.asarray(p, dtype=float)
    half = probe.size * 0.5
    local = np.abs((p - probe.center) / half)
    return float(np.max(local))


def overlap_weight(probes, probe_index: int, p: np.ndarray,
                   blend_width: float = 0.25) -> float:
    """Complementary smooth weights over the physical overlap interval.

    Outside the overlap the single covering probe has weight 1. Inside it
    the low-side probe ramps 1 -> 0 and the high-side probe 0 -> 1 in
    physical units, reaching exactly 0/1 at the overlap faces, so toggling
    probe coverage never coincides with a nonzero weight. ``blend_width`` in
    (0, 0.5] sets the flat-to-flat transition band as a fraction of overlap.
    """
    p = np.asarray(p, dtype=float)
    probe = probes[probe_index]
    if not probe.contains(p):
        return 0.0

    # Points covered by a single probe keep full weight.
    if sum(q.contains(p) for q in probes) == 1:
        return 1.0
    # Fixed overlap interval of the *full* probe set, independent of which
    # probes cover this particular point, so u varies monotonically through
    # the whole overlap instead of being re-anchored at every coverage change.
    lo_axis = np.max([q.lo for q in probes], axis=0)
    hi_axis = np.min([q.hi for q in probes], axis=0)
    # Blend along the axis on which the probe centers actually differ; the
    # other axes are perfectly aligned and would give a degenerate ramp.
    center_span = np.ptp([q.center for q in probes], axis=0)
    axis = int(np.argmax(center_span))
    lo, hi = float(lo_axis[axis]), float(hi_axis[axis])
    if hi - lo < 1e-9:
        return 1.0
    u = float((p[axis] - lo) / (hi - lo))
    # Full-interval smoothstep keeps the endpoint values at exactly 0/1 and
    # gives a zero derivative there; a small ``edge`` widens the flat zones.
    edge = min(max(blend_width, 0.0), 0.5)
    if probe_index == 0:
        return float(1.0 - smoothstep(edge, 1.0 - edge, u))
    return float(smoothstep(edge, 1.0 - edge, u))


def blended_direction(probes, p: np.ndarray, reflect_dir: np.ndarray,
                      blend_width: float = 0.25):
    """Normalized weighted blend of per-probe BPR cubemap directions."""
    r = np.asarray(reflect_dir, dtype=float)
    acc = np.zeros(3)
    wsum = 0.0
    weights = []
    for idx, probe in enumerate(probes):
        w = overlap_weight(probes, idx, p, blend_width)
        if w > 0.0:
            acc += w * probe.box_direction(p, r)
            wsum += w
        weights.append(w)
    if wsum <= 0.0:
        nearest = min(probes, key=lambda q: np.linalg.norm(q.center - p))
        return normalize(nearest.box_direction(p, r)), np.zeros(len(probes))
    return acc / wsum, np.asarray(weights) / wsum


def hard_switch_direction(probes, p: np.ndarray, reflect_dir: np.ndarray):
    """Nearest-center probe only: reproduces a visible hard boundary seam."""
    p = np.asarray(p, dtype=float)
    distances = [np.linalg.norm(q.center - p) for q in probes]
    idx = int(np.argmin(distances))
    return probes[idx].box_direction(p, reflect_dir), idx


def direction_jump_series(probes, points: np.ndarray, reflect_dir: np.ndarray,
                          blend_width: float = 0.25):
    """Per-step direction change along a line crossing a probe boundary."""
    points = np.asarray(points, dtype=float)
    hard = np.array([hard_switch_direction(probes, p, reflect_dir)[0] for p in points])
    soft = np.array([blended_direction(probes, p, reflect_dir, blend_width)[0]
                     for p in points])

    def jumps(dirs):
        dot = np.sum(dirs[1:] * dirs[:-1], axis=1)
        return np.degrees(np.arccos(np.clip(dot, -1.0, 1.0)))

    return jumps(hard), jumps(soft)


def max_seam_jump(probes, points: np.ndarray, reflect_dir: np.ndarray,
                  blend_width: float = 0.25) -> tuple[float, float]:
    """Worst angular step for hard switching vs blended sampling."""
    hard, soft = direction_jump_series(probes, points, reflect_dir, blend_width)
    return float(np.max(hard)), float(np.max(soft))


def limiting_discontinuity(probes, x_axis: int, xs: np.ndarray,
                           reflect_dir: np.ndarray, epsilons,
                           blend_width: float = 0.25):
    """Largest direction change across each x for shrinking epsilon.

    Continuity is judged on the L2 distance between unit direction vectors:
    a continuous function yields a distance proportional to epsilon (finite
    derivative), while a true C0 seam keeps a finite distance as epsilon -> 0.
    Angles are reported only at the smallest epsilon where the small-angle
    approximation holds.
    """
    r = normalize(np.asarray(reflect_dir, dtype=float))
    base = np.zeros(3)
    hard_rows, soft_rows = [], []
    for eps in epsilons:
        hard_dist, soft_dist = [], []
        for x in xs:
            p_lo = base.copy()
            p_hi = base.copy()
            p_lo[x_axis] = x - eps
            p_hi[x_axis] = x + eps
            hard_a = hard_switch_direction(probes, p_lo, r)[0]
            hard_b = hard_switch_direction(probes, p_hi, r)[0]
            soft_a = blended_direction(probes, p_lo, r, blend_width)[0]
            soft_b = blended_direction(probes, p_hi, r, blend_width)[0]
            hard_dist.append(float(np.linalg.norm(hard_a - hard_b)))
            soft_dist.append(float(np.linalg.norm(soft_a - soft_b)))
        hard_rows.append(float(np.max(hard_dist)))
        soft_rows.append(float(np.max(soft_dist)))
    return hard_rows, soft_rows
